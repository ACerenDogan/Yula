"""YULA tablo hücreleri için küçük, yeniden kullanılabilir çizim bileşenleri."""

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
)


RISK_BADGE_COLORS = {
    "HIGH": QColor("#FF6B6B"),
    "MEDIUM": QColor("#F5A524"),
    "LOW": QColor("#57C78B"),
}


class RiskBadgeDelegate(QStyledItemDelegate):
    """Risk metnini düşük kontrastlı, okunaklı bir pill olarak çizer."""

    def paint(self, painter: QPainter, option, index) -> None:
        if index.column() != 1:
            super().paint(painter, option, index)
            return

        style_option = QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        text = style_option.text
        style_option.text = ""
        style_option.icon = QIcon()
        style = (
            style_option.widget.style()
            if style_option.widget is not None
            else None
        )
        if style is not None:
            style.drawControl(
                QStyle.ControlElement.CE_ItemViewItem,
                style_option,
                painter,
                style_option.widget,
            )

        risk = index.data(Qt.ItemDataRole.UserRole + 1) or "LOW"
        accent = RISK_BADGE_COLORS.get(risk, QColor("#8E96A3"))
        fill = QColor(accent)
        fill.setAlpha(38)
        outline = QColor(accent)
        outline.setAlpha(92)

        metrics = option.fontMetrics
        badge_width = min(
            max(metrics.horizontalAdvance(text) + 18, 58),
            max(option.rect.width() - 12, 20),
        )
        badge_height = min(22, max(option.rect.height() - 8, 16))
        badge_rect = QRectF(
            option.rect.center().x() - badge_width / 2,
            option.rect.center().y() - badge_height / 2,
            badge_width,
            badge_height,
        )

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(fill)
        painter.setPen(outline)
        painter.drawRoundedRect(
            badge_rect,
            badge_height / 2,
            badge_height / 2,
        )
        painter.setPen(accent)
        painter.drawText(
            badge_rect,
            Qt.AlignmentFlag.AlignCenter,
            text,
        )
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(max(size.width(), 86), max(size.height(), 34))
