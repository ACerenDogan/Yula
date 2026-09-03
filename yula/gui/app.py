import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor

from yula.storage.database import DatabaseManager

class YulaMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YULA - Güvenlik ve Dosya Bütünlüğü Sistemi")
        self.resize(1000, 650)

        self.db = DatabaseManager("yula.db")

        self._init_ui()
        self._refresh_data()

        # Her 2 saniyede bir veritabanındaki yeni olayları ekrana çeken canlı zamanlayıcı (Timer)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_data)
        self.timer.start(2000)

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 1. ÜST BAŞLIK (Header)
        header_layout = QHBoxLayout()
        
        title_box = QVBoxLayout()
        title = QLabel("🛡️ YULA GÜVENLİK KONSOLU")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setStyleSheet("color: #1a365d;")
        
        subtitle = QLabel("Gerçek Zamanlı Dosya Bütünlüğü (FIM) ve Saldırı Tespit Paneli")
        subtitle.setStyleSheet("color: #718096; font-size: 11px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        self.badge = QLabel("İzleme: AKTİF 🟢")
        self.badge.setStyleSheet("""
            background-color: #def7ec; color: #03543f; font-weight: bold;
            padding: 8px 16px; border-radius: 12px; border: 1px solid #bcf0da;
        """)
        header_layout.addWidget(self.badge)
        main_layout.addLayout(header_layout)

        # 2. KPI ÖZET KARTLARI
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(15)

        self.card_total = self._create_card("Toplam Olay", "0", "#3182ce")
        self.card_high = self._create_card("Kritik (HIGH) Alarm", "0", "#e53e3e")
        self.card_low = self._create_card("Düşük Riskli Olay", "0", "#38a169")

        kpi_layout.addWidget(self.card_total)
        kpi_layout.addWidget(self.card_high)
        kpi_layout.addWidget(self.card_low)
        main_layout.addLayout(kpi_layout)

        # 3. CANLI GÜVENLİK OLAYLARI TABLOSU
        table_lbl = QLabel("📋 Canlı Güvenlik Olay Günlüğü (Event Log)")
        table_lbl.setStyleSheet("font-weight: bold; color: #2d3748; margin-top: 5px;")
        main_layout.addWidget(table_lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Zaman", "Risk", "Olay Tipi", "Açıklama"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        main_layout.addWidget(self.table)

        # 4. ALT BUTONLAR
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 Şimdi Yenile")
        self.btn_refresh.clicked.connect(self._refresh_data)
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

    def _create_card(self, title: str, val: str, color_hex: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet("background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px;")
        layout = QVBoxLayout(card)
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("color: #718096; font-size: 11px; font-weight: bold;")
        lbl_v = QLabel(val)
        lbl_v.setFont(QFont("Arial", 16, QFont.Bold))
        lbl_v.setStyleSheet(f"color: {color_hex};")
        layout.addWidget(lbl_t)
        layout.addWidget(lbl_v)
        card.lbl_val = lbl_v
        return card

    def _refresh_data(self):
        events = self.db.get_recent_events(limit=50)
        self.table.setRowCount(len(events))

        high_count = sum(1 for e in events if e["risk_level"] == "HIGH")
        low_count = sum(1 for e in events if e["risk_level"] == "LOW")

        self.card_total.lbl_val.setText(str(len(events)))
        self.card_high.lbl_val.setText(str(high_count))
        self.card_low.lbl_val.setText(str(low_count))

        for row_idx, ev in enumerate(events):
            self.table.setItem(row_idx, 0, QTableWidgetItem(ev["timestamp"]))

            risk_item = QTableWidgetItem(ev["risk_level"])
            risk_item.setTextAlignment(Qt.AlignCenter)
            if ev["risk_level"] == "HIGH":
                risk_item.setForeground(QColor("#e53e3e"))
                risk_item.setFont(QFont("Arial", 9, QFont.Bold))
            else:
                risk_item.setForeground(QColor("#38a169"))
            self.table.setItem(row_idx, 1, risk_item)

            self.table.setItem(row_idx, 2, QTableWidgetItem(ev["event_type"]))
            self.table.setItem(row_idx, 3, QTableWidgetItem(ev["description"]))


def start_gui():
    app = QApplication(sys.argv)
    window = YulaMainWindow()
    window.show()
    sys.exit(app.exec())