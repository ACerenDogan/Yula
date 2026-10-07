from datetime import datetime


def parse_stored_datetime(value: str | datetime) -> datetime:
    """SQLite'ta ISO saklanan zamanı uygulama içinde datetime'a çevirir."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Tarih-saat değeri boş olamaz.")
    return datetime.fromisoformat(value)


def format_tr_datetime(
    value: str | datetime | None,
    include_seconds: bool = True,
) -> str:
    """Tarih-saat değerini Türkiye'de alışılan gün.ay.yıl biçiminde gösterir."""
    if value is None:
        return "-"
    parsed = parse_stored_datetime(value)
    pattern = "%d.%m.%Y %H:%M:%S" if include_seconds else "%d.%m.%Y %H:%M"
    return parsed.strftime(pattern)
