import os
from collections.abc import Iterable


IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    ".venv-1",
    ".vscode",
    "__pycache__",
}

IGNORED_FILE_NAMES = {
    ".DS_Store",
    "yula.db",
    "yula.db-shm",
    "yula.db-wal",
}


def normalize_path(path: str) -> str:
    """Return one stable representation for paths used as dictionary keys."""
    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))


def should_ignore_path(path: str) -> bool:
    """Ignore application artefacts without hiding security-relevant dotfiles."""
    normalized = normalize_path(path)
    parts = set(normalized.split(os.sep))
    name = os.path.basename(normalized)

    return (
        bool(parts & IGNORED_DIRECTORY_NAMES)
        or name in IGNORED_FILE_NAMES
        or name.endswith(".pyc")
    )


def is_selected_path(path: str, targets: Iterable[str] | None) -> bool:
    """Check whether a filesystem event belongs to a selected file or directory."""
    if targets is None:
        return True

    candidate = normalize_path(path)
    for target in targets:
        normalized_target = normalize_path(target)
        if candidate == normalized_target:
            return True
        if os.path.isdir(normalized_target):
            try:
                if os.path.commonpath((candidate, normalized_target)) == normalized_target:
                    return True
            except ValueError:
                continue
    return False
