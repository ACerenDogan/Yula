RISK_LABELS = {
    "HIGH": "Yüksek",
    "MEDIUM": "Orta",
    "LOW": "Düşük",
}

EVENT_TYPE_LABELS = {
    "MODIFIED": "Değiştirildi",
    "CREATED": "Oluşturuldu",
    "DELETED": "Silindi",
    "RESTORED": "Referans duruma döndü",
    "MOVED": "Taşındı / yeniden adlandırıldı",
    "PERMISSIONS_CHANGED": "İzinleri değişti",
    "OWNERSHIP_CHANGED": "Sahibi / grubu değişti",
    "SYMLINK_CHANGED": "Sembolik bağlantı değişti",
    "POSSIBLE_COPY": "Dosya kopyası oluşturuldu",
    "CLIPBOARD_COPY": "Dosya kopyalandı",
    "CONTENT_CLIPBOARD_COPY": "İçerik kopyalandı",
}

SESSION_STATUS_LABELS = {
    "PREPARING": "Hazırlanıyor",
    "RUNNING": "İzleniyor",
    "STOPPED": "Durduruldu",
    "ERROR": "Hata",
}


def risk_label(risk_level: str) -> str:
    """Teknik risk değerinin Türkçe karşılığını döndürür."""
    return RISK_LABELS.get(
        risk_level,
        risk_level,
    )


def event_type_label(event_type: str) -> str:
    """Teknik olay türünün Türkçe karşılığını döndürür."""
    return EVENT_TYPE_LABELS.get(
        event_type,
        event_type,
    )


def session_status_label(status: str) -> str:
    """Teknik çalışma durumunun Türkçe karşılığını döndürür."""
    return SESSION_STATUS_LABELS.get(
        status,
        status,
    )
