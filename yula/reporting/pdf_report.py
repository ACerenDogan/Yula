import os
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from yula.gui.labels import event_type_label, risk_label


def _register_fonts() -> tuple[str, str]:
    regular_candidates = (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        os.path.join(os.path.dirname(__file__), "Vera.ttf"),
    )
    bold_candidates = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        os.path.join(os.path.dirname(__file__), "VeraBd.ttf"),
    )

    try:
        import reportlab

        reportlab_fonts = os.path.join(
            os.path.dirname(reportlab.__file__),
            "fonts",
        )
        regular_candidates += (os.path.join(reportlab_fonts, "Vera.ttf"),)
        bold_candidates += (os.path.join(reportlab_fonts, "VeraBd.ttf"),)
    except ImportError:
        pass

    regular_path = next(
        (path for path in regular_candidates if os.path.isfile(path)),
        None,
    )
    bold_path = next(
        (path for path in bold_candidates if os.path.isfile(path)),
        None,
    )
    if regular_path is None or bold_path is None:
        raise RuntimeError("Türkçe karakterleri destekleyen rapor yazı tipi bulunamadı.")

    if "YulaSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("YulaSans", regular_path))
    if "YulaSans-Bold" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("YulaSans-Bold", bold_path))

    return "YulaSans", "YulaSans-Bold"


def _format_timestamp(timestamp: str, include_times: bool) -> str:
    value = datetime.fromisoformat(timestamp)
    return value.strftime("%d.%m.%Y %H:%M:%S" if include_times else "%d.%m.%Y")


def _event_detail_text(event: dict) -> str:
    details = event.get("details") or {}
    parts = []
    if details.get("old_hash") and details.get("new_hash"):
        parts.append(
            f"Hash: {details['old_hash'][:10]}... → {details['new_hash'][:10]}..."
        )
    if details.get("old_size") is not None and details.get("new_size") is not None:
        parts.append(f"Boyut: {details['old_size']} → {details['new_size']} bayt")
    if details.get("old_mode") is not None and details.get("new_mode") is not None:
        parts.append(f"İzin: {details['old_mode']:03o} → {details['new_mode']:03o}")
    if details.get("detected_after_restart"):
        parts.append("Ajan yeniden başladıktan sonra fark edildi; gerçek işlem zamanı bilinmiyor")
    if details.get("match_type") == "FULL_CONTENT":
        parts.append("Dosyanın tüm içeriği panoya alındı")
    elif details.get("match_type") == "PARTIAL_CONTENT":
        parts.append("Dosyadan seçili içerik panoya alındı")
    if details.get("character_count") is not None:
        parts.append(f"İçerik uzunluğu: {details['character_count']} karakter")
    if details.get("raw_content_stored") is False:
        parts.append("Kopyalanan içerik raporda ve veritabanında saklanmadı")
    return " | ".join(parts)


def _page_footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setFont("YulaSans", 8)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(15 * mm, 9 * mm, "YULA - Dosya Bütünlüğü Güvenlik Raporu")
    canvas.drawRightString(
        landscape(A4)[0] - 15 * mm,
        9 * mm,
        f"Sayfa {document.page}",
    )
    canvas.restoreState()


def generate_security_report(
    output_path: str,
    events: list[dict],
    start_at: datetime,
    end_at: datetime,
    include_times: bool = True,
    report_scope: str | None = None,
) -> str:
    """Güvenlik olaylarını okunabilir, salt okunur bir PDF rapora dönüştürür."""
    if not output_path.lower().endswith(".pdf"):
        output_path += ".pdf"
    output_path = os.path.abspath(os.path.expanduser(output_path))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    regular_font, bold_font = _register_fonts()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "YulaTitle",
        parent=styles["Title"],
        fontName=bold_font,
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#0F172A"),
        alignment=TA_LEFT,
        spaceAfter=4 * mm,
    )
    body_style = ParagraphStyle(
        "YulaBody",
        parent=styles["BodyText"],
        fontName=regular_font,
        fontSize=8.3,
        leading=11,
        textColor=colors.HexColor("#334155"),
    )
    small_style = ParagraphStyle(
        "YulaSmall",
        parent=body_style,
        fontSize=7.4,
        leading=9,
    )
    header_style = ParagraphStyle(
        "YulaTableHeader",
        parent=small_style,
        fontName=bold_font,
        textColor=colors.white,
        alignment=TA_CENTER,
    )

    document = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title="YULA Dosya Bütünlüğü Güvenlik Raporu",
        author="YULA",
    )

    period_format = "%d.%m.%Y %H:%M" if include_times else "%d.%m.%Y"
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for event in events:
        counts[event.get("risk_level", "LOW")] = (
            counts.get(event.get("risk_level", "LOW"), 0) + 1
        )

    story = [
        Paragraph("YULA Güvenlik Raporu", title_style),
        Paragraph(
            f"Rapor aralığı: {start_at.strftime(period_format)} - "
            f"{end_at.strftime(period_format)}",
            body_style,
        ),
        Paragraph(
            f"Rapor kapsamı: {escape(report_scope or 'Tüm izleme çalışmaları')}",
            body_style,
        ),
        Spacer(1, 4 * mm),
    ]

    summary = Table(
        [
            ["Toplam olay", "Yüksek risk", "Orta risk", "Düşük risk"],
            [len(events), counts["HIGH"], counts["MEDIUM"], counts["LOW"]],
        ],
        colWidths=[45 * mm] * 4,
        hAlign="LEFT",
    )
    summary.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), bold_font),
        ("FONTNAME", (0, 1), (-1, 1), bold_font),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#475569")),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#0F172A")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([summary, Spacer(1, 5 * mm)])

    headers = [
        "Algılanma zamanı" if include_times else "Algılanma tarihi",
        "Risk",
        "Olay",
        "Hedef",
        "Kaynak",
        "Oturum kullanıcısı*",
        "Açıklama",
    ]
    rows = [[Paragraph(header, header_style) for header in headers]]
    for event in events:
        detail_text = _event_detail_text(event)
        description = event.get("description") or "-"
        if detail_text:
            description = f"{description}\n{detail_text}"
        values = (
            _format_timestamp(event["timestamp"], include_times),
            risk_label(event["risk_level"]),
            event_type_label(event["event_type"]),
            event.get("target_path") or "-",
            event.get("source_path") or "-",
            event.get("actor_name") or "Belirlenemedi",
            description,
        )
        rows.append([
            Paragraph(escape(str(value)), small_style)
            for value in values
        ])

    event_table = Table(
        rows,
        repeatRows=1,
        colWidths=[26 * mm, 16 * mm, 27 * mm, 47 * mm, 42 * mm, 27 * mm, 78 * mm],
    )
    event_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(event_table)
    story.extend([
        Spacer(1, 5 * mm),
        Paragraph(
            "* Oturum kullanıcısı, olay gözlenirken açık olan kullanıcı hesabıdır. "
            "İşlemi yapan kişiyi tek başına kanıtlamaz. Kesin aktör tespiti için "
            "yetkili işletim sistemi denetim kayıtları gerekir.",
            body_style,
        ),
    ])

    document.build(
        story,
        onFirstPage=_page_footer,
        onLaterPages=_page_footer,
    )
    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError("PDF raporu oluşturulamadı.")
    return output_path
