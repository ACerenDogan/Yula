import logging
import os
import time
from collections.abc import Callable, Iterable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from yula.core.hasher import calculate_sha256
from yula.core.paths import is_selected_path, normalize_path, should_ignore_path
from yula.core.risk_engine import RiskEngine
from yula.storage.database import DatabaseManager


logger = logging.getLogger(__name__)


class YulaFileEventHandler(FileSystemEventHandler):
    """Translate raw filesystem notifications into meaningful integrity events."""

    def __init__(
        self,
        baseline_data: dict,
        db: DatabaseManager,
        targets: Iterable[str] | None = None,
        event_callback: Callable[[dict], None] | None = None,
    ):
        super().__init__()
        self.db = db
        self.targets = (
            tuple(normalize_path(target) for target in targets)
            if targets is not None
            else None
        )
        self.event_callback = event_callback
        self.baseline_hashes = {
            normalize_path(path): self._extract_hash(value)
            for path, value in baseline_data.items()
        }
        self.current_hashes = dict(self.baseline_hashes)
        self.deleted_paths: set[str] = set()

    @staticmethod
    def _extract_hash(value: object) -> str:
        if isinstance(value, dict):
            file_hash = value.get("hash")
        else:
            file_hash = value
        if not isinstance(file_hash, str) or not file_hash:
            raise ValueError("Baseline kaydı geçerli bir SHA-256 değeri içermiyor.")
        return file_hash

    def _accepts(self, path: str) -> bool:
        return not should_ignore_path(path) and is_selected_path(path, self.targets)

    def _record(self, event_type: str, path: str, is_hash_changed: bool = False) -> None:
        normalized = normalize_path(path)
        risk, description = RiskEngine.evaluate_file_event(
            event_type,
            normalized,
            is_hash_changed=is_hash_changed,
        )
        event_id = self.db.log_security_event(
            event_type,
            risk,
            normalized,
            description,
        )
        if self.event_callback is not None:
            self.event_callback(
                {
                    "id": event_id,
                    "event_type": event_type,
                    "risk_level": risk,
                    "target_path": normalized,
                    "description": description,
                }
            )

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._accepts(event.src_path):
            return

        path = normalize_path(event.src_path)
        try:
            current_hash = calculate_sha256(path)
        except (FileNotFoundError, PermissionError, OSError):
            logger.exception("Oluşturulan dosyanın hash'i hesaplanamadı: %s", path)
            return

        baseline_hash = self.baseline_hashes.get(path)
        was_deleted = path in self.deleted_paths
        self.current_hashes[path] = current_hash
        self.deleted_paths.discard(path)

        if baseline_hash is not None and was_deleted:
            event_type = "RESTORED" if current_hash == baseline_hash else "MODIFIED"
            self._record(event_type, path, is_hash_changed=current_hash != baseline_hash)
            return

        if baseline_hash is not None:
            if current_hash != baseline_hash:
                self._record("MODIFIED", path, is_hash_changed=True)
            return

        self._record("CREATED", path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._accepts(event.src_path):
            return

        path = normalize_path(event.src_path)
        if path in self.deleted_paths:
            return
        self.current_hashes.pop(path, None)
        self.deleted_paths.add(path)
        self._record("DELETED", path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._accepts(event.src_path):
            return

        path = normalize_path(event.src_path)
        try:
            current_hash = calculate_sha256(path)
        except FileNotFoundError:
            # Atomic saves can briefly remove a file. The following move/create
            # event will carry the stable state, so this transient event is ignored.
            return
        except (PermissionError, OSError):
            logger.exception("Değiştirilen dosyanın hash'i hesaplanamadı: %s", path)
            return

        previous_hash = self.current_hashes.get(path)
        if previous_hash == current_hash:
            return

        baseline_hash = self.baseline_hashes.get(path)
        self.current_hashes[path] = current_hash
        self.deleted_paths.discard(path)

        if baseline_hash is not None and current_hash == baseline_hash:
            self._record("RESTORED", path)
            return

        self._record("MODIFIED", path, is_hash_changed=True)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return

        source = normalize_path(event.src_path)
        destination = normalize_path(event.dest_path)
        source_selected = self._accepts(source)
        destination_selected = self._accepts(destination)

        if source_selected and not destination_selected:
            self.on_deleted(event)
            return
        if destination_selected and not source_selected:
            created_event = FileSystemEvent(destination)
            self.on_created(created_event)
            return
        if not source_selected and not destination_selected:
            return

        destination_baseline = self.baseline_hashes.get(destination)
        source_baseline = self.baseline_hashes.get(source)
        destination_previous_hash = self.current_hashes.get(destination)
        previous_hash = self.current_hashes.pop(source, None)
        self.deleted_paths.add(source)
        try:
            current_hash = calculate_sha256(destination)
        except (FileNotFoundError, PermissionError, OSError):
            logger.exception("Taşınan dosyanın hash'i hesaplanamadı: %s", destination)
            return

        self.current_hashes[destination] = current_hash
        self.deleted_paths.discard(destination)

        # Many editors save safely by moving a temporary file over the original.
        # For an existing baseline destination, this is a content change rather
        # than a user-facing rename event.
        if destination_baseline is not None and source_baseline is None:
            if destination_previous_hash == current_hash:
                return
            event_type = "RESTORED" if current_hash == destination_baseline else "MODIFIED"
            self._record(
                event_type,
                destination,
                is_hash_changed=current_hash != destination_baseline,
            )
            return

        self._record(
            "MOVED",
            destination,
            is_hash_changed=previous_hash is not None and previous_hash != current_hash,
        )


class YulaWatcher:
    """Non-blocking watcher lifecycle suitable for a GUI controller."""

    def __init__(
        self,
        targets: Iterable[str],
        baseline_data: dict,
        db: DatabaseManager,
        event_callback: Callable[[dict], None] | None = None,
    ):
        self.targets = tuple(normalize_path(target) for target in targets)
        if not self.targets:
            raise ValueError("İzlemek için en az bir dosya veya klasör seçilmelidir.")
        self.handler = YulaFileEventHandler(
            baseline_data,
            db,
            targets=self.targets,
            event_callback=event_callback,
        )
        self.observer = Observer()
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started and self.observer.is_alive()

    def start(self) -> None:
        if self._started:
            return

        watch_directories = {
            target if os.path.isdir(target) else os.path.dirname(target)
            for target in self.targets
        }
        for directory in watch_directories:
            self.observer.schedule(self.handler, directory, recursive=True)
        self.observer.start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self.observer.stop()
        self.observer.join(timeout=5)
        self._started = False


def start_live_watcher(
    target_directory: str,
    baseline_data: dict,
    db: DatabaseManager,
) -> None:
    """Backward-compatible blocking entry point for terminal usage."""
    watcher = YulaWatcher([target_directory], baseline_data, db)
    watcher.start()
    print(f"YULA izlemeye başladı: {normalize_path(target_directory)}")

    try:
        while watcher.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("İzleme durduruluyor.")
    finally:
        watcher.stop()
