import os
from collections.abc import Iterable
from typing import Dict

from yula.core.hasher import calculate_sha256
from yula.core.paths import normalize_path, should_ignore_path


def scan_file(file_path: str) -> dict:
    """Create a baseline record for one regular file."""
    normalized = normalize_path(file_path)
    if not os.path.exists(normalized):
        raise FileNotFoundError(f"Taranacak dosya bulunamadı: {normalized}")
    if not os.path.isfile(normalized):
        raise IsADirectoryError(f"Verilen yol bir dosya değil: {normalized}")

    stat_info = os.stat(normalized)
    return {
        "hash": calculate_sha256(normalized),
        "size": stat_info.st_size,
        "last_modified": stat_info.st_mtime,
    }


def scan_directory(directory_path: str) -> Dict[str, dict]:
    """
    Belirtilen klasördeki tüm dosyaları tarar ve her birinin
    boyutunu, son değiştirilme zamanını ve SHA-256 parmak izini çıkarır.
    """
    if not os.path.exists(directory_path):
        raise FileNotFoundError(f"Taranacak dizin bulunamadı: {directory_path}")

    if not os.path.isdir(directory_path):
        raise NotADirectoryError(f"Verilen yol bir klasör değil: {directory_path}")

    baseline_data: Dict[str, dict] = {}
    normalized_directory = normalize_path(directory_path)

    # os.walk klasörün içindeki tüm alt klasörleri ve dosyaları özyinelemeli (recursive) gezer
    for root, dirs, files in os.walk(normalized_directory):
        dirs[:] = [
            directory
            for directory in dirs
            if not should_ignore_path(os.path.join(root, directory))
        ]

        for file_name in files:
            full_path = normalize_path(os.path.join(root, file_name))
            if should_ignore_path(full_path):
                continue
            try:
                baseline_data[full_path] = scan_file(full_path)

            except PermissionError:
                print(f"Erişim engellendi (Yetki yok): {full_path}")
            except Exception as e:
                print(f"Tarama hatası ({full_path}): {str(e)}")

    return baseline_data


def scan_targets(targets: Iterable[str]) -> Dict[str, dict]:
    """Scan a mixed selection of files and directories into one baseline."""
    baseline_data: Dict[str, dict] = {}

    for target in targets:
        normalized = normalize_path(target)
        if not os.path.exists(normalized):
            raise FileNotFoundError(f"Taranacak hedef bulunamadı: {normalized}")
        if should_ignore_path(normalized):
            continue
        if os.path.isdir(normalized):
            baseline_data.update(scan_directory(normalized))
        else:
            baseline_data[normalized] = scan_file(normalized)

    return baseline_data
