"""Olay tablosunun sütun yerleşimi ve kullanıcı gezinme davranışı."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTreeWidget


class EventTreeWidget(QTreeWidget):
    """Sabit meta sütunları ile iki esnek içerik sütununu dengeler."""

    userScrolledDown = Signal()

    TIME_WIDTH = 140
    RISK_WIDTH = 110
    EVENT_WIDTH = 90
    ACTOR_WIDTH = 120
    PATH_MINIMUM = 200
    RIGHT_PADDING = 4
    PATH_SHARE = 0.32

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.apply_column_widths()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.apply_column_widths()

    def wheelEvent(self, event) -> None:
        vertical_delta = event.pixelDelta().y() or event.angleDelta().y()
        if vertical_delta < 0:
            self.userScrolledDown.emit()
        super().wheelEvent(event)

    def apply_column_widths(self) -> None:
        viewport_width = self.viewport().width()
        fixed_width = (
            self.TIME_WIDTH
            + self.RISK_WIDTH
            + self.EVENT_WIDTH
            + self.ACTOR_WIDTH
            + self.RIGHT_PADDING
        )
        flexible_width = max(viewport_width - fixed_width, 0)
        path_width = min(
            max(int(flexible_width * self.PATH_SHARE), self.PATH_MINIMUM),
            flexible_width,
        )
        detail_width = max(flexible_width - path_width, 0)

        widths = (
            self.TIME_WIDTH,
            self.RISK_WIDTH,
            self.EVENT_WIDTH,
            path_width,
            detail_width,
            self.ACTOR_WIDTH,
        )
        for column, width in enumerate(widths):
            self.setColumnWidth(column, width)
