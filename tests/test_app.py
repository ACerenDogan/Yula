import os
import tempfile
import unittest

os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSlider,
    QApplication,
)
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent

from yula.gui.app import (
    YulaMainWindow,
    configure_application_font,
)
from yula.storage.database import DatabaseManager


class FakeMonitoringService:
    def __init__(
        self,
        database,
        event_callback=None,
    ):
        self.database = database
        self.event_callback = event_callback
        self.is_running = False
        self.session_id = None
        self.targets = ()

    def start(self, targets):
        self.is_running = True
        self.session_id = 99
        self.targets = tuple(targets)
        return self.session_id

    def stop(self):
        self.is_running = False
        self.session_id = None
        self.targets = ()


class TestYulaMainWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = (
            QApplication.instance()
            or QApplication([])
        )
        configure_application_font(cls.application)

    def test_olay_tablosu_salt_okunurdur(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            window = YulaMainWindow(
                database=database,
                service_factory=FakeMonitoringService,
                show_startup_dialog=False,
            )

            self.assertEqual(
                window.table.editTriggers(),
                QAbstractItemView.EditTrigger.NoEditTriggers,
            )
            self.assertEqual(
                window.sidebar_status_label.text(),
                "SEÇİM BEKLENİYOR",
            )
            self.assertIs(
                window.event_stack.currentWidget(),
                window.empty_state,
            )
            self.assertEqual(
                window.empty_title.text(),
                "İzleme başlatılmadı",
            )
            self.assertTrue(window.sessions_dock.isHidden())
            self.assertEqual(window.live_follow_button.text(), "● Canlı")
            self.assertIn("Hedef seçilmedi", window.target_summary.text())

            window.close()

    def test_pencere_yula_simgesini_kullanir(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )
            window = YulaMainWindow(
                database=database,
                service_factory=FakeMonitoringService,
                show_startup_dialog=False,
            )
            try:
                self.assertFalse(window.windowIcon().isNull())
            finally:
                window.close()

    def test_yalnizca_secili_izleme_calismasini_gosterir(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            first_session = (
                database.create_monitoring_session([
                    {
                        "path": "/project/first.py",
                        "type": "FILE",
                    },
                ])
            )

            second_session = (
                database.create_monitoring_session([
                    {
                        "path": "/project/second.py",
                        "type": "FILE",
                    },
                ])
            )

            database.log_security_event(
                event_type="MODIFIED",
                risk_level="HIGH",
                target_path="/project/first.py",
                description="Birinci çalışma",
                session_id=first_session,
            )

            database.log_security_event(
                event_type="MODIFIED",
                risk_level="HIGH",
                target_path="/project/second.py",
                description="İkinci çalışma",
                session_id=second_session,
            )

            window = YulaMainWindow(
                database=database,
                service_factory=FakeMonitoringService,
                show_startup_dialog=False,
            )

            window.current_session_id = first_session
            window._refresh_events()

            self.assertEqual(
                window.table.topLevelItemCount(),
                1,
            )

            group_item = window.table.topLevelItem(0)

            self.assertIn(
                "Birinci çalışma",
                group_item.text(4),
            )
            self.assertEqual(
                group_item.text(1),
                "Yüksek",
            )
            self.assertEqual(
                group_item.text(2),
                "Değiştirildi",
            )

            low_risk_index = (
                window.risk_filter.findData("LOW")
            )
            window.risk_filter.setCurrentIndex(
                low_risk_index
            )

            self.assertEqual(
                window.table.topLevelItemCount(),
                0,
            )
            self.assertEqual(
                window.empty_title.text(),
                "Eşleşen olay bulunamadı",
            )

            high_risk_index = (
                window.risk_filter.findData("HIGH")
            )
            window.risk_filter.setCurrentIndex(
                high_risk_index
            )

            self.assertEqual(
                window.table.topLevelItemCount(),
                1,
            )

            window.search_input.setText("second.py")

            self.assertEqual(
                window.table.topLevelItemCount(),
                0,
            )

            window.close()

    def test_ayni_hedefin_olaylarini_tek_baslik_altinda_gosterir(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            target_path = "/project/app.py"

            session_id = database.create_monitoring_session([
                {
                    "path": target_path,
                    "type": "FILE",
                },
            ])

            database.log_security_event(
                event_type="MODIFIED",
                risk_level="HIGH",
                target_path=target_path,
                description="İlk değişiklik",
                session_id=session_id,
            )

            database.log_security_event(
                event_type="RESTORED",
                risk_level="LOW",
                target_path=target_path,
                description="Referans duruma döndü",
                session_id=session_id,
            )

            window = YulaMainWindow(
                database=database,
                service_factory=FakeMonitoringService,
                show_startup_dialog=False,
            )

            try:
                window.current_session_id = session_id
                window.event_view_tabs.setCurrentIndex(1)
                window._refresh_events()

                self.assertEqual(
                    window.table.topLevelItemCount(),
                    1,
                )

                group_item = window.table.topLevelItem(0)

                self.assertEqual(
                    group_item.text(3),
                    "app.py",
                )
                self.assertEqual(
                    group_item.childCount(),
                    2,
                )

            finally:
                window.close()

    def test_pencere_kapaninca_izlemeyi_durdurmaz(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(os.path.join(directory, "test.db"))
            window = YulaMainWindow(
                database=database,
                service_factory=FakeMonitoringService,
                show_startup_dialog=False,
            )
            window.service.is_running = True

            window.close()

            self.assertTrue(window.service.is_running)

    def test_calismalar_panelinden_gecmis_calisma_secilir(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(os.path.join(directory, "test.db"))
            first_session = database.create_monitoring_session([
                {"path": "/project/first.py", "type": "FILE"}
            ])
            database.set_monitoring_session_status(
                first_session,
                "STOPPED",
            )
            database.create_monitoring_session([
                {"path": "/project/second.py", "type": "FILE"}
            ])
            database.log_security_event(
                event_type="MODIFIED",
                risk_level="LOW",
                target_path="/project/first.py",
                description="İlk çalışmanın olayı",
                session_id=first_session,
            )
            window = YulaMainWindow(
                database=database,
                service_factory=FakeMonitoringService,
                show_startup_dialog=False,
            )

            try:
                self.assertEqual(window.sessions_list.count(), 2)
                first_item = next(
                    window.sessions_list.item(index)
                    for index in range(window.sessions_list.count())
                    if window.sessions_list.item(index).data(
                        Qt.ItemDataRole.UserRole
                    ) == first_session
                )
                window.sessions_list.setCurrentItem(first_item)

                self.assertEqual(window.current_session_id, first_session)
                self.assertEqual(
                    window.sidebar_status_label.text(),
                    "İZLEME DURDURULDU",
                )
                self.assertEqual(window.table.topLevelItemCount(), 1)
                self.assertRegex(
                    window.table.topLevelItem(0).text(0),
                    r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2}$",
                )
                self.assertEqual(
                    window.table.headerItem().text(5),
                    "Kullanıcı bağlamı*",
                )
            finally:
                window.close()

    def test_calismalar_paneli_periyodik_yenilemede_yukariya_sicramaz(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(os.path.join(directory, "test.db"))
            for index in range(30):
                database.create_monitoring_session([{
                    "path": f"/project/session-{index}.txt",
                    "type": "FILE",
                }])

            window = YulaMainWindow(
                database=database,
                service_factory=FakeMonitoringService,
                show_startup_dialog=False,
            )
            try:
                window.show()
                window.sessions_dock.show()
                self.application.processEvents()
                scroll_bar = window.sessions_list.verticalScrollBar()
                self.assertGreater(scroll_bar.maximum(), 0)
                scroll_bar.setValue(scroll_bar.maximum())
                expected_position = scroll_bar.value()

                window._periodic_refresh()
                self.application.processEvents()

                self.assertEqual(scroll_bar.value(), expected_position)
            finally:
                window.close()

    def test_icerik_kopyalama_ayrintisini_acikca_gosterir(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([{
                "path": "/project/notes.rtf",
                "type": "FILE",
            }])
            database.log_security_event(
                event_type="CONTENT_CLIPBOARD_COPY",
                risk_level="MEDIUM",
                target_path="/project/notes.rtf",
                description="Dosyadan seçili içerik panoya alındı: notes.rtf",
                session_id=session_id,
                actor_name="ceren",
                details={
                    "match_type": "PARTIAL_CONTENT",
                    "character_count": 42,
                    "clipboard_sha256": "a" * 64,
                    "raw_content_stored": False,
                },
                actor_source="CONSOLE_CONTEXT",
            )
            window = YulaMainWindow(
                database=database,
                service_factory=FakeMonitoringService,
                show_startup_dialog=False,
            )
            try:
                self.assertTrue(window.event_inspector_dock.isHidden())
                event_item = window.table.topLevelItem(0)
                window._show_selected_event_details(event_item, 0)
                self.assertFalse(window.event_inspector_dock.isHidden())
                self.assertEqual(window.event_detail_title.text(), "notes.rtf")
                self.assertEqual(
                    window.event_detail_change.text(),
                    "İçerik kopyalandı",
                )
                self.assertIn("42 karakter", window.event_detail_summary.text())
                self.assertIn(
                    "Yapıştırma hedefi henüz bilinmiyor",
                    window.event_detail_summary.text(),
                )
                self.assertIn("Pano:", window.event_detail_hash.text())
                self.assertIn(
                    "Olay süreç PID'i: Kaydedilmedi",
                    window.event_detail_context.text(),
                )
                self.assertEqual(
                    window.table.headerItem().text(2),
                    "Ne oldu?",
                )
            finally:
                window.close()

    def test_olay_listesi_manuel_scroll_ve_secimi_korur(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([{
                "path": "/project/events",
                "type": "DIRECTORY",
            }])
            for index in range(60):
                database.log_security_event(
                    event_type="MODIFIED",
                    risk_level="LOW",
                    target_path=f"/project/events/file-{index}.txt",
                    description=f"Olay {index}",
                    session_id=session_id,
                )

            window = YulaMainWindow(
                database=database,
                service_factory=FakeMonitoringService,
                show_startup_dialog=False,
            )
            try:
                window.show()
                self.application.processEvents()
                scroll_bar = window.table.verticalScrollBar()
                scroll_bar.setValue(scroll_bar.maximum() // 2)
                selected_item = window.table.topLevelItem(30)
                window.table.setCurrentItem(selected_item)
                window._show_selected_event_details(selected_item, 0)
                selected_event_id = selected_item.data(
                    0,
                    Qt.ItemDataRole.UserRole,
                )["id"]
                previous_scroll = scroll_bar.value()

                database.log_security_event(
                    event_type="CREATED",
                    risk_level="LOW",
                    target_path="/project/events/new.txt",
                    description="Yeni olay",
                    session_id=session_id,
                )
                window._refresh_events()
                self.application.processEvents()

                current_event = window.table.currentItem().data(
                    0,
                    Qt.ItemDataRole.UserRole,
                )
                self.assertEqual(scroll_bar.value(), previous_scroll)
                self.assertEqual(current_event["id"], selected_event_id)
            finally:
                window.close()

    def test_canli_takip_acikken_yeni_olaya_doner(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([{
                "path": "/project/events",
                "type": "DIRECTORY",
            }])
            for index in range(40):
                database.log_security_event(
                    event_type="MODIFIED",
                    risk_level="LOW",
                    target_path=f"/project/events/file-{index}.txt",
                    description=f"Olay {index}",
                    session_id=session_id,
                )

            window = YulaMainWindow(
                database=database,
                service_factory=FakeMonitoringService,
                show_startup_dialog=False,
            )
            try:
                window.show()
                self.application.processEvents()
                scroll_bar = window.table.verticalScrollBar()
                scroll_bar.setValue(scroll_bar.maximum())
                window.live_follow_button.setChecked(True)

                new_event_id = database.log_security_event(
                    event_type="CREATED",
                    risk_level="LOW",
                    target_path="/project/events/new.txt",
                    description="Yeni olay",
                    session_id=session_id,
                )
                window._refresh_events()
                self.application.processEvents()

                newest_event = window.table.topLevelItem(0).data(
                    0,
                    Qt.ItemDataRole.UserRole,
                )
                self.assertEqual(scroll_bar.value(), scroll_bar.minimum())
                self.assertEqual(newest_event["id"], new_event_id)

                wheel_event = QWheelEvent(
                    QPointF(10, 10),
                    QPointF(10, 10),
                    QPoint(0, 0),
                    QPoint(0, -120),
                    Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier,
                    Qt.ScrollPhase.ScrollUpdate,
                    False,
                )
                window.table.wheelEvent(wheel_event)
                self.assertFalse(window.live_follow_button.isChecked())
                self.assertEqual(
                    window.live_follow_button.text(),
                    "○ Duraklatıldı",
                )

                scroll_bar.setValue(scroll_bar.maximum())
                scroll_bar.setValue(scroll_bar.minimum())
                self.assertTrue(window.live_follow_button.isChecked())
                self.assertEqual(window.live_follow_button.text(), "● Canlı")

                scroll_bar.triggerAction(
                    QAbstractSlider.SliderAction.SliderPageStepAdd
                )
                self.assertFalse(window.live_follow_button.isChecked())
            finally:
                window.close()

    def test_olay_tablosu_sutunlari_oransal_ve_yatay_scrollsizdir(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([{
                "path": "/project/events",
                "type": "DIRECTORY",
            }])
            database.log_security_event(
                event_type="MODIFIED",
                risk_level="HIGH",
                target_path="/project/events/a-very-long-file-name.py",
                description="Uzun olay ayrıntısı " * 12,
                session_id=session_id,
            )
            window = YulaMainWindow(
                database=database,
                service_factory=FakeMonitoringService,
                show_startup_dialog=False,
            )
            try:
                window.resize(1200, 720)
                window.show()
                self.application.processEvents()
                window.table.apply_column_widths()

                self.assertEqual(window.table.columnWidth(0), 140)
                self.assertEqual(window.table.columnWidth(1), 110)
                self.assertEqual(window.table.columnWidth(2), 90)
                self.assertGreaterEqual(window.table.columnWidth(3), 200)
                self.assertGreater(
                    window.table.columnWidth(4),
                    window.table.columnWidth(3),
                )
                self.assertEqual(window.table.columnWidth(5), 120)
                self.assertEqual(
                    window.table.horizontalScrollBar().maximum(),
                    0,
                )
            finally:
                window.close()

    def test_kopyalamalari_ayri_ve_duz_liste_gosterir(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([{
                "path": "/project/notes.txt",
                "type": "FILE",
            }])
            database.log_security_event(
                event_type="MODIFIED",
                risk_level="LOW",
                target_path="/project/notes.txt",
                description="Dosya değişti",
                session_id=session_id,
            )
            for length in (20, 40):
                database.log_security_event(
                    event_type="CONTENT_CLIPBOARD_COPY",
                    risk_level="MEDIUM",
                    target_path="/project/notes.txt",
                    description="İçerik kopyalandı",
                    session_id=session_id,
                    details={
                        "match_type": "PARTIAL_CONTENT",
                        "character_count": length,
                        "raw_content_stored": False,
                    },
                )

            window = YulaMainWindow(
                database=database,
                service_factory=FakeMonitoringService,
                show_startup_dialog=False,
            )
            try:
                window._set_event_category("COPIES")

                self.assertEqual(window.table.topLevelItemCount(), 2)
                for index in range(window.table.topLevelItemCount()):
                    item = window.table.topLevelItem(index)
                    self.assertEqual(item.text(2), "İçerik kopyalandı")
                    self.assertEqual(item.childCount(), 0)
                self.assertEqual(
                    window.event_filter_actions["COPIES"].text(),
                    "Kopyalamalar",
                )
            finally:
                window.close()

    def test_dosya_ozeti_risk_ile_son_olayi_birbirine_karistirmaz(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([{
                "path": "/project/notes.txt",
                "type": "FILE",
            }])
            database.log_security_event(
                event_type="CONTENT_CLIPBOARD_COPY",
                risk_level="MEDIUM",
                target_path="/project/notes.txt",
                description="İçerik kopyalandı",
                session_id=session_id,
            )
            database.log_security_event(
                event_type="DELETED",
                risk_level="LOW",
                target_path="/project/notes.txt",
                description="Dosya silindi",
                session_id=session_id,
            )
            window = YulaMainWindow(
                database=database,
                service_factory=FakeMonitoringService,
                show_startup_dialog=False,
            )
            try:
                window.event_view_tabs.setCurrentIndex(1)
                summary = window.table.topLevelItem(0)

                self.assertEqual(summary.text(1), "Orta")
                self.assertEqual(summary.text(2), "2 olay")
                self.assertEqual(summary.text(5), "")
                self.assertNotIn(
                    "Ayrıntıları görmek için",
                    summary.text(4),
                )
                self.assertNotEqual(summary.text(2), "Silindi")
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
