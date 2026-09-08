import os
import sys
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QThread,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from yula.application.monitoring_service import (
    MonitoringService,
)
from yula.gui.labels import (
    event_type_label,
    risk_label,
)
from yula.gui.target_selection import (
    TargetSelectionDialog,
)
from yula.storage.database import DatabaseManager


def configure_application_font(
    application: QApplication,
) -> None:
    """Uygulama için sistemde bulunan okunaklı bir arayüz yazı tipi seçer."""
    available_families = set(QFontDatabase.families())
    current_font = application.font()

    if current_font.family() in available_families:
        return

    for family in (
        "Helvetica Neue",
        "Arial",
        "DejaVu Sans",
    ):
        if family in available_families:
            current_font.setFamily(family)
            application.setFont(current_font)
            return


class EventBridge(QObject):
    """Watchdog thread'indeki olayları GUI thread'ine taşır."""

    event_received = Signal(dict)


class MonitoringStartWorker(QObject):
    """Referans durum taramasını arayüzü dondurmadan çalıştırır."""

    succeeded = Signal(int)
    failed = Signal(str)

    def __init__(
        self,
        service: MonitoringService,
        targets: list[str],
    ):
        super().__init__()
        self.service = service
        self.targets = targets

    @Slot()
    def run(self) -> None:
        try:
            session_id = self.service.start(
                self.targets
            )
            self.succeeded.emit(session_id)

        except Exception as error:
            self.failed.emit(str(error))


class YulaMainWindow(QMainWindow):
    STATUS_STYLES = {
        "WAITING": (
            "#475569",
            "#f1f5f9",
            "#cbd5e1",
        ),
        "PREPARING": (
            "#92400e",
            "#fffbeb",
            "#fde68a",
        ),
        "RUNNING": (
            "#166534",
            "#f0fdf4",
            "#bbf7d0",
        ),
        "STOPPED": (
            "#334155",
            "#f8fafc",
            "#cbd5e1",
        ),
        "ERROR": (
            "#991b1b",
            "#fef2f2",
            "#fecaca",
        ),
    }

    def __init__(
        self,
        database: DatabaseManager | None = None,
        service_factory=MonitoringService,
        show_startup_dialog: bool = True,
    ):
        super().__init__()

        self.setWindowTitle(
            "YULA — Dosya Bütünlüğü Denetim Paneli"
        )
        self.resize(1180, 720)
        self.setMinimumSize(920, 600)

        project_root = Path(__file__).resolve().parents[2]
        database_path = project_root / "yula.db"

        self.database = (
            database
            if database is not None
            else DatabaseManager(str(database_path))
        )

        self.event_bridge = EventBridge()
        self.event_bridge.event_received.connect(
            self._on_event_received
        )

        self.service = service_factory(
            database=self.database,
            event_callback=(
                self.event_bridge.event_received.emit
            ),
        )

        self.current_session_id: int | None = None
        self.selected_targets: list[str] = []
        self.expect_running = False

        self._start_thread: QThread | None = None
        self._start_worker: MonitoringStartWorker | None = None

        self._build_ui()
        self._set_status(
            "WAITING",
            "SEÇİM BEKLENİYOR",
        )
        self._refresh_events()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(
            self._periodic_refresh
        )
        self.refresh_timer.start(1000)

        if show_startup_dialog:
            QTimer.singleShot(
                0,
                self._open_target_selection,
            )

    def _build_ui(self) -> None:
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(28, 24, 28, 24)
        main_layout.setSpacing(18)

        header_layout = QHBoxLayout()

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)

        title = QLabel("YULA")
        title.setObjectName("applicationTitle")

        subtitle = QLabel(
            "Yerel dosya ve klasör değişikliklerini güvenilir referansa göre izler"
        )
        subtitle.setObjectName("applicationSubtitle")

        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        self.status_badge = QLabel()
        self.status_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.status_badge.setMinimumWidth(180)
        self.status_badge.setMinimumHeight(38)

        header_layout.addWidget(self.status_badge)
        main_layout.addLayout(header_layout)

        control_frame = QFrame()
        control_frame.setObjectName("controlFrame")

        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(18, 14, 18, 14)
        control_layout.setSpacing(12)

        target_layout = QVBoxLayout()
        target_layout.setSpacing(2)

        target_title = QLabel("İzlenen hedefler")
        target_title.setObjectName("sectionCaption")

        self.target_summary = QLabel(
            "Henüz dosya veya klasör seçilmedi."
        )
        self.target_summary.setObjectName("targetSummary")
        self.target_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        target_layout.addWidget(target_title)
        target_layout.addWidget(self.target_summary)

        control_layout.addLayout(target_layout)
        control_layout.addStretch()

        self.select_targets_button = QPushButton(
            "Dosya veya Klasör Seç"
        )
        self.select_targets_button.setObjectName(
            "primaryButton"
        )
        self.select_targets_button.clicked.connect(
            self._open_target_selection
        )

        self.stop_button = QPushButton(
            "İzlemeyi Durdur"
        )
        self.stop_button.setObjectName("dangerButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(
            self._stop_monitoring
        )

        control_layout.addWidget(
            self.select_targets_button
        )
        control_layout.addWidget(self.stop_button)

        main_layout.addWidget(control_frame)

        event_header_layout = QHBoxLayout()

        event_title_layout = QVBoxLayout()
        event_title_layout.setSpacing(2)

        event_title = QLabel("Dosya değişiklikleri")
        event_title.setObjectName("sectionTitle")

        event_description = QLabel(
            "Bir dosya satırını açarak o dosyanın "
            "değişiklik geçmişini inceleyin."
        )
        event_description.setObjectName(
            "sectionDescription"
        )

        event_title_layout.addWidget(event_title)
        event_title_layout.addWidget(
            event_description
        )

        self.session_label = QLabel(
            "Aktif çalışma yok"
        )
        self.session_label.setObjectName("sessionLabel")

        event_header_layout.addLayout(
            event_title_layout
        )
        event_header_layout.addStretch()
        event_header_layout.addWidget(
            self.session_label
        )

        main_layout.addLayout(event_header_layout)

        filter_frame = QFrame()
        filter_frame.setObjectName("filterFrame")

        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Dosya adı, yol veya açıklama ara"
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(
            self._refresh_events
        )

        self.risk_filter = QComboBox()
        self.risk_filter.addItem(
            "Tüm risk düzeyleri",
            None,
        )
        self.risk_filter.addItem("Yüksek", "HIGH")
        self.risk_filter.addItem("Orta", "MEDIUM")
        self.risk_filter.addItem("Düşük", "LOW")
        self.risk_filter.currentIndexChanged.connect(
            self._refresh_events
        )

        filter_layout.addWidget(self.search_input, 1)
        filter_layout.addWidget(self.risk_filter)

        main_layout.addWidget(filter_frame)

        self.table = QTreeWidget()
        self.table.setObjectName("eventTree")
        self.table.setColumnCount(5)
        self.table.setHeaderLabels([
            "Son olay",
            "En yüksek risk",
            "Son işlem",
            "Dosya / hedef",
            "Özet",
        ])

        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setAlternatingRowColors(True)
        self.table.setRootIsDecorated(True)
        self.table.setItemsExpandable(True)
        self.table.setAnimated(True)
        self.table.setIndentation(22)
        self.table.setExpandsOnDoubleClick(True)

        header = self.table.header()

        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            4,
            QHeaderView.ResizeMode.Stretch,
        )

        self.empty_state = QFrame()
        self.empty_state.setObjectName("emptyState")

        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(32, 48, 32, 48)
        empty_layout.setSpacing(8)
        empty_layout.addStretch()

        self.empty_title = QLabel(
            "İzleme henüz başlamadı"
        )
        self.empty_title.setObjectName("emptyTitle")
        self.empty_title.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.empty_description = QLabel(
            "Başlamak için yukarıdan bir dosya veya "
            "klasör seçin."
        )
        self.empty_description.setObjectName(
            "emptyDescription"
        )
        self.empty_description.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.empty_description.setWordWrap(True)

        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(
            self.empty_description
        )
        empty_layout.addStretch()

        self.event_stack = QStackedWidget()
        self.event_stack.addWidget(self.empty_state)
        self.event_stack.addWidget(self.table)

        main_layout.addWidget(self.event_stack, 1)

        footer_layout = QHBoxLayout()

        self.event_count_label = QLabel(
            "0 olay görüntüleniyor"
        )
        self.event_count_label.setObjectName("footerLabel")

        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.clicked.connect(
            self._refresh_events
        )

        footer_layout.addWidget(
            self.event_count_label
        )
        footer_layout.addStretch()
        footer_layout.addWidget(self.refresh_button)

        main_layout.addLayout(footer_layout)

        self.setStyleSheet("""
            QWidget#centralWidget {
                background-color: #f8fafc;
            }

            QLabel#applicationTitle {
                color: #0f172a;
                font-size: 25px;
                font-weight: 750;
            }

            QLabel#applicationSubtitle {
                color: #64748b;
                font-size: 13px;
            }

            QFrame#controlFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }

            QLabel#sectionCaption {
                color: #64748b;
                font-size: 11px;
                font-weight: 650;
            }

            QLabel#targetSummary {
                color: #0f172a;
                font-size: 13px;
            }

            QLabel#sectionTitle {
                color: #0f172a;
                font-size: 16px;
                font-weight: 700;
            }

            QLabel#sectionDescription {
                color: #64748b;
                font-size: 12px;
            }

            QLabel#sessionLabel,
            QLabel#footerLabel {
                color: #64748b;
                font-size: 12px;
            }

            QPushButton {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                min-height: 32px;
                padding: 2px 16px;
            }

            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }

            QPushButton:disabled {
                color: #94a3b8;
                background-color: #f8fafc;
            }

            QPushButton#dangerButton {
                color: #991b1b;
                border-color: #fecaca;
            }

            QPushButton#primaryButton {
                color: #ffffff;
                background-color: #1d4ed8;
                border-color: #1d4ed8;
                font-weight: 650;
            }

            QPushButton#primaryButton:hover {
                background-color: #1e40af;
                border-color: #1e40af;
            }

            QPushButton#primaryButton:disabled {
                color: #dbeafe;
                background-color: #93c5fd;
                border-color: #93c5fd;
            }

            QFrame#filterFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 7px;
            }

            QLineEdit,
            QComboBox {
                min-height: 32px;
                color: #0f172a;
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 10px;
            }

            QLineEdit:focus,
            QComboBox:focus {
                border-color: #2563eb;
            }

            QTreeWidget#eventTree {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 7px;
                selection-background-color: #dbeafe;
                selection-color: #172554;
                outline: none;
            }

            QTreeWidget#eventTree::item {
                min-height: 36px;
                border-bottom: 1px solid #f1f5f9;
            }

            QTreeWidget#eventTree::item:hover {
                background-color: #eff6ff;
            }

            QFrame#emptyState {
                background-color: #ffffff;
                border: 1px dashed #cbd5e1;
                border-radius: 8px;
            }

            QLabel#emptyTitle {
                color: #0f172a;
                font-size: 17px;
                font-weight: 700;
            }

            QLabel#emptyDescription {
                color: #64748b;
                font-size: 13px;
            }

            QHeaderView::section {
                background-color: #f1f5f9;
                color: #475569;
                border: none;
                border-bottom: 1px solid #cbd5e1;
                padding: 9px;
                font-weight: 650;
            }
        """)

    def _set_status(
        self,
        status: str,
        text: str,
    ) -> None:
        foreground, background, border = (
            self.STATUS_STYLES[status]
        )

        self.status_badge.setText(text)
        self.status_badge.setStyleSheet(f"""
            QLabel {{
                color: {foreground};
                background-color: {background};
                border: 1px solid {border};
                border-radius: 7px;
                padding: 7px 14px;
                font-size: 12px;
                font-weight: 700;
            }}
        """)

    def _open_target_selection(self) -> None:
        if self.service.is_running:
            return

        dialog = TargetSelectionDialog(
            self,
            initial_targets=self.selected_targets,
        )

        result = dialog.exec()

        if (
            result
            != TargetSelectionDialog.DialogCode.Accepted
        ):
            return

        self.selected_targets = (
            dialog.selected_targets()
        )
        self._update_target_summary()
        self._begin_monitoring()

    def _update_target_summary(self) -> None:
        target_count = len(self.selected_targets)

        if target_count == 0:
            text = "Henüz dosya veya klasör seçilmedi."
            tooltip = ""

        elif target_count == 1:
            text = self.selected_targets[0]
            tooltip = self.selected_targets[0]

        else:
            text = f"{target_count} hedef seçildi"
            tooltip = "\n".join(self.selected_targets)

        self.target_summary.setText(text)
        self.target_summary.setToolTip(tooltip)

    def _begin_monitoring(self) -> None:
        if not self.selected_targets:
            return

        self._set_status(
            "PREPARING",
            "REFERANS DURUM HAZIRLANIYOR",
        )

        self.select_targets_button.setEnabled(False)
        self.stop_button.setEnabled(False)

        thread = QThread(self)
        worker = MonitoringStartWorker(
            self.service,
            list(self.selected_targets),
        )

        worker.moveToThread(thread)

        thread.started.connect(worker.run)

        worker.succeeded.connect(
            self._on_monitoring_started
        )
        worker.failed.connect(
            self._on_monitoring_failed
        )

        worker.succeeded.connect(thread.quit)
        worker.failed.connect(thread.quit)

        worker.succeeded.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)

        thread.finished.connect(
            self._clear_start_worker
        )
        thread.finished.connect(thread.deleteLater)

        self._start_thread = thread
        self._start_worker = worker

        thread.start()

    @Slot(int)
    def _on_monitoring_started(
        self,
        session_id: int,
    ) -> None:
        self.current_session_id = session_id
        self.expect_running = True

        self.session_label.setText(
            f"İzleme çalışması #{session_id}"
        )

        self._set_status(
            "RUNNING",
            "İZLEME AKTİF",
        )

        self.select_targets_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self._refresh_events()

    @Slot(str)
    def _on_monitoring_failed(
        self,
        error_message: str,
    ) -> None:
        self.expect_running = False

        self._set_status(
            "ERROR",
            "BAŞLATMA HATASI",
        )

        self.select_targets_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        QMessageBox.critical(
            self,
            "İzleme Başlatılamadı",
            error_message,
        )

    @Slot()
    def _clear_start_worker(self) -> None:
        self._start_worker = None
        self._start_thread = None

    def _stop_monitoring(self) -> None:
        if not self.service.is_running:
            return

        try:
            self.service.stop()

        except Exception as error:
            self._set_status(
                "ERROR",
                "DURDURMA HATASI",
            )

            QMessageBox.critical(
                self,
                "İzleme Durdurulamadı",
                str(error),
            )
            return

        self.expect_running = False

        self._set_status(
            "STOPPED",
            "İZLEME DURDURULDU",
        )

        self.select_targets_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        self._refresh_events()

    @Slot(dict)
    def _on_event_received(
        self,
        event: dict,
    ) -> None:
        if (
            event.get("session_id")
            == self.current_session_id
        ):
            self._refresh_events()

    def _periodic_refresh(self) -> None:
        if self.current_session_id is not None:
            self._refresh_events()

        if (
            self.expect_running
            and self._start_thread is None
            and not self.service.is_running
        ):
            self.expect_running = False
            self._set_status(
                "ERROR",
                "İZLEYİCİ DURDU",
            )
            self.select_targets_button.setEnabled(True)
            self.stop_button.setEnabled(False)

    def _refresh_events(self) -> None:
        expanded_targets = set()

        for index in range(
            self.table.topLevelItemCount()
        ):
            item = self.table.topLevelItem(index)

            if item.isExpanded():
                expanded_targets.add(
                    item.data(
                        3,
                        Qt.ItemDataRole.UserRole,
                    )
                )

        if self.current_session_id is None:
            all_groups = []
        else:
            all_groups = self.database.get_event_groups(
                session_id=self.current_session_id,
                limit=100,
            )

        search_term = (
            self.search_input.text().strip().casefold()
        )
        selected_risk = self.risk_filter.currentData()

        groups = []

        for group in all_groups:
            searchable_text = " ".join((
                group["target_path"] or "",
                group["description"] or "",
                event_type_label(group["event_type"]),
            )).casefold()

            if (
                search_term
                and search_term not in searchable_text
            ):
                continue

            if (
                selected_risk is not None
                and group["highest_risk"]
                != selected_risk
            ):
                continue

            groups.append(group)

        self.table.clear()

        if groups:
            self.event_stack.setCurrentWidget(
                self.table
            )
        else:
            self.event_stack.setCurrentWidget(
                self.empty_state
            )

            if self.current_session_id is None:
                self.empty_title.setText(
                    "İzleme henüz başlamadı"
                )
                self.empty_description.setText(
                    "Başlamak için yukarıdan bir dosya "
                    "veya klasör seçin."
                )
            elif all_groups:
                self.empty_title.setText(
                    "Eşleşen olay bulunamadı"
                )
                self.empty_description.setText(
                    "Arama metnini veya risk filtresini "
                    "değiştirerek yeniden deneyin."
                )
            else:
                self.empty_title.setText(
                    "Henüz güvenlik olayı yok"
                )
                self.empty_description.setText(
                    "İzleme aktif. Seçtiğiniz hedeflerdeki "
                    "değişiklikler burada görünecek."
                )

        risk_colors = {
            "HIGH": "#dc2626",
            "MEDIUM": "#d97706",
            "LOW": "#15803d",
        }
        risk_backgrounds = {
            "HIGH": "#fef2f2",
            "MEDIUM": "#fffbeb",
            "LOW": "#f0fdf4",
        }

        total_event_count = 0

        for group in groups:
            target_path = group["target_path"] or ""
            target_name = (
                os.path.basename(target_path)
                or target_path
            )

            event_count = group["event_count"]
            total_event_count += event_count

            last_seen = group["last_seen"].replace(
                "T",
                " ",
            )

            group_item = QTreeWidgetItem(
                self.table
            )

            group_item.setText(0, last_seen)
            group_item.setText(
                1,
                risk_label(group["highest_risk"]),
            )
            group_item.setText(
                2,
                event_type_label(group["event_type"]),
            )
            group_item.setText(3, target_name)
            group_item.setIcon(
                3,
                self.style().standardIcon(
                    QStyle.StandardPixmap.SP_FileIcon
                ),
            )
            group_item.setText(
                4,
                f"{event_count} olay · "
                f"{group['description']}",
            )

            group_item.setData(
                3,
                Qt.ItemDataRole.UserRole,
                target_path,
            )
            group_item.setToolTip(
                3,
                target_path,
            )
            group_item.setToolTip(
                4,
                "Dosyanın olay geçmişini görmek için "
                "satırı açın.",
            )
            group_item.setTextAlignment(
                1,
                Qt.AlignmentFlag.AlignCenter,
            )
            group_item.setForeground(
                1,
                QColor(
                    risk_colors.get(
                        group["highest_risk"],
                        "#475569",
                    )
                ),
            )
            group_item.setBackground(
                1,
                QColor(
                    risk_backgrounds.get(
                        group["highest_risk"],
                        "#ffffff",
                    )
                ),
            )

            for column in range(
                self.table.columnCount()
            ):
                group_font = group_item.font(
                    column
                )
                group_font.setWeight(
                    QFont.Weight.DemiBold
                )
                group_item.setFont(
                    column,
                    group_font,
                )

                if column != 1:
                    group_item.setBackground(
                        column,
                        QColor("#f8fafc"),
                    )

            events = (
                self.database.get_events_for_target(
                    session_id=self.current_session_id,
                    target_path=target_path,
                    limit=200,
                )
            )

            for event in events:
                timestamp = event["timestamp"].replace(
                    "T",
                    " ",
                )

                event_item = QTreeWidgetItem(
                    group_item
                )

                event_item.setText(0, timestamp)
                event_item.setText(
                    1,
                    risk_label(event["risk_level"]),
                )
                event_item.setText(
                    2,
                    event_type_label(
                        event["event_type"]
                    ),
                )
                event_item.setText(3, "")
                event_item.setText(
                    4,
                    event["description"],
                )

                event_item.setTextAlignment(
                    1,
                    Qt.AlignmentFlag.AlignCenter,
                )
                event_item.setForeground(
                    1,
                    QColor(
                        risk_colors.get(
                            event["risk_level"],
                            "#475569",
                        )
                    ),
                )
                event_item.setBackground(
                    1,
                    QColor(
                        risk_backgrounds.get(
                            event["risk_level"],
                            "#ffffff",
                        )
                    ),
                )

            group_item.setExpanded(
                target_path in expanded_targets
            )

        if len(groups) != len(all_groups):
            count_text = (
                f"{total_event_count} olay, "
                f"{len(groups)} hedef eşleşiyor"
            )
        else:
            count_text = (
                f"{total_event_count} olay, "
                f"{len(groups)} hedef görüntüleniyor"
            )

        self.event_count_label.setText(count_text)

    def closeEvent(self, event) -> None:
        if (
            self._start_thread is not None
            and self._start_thread.isRunning()
        ):
            QMessageBox.information(
                self,
                "Tarama Devam Ediyor",
                "Referans durum taraması tamamlanmadan "
                "uygulama kapatılamaz.",
            )
            event.ignore()
            return

        if self.service.is_running:
            try:
                self.service.stop()
            except Exception:
                pass

        event.accept()


def start_gui() -> None:
    application = QApplication(sys.argv)
    application.setStyle("Fusion")
    configure_application_font(application)

    window = YulaMainWindow()
    window.show()

    sys.exit(application.exec())
