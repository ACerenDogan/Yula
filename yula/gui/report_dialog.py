import os
from datetime import datetime, timedelta

from PySide6.QtCore import QDateTime, QLocale, QStandardPaths, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from yula.gui.labels import session_status_label
from yula.gui.branding import yula_icon
from yula.gui.theme import APPLICATION_STYLESHEET
from yula.gui.time_format import format_tr_datetime, parse_stored_datetime
from yula.reporting.pdf_report import generate_security_report
from yula.storage.database import DatabaseManager


class ReportDialog(QDialog):
    """Çalışma ve tarih-saat aralığı seçilerek PDF raporu üretir."""

    RANGE_TODAY = "TODAY"
    RANGE_LAST_24_HOURS = "LAST_24_HOURS"
    RANGE_LAST_7_DAYS = "LAST_7_DAYS"
    RANGE_SESSION = "SESSION"
    RANGE_CUSTOM = "CUSTOM"

    def __init__(
        self,
        database: DatabaseManager,
        session_id: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.database = database
        self.setWindowTitle("PDF Güvenlik Raporu")
        self.setWindowIcon(yula_icon())
        self.setMinimumWidth(570)
        self.setStyleSheet(APPLICATION_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel("PDF güvenlik raporu oluştur")
        title.setObjectName("dialogTitle")
        description = QLabel(
            "Önce raporlanacak çalışmayı, ardından tarih ve saat aralığını seçin."
        )
        description.setWordWrap(True)
        description.setObjectName("dialogDescription")
        layout.addWidget(title)
        layout.addWidget(description)

        self.session_combo = QComboBox()
        self.session_combo.addItem("Tüm izleme çalışmaları", None)
        for session in self.database.list_monitoring_sessions(limit=100):
            target_names = [
                os.path.basename(target["target_path"]) or target["target_path"]
                for target in session["targets"]
            ]
            targets_text = ", ".join(target_names[:2]) or "Hedef yok"
            if len(target_names) > 2:
                targets_text += f" +{len(target_names) - 2}"
            self.session_combo.addItem(
                f"Çalışma #{session['id']} · "
                f"{session_status_label(session['status'])} · "
                f"{format_tr_datetime(session['started_at'], False)} · "
                f"{targets_text}",
                session["id"],
            )

        if session_id is not None:
            selected_index = self.session_combo.findData(session_id)
            if selected_index >= 0:
                self.session_combo.setCurrentIndex(selected_index)

        self.range_combo = QComboBox()
        self.range_combo.addItem("Bugün", self.RANGE_TODAY)
        self.range_combo.addItem("Son 24 saat", self.RANGE_LAST_24_HOURS)
        self.range_combo.addItem("Son 7 gün", self.RANGE_LAST_7_DAYS)
        self.range_combo.addItem("Seçilen çalışmanın tamamı", self.RANGE_SESSION)
        self.range_combo.addItem("Özel tarih ve saat aralığı", self.RANGE_CUSTOM)
        self.range_combo.setCurrentIndex(2)

        now = QDateTime.currentDateTime()
        self.start_edit = QDateTimeEdit(now.addDays(-7))
        self.end_edit = QDateTimeEdit(now)
        turkish_locale = QLocale(
            QLocale.Language.Turkish,
            QLocale.Country.Turkey,
        )
        for editor in (self.start_edit, self.end_edit):
            editor.setCalendarPopup(True)
            editor.setLocale(turkish_locale)
            editor.setDisplayFormat("dd.MM.yyyy HH:mm")
            editor.dateTimeChanged.connect(self._update_preview)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.addRow("Raporlanacak çalışma", self.session_combo)
        form.addRow("Zaman aralığı", self.range_combo)
        form.addRow("Başlangıç", self.start_edit)
        form.addRow("Bitiş", self.end_edit)
        layout.addLayout(form)

        self.filter_with_times = QCheckBox(
            "Tarih filtresinde saat ve dakika kullan"
        )
        self.filter_with_times.setChecked(True)
        self.filter_with_times.toggled.connect(self._toggle_time_filter)
        layout.addWidget(self.filter_with_times)

        self.include_times = QCheckBox("Olay saatlerini PDF'de göster")
        self.include_times.setChecked(True)
        layout.addWidget(self.include_times)

        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setObjectName("reportPreview")
        layout.addWidget(self.preview_label)

        button_layout = QHBoxLayout()
        cancel_button = QPushButton("Vazgeç")
        cancel_button.clicked.connect(self.reject)
        self.generate_button = QPushButton("PDF Raporu Oluştur")
        self.generate_button.setObjectName("primaryButton")
        self.generate_button.clicked.connect(self._generate)
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(self.generate_button)
        layout.addLayout(button_layout)

        self.session_combo.currentIndexChanged.connect(self._session_changed)
        self.range_combo.currentIndexChanged.connect(self._apply_range_preset)
        self._apply_range_preset()

    def _selected_session_id(self) -> int | None:
        return self.session_combo.currentData()

    def _selected_range(self) -> tuple[datetime, datetime]:
        start_at = self.start_edit.dateTime().toPython()
        end_at = self.end_edit.dateTime().toPython()
        if not self.filter_with_times.isChecked():
            start_at = start_at.replace(hour=0, minute=0, second=0, microsecond=0)
            end_at = end_at.replace(hour=23, minute=59, second=59, microsecond=999999)
        return start_at, end_at

    def _session_changed(self) -> None:
        if self.range_combo.currentData() == self.RANGE_SESSION:
            self._apply_range_preset()
        else:
            self._update_preview()

    def _apply_range_preset(self) -> None:
        preset = self.range_combo.currentData()
        now = datetime.now()
        start_at = None
        end_at = now

        if preset == self.RANGE_TODAY:
            start_at = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif preset == self.RANGE_LAST_24_HOURS:
            start_at = now - timedelta(hours=24)
        elif preset == self.RANGE_LAST_7_DAYS:
            start_at = now - timedelta(days=7)
        elif preset == self.RANGE_SESSION:
            session_id = self._selected_session_id()
            session = (
                self.database.get_monitoring_session(session_id)
                if session_id is not None
                else None
            )
            if session is not None:
                start_at = parse_stored_datetime(session["started_at"])
                end_at = (
                    parse_stored_datetime(session["stopped_at"])
                    if session["stopped_at"]
                    else now
                )
            else:
                sessions = self.database.list_monitoring_sessions(limit=100)
                if sessions:
                    start_at = min(
                        parse_stored_datetime(item["started_at"])
                        for item in sessions
                    )
                    stopped_values = [
                        parse_stored_datetime(item["stopped_at"])
                        for item in sessions
                        if item["stopped_at"]
                    ]
                    if any(not item["stopped_at"] for item in sessions):
                        end_at = now
                    elif stopped_values:
                        end_at = max(stopped_values)

        if start_at is not None:
            self.start_edit.setDateTime(QDateTime(start_at))
            self.end_edit.setDateTime(QDateTime(end_at))

        editable = preset == self.RANGE_CUSTOM
        self.start_edit.setEnabled(editable)
        self.end_edit.setEnabled(editable)
        self._update_preview()

    def _toggle_time_filter(self, checked: bool) -> None:
        display_format = "dd.MM.yyyy HH:mm" if checked else "dd.MM.yyyy"
        self.start_edit.setDisplayFormat(display_format)
        self.end_edit.setDisplayFormat(display_format)
        self._update_preview()

    def _events(self) -> list[dict]:
        start_at, end_at = self._selected_range()
        return self.database.get_events_in_range(
            start_at,
            end_at,
            session_id=self._selected_session_id(),
        )

    def _scope_text(self) -> str:
        session_id = self._selected_session_id()
        return (
            f"Çalışma #{session_id}"
            if session_id is not None
            else "Tüm izleme çalışmaları"
        )

    def _update_preview(self) -> None:
        try:
            event_count = len(self._events())
            self.preview_label.setText(
                f"{self._scope_text()} seçildi. Bu aralıkta "
                f"{event_count} güvenlik olayı PDF'ye eklenecek."
            )
            self.generate_button.setEnabled(event_count > 0)
        except ValueError as error:
            self.preview_label.setText(str(error))
            self.generate_button.setEnabled(False)

    def _generate(self) -> None:
        start_at, end_at = self._selected_range()
        try:
            events = self._events()
        except ValueError as error:
            QMessageBox.warning(self, "Geçersiz tarih aralığı", str(error))
            return

        default_directory = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DownloadLocation
        ) or os.path.expanduser("~/Downloads")
        default_name = f"YULA_Guvenlik_Raporu_{start_at:%Y%m%d}_{end_at:%Y%m%d}.pdf"
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "PDF raporunu kaydet",
            os.path.join(default_directory, default_name),
            "PDF Dosyası (*.pdf)",
        )
        if not output_path:
            return

        try:
            final_path = generate_security_report(
                output_path,
                events,
                start_at,
                end_at,
                include_times=self.include_times.isChecked(),
                report_scope=self._scope_text(),
            )
        except Exception as error:
            QMessageBox.critical(self, "Rapor oluşturulamadı", str(error))
            return

        QMessageBox.information(
            self,
            "Rapor hazır",
            f"PDF güvenlik raporu oluşturuldu:\n{final_path}",
        )
        self.accept()
