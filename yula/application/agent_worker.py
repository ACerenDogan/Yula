import argparse
import fcntl
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileDeletedEvent, FileModifiedEvent

from yula.core.scanner import scan_targets
from yula.core.watcher import YulaWatcher
from yula.storage.database import DatabaseManager


def _save_initial_baseline(
    database: DatabaseManager,
    targets: list[str],
) -> dict:
    combined_baseline = {}
    for target in targets:
        scan_result = scan_targets([target])
        path_id = database.add_monitored_path(target)
        database.save_baseline_records(path_id, scan_result)
        combined_baseline.update(scan_result)
    return combined_baseline


def _reconcile_offline_changes(
    watcher: YulaWatcher,
    baseline: dict,
    targets: list[str],
) -> None:
    """Ajan çalışmıyorken oluşan mevcut durum farklarını kaydeder."""
    current = scan_targets(targets)
    baseline_paths = set(baseline)
    current_paths = set(current)

    for path in sorted(baseline_paths - current_paths):
        watcher.handler.on_deleted(FileDeletedEvent(path))
    for path in sorted(current_paths - baseline_paths):
        watcher.handler.on_created(FileCreatedEvent(path))
    for path in sorted(baseline_paths & current_paths):
        watcher.handler.on_modified(FileModifiedEvent(path))


def run_agent(database_path: str, session_id: int | None = None) -> int:
    database = DatabaseManager(database_path)
    state = database.get_agent_state()
    if state is None or state["desired_state"] != "RUNNING":
        return 0

    active_session_id = session_id or state["session_id"]
    if active_session_id is None or active_session_id != state["session_id"]:
        return 1

    session = database.get_monitoring_session(active_session_id)
    if session is None:
        return 1
    targets = [target["target_path"] for target in session["targets"]]

    lock_path = f"{database.db_path}-agent.lock"
    lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(
            "YULA ajan kilidi alınamadı: "
            "başka bir ajan süreci hâlâ çalışıyor.",
            file=sys.stderr,
            flush=True,
        )
        os.close(lock_descriptor)
        return 0

    stop_signal_received = False

    def handle_stop_signal(_signal_number, _frame):
        nonlocal stop_signal_received
        stop_signal_received = True

    signal.signal(signal.SIGTERM, handle_stop_signal)
    signal.signal(signal.SIGINT, handle_stop_signal)

    watcher = None
    clipboard_process = None
    try:
        baseline = database.get_baseline_snapshots_for_targets(targets)
        is_initial_start = session["status"] == "PREPARING" or not baseline
        if is_initial_start:
            baseline = _save_initial_baseline(database, targets)

        watcher = YulaWatcher(
            targets=targets,
            baseline_data=baseline,
            db=database,
            session_id=active_session_id,
            event_context=(
                {"detected_after_restart": True}
                if not is_initial_start
                else None
            ),
        )

        if not is_initial_start:
            _reconcile_offline_changes(watcher, baseline, targets)
            watcher.handler.event_context = {}

        watcher.start()
        database.set_monitoring_session_status(active_session_id, "RUNNING")

        project_root = str(Path(__file__).resolve().parents[2])
        clipboard_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "yula.application.clipboard_worker",
                "--db",
                database.db_path,
                "--session-id",
                str(active_session_id),
            ],
            cwd=project_root,
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )

        while not stop_signal_received:
            state = database.get_agent_state()

            if (
                state is None
                or state["desired_state"] != "RUNNING"
                or state["session_id"] != active_session_id
            ):
                break
            if not watcher.is_running:
                raise RuntimeError("Dosya sistemi izleyicisi beklenmedik biçimde durdu.")
            if clipboard_process.poll() is not None:
                raise RuntimeError(
                    "Sistem panosu izleyicisi beklenmedik biçimde durdu."
                )
            database.update_agent_heartbeat(os.getpid())
            time.sleep(1)

        state = database.get_agent_state()
        should_finish_session = (
            state is None
            or state["desired_state"] == "STOPPED"
            or state["session_id"] != active_session_id
        )
        if should_finish_session:
            current_session = database.get_monitoring_session(
                active_session_id
            )
            if (
                current_session is not None
                and current_session["status"] in {"PREPARING", "RUNNING"}
            ):
                database.set_monitoring_session_status(
                    active_session_id,
                    "STOPPED",
                )
            return 0

        # Sistem kapanışı veya süreç sinyalinde RUNNING isteği korunur.
        # LaunchAgent sonraki kullanıcı girişinde aynı çalışmayı sürdürür.
        return 1

    except Exception:
        traceback.print_exc()

        state = database.get_agent_state()
        if (
            state is not None
            and state["desired_state"] == "RUNNING"
            and state["session_id"] == active_session_id
        ):
            try:
                database.set_monitoring_session_status(active_session_id, "ERROR")
            except (LookupError, ValueError):
                pass
            database.request_agent_stop()
        return 1
    finally:
        if clipboard_process is not None and clipboard_process.poll() is None:
            clipboard_process.terminate()
            try:
                clipboard_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                clipboard_process.kill()
                clipboard_process.wait(timeout=2)
        if watcher is not None:
            watcher.stop()
        os.close(lock_descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description="YULA arka plan izleme ajanı")
    parser.add_argument("--db", required=True, help="YULA SQLite veritabanı")
    parser.add_argument("--session-id", type=int)
    parser.add_argument("--resume", action="store_true")
    arguments = parser.parse_args()
    return run_agent(arguments.db, arguments.session_id)


if __name__ == "__main__":
    raise SystemExit(main())
