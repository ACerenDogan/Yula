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

from yula.gui.app import YulaMainWindow
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
                window.table.rowCount(),
                1,
            )
            self.assertEqual(
                window.table.item(0, 4).text(),
                "Birinci çalışma",
            )

            window.close()


if __name__ == "__main__":
    unittest.main()