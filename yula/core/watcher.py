import logging
import os
import sys
import time
from collections.abc import Callable, Iterable

from watchdog.events import FileSystemEvent, FileSystemEventHandler

if sys.platform == "darwin":
    # kqueue, chmod/chown gibi öznitelik değişikliklerini doğrudan bildirir
    # ve FSEvents akışının açılamadığı macOS ortamlarında da çalışır.
    from watchdog.observers.kqueue import KqueueObserver as Observer
else:
    from watchdog.observers import Observer

from yula.core.file_snapshot import capture_file_snapshot
from yula.core.identity import get_context_user
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
        session_id: int | None = None,
        event_context: dict | None = None,
    ):
        super().__init__()
        self.db = db
        self.session_id = session_id

        self.targets = (
            tuple(normalize_path(target) for target in targets)
            if targets is not None
            else None
        )
        self.event_callback = event_callback
        self.event_context = dict(event_context or {})
        self.baseline_snapshots = {
            normalize_path(path): self._extract_snapshot(value)
            for path, value in baseline_data.items()
        }
        self.current_snapshots = {
            path: dict(snapshot)
            for path, snapshot in self.baseline_snapshots.items()
        }

        # Bu iki sözlük eski kod ve testlerle uyumluluk için korunur.
        self.baseline_hashes = {
            path: snapshot["hash"]
            for path, snapshot in self.baseline_snapshots.items()
        }
        self.current_hashes = dict(self.baseline_hashes)
        self.deleted_paths: set[str] = set()

    @staticmethod
    def _extract_snapshot(value: object) -> dict:
        if isinstance(value, dict):
            file_hash = value.get("hash")
            snapshot = dict(value)
        else:
            file_hash = value
            snapshot = {"hash": value}
        if not isinstance(file_hash, str) or not file_hash:
            raise ValueError("Baseline kaydı geçerli bir SHA-256 değeri içermiyor.")
        return snapshot

    @staticmethod
    def _same_value(
        previous: dict,
        current: dict,
        key: str,
    ) -> bool:
        """Eski, yalnızca hash içeren baseline kayıtlarını destekler."""
        return (
            key not in previous
            or key not in current
            or previous[key] == current[key]
        )

    def _record_snapshot_changes(
        self,
        path: str,
        previous: dict,
        current: dict,
        baseline: dict | None = None,
    ) -> None:
        """İki güvenlik görüntüsü arasındaki anlamlı farkları kaydeder."""
        previous_hash = previous["hash"]
        current_hash = current["hash"]
        baseline_hash = baseline.get("hash") if baseline else None

        symlink_changed = any(
            not self._same_value(previous, current, key)
            for key in ("kind", "is_symlink", "symlink_target")
        ) and (
            previous.get("is_symlink", False)
            or current.get("is_symlink", False)
        )

        if symlink_changed:
            self._record(
                "SYMLINK_CHANGED",
                path,
                details={
                    "old_kind": previous.get("kind"),
                    "new_kind": current.get("kind"),
                    "old_symlink_target": previous.get("symlink_target"),
                    "new_symlink_target": current.get("symlink_target"),
                },
            )
        elif previous_hash != current_hash:
            if baseline_hash is not None and current_hash == baseline_hash:
                self._record(
                    "RESTORED",
                    path,
                    details={
                        "old_hash": previous_hash,
                        "new_hash": current_hash,
                    },
                )
            else:
                self._record(
                    "MODIFIED",
                    path,
                    is_hash_changed=True,
                    details={
                        "old_hash": previous_hash,
                        "new_hash": current_hash,
                        "old_size": previous.get("size"),
                        "new_size": current.get("size"),
                    },
                )

        if not self._same_value(previous, current, "uid") or not self._same_value(
            previous,
            current,
            "gid",
        ):
            self._record(
                "OWNERSHIP_CHANGED",
                path,
                previous_snapshot=previous,
                current_snapshot=current,
                details={
                    "old_uid": previous.get("uid"),
                    "new_uid": current.get("uid"),
                    "old_gid": previous.get("gid"),
                    "new_gid": current.get("gid"),
                },
            )

        if not self._same_value(previous, current, "mode"):
            self._record(
                "PERMISSIONS_CHANGED",
                path,
                previous_snapshot=previous,
                current_snapshot=current,
                details={
                    "old_mode": previous.get("mode"),
                    "new_mode": current.get("mode"),
                },
            )

    def _find_possible_copy_source(
        self,
        destination: str,
        snapshot: dict,
    ) -> str | None:
        """Aynı içerik özetine sahip bilinen başka bir normal dosya bulur."""
        if snapshot.get("is_symlink", False):
            return None

        for candidate, candidate_snapshot in self.current_snapshots.items():
            if (
                candidate != destination
                and not candidate_snapshot.get("is_symlink", False)
                and candidate_snapshot.get("hash") == snapshot.get("hash")
            ):
                return candidate

        return None

    def _accepts(self, path: str) -> bool:
        return not should_ignore_path(path) and is_selected_path(path, self.targets)

    def _record(
        self,
        event_type: str,
        path: str,
        is_hash_changed: bool = False,
        previous_snapshot: dict | None = None,
        current_snapshot: dict | None = None,
        source_path: str | None = None,
        details: dict | None = None,
    ) -> None:
        normalized = normalize_path(path)
        risk, description = RiskEngine.evaluate_file_event(
            event_type,
            normalized,
            is_hash_changed=is_hash_changed,
            previous_snapshot=previous_snapshot,
            current_snapshot=current_snapshot,
            source_path=source_path,
        )
        actor_name, actor_source = get_context_user()
        combined_details = {
            **self.event_context,
            **(details or {}),
        } or None
        event_id = self.db.log_security_event(
            event_type,
            risk,
            normalized,
            description,
            session_id=self.session_id,
            source_path=source_path,
            details=combined_details,
            actor_name=actor_name,
            actor_source=actor_source,
        )
        if self.event_callback is not None:
            self.event_callback(
                {
                    "id": event_id,
                    "event_type": event_type,
                    "risk_level": risk,
                    "target_path": normalized,
                    "description": description,
                    "session_id": self.session_id,
                    "source_path": source_path,
                    "details": combined_details,
                    "actor_name": actor_name,
                    "actor_source": actor_source,
                }
            )

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._accepts(event.src_path):
            return

        path = normalize_path(event.src_path)
        try:
            current_snapshot = capture_file_snapshot(path)
        except (FileNotFoundError, PermissionError, OSError):
            logger.exception(
                "Oluşturulan dosyanın güvenlik görüntüsü alınamadı: %s",
                path,
            )
            return

        baseline_snapshot = self.baseline_snapshots.get(path)
        was_deleted = path in self.deleted_paths
        previous_snapshot = self.current_snapshots.get(path)
        possible_copy_source = self._find_possible_copy_source(
            path,
            current_snapshot,
        )
        self.current_snapshots[path] = current_snapshot
        self.current_hashes[path] = current_snapshot["hash"]
        self.deleted_paths.discard(path)

        if baseline_snapshot is not None and was_deleted:
            if current_snapshot["hash"] == baseline_snapshot["hash"]:
                self._record(
                    "RESTORED",
                    path,
                    details={
                        "new_hash": current_snapshot["hash"],
                        "restored_after_deletion": True,
                    },
                )
            self._record_snapshot_changes(
                path,
                baseline_snapshot,
                current_snapshot,
                baseline_snapshot,
            )
            return

        if baseline_snapshot is not None:
            self._record_snapshot_changes(
                path,
                previous_snapshot or baseline_snapshot,
                current_snapshot,
                baseline_snapshot,
            )
            return

        if possible_copy_source is not None:
            self._record(
                "POSSIBLE_COPY",
                path,
                source_path=possible_copy_source,
                details={
                    "matching_hash": current_snapshot["hash"],
                    "detection": "HASH_MATCH",
                },
            )
        else:
            self._record(
                "CREATED",
                path,
                details={"snapshot": current_snapshot},
            )

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._accepts(event.src_path):
            return

        path = normalize_path(event.src_path)
        if path in self.deleted_paths:
            return
        previous_snapshot = self.current_snapshots.pop(path, None)
        self.current_hashes.pop(path, None)
        self.deleted_paths.add(path)
        self._record(
            "DELETED",
            path,
            details={"previous_snapshot": previous_snapshot},
        )

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._accepts(event.src_path):
            return

        path = normalize_path(event.src_path)
        try:
            current_snapshot = capture_file_snapshot(path)
        except FileNotFoundError:
            # Atomic saves can briefly remove a file. The following move/create
            # event will carry the stable state, so this transient event is ignored.
            return
        except (PermissionError, OSError):
            logger.exception(
                "Değiştirilen dosyanın güvenlik görüntüsü alınamadı: %s",
                path,
            )
            return

        previous_snapshot = self.current_snapshots.get(path)
        if previous_snapshot is None:
            previous_snapshot = self.baseline_snapshots.get(path)

        if previous_snapshot is None:
            possible_copy_source = self._find_possible_copy_source(
                path,
                current_snapshot,
            )
            self.current_snapshots[path] = current_snapshot
            self.current_hashes[path] = current_snapshot["hash"]
            if possible_copy_source is not None:
                self._record(
                    "POSSIBLE_COPY",
                    path,
                    source_path=possible_copy_source,
                    details={
                        "matching_hash": current_snapshot["hash"],
                        "detection": "HASH_MATCH",
                    },
                )
            else:
                self._record(
                    "CREATED",
                    path,
                    details={"snapshot": current_snapshot},
                )
            return

        self.current_snapshots[path] = current_snapshot
        self.current_hashes[path] = current_snapshot["hash"]
        self.deleted_paths.discard(path)
        self._record_snapshot_changes(
            path,
            previous_snapshot,
            current_snapshot,
            self.baseline_snapshots.get(path),
        )

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

        destination_baseline = self.baseline_snapshots.get(destination)
        source_baseline = self.baseline_snapshots.get(source)
        destination_previous = self.current_snapshots.get(destination)
        previous_snapshot = self.current_snapshots.pop(source, None)
        self.current_hashes.pop(source, None)
        self.deleted_paths.add(source)
        try:
            current_snapshot = capture_file_snapshot(destination)
        except (FileNotFoundError, PermissionError, OSError):
            logger.exception(
                "Taşınan dosyanın güvenlik görüntüsü alınamadı: %s",
                destination,
            )
            return

        self.current_snapshots[destination] = current_snapshot
        self.current_hashes[destination] = current_snapshot["hash"]
        self.deleted_paths.discard(destination)

        # Many editors save safely by moving a temporary file over the original.
        # For an existing baseline destination, this is a content change rather
        # than a user-facing rename event.
        if destination_baseline is not None and source_baseline is None:
            self._record_snapshot_changes(
                destination,
                destination_previous or destination_baseline,
                current_snapshot,
                destination_baseline,
            )
            return

        self._record(
            "MOVED",
            destination,
            is_hash_changed=(
                previous_snapshot is not None
                and previous_snapshot["hash"] != current_snapshot["hash"]
            ),
            source_path=source,
            details={
                "source_path": source,
                "destination_path": destination,
                "old_hash": (
                    previous_snapshot.get("hash")
                    if previous_snapshot
                    else None
                ),
                "new_hash": current_snapshot.get("hash"),
            },
        )


class YulaWatcher:
    """Non-blocking watcher lifecycle suitable for a GUI controller."""

    def __init__(
        self,
        targets: Iterable[str],
        baseline_data: dict,
        db: DatabaseManager,
        event_callback: Callable[[dict], None] | None = None,
        session_id: int | None = None,
        event_context: dict | None = None,
    ):
        self.targets = tuple(normalize_path(target) for target in targets)
        if not self.targets:
            raise ValueError("İzlemek için en az bir dosya veya klasör seçilmelidir.")
        self.handler = YulaFileEventHandler(
            baseline_data,
            db,
            targets=self.targets,
            event_callback=event_callback,
            session_id=session_id,
            event_context=event_context,
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
            target
            if os.path.isdir(target) and not os.path.islink(target)
            else os.path.dirname(target)
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
