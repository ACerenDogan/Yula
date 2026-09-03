import os
from typing import Tuple

class RiskEngine:
    """
    Yula Kural Tabanlı Güvenlik Risk Sınıflandırma Motoru.
    Olayları 'LOW', 'MEDIUM', 'HIGH' olarak etiketler.
    """
    # Kritik çalıştırılabilir ve ayar dosyaları (Değişirse YÜKSEK RİSK)
    CRITICAL_EXTENSIONS = {
        ".py", ".exe", ".sh", ".bat", ".json", ".config", ".dll", ".php"
    }
    CRITICAL_FILENAMES = {".env"}

    @classmethod
    def evaluate_file_event(cls, event_type: str, file_path: str, is_hash_changed: bool = False) -> Tuple[str, str]:
        """
        Dosya olayını inceleyip (Risk_Seviyesi, Açıklama) ikilisini döner.
        """
        filename = os.path.basename(file_path)
        _, ext = os.path.splitext(filename)
        ext = ext.lower()

        is_critical = (
            ext in cls.CRITICAL_EXTENSIONS
            or filename.lower() in cls.CRITICAL_FILENAMES
        )

        if event_type == "MODIFIED":
            if is_critical and is_hash_changed:
                return "HIGH", f"Kritik kod/ayar dosyasının içeriği değişti: {filename}"
            elif is_critical:
                return "MEDIUM", f"Kritik dosyada değişiklik yapıldı: {filename}"
            else:
                return "LOW", f"Standart dosya güncellendi: {filename}"

        elif event_type == "CREATED":
            if is_critical:
                return "HIGH", f"İzlenen alana yeni kritik/kod dosyası eklendi: {filename}"
            else:
                return "LOW", f"Yeni dosya oluşturuldu: {filename}"

        elif event_type == "DELETED":
            if is_critical:
                return "HIGH", f"Kritik dosya silindi: {filename}"
            else:
                return "LOW", f"Dosya silindi: {filename}"

        elif event_type == "RESTORED":
            return "LOW", f"Dosya güvenilir baseline içeriğine geri döndü: {filename}"

        elif event_type == "MOVED":
            if is_critical:
                return "HIGH", f"Kritik dosya taşındı veya yeniden adlandırıldı: {filename}"
            return "LOW", f"Dosya taşındı veya yeniden adlandırıldı: {filename}"

        return "LOW", f"Dosya olayı: {filename} ({event_type})"
