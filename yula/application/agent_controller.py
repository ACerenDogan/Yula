import os
import fcntl
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path

from yula.application.launch_agent import install_launch_agent
from yula.core.paths import normalize_path, should_ignore_path
from yula.storage.database import DatabaseManager


class BackgroundAgentController:
    """GUI ile bağımsız YULA ajanı arasındaki kontrol katmanı."""

    def __init__(
        self,
        database: DatabaseManager,
        event_callback=None,
        process_factory=subprocess.Popen,
        install_autostart: bool = True,
        log_directory: str | os.PathLike | None = None,
    ):
        self.database = database
        self.event_callback = event_callback
        self.process_factory = process_factory
        self.install_autostart = install_autostart
        self.log_directory = Path(
            log_directory or os.path.expanduser("~/Library/Logs/YULA")
        )
        self._process = None

    @property
    def session_id(self) -> int | None:
        state = self.database.get_agent_state()
        return state["session_id"] if state else None

    @property
    def targets(self) -> tuple[str, ...]:
        session_id = self.session_id
        if session_id is None:
            return ()
        session = self.database.get_monitoring_session(session_id)
        if session is None:
            return ()
        return tuple(target["target_path"] for target in session["targets"])

    @property
    def is_running(self) -> bool:
        state = self.database.get_agent_state()
        if state is None or state["desired_state"] != "RUNNING":
            return False
        session = self.database.get_monitoring_session(state["session_id"])
        return session is not None and session["status"] in {"PREPARING", "RUNNING"}

    def _prepare_targets(self, targets: Iterable[str]) -> list[dict]:
        prepared = []
        seen = set()
        for target in targets:
            normalized = normalize_path(target)
            if normalized in seen:
                continue
            if not os.path.lexists(normalized):
                raise FileNotFoundError(f"İzleme hedefi bulunamadı: {normalized}")
            if should_ignore_path(normalized):
                raise ValueError(f"Bu hedef YULA tarafından izlenemez: {normalized}")
            target_type = (
                "DIRECTORY"
                if os.path.isdir(normalized) and not os.path.islink(normalized)
                else "FILE"
            )
            prepared.append({"path": normalized, "type": target_type})
            seen.add(normalized)
        if not prepared:
            raise ValueError("İzlemek için en az bir dosya veya klasör seçilmelidir.")
        return prepared

    def _wait_for_agent_lock(
        self,
        timeout_seconds: float = 6,
    ) -> None:
        """Önceki ajanın dosya kilidini bırakmasını bekler.

        Yeni çalışma isteği yazıldığında eski ajan çalışma kimliğinin
        değiştiğini görür ve kapanır. Bu bekleme, yeni ajanın o kısa
        kapanış aralığında kilit hatası almasını önler.
        """
        lock_path = f"{self.database.db_path}-agent.lock"
        lock_descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_RDWR,
            0o600,
        )

        deadline = time.monotonic() + timeout_seconds

        try:
            while True:
                try:
                    fcntl.flock(
                        lock_descriptor,
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                    fcntl.flock(
                        lock_descriptor,
                        fcntl.LOCK_UN,
                    )
                    return

                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            "Önceki YULA ajanı kilidi "
                            "zamanında bırakmadı."
                        )

                    time.sleep(0.1)

        finally:
            os.close(lock_descriptor)

    @staticmethod
    def _read_error_tail(error_path: Path, line_count: int = 12) -> str:
        try:
            with open(error_path, "r", encoding="utf-8") as error_file:
                lines = error_file.readlines()
        except OSError:
            return ""
        return "".join(lines[-line_count:]).strip()

    def _mark_start_failed(self, session_id: int) -> None:
        state = self.database.get_agent_state()
        if state is not None and state["session_id"] == session_id:
            self.database.request_agent_stop()

        session = self.database.get_monitoring_session(session_id)
        if (
            session is not None
            and session["status"] in {"PREPARING", "RUNNING"}
        ):
            self.database.set_monitoring_session_status(
                session_id,
                "ERROR",
            )

    @staticmethod
    def _terminate_process(process) -> None:
        if process.poll() is not None:
            process.wait(timeout=2)
            return

        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    def start(self, targets: Iterable[str]) -> int:
        if self.is_running:
            raise RuntimeError("Zaten aktif bir izleme çalışması var.")

        prepared_targets = self._prepare_targets(targets)
        session_id = self.database.create_monitoring_session(prepared_targets)
        self.database.request_agent_start(session_id)

        project_root = str(Path(__file__).resolve().parents[2])
        if self.install_autostart:
            install_launch_agent(
                database_path=self.database.db_path,
                project_root=project_root,
                python_executable=sys.executable,
            )

        try:
            self._wait_for_agent_lock()
        except Exception:
            self._mark_start_failed(session_id)
            raise

        self.log_directory.mkdir(
            mode=0o700,
            parents=True,
            exist_ok=True,
        )
        agent_log_path = self.log_directory / "agent.log"
        agent_error_path = self.log_directory / "agent-error.log"

        try:
            with (
                open(agent_log_path, "a", encoding="utf-8") as log_file,
                open(agent_error_path, "a", encoding="utf-8") as error_file,
            ):
                process = self.process_factory(
                    [
                        sys.executable,
                        "-m",
                        "yula.application.agent_worker",
                        "--db",
                        self.database.db_path,
                        "--session-id",
                        str(session_id),
                    ],
                    cwd=project_root,
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=error_file,
                    start_new_session=True,
                    close_fds=True,
                )
        except Exception:
            self._mark_start_failed(session_id)
            raise

        self._process = process

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            session = self.database.get_monitoring_session(session_id)
            if session["status"] == "RUNNING":
                return session_id
            if session["status"] == "ERROR" or process.poll() is not None:
                self._terminate_process(process)
                self._process = None
                self._mark_start_failed(session_id)
                error_detail = self._read_error_tail(agent_error_path)
                message = "YULA arka plan ajanı başlatılamadı."
                if error_detail:
                    message += f"\n\nTeknik ayrıntı:\n{error_detail}"
                else:
                    message += (
                        " Ayrıntılar ~/Library/Logs/YULA/"
                        "agent-error.log dosyasına yazılır."
                    )
                raise RuntimeError(message)
            time.sleep(0.1)

        self._terminate_process(process)
        self._process = None
        self._mark_start_failed(session_id)
        raise TimeoutError("YULA arka plan ajanı zamanında başlatılamadı.")

    def stop(self) -> None:
        state = self.database.get_agent_state()
        if state is None or state["desired_state"] == "STOPPED":
            return
        self.database.request_agent_stop()

        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            session = self.database.get_monitoring_session(state["session_id"])
            if session is None or session["status"] == "STOPPED":
                if self._process is not None:
                    self._process.wait(timeout=2)
                    self._process = None
                return
            time.sleep(0.1)
        raise TimeoutError("Arka plan ajanı zamanında durmadı.")
