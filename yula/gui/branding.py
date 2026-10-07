from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


ASSETS_DIRECTORY = Path(__file__).resolve().parent / "assets"
YULA_ICON_PATH = ASSETS_DIRECTORY / "yula-icon-v3.png"


def yula_icon() -> QIcon:
    """Yula'nın pencere ve başlık simgesini döndürür."""
    return QIcon(str(YULA_ICON_PATH))


def filter_icon() -> QIcon:
    """Minimal olay filtresi simgesi oluşturur."""
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#8D969F"), 1.2))
    painter.drawLine(3, 4, 15, 4)
    painter.drawLine(5, 9, 13, 9)
    painter.drawLine(7, 14, 11, 14)
    painter.end()
    return QIcon(pixmap)


def search_icon() -> QIcon:
    """Arama alanı için ince çizgili büyüteç simgesi oluşturur."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#727B88"), 1.3))
    painter.drawEllipse(2, 2, 8, 8)
    painter.drawLine(9, 9, 14, 14)
    painter.end()
    return QIcon(pixmap)
