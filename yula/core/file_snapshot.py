import hashlib
import os
import stat

from yula.core.hasher import calculate_sha256
from yula.core.paths import normalize_path


def _calculate_symlink_fingerprint(
    link_target: str,
) -> str:
    """
    Symlink'in gösterdiği dosyayı okumadan yalnızca
    bağlantı hedefinin metninden parmak izi üretir.
    """
    return hashlib.sha256(
        os.fsencode(link_target)
    ).hexdigest()


def capture_file_snapshot(file_path: str) -> dict:
    """
    Bir dosya sistemi nesnesinin güvenlik fotoğrafını çıkarır.

    Symlink'ler takip edilmez. Bağlantının kendisi ve
    hedef yolunun metni kaydedilir.
    """
    normalized = normalize_path(file_path)

    if not os.path.lexists(normalized):
        raise FileNotFoundError(
            f"Dosya sistemi nesnesi bulunamadı: "
            f"{normalized}"
        )

    stat_info = os.lstat(normalized)
    file_mode = stat.S_IMODE(stat_info.st_mode)

    common_data = {
        "size": stat_info.st_size,
        "last_modified": stat_info.st_mtime_ns,
        "mode": file_mode,
        "uid": stat_info.st_uid,
        "gid": stat_info.st_gid,
    }

    if stat.S_ISLNK(stat_info.st_mode):
        link_target = os.readlink(normalized)

        return {
            **common_data,
            "hash": _calculate_symlink_fingerprint(
                link_target
            ),
            "kind": "SYMLINK",
            "is_symlink": True,
            "symlink_target": link_target,
        }

    if not stat.S_ISREG(stat_info.st_mode):
        raise ValueError(
            "Yalnızca normal dosyalar ve sembolik "
            "bağlantılar taranabilir."
        )

    return {
        **common_data,
        "hash": calculate_sha256(normalized),
        "kind": "FILE",
        "is_symlink": False,
        "symlink_target": None,
    }