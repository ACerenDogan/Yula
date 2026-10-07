import os
import sys
from pathlib import Path

from PySide6.QtCore import (
    QLocale,
    QObject,
    QSignalBlocker,
    QSize,
    QThread,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractSlider,
    QApplication,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStyle,
    QTreeWidgetItem,
)

from yula.application.monitoring_service import (
    MonitoringService,
)
from yula.application.agent_controller import BackgroundAgentController
from yula.gui.branding import yula_icon
from yula.gui.event_presenter import (
    event_details_summary,
    event_details_tooltip,
    event_technical_summary,
    session_status_icon,
)
from yula.gui.labels import (
    event_type_label,
    risk_label,
    session_status_label,
)
from yula.gui.main_window_view import build_main_window
from yula.gui.target_selection import (
    TargetSelectionDialog,
)
from yula.gui.report_dialog import ReportDialog
from yula.gui.theme import (
    APPLICATION_STYLESHEET,
    risk_badge_stylesheet,
    status_dot_stylesheet,
)
from yula.gui.time_format import format_tr_datetime
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
    def __init__(
        self,
        database: DatabaseManager | None = None,
        service_factory=BackgroundAgentController,
        show_startup_dialog: bool = True,
    ):
        super().__init__()

        self.setWindowTitle(
            "YULA — Dosya Bütünlüğü Denetim Paneli"
        )
        self.setWindowIcon(yula_icon())
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
        self.selected_event_category = "ALL"
        self.expect_running = False
        self._event_selection_is_manual = False
        self._current_status_text = "Seçim bekleniyor"

        self._start_thread: QThread | None = None
        self._start_worker: MonitoringStartWorker | None = None

        self._build_ui()
        self._set_status(
            "WAITING",
            "SEÇİM BEKLENİYOR",
        )

        if self.service.is_running:
            self.current_session_id = self.service.session_id
            self.selected_targets = list(self.service.targets)
            self.expect_running = True
            self._update_target_summary()
            self.session_label.setText(
                f"İzleme çalışması #{self.current_session_id}"
            )
            self._set_status("RUNNING", "ARKA PLAN İZLEMESİ AKTİF")
            self.select_targets_button.setEnabled(False)
            self.stop_button.setEnabled(True)

        self._refresh_sessions(
            select_session_id=self.current_session_id,
            select_latest=self.current_session_id is None,
        )
        self._refresh_events()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(
            self._periodic_refresh
        )
        self.refresh_timer.start(1000)

        if show_startup_dialog and not self.service.is_running:
            QTimer.singleShot(
                0,
                self._open_target_selection,
            )

    def _build_ui(self) -> None:
        build_main_window(self)
    def _toggle_sessions_dock(self) -> None:
        should_show = self.sessions_dock.isHidden()
        self.sessions_dock.setVisible(should_show)
        if should_show:
            self._refresh_sessions(select_session_id=self.current_session_id)

    @Slot(bool)
    def _update_sessions_button_state(self, visible: bool) -> None:
        self.sessions_button.setChecked(visible)

    def _refresh_sessions(
        self,
        select_session_id: int | None = None,
        select_latest: bool = False,
    ) -> None:
        sessions = self.database.list_monitoring_sessions(limit=100)
        scroll_bar = self.sessions_list.verticalScrollBar()
        previous_scroll_position = scroll_bar.value()
        wanted_id = select_session_id
        if wanted_id is None and self.current_session_id is not None:
            wanted_id = self.current_session_id
        if wanted_id is None and select_latest and sessions:
            wanted_id = sessions[0]["id"]

        self.sessions_list.blockSignals(True)
        self.sessions_list.clear()
        selected_item = None

        running_count = sum(
            session["status"] in {"RUNNING", "PREPARING"}
            for session in sessions
        )
        history_count = len(sessions) - running_count
        self.sessions_summary.setText(
            f"{running_count} etkin · {history_count} geçmiş çalışma"
            if sessions
            else "Henüz izleme çalışması yok"
        )
        self.sessions_button.setText("Çalışmalar")

        for session in sessions:
            targets = session["targets"]
            target_names = [
                os.path.basename(target["target_path"]) or target["target_path"]
                for target in targets
            ]
            target_text = ", ".join(target_names[:2]) or "Hedef yok"
            if len(target_names) > 2:
                target_text += f" +{len(target_names) - 2}"
            item = QListWidgetItem(
                f"Çalışma #{session['id']}\n"
                f"{session_status_label(session['status'])} · "
                f"{format_tr_datetime(session['started_at'], False)}\n"
                f"{session['event_count']} olay · {target_text}"
            )
            item.setIcon(session_status_icon(session["status"]))
            item.setSizeHint(QSize(0, 78))
            item.setData(Qt.ItemDataRole.UserRole, session["id"])
            item.setToolTip("\n".join(
                target["target_path"] for target in targets
            ))
            self.sessions_list.addItem(item)
            if session["id"] == wanted_id:
                selected_item = item

        if selected_item is not None:
            self.sessions_list.setCurrentItem(selected_item)
        self.sessions_list.blockSignals(False)
        scroll_bar.setValue(previous_scroll_position)

        if wanted_id is not None:
            self._show_session(wanted_id, refresh_events=False)

    @Slot(QListWidgetItem, QListWidgetItem)
    def _on_session_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        session_id = current.data(Qt.ItemDataRole.UserRole)
        self._show_session(session_id)

    def _show_session(
        self,
        session_id: int,
        refresh_events: bool = True,
    ) -> None:
        session = self.database.get_monitoring_session(session_id)
        if session is None:
            return
        self.current_session_id = session_id
        self.selected_targets = [
            target["target_path"] for target in session["targets"]
        ]
        self._update_target_summary()
        session_text = (
            f"Çalışma #{session_id} · "
            f"{session_status_label(session['status'])} · "
            f"{format_tr_datetime(session['started_at'], False)}"
        )
        self.session_label.setText(session_text)
        self.session_label.setToolTip(session_text)
        status_texts = {
            "PREPARING": "REFERANS DURUM HAZIRLANIYOR",
            "RUNNING": "İZLEME AKTİF",
            "STOPPED": "İZLEME DURDURULDU",
            "ERROR": "İZLEME HATASI",
        }
        self._set_status(
            session["status"],
            status_texts[session["status"]],
        )
        if refresh_events:
            self._refresh_events()

    def _refresh_all(self) -> None:
        self._refresh_sessions(select_session_id=self.current_session_id)
        self._refresh_events()

    def _set_status(
        self,
        status: str,
        text: str,
    ) -> None:
        self.sidebar_status_label.setText(text)
        self.status_dot.setStyleSheet(status_dot_stylesheet(status))
        self._current_status_text = (
            text.replace("İZLEME", "İzleme").lower().capitalize()
        )
        self._update_header_breadcrumb()

    @Slot(bool)
    def _set_live_follow(self, enabled: bool) -> None:
        self.live_follow_button.setText(
            "● Canlı" if enabled else "○ Duraklatıldı"
        )
        if enabled:
            self._event_selection_is_manual = False
            self.table.verticalScrollBar().setValue(
                self.table.verticalScrollBar().minimum()
            )
            self._refresh_events()

    @Slot()
    def _disable_live_follow(self) -> None:
        if not self.live_follow_button.isChecked():
            return
        blocker = QSignalBlocker(self.live_follow_button)
        self.live_follow_button.setChecked(False)
        self.live_follow_button.setText("○ Duraklatıldı")
        del blocker

    @Slot(int)
    def _on_event_scroll_position_changed(self, value: int) -> None:
        scroll_bar = self.table.verticalScrollBar()
        if value > scroll_bar.minimum() or self.live_follow_button.isChecked():
            return
        blocker = QSignalBlocker(self.live_follow_button)
        self.live_follow_button.setChecked(True)
        self.live_follow_button.setText("● Canlı")
        del blocker
        self._event_selection_is_manual = False

    @Slot(int)
    def _on_event_scroll_action(self, action: int) -> None:
        if action == QAbstractSlider.SliderAction.SliderToMinimum.value:
            return
        self._disable_live_follow()

    def _open_report_dialog(self) -> None:
        dialog = ReportDialog(
            database=self.database,
            session_id=self.current_session_id,
            parent=self,
        )
        dialog.exec()

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
        if not self.selected_targets:
            tooltip = ""
        else:
            tooltip = "\n".join(self.selected_targets)
        self.target_summary.setToolTip(tooltip)
        self._update_header_breadcrumb()

    def _update_header_breadcrumb(self) -> None:
        if not self.selected_targets:
            target_text = "Hedef seçilmedi"
        else:
            target_path = self.selected_targets[0]
            user_home = os.path.expanduser("~")
            if target_path == user_home:
                target_text = "~"
            elif target_path.startswith(f"{user_home}{os.sep}"):
                target_text = f"~{target_path[len(user_home):]}"
            else:
                target_text = target_path
            if len(self.selected_targets) > 1:
                target_text += f" · +{len(self.selected_targets) - 1} hedef"

        self.target_summary.setText(
            f"📁 {target_text} · Durum: {self._current_status_text}"
        )

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

        self._refresh_sessions(select_session_id=session_id)
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

        self._refresh_sessions(select_session_id=self.current_session_id)

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

        self._refresh_sessions(select_session_id=self.current_session_id)
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

    def _selected_category_types(self) -> set[str] | None:
        categories = {
            "COPIES": {
                "CLIPBOARD_COPY",
                "CONTENT_CLIPBOARD_COPY",
                "POSSIBLE_COPY",
            },
            "CHANGES": {"MODIFIED", "CREATED", "RESTORED", "MOVED"},
            "DELETIONS": {"DELETED"},
            "AUTHORITY": {
                "PERMISSIONS_CHANGED",
                "OWNERSHIP_CHANGED",
                "SYMLINK_CHANGED",
            },
        }
        return categories.get(self.selected_event_category)

    def _set_event_category(self, category: str) -> None:
        self.selected_event_category = category
        selected_action = self.event_filter_actions.get(category)
        if selected_action is not None:
            selected_action.setChecked(True)
            self.event_filter_button.setToolTip(
                f"Olay türü filtresi: {selected_action.text()}"
            )
        self._refresh_events()

    def _event_matches_filters(self, event: dict) -> bool:
        selected_types = self._selected_category_types()
        if selected_types is not None and event["event_type"] not in selected_types:
            return False

        selected_risk = self.risk_filter.currentData()
        if selected_risk is not None and event["risk_level"] != selected_risk:
            return False

        search_term = self.search_input.text().strip().casefold()
        if not search_term:
            return True
        searchable_text = " ".join((
            event.get("target_path") or "",
            event.get("source_path") or "",
            event.get("description") or "",
            event_type_label(event["event_type"]),
            event_details_summary(event),
        )).casefold()
        return search_term in searchable_text

    def _set_event_item_values(
        self,
        item: QTreeWidgetItem,
        event: dict,
    ) -> None:
        target_path = event.get("target_path") or ""
        source_path = event.get("source_path")
        if source_path:
            path_text = (
                f"{os.path.basename(source_path)} → "
                f"{os.path.basename(target_path)}"
            )
            path_tooltip = f"Kaynak: {source_path}\nHedef: {target_path}"
        else:
            path_text = os.path.basename(target_path) or target_path
            path_tooltip = target_path

        item.setData(0, Qt.ItemDataRole.UserRole, event)
        item.setText(0, format_tr_datetime(event["timestamp"]))
        item.setText(1, risk_label(event["risk_level"]))
        item.setData(
            1,
            Qt.ItemDataRole.UserRole + 1,
            event["risk_level"],
        )
        item.setText(2, event_type_label(event["event_type"]))
        item.setText(3, path_text)
        item.setIcon(
            3,
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon),
        )
        item.setToolTip(3, path_tooltip)
        path_font = item.font(3)
        available_families = set(QFontDatabase.families())
        for family in (
            "SF Mono",
            "Menlo",
            "Consolas",
            "DejaVu Sans Mono",
        ):
            if family in available_families:
                path_font.setFamily(family)
                break
        path_font.setPointSize(11)
        item.setFont(3, path_font)
        item.setText(4, event_details_summary(event))
        item.setToolTip(4, event_details_tooltip(event))
        item.setText(5, event.get("actor_name") or "Belirlenemedi")
        item.setToolTip(
            5,
            "Olay sırasında etkin olan kullanıcı hesabıdır; "
            "işlemi yapan kişiyi tek başına kanıtlamaz.",
        )
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)

    def _refresh_events(self) -> None:
        if self.current_session_id is None:
            all_events = []
        else:
            all_events = self.database.get_recent_events(
                limit=1000,
                session_id=self.current_session_id,
            )

        if self.event_view_tabs.currentIndex() == 0:
            self._refresh_timeline_events(all_events)
        else:
            self._refresh_grouped_events()

    def _refresh_timeline_events(self, all_events: list[dict]) -> None:
        scroll_bar = self.table.verticalScrollBar()
        previous_scroll_position = scroll_bar.value()
        was_at_top = previous_scroll_position <= scroll_bar.minimum() + 1
        live_follow = self.live_follow_button.isChecked()
        scroll_signal_blocker = QSignalBlocker(scroll_bar)
        selected_event_id = None
        current_item = self.table.currentItem()
        if current_item is not None and self._event_selection_is_manual:
            current_event = current_item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(current_event, dict):
                selected_event_id = current_event.get("id")

        events = [
            event for event in all_events if self._event_matches_filters(event)
        ]
        self.table.clear()
        self.table.setRootIsDecorated(False)

        if events:
            self.event_stack.setCurrentWidget(self.table)
        else:
            self.event_stack.setCurrentWidget(self.empty_state)
            if self.current_session_id is None:
                self.empty_title.setText("İzleme başlatılmadı")
                self.empty_description.setText(
                    "Dosya veya klasör seçerek başlayın."
                )
            elif all_events:
                self.empty_title.setText("Eşleşen olay bulunamadı")
                self.empty_description.setText(
                    "Olay türü, arama veya risk filtresini değiştirin."
                )
            else:
                self.empty_title.setText("Olay bekleniyor")
                self.empty_description.setText(
                    "İlk değişiklik burada görünecek."
                )

        item_to_select = None
        for event in events:
            item = QTreeWidgetItem(self.table)
            self._set_event_item_values(item, event)
            if event.get("id") == selected_event_id:
                item_to_select = item

        should_follow_latest = live_follow or (
            was_at_top and selected_event_id is None
        )
        if item_to_select is None and events and should_follow_latest:
            item_to_select = self.table.topLevelItem(0)
        if item_to_select is not None:
            blocker = QSignalBlocker(self.table)
            self.table.setCurrentItem(item_to_select)
            del blocker

        if should_follow_latest:
            scroll_bar.setValue(scroll_bar.minimum())
        else:
            scroll_bar.setValue(
                min(previous_scroll_position, scroll_bar.maximum())
            )
        del scroll_signal_blocker

        if len(events) == len(all_events):
            count_text = f"{len(events)} olay görüntüleniyor"
        else:
            count_text = f"{len(events)} / {len(all_events)} olay eşleşiyor"
        self.event_count_label.setText(count_text)

    def _refresh_grouped_events(self) -> None:
        scroll_bar = self.table.verticalScrollBar()
        previous_scroll_position = scroll_bar.value()
        was_at_top = previous_scroll_position <= scroll_bar.minimum() + 1
        live_follow = self.live_follow_button.isChecked()
        scroll_signal_blocker = QSignalBlocker(scroll_bar)
        self.table.setRootIsDecorated(True)
        expanded_targets = set()
        selected_event_id = None
        selected_item = self.table.currentItem()
        if selected_item is not None and self._event_selection_is_manual:
            selected_event = selected_item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(selected_event, dict):
                selected_event_id = selected_event.get("id")

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

        groups = []

        risk_scores = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        for stored_group in all_groups:
            matching_events = [
                event
                for event in self.database.get_events_for_target(
                    session_id=self.current_session_id,
                    target_path=stored_group["target_path"],
                    limit=200,
                )
                if self._event_matches_filters(event)
            ]
            if not matching_events:
                continue
            latest_event = matching_events[0]
            group = dict(stored_group)
            group.update({
                "id": latest_event["id"],
                "last_seen": latest_event["timestamp"],
                "event_type": latest_event["event_type"],
                "description": latest_event["description"],
                "actor_name": latest_event.get("actor_name"),
                "event_count": len(matching_events),
                "highest_risk": max(
                    (event["risk_level"] for event in matching_events),
                    key=risk_scores.get,
                ),
                "events": matching_events,
            })
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
                    "İzleme başlatılmadı"
                )
                self.empty_description.setText(
                    "Dosya veya klasör seçerek başlayın."
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
                    "Olay bekleniyor"
                )
                self.empty_description.setText(
                    "İlk değişiklik burada görünecek."
                )

        total_event_count = 0
        event_item_to_select = None

        for group in groups:
            target_path = group["target_path"] or ""
            target_name = (
                os.path.basename(target_path)
                or target_path
            )

            event_count = group["event_count"]
            total_event_count += event_count

            last_seen = format_tr_datetime(group["last_seen"])

            group_item = QTreeWidgetItem(
                self.table
            )

            group_item.setText(0, last_seen)
            group_item.setText(
                1,
                risk_label(group["highest_risk"]),
            )
            group_item.setData(
                1,
                Qt.ItemDataRole.UserRole + 1,
                group["highest_risk"],
            )
            group_item.setText(
                2,
                f"{event_count} olay",
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
                event_details_summary(group["events"][0]),
            )
            group_item.setText(5, "")

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
                event_details_tooltip(group["events"][0]),
            )
            group_item.setTextAlignment(
                1,
                Qt.AlignmentFlag.AlignCenter,
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

            events = group["events"]

            for event in events:
                event_item = QTreeWidgetItem(
                    group_item
                )
                self._set_event_item_values(event_item, event)

                if event.get("id") == selected_event_id:
                    event_item_to_select = event_item

            group_item.setExpanded(
                target_path in expanded_targets
                or group["event_type"] in {
                    "CLIPBOARD_COPY",
                    "CONTENT_CLIPBOARD_COPY",
                    "POSSIBLE_COPY",
                }
            )

        if event_item_to_select is not None:
            blocker = QSignalBlocker(self.table)
            self.table.setCurrentItem(event_item_to_select)
            del blocker

        should_follow_latest = live_follow or (
            was_at_top and selected_event_id is None
        )
        if should_follow_latest:
            scroll_bar.setValue(scroll_bar.minimum())
        else:
            scroll_bar.setValue(
                min(previous_scroll_position, scroll_bar.maximum())
            )
        del scroll_signal_blocker

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

    @Slot(QTreeWidgetItem, int)
    def _show_selected_event_details(
        self,
        current: QTreeWidgetItem | None,
        _column: int = 0,
    ) -> None:
        if current is None:
            self.event_inspector_dock.hide()
            return

        event = current.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(event, dict):
            self._event_selection_is_manual = False
            self.event_inspector_dock.hide()
            return

        self._disable_live_follow()
        self._event_selection_is_manual = True

        target_path = event.get("target_path") or "Belirlenemedi"
        target_name = os.path.basename(target_path) or target_path
        self.event_detail_title.setText(target_name)
        risk = event.get("risk_level", "LOW")
        self.event_detail_risk.setText(risk_label(risk))
        self.event_detail_risk.setStyleSheet(risk_badge_stylesheet(risk))
        self.event_detail_summary.setText(event_details_summary(event))
        self.event_detail_time.setText(
            format_tr_datetime(event.get("timestamp"))
        )
        self.event_detail_path.setText(target_path)
        self.event_detail_path.setToolTip(target_path)
        self.event_detail_change.setText(
            event_type_label(event["event_type"])
        )

        technical = event_technical_summary(event)
        self.event_detail_hash.setText(technical["hash"])
        context_parts = [
            f"Kullanıcı: {event.get('actor_name') or 'Belirlenemedi'}",
            f"Kimlik kaynağı: {event.get('actor_source') or 'Kaydedilmedi'}",
            f"Olay süreç PID'i: {technical['process_id']}",
        ]
        if event.get("source_path"):
            context_parts.append(f"Kaynak dosya: {event['source_path']}")
        self.event_detail_context.setText("\n".join(context_parts))
        self.event_inspector_dock.show()
        self.event_inspector_dock.raise_()

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

        # İzleme GUI'den bağımsız ajan sürecinde devam eder. Yalnızca
        # "İzlemeyi Durdur" düğmesi kalıcı çalışma isteğini sonlandırır.
        event.accept()


def start_gui() -> None:
    application = QApplication(sys.argv)
    application.setStyle("Fusion")
    application.setWindowIcon(yula_icon())
    application.setStyleSheet(APPLICATION_STYLESHEET)
    turkish_locale = QLocale(
        QLocale.Language.Turkish,
        QLocale.Country.Turkey,
    )
    QLocale.setDefault(turkish_locale)
    configure_application_font(application)

    window = YulaMainWindow()
    window.show()

    sys.exit(application.exec())
