import hashlib
import os

def calculate_sha256(filepath: str, chunk_size: int = 65536) -> str:
    """
    Belirtilen dosyanın SHA-256 özetini belleği şişirmeden
    parça parça (varsayılan olan 64 KB için) okuyarak hesaplar.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Dosya bulunamadı: {filepath}")
    
    if os.path.isdir(filepath):
        raise IsADirectoryError(f"Verilen yol bir klasördür, dosya bekleniyordu: {filepath}")

    sha256 = hashlib.sha256()

    try:
        with open(filepath, "rb") as f:
            # Dosyayı 64 KB'lık parçalar halinde döngüyle okuyoruz
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    # Dosyanın sonuna gelindiğinde döngüden çık
                    break
                sha256.update(chunk)
                
        return sha256.hexdigest()

    except PermissionError:
        raise PermissionError(f"Dosyayı okumak için yetki yok: {filepath}")
