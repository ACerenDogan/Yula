import hashlib
import os
import subprocess
import sys
import time
from collections.abc import Iterable

from yula.core.file_snapshot import capture_file_snapshot
from yula.core.identity import get_context_user
from yula.core.paths import is_selected_path, normalize_path, should_ignore_path
from yula.core.risk_engine import RiskEngine
from yula.storage.database import DatabaseManager


class ClipboardFileMonitor:
    """Sistem panosuna kopyalanan, izleme kapsamındaki dosyaları kaydeder."""

    TEXT_EXTENSIONS = {
        ".txt", ".md", ".py", ".json", ".yaml", ".yml", ".toml",
        ".ini", ".cfg", ".conf", ".csv", ".log", ".sh", ".js",
        ".ts", ".html", ".css", ".xml", ".sql", ".rtf",
    } 
    TEXT_FILENAMES = {".env", ".gitignore"}
    MINIMUM_TEXT_LENGTH = 6
    MAXIMUM_TEXT_LENGTH = 200_000
    MAXIMUM_FILE_SIZE = 1_000_000
    MAXIMUM_CANDIDATES = 200
    MAXIMUM_TOTAL_SCAN_SIZE = 20_000_000

    def __init__(
        self,
        clipboard,
        database: DatabaseManager,
        targets: Iterable[str],
        session_id: int,
    ):
        self.clipboard = clipboard
        self.database = database
        self.targets = tuple(normalize_path(target) for target in targets)
        self.session_id = session_id
        self._dirty = False
        self._primed = False
        self._last_clipboard_signature: tuple | None = None
        self._pending_text: tuple[str, float] | None = None

        changed_signal = getattr(self.clipboard, "changed", None)
        if changed_signal is not None:
            changed_signal.connect(self.mark_changed)

    def mark_changed(self, *_arguments) -> None:
        self._dirty = True

    def _clipboard_file_paths(self) -> list[str]:
        mime_data = self.clipboard.mimeData()
        if mime_data is None or not mime_data.hasUrls():
            return []

        paths = []
        seen = set()
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = normalize_path(url.toLocalFile())
            if path in seen or should_ignore_path(path):
                continue
            if not is_selected_path(path, self.targets):
                continue
            if not os.path.lexists(path):
                continue
            seen.add(path)
            paths.append(path)
        return paths

    def _clipboard_text(self) -> str | None:
        mime_data = self.clipboard.mimeData()
        if mime_data is None:
            return None
        has_text = getattr(mime_data, "hasText", None)
        text_reader = getattr(mime_data, "text", None)
        if has_text is None or text_reader is None or not has_text():
            return None
        text = text_reader()
        if not isinstance(text, str):
            return None
        if not (self.MINIMUM_TEXT_LENGTH <= len(text) <= self.MAXIMUM_TEXT_LENGTH):
            return None
        return text

    def _text_candidates(self) -> list[str]:
        snapshots = self.database.get_baseline_snapshots_for_targets(
            list(self.targets)
        )
        candidates = []
        for path, snapshot in snapshots.items():
            filename = os.path.basename(path).lower()
            extension = os.path.splitext(filename)[1]
            if (
                filename not in self.TEXT_FILENAMES
                and extension not in self.TEXT_EXTENSIONS
            ):
                continue
            if snapshot.get("size", self.MAXIMUM_FILE_SIZE + 1) > self.MAXIMUM_FILE_SIZE:
                continue
            if not os.path.isfile(path) or os.path.islink(path):
                continue
            candidates.append((
                path in self.targets,
                snapshot.get("last_modified", 0),
                snapshot.get("size", 0),
                path,
            ))

        candidates.sort(reverse=True)
        selected_paths = []
        total_size = 0
        for _direct_target, _modified_at, file_size, path in candidates:
            if len(selected_paths) >= self.MAXIMUM_CANDIDATES:
                break
            if total_size + file_size > self.MAXIMUM_TOTAL_SCAN_SIZE:
                continue
            selected_paths.append(path)
            total_size += file_size
        return selected_paths

    def _find_text_source(self, clipboard_text: str) -> tuple[str, str] | None:
        """Pano metninin geldiği izlenen dosyayı sınırlı ve geçici taramayla bulur."""
        normalized_clipboard_text = self._normalize_text(clipboard_text)
        for path in self._text_candidates():
            content = self._read_text_content(path)
            if content is None:
                continue

            normalized_content = self._normalize_text(content)
            if normalized_clipboard_text == normalized_content:
                return path, "FULL_CONTENT"
            if normalized_clipboard_text in normalized_content:
                return path, "PARTIAL_CONTENT"
        return None

    @staticmethod
    def _normalize_text(value: str) -> str:
        return (
            value.replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\u00a0", " ")
        )

    def _read_text_content(self, path: str) -> str | None:
        extension = os.path.splitext(path)[1].lower()
        if extension == ".rtf" and sys.platform == "darwin":
            try:
                result = subprocess.run(
                    ["textutil", "-convert", "txt", "-stdout", path],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=2,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                return None
            if result.returncode != 0:
                return None
            try:
                return result.stdout.decode("utf-8")
            except UnicodeError:
                return None

        try:
            with open(path, "r", encoding="utf-8") as source_file:
                return source_file.read(self.MAXIMUM_FILE_SIZE + 1)
        except (OSError, UnicodeError):
            return None

    def _log_text_copy(self, clipboard_text: str) -> int | None:
        source_match = self._find_text_source(clipboard_text)
        if source_match is None:
            return None

        path, match_type = source_match
        risk, description = RiskEngine.evaluate_file_event(
            "CONTENT_CLIPBOARD_COPY",
            path,
        )
        if match_type == "PARTIAL_CONTENT":
            description = f"Dosyadan seçilen içerik kopyalandı: {os.path.basename(path)}"

        actor_name, actor_source = get_context_user()
        return self.database.log_security_event(
            event_type="CONTENT_CLIPBOARD_COPY",
            risk_level=risk,
            target_path=path,
            description=description,
            session_id=self.session_id,
            details={
                "method": "SYSTEM_CLIPBOARD",
                "match_type": match_type,
                "confidence": (
                    "HIGH"
                    if len(clipboard_text) >= 12
                    else "MEDIUM"
                ),
                "character_count": len(clipboard_text),
                "clipboard_sha256": hashlib.sha256(
                    clipboard_text.encode("utf-8")
                ).hexdigest(),
                "raw_content_stored": False,
                "copy_completed": False,
            },
            actor_name=actor_name,
            actor_source=actor_source,
        )

    @staticmethod
    def _clipboard_signature(
        paths: list[str],
        clipboard_text: str | None,
    ) -> tuple:
        if paths:
            return ("FILES", *paths)
        if clipboard_text is not None:
            return (
                "TEXT",
                hashlib.sha256(clipboard_text.encode("utf-8")).hexdigest(),
            )
        return ("EMPTY",)

    def poll(self) -> list[int]:
        """Yeni pano olayı varsa dosya kayıtlarını oluşturup kimliklerini döndürür."""
        clipboard_paths = self._clipboard_file_paths()
        clipboard_text = None if clipboard_paths else self._clipboard_text()
        signature = self._clipboard_signature(clipboard_paths, clipboard_text)

        if not self._primed:
            self._primed = True
            self._dirty = False
            self._last_clipboard_signature = signature
            return []

        signature_changed = signature != self._last_clipboard_signature
        if not self._dirty and not signature_changed and self._pending_text is None:
            return []

        self._dirty = False
        if signature_changed:
            self._last_clipboard_signature = signature
        event_ids = []
        actor_name, actor_source = get_context_user()

        if signature_changed or clipboard_paths:
            paths_to_log = clipboard_paths
        else:
            paths_to_log = []

        for path in paths_to_log:
            is_directory = os.path.isdir(path) and not os.path.islink(path)
            snapshot = None
            if not is_directory:
                try:
                    snapshot = capture_file_snapshot(path)
                except (OSError, ValueError):
                    snapshot = None

            risk, description = RiskEngine.evaluate_file_event(
                "CLIPBOARD_COPY",
                path,
            )
            event_id = self.database.log_security_event(
                event_type="CLIPBOARD_COPY",
                risk_level=risk,
                target_path=path,
                description=description,
                session_id=self.session_id,
                details={
                    "method": "SYSTEM_CLIPBOARD",
                    "copy_completed": False,
                    "object_type": "DIRECTORY" if is_directory else "FILE",
                    "snapshot": snapshot,
                },
                actor_name=actor_name,
                actor_source=actor_source,
            )
            event_ids.append(event_id)

        # Finder dosya kopyalarında pano hem URL hem metin taşıyabilir. Aynı
        # işlemi iki farklı olay gibi göstermemek için metni yalnızca URL yoksa
        # dosya içeriği kopyası olarak değerlendiriyoruz.
        if not clipboard_paths and clipboard_text is not None:
            if signature_changed or self._pending_text is None:
                self._pending_text = (clipboard_text, time.monotonic() + 5)

        if self._pending_text is not None:
            pending_text, retry_until = self._pending_text
            text_event_id = self._log_text_copy(pending_text)
            if text_event_id is not None:
                event_ids.append(text_event_id)
                self._pending_text = None
            elif time.monotonic() >= retry_until:
                self._pending_text = None

        return event_ids
