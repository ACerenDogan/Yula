import os
import tempfile
import unittest

os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
)

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
                window.status_badge.text(),
                "SEÇİM BEKLENİYOR",
            )
            self.assertIs(
                window.event_stack.currentWidget(),
                window.empty_state,
            )
            self.assertEqual(
                window.empty_title.text(),
                "İzleme henüz başlamadı",
            )

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


if __name__ == "__main__":
    unittest.main()
