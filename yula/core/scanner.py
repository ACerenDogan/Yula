import os
from collections.abc import Iterable
from typing import Dict

from yula.core.file_snapshot import (
    capture_file_snapshot,
)
from yula.core.paths import (
    normalize_path,
    should_ignore_path,
)


def scan_file(file_path: str) -> dict:
    """Bir dosya veya symlink için güvenlik fotoğrafı oluşturur."""
    return capture_file_snapshot(file_path)


def scan_directory(
    directory_path: str,
) -> Dict[str, dict]:
    """
    Klasördeki dosyaları ve symlink'leri güvenli şekilde tarar.

    Symlink olan dizinlerin hedeflerine girmez.
    """
    normalized_directory = normalize_path(
        directory_path
    )

    if not os.path.exists(normalized_directory):
        raise FileNotFoundError(
            f"Taranacak dizin bulunamadı: "
            f"{normalized_directory}"
        )

    if os.path.islink(normalized_directory):
        raise ValueError(
            "Symlink bir yol doğrudan klasör olarak "
            "taranamaz."
        )

    if not os.path.isdir(normalized_directory):
        raise NotADirectoryError(
            f"Verilen yol bir klasör değil: "
            f"{normalized_directory}"
        )

    baseline_data: Dict[str, dict] = {}

    for root, directories, files in os.walk(
        normalized_directory,
        followlinks=False,
    ):
        safe_directories = []

        for directory_name in directories:
            full_path = normalize_path(
                os.path.join(
                    root,
                    directory_name,
                )
            )

            if should_ignore_path(full_path):
                continue

            if os.path.islink(full_path):
                try:
                    baseline_data[full_path] = (
                        scan_file(full_path)
                    )
                except (OSError, ValueError) as error:
                    print(
                        f"Symlink tarama hatası "
                        f"({full_path}): {error}"
                    )

                continue

            safe_directories.append(
                directory_name
            )

        directories[:] = safe_directories

        for file_name in files:
            full_path = normalize_path(
                os.path.join(
                    root,
                    file_name,
                )
            )

            if should_ignore_path(full_path):
                continue

            try:
                baseline_data[full_path] = (
                    scan_file(full_path)
                )

            except PermissionError:
                print(
                    f"Erişim engellendi: {full_path}"
                )

            except (OSError, ValueError) as error:
                print(
                    f"Tarama hatası ({full_path}): "
                    f"{error}"
                )

    return baseline_data


def scan_targets(
    targets: Iterable[str],
) -> Dict[str, dict]:
    """
    Dosya, klasör ve symlink seçimlerini tek referans
    durum altında birleştirir.
    """
    baseline_data: Dict[str, dict] = {}

    for target in targets:
        normalized = normalize_path(target)

        if not os.path.lexists(normalized):
            raise FileNotFoundError(
                f"Taranacak hedef bulunamadı: "
                f"{normalized}"
            )

        if should_ignore_path(normalized):
            continue

        if os.path.islink(normalized):
            baseline_data[normalized] = (
                scan_file(normalized)
            )

        elif os.path.isdir(normalized):
            baseline_data.update(
                scan_directory(normalized)
            )

        else:
            baseline_data[normalized] = (
                scan_file(normalized)
            )

    return baseline_data