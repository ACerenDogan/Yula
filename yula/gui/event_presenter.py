import json
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def event_details_tooltip(event: dict) -> str:
    """Teknik olay ayrıntılarını ham JSON göstermeden okunabilir özetler."""
    lines = [event.get("description") or "Olay ayrıntısı bulunmuyor."]
    source_path = event.get("source_path")
    if source_path:
        lines.append(f"Kaynak: {source_path}")
    if event.get("target_path"):
        lines.append(f"Hedef: {event['target_path']}")

    details_value = event.get("details_json")
    try:
        details = json.loads(details_value) if details_value else {}
    except (TypeError, json.JSONDecodeError):
        details = {}

    if details.get("old_size") is not None and details.get("new_size") is not None:
        lines.append(f"Boyut: {details['old_size']} → {details['new_size']} bayt")
    if details.get("old_mode") is not None and details.get("new_mode") is not None:
        lines.append(f"İzin: {details['old_mode']:03o} → {details['new_mode']:03o}")
    if details.get("match_type") == "FULL_CONTENT":
        lines.append("Kapsam: Dosyanın tüm içeriği")
    elif details.get("match_type") == "PARTIAL_CONTENT":
        lines.append("Kapsam: Dosyadan seçilen bölüm")
    if details.get("character_count") is not None:
        lines.append(f"Uzunluk: {details['character_count']} karakter")
    if details.get("raw_content_stored") is False:
        lines.append("Gizlilik: Kopyalanan metin saklanmadı")
    if details.get("detected_after_restart"):
        lines.append("Ajan yeniden başladıktan sonra fark edildi")
    return "\n".join(lines)


def event_details_summary(event: dict) -> str:
    """Tabloda olayın sonucunu kısa fakat somut biçimde açıklar."""
    details_value = event.get("details_json")
    try:
        details = json.loads(details_value) if details_value else {}
    except (TypeError, json.JSONDecodeError):
        details = {}

    event_type = event.get("event_type")
    if event_type == "CONTENT_CLIPBOARD_COPY":
        scope = (
            "Dosyanın tamamı"
            if details.get("match_type") == "FULL_CONTENT"
            else "Seçilen bölüm"
        )
        length = details.get("character_count")
        length_text = f" · {length} karakter" if length is not None else ""
        return (
            f"{scope}{length_text} · Yapıştırma hedefi henüz bilinmiyor · "
            "Kopyalanan metin saklanmadı"
        )
    if event_type == "CLIPBOARD_COPY":
        return "Dosya panoya alındı · Yapıştırma hedefi henüz bilinmiyor"
    if event_type == "POSSIBLE_COPY":
        source = os.path.basename(event.get("source_path") or "Bilinmeyen kaynak")
        target = os.path.basename(event.get("target_path") or "Bilinmeyen hedef")
        return f"Aynı içerik özeti bulundu · {source} → {target}"
    if event_type == "MODIFIED":
        old_size = details.get("old_size")
        new_size = details.get("new_size")
        if old_size is not None and new_size is not None:
            return f"Dosya içeriği değişti · {old_size} → {new_size} bayt"
    if event_type == "DELETED":
        previous = details.get("previous_snapshot") or {}
        if previous.get("size") is not None:
            return (
                "Dosya izlenen konumdan kaldırıldı · "
                f"Son boyut {previous['size']} bayt"
            )
    return event.get("description") or "Ayrıntı bulunmuyor"


def event_technical_summary(event: dict) -> dict[str, str]:
    """Inspector için hash ve süreç bilgisini güvenli biçimde özetler."""
    details_value = event.get("details_json")
    try:
        details = json.loads(details_value) if details_value else {}
    except (TypeError, json.JSONDecodeError):
        details = {}

    old_hash = details.get("old_hash")
    new_hash = details.get("new_hash")
    clipboard_hash = details.get("clipboard_sha256")
    snapshot_hash = (details.get("snapshot") or {}).get("hash")

    def short_hash(value) -> str:
        if not value:
            return ""
        value = str(value)
        return value if len(value) <= 16 else f"{value[:12]}…{value[-4:]}"

    if old_hash and new_hash:
        hash_summary = f"{short_hash(old_hash)} → {short_hash(new_hash)}"
    elif new_hash:
        hash_summary = short_hash(new_hash)
    elif snapshot_hash:
        hash_summary = short_hash(snapshot_hash)
    elif clipboard_hash:
        hash_summary = f"Pano: {short_hash(clipboard_hash)}"
    else:
        hash_summary = "Bu olay için kaydedilmedi"

    process_id = details.get("process_id") or details.get("pid")
    return {
        "hash": hash_summary,
        "process_id": str(process_id) if process_id is not None else "Kaydedilmedi",
    }


def session_status_icon(status: str) -> QIcon:
    """Çalışma durumunu küçük ve erişilebilir bir renk noktasıyla gösterir."""
    colors = {
        "RUNNING": "#149BFF",
        "PREPARING": "#BBC2C9",
        "STOPPED": "#69737C",
        "ERROR": "#D7DCE1",
    }
    pixmap = QPixmap(14, 14)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(colors.get(status, "#64748B")))
    painter.drawEllipse(2, 2, 10, 10)
    painter.end()
    return QIcon(pixmap)


def risk_level_icon(risk_level: str) -> QIcon:
    """Riski büyük renk blokları yerine küçük ve sakin bir noktayla gösterir."""
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if risk_level == "HIGH":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#149BFF"))
        painter.drawEllipse(3, 3, 6, 6)
    elif risk_level == "MEDIUM":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#A4ADB5"))
        painter.drawEllipse(4, 4, 4, 4)
    else:
        painter.setPen(QPen(QColor("#69737C"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(4, 4, 4, 4)

    painter.end()
    return QIcon(pixmap)
