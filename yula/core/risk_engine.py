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
    def evaluate_file_event(
        cls,
        event_type: str,
        file_path: str,
        is_hash_changed: bool = False,
        previous_snapshot: dict | None = None,
        current_snapshot: dict | None = None,
        source_path: str | None = None,
    ) -> Tuple[str, str]:
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
            return "LOW", f"Dosya güvenilir referans içeriğine geri döndü: {filename}"

        elif event_type == "MOVED":
            source_name = os.path.basename(source_path) if source_path else None
            if source_name:
                movement = f"{source_name} → {filename}"
            else:
                movement = filename
            if is_critical:
                return "HIGH", f"Kritik dosya taşındı veya yeniden adlandırıldı: {movement}"
            return "LOW", f"Dosya taşındı veya yeniden adlandırıldı: {movement}"

        elif event_type == "PERMISSIONS_CHANGED":
            previous_mode = (
                previous_snapshot.get("mode")
                if previous_snapshot
                else None
            )
            current_mode = (
                current_snapshot.get("mode")
                if current_snapshot
                else None
            )
            mode_text = ""
            if previous_mode is not None and current_mode is not None:
                mode_text = f" ({previous_mode:03o} → {current_mode:03o})"

            newly_added_permissions = (
                previous_mode is not None
                and current_mode is not None
                and (current_mode & ~previous_mode)
            )
            newly_writable_by_others = bool(
                newly_added_permissions
                and newly_added_permissions & 0o022
            )
            newly_executable = bool(
                newly_added_permissions
                and newly_added_permissions & 0o111
            )

            if newly_writable_by_others:
                risk = "HIGH"
            elif newly_executable or is_critical:
                risk = "MEDIUM"
            else:
                risk = "LOW"

            return risk, f"Dosya izinleri değişti{mode_text}: {filename}"

        elif event_type == "OWNERSHIP_CHANGED":
            risk = "HIGH" if is_critical else "MEDIUM"
            return risk, f"Dosyanın sahibi veya grubu değişti: {filename}"

        elif event_type == "SYMLINK_CHANGED":
            return "HIGH", f"Sembolik bağlantının hedefi veya türü değişti: {filename}"

        elif event_type == "POSSIBLE_COPY":
            risk = "HIGH" if is_critical else "LOW"
            source_name = os.path.basename(source_path) if source_path else "bilinmeyen kaynak"
            return risk, f"Dosya kopyası oluşturuldu: {source_name} → {filename}"

        elif event_type == "CLIPBOARD_COPY":
            risk = "HIGH" if is_critical else "MEDIUM"
            return risk, f"Dosya kopyalandı; yapıştırma hedefi henüz bilinmiyor: {filename}"

        elif event_type == "CONTENT_CLIPBOARD_COPY":
            risk = "HIGH" if is_critical else "MEDIUM"
            return risk, f"Dosya içeriği kopyalandı: {filename}"

        return "LOW", f"Dosya olayı: {filename} ({event_type})"
