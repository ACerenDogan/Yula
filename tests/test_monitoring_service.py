import os
import tempfile
import unittest

from yula.application.monitoring_service import (
    MonitoringService,
)
from yula.storage.database import DatabaseManager


class FakeWatcher:
    """Testlerde gerçek filesystem thread'i başlatmaz."""

    latest_instance = None

    def __init__(
        self,
        targets,
        baseline_data,
        db,
        event_callback=None,
        session_id=None,
    ):
        self.targets = targets
        self.baseline_data = baseline_data
        self.database = db
        self.event_callback = event_callback
        self.session_id = session_id

        self.started = False
        self.stopped = False

        FakeWatcher.latest_instance = self

    @property
    def is_running(self):
        return self.started and not self.stopped

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class FailingWatcher(FakeWatcher):
    """Watcher başlatma hatasını test eder."""

    def start(self):
        raise RuntimeError(
            "Watcher başlatılamadı."
        )


class TestMonitoringService(unittest.TestCase):
    def test_izleme_calismasini_baslatir_ve_durdurur(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            watched_file = os.path.join(
                directory,
                "app.py",
            )

            with open(
                watched_file,
                "w",
                encoding="utf-8",
            ) as file:
                file.write("trusted")

            service = MonitoringService(
                database=database,
                watcher_factory=FakeWatcher,
            )

            session_id = service.start([
                watched_file
            ])

            session = database.get_monitoring_session(
                session_id
            )

            self.assertEqual(
                session["status"],
                "RUNNING",
            )
            self.assertTrue(
                service.is_running
            )
            self.assertEqual(
                service.session_id,
                session_id,
            )
            self.assertEqual(
                FakeWatcher.latest_instance.session_id,
                session_id,
            )
            self.assertIn(
                watched_file,
                FakeWatcher.latest_instance.baseline_data,
            )

            service.stop()

            stopped_session = (
                database.get_monitoring_session(
                    session_id
                )
            )

            self.assertEqual(
                stopped_session["status"],
                "STOPPED",
            )
            self.assertIsNotNone(
                stopped_session["stopped_at"]
            )
            self.assertFalse(
                service.is_running
            )
            self.assertIsNone(
                service.session_id
            )

    def test_ayni_anda_ikinci_izlemeyi_baslatmaz(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            watched_file = os.path.join(
                directory,
                "app.py",
            )

            with open(
                watched_file,
                "w",
                encoding="utf-8",
            ) as file:
                file.write("trusted")

            service = MonitoringService(
                database=database,
                watcher_factory=FakeWatcher,
            )

            service.start([
                watched_file
            ])

            with self.assertRaises(RuntimeError):
                service.start([
                    watched_file
                ])

            service.stop()

    def test_bulunmayan_hedefi_reddeder(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            missing_path = os.path.join(
                directory,
                "missing.py",
            )

            service = MonitoringService(
                database=database,
                watcher_factory=FakeWatcher,
            )

            with self.assertRaises(FileNotFoundError):
                service.start([
                    missing_path
                ])

            with database._get_connection() as connection:
                session_count = connection.execute("""
                    SELECT COUNT(*)
                    FROM monitoring_sessions
                """).fetchone()[0]

            self.assertEqual(
                session_count,
                0,
            )

    def test_watcher_baslatilamazsa_oturumu_error_yapar(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            watched_file = os.path.join(
                directory,
                "app.py",
            )

            with open(
                watched_file,
                "w",
                encoding="utf-8",
            ) as file:
                file.write("trusted")

            service = MonitoringService(
                database=database,
                watcher_factory=FailingWatcher,
            )

            with self.assertRaises(RuntimeError):
                service.start([
                    watched_file
                ])

            with database._get_connection() as connection:
                session = connection.execute("""
                    SELECT *
                    FROM monitoring_sessions
                    ORDER BY id DESC
                    LIMIT 1
                """).fetchone()

            self.assertIsNotNone(
                session
            )
            self.assertEqual(
                session["status"],
                "ERROR",
            )


if __name__ == "__main__":
    unittest.main()