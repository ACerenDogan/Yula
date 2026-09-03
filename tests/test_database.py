import os
import tempfile
import unittest

from yula.storage.database import DatabaseManager


class TestDatabaseManager(unittest.TestCase):
    def test_baglanti_foreign_key_kontrolunu_etkinlestirir(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            with database._get_connection() as connection:
                foreign_keys_enabled = connection.execute(
                    "PRAGMA foreign_keys"
                ).fetchone()[0]

            self.assertEqual(foreign_keys_enabled, 1)

    def test_oturum_tablolarini_ve_event_baglantisini_olusturur(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            with database._get_connection() as connection:
                table_names = {
                    row["name"]
                    for row in connection.execute("""
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'table'
                    """).fetchall()
                }

                event_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(security_events)"
                    ).fetchall()
                }

            self.assertIn(
                "monitoring_sessions",
                table_names,
            )
            self.assertIn(
                "session_targets",
                table_names,
            )
            self.assertIn(
                "session_id",
                event_columns,
            )

    def test_oturum_ve_hedefleri_kaydeder(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            file_path = os.path.join(
                directory,
                "app.py",
            )
            folder_path = os.path.join(
                directory,
                "config",
            )

            session_id = database.create_monitoring_session([
                {
                    "path": file_path,
                    "type": "FILE",
                },
                {
                    "path": folder_path,
                    "type": "DIRECTORY",
                },
            ])

            session = database.get_monitoring_session(
                session_id
            )

            self.assertIsNotNone(session)
            self.assertEqual(
                session["status"],
                "PREPARING",
            )
            self.assertIsNone(
                session["stopped_at"]
            )
            self.assertEqual(
                len(session["targets"]),
                2,
            )
            self.assertEqual(
                session["targets"][0]["target_path"],
                os.path.abspath(file_path),
            )
            self.assertEqual(
                session["targets"][0]["target_type"],
                "FILE",
            )

    def test_oturum_durum_gecislerini_kontrol_eder(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            session_id = database.create_monitoring_session([
                {
                    "path": "/project",
                    "type": "DIRECTORY",
                },
            ])

            database.set_monitoring_session_status(
                session_id,
                "RUNNING",
            )

            running_session = (
                database.get_monitoring_session(
                    session_id
                )
            )

            self.assertEqual(
                running_session["status"],
                "RUNNING",
            )
            self.assertIsNone(
                running_session["stopped_at"]
            )

            database.set_monitoring_session_status(
                session_id,
                "STOPPED",
            )

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

            with self.assertRaises(ValueError):
                database.set_monitoring_session_status(
                    session_id,
                    "RUNNING",
                )

    def test_gecersiz_hedef_ve_bos_secim_reddedilir(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            with self.assertRaises(ValueError):
                database.create_monitoring_session([])

            with self.assertRaises(ValueError):
                database.create_monitoring_session([
                    {
                        "path": "/project",
                        "type": "UNKNOWN",
                    },
                ])

    def test_olayi_oturuma_bagli_kaydeder(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            session_id = database.create_monitoring_session([
                {
                    "path": "/project/app.py",
                    "type": "FILE",
                },
            ])

            event_id = database.log_security_event(
                event_type="MODIFIED",
                risk_level="HIGH",
                target_path="/project/app.py",
                description="İçerik değişti",
                session_id=session_id,
            )

            events = database.get_recent_events(
                limit=10,
                session_id=session_id,
            )

            self.assertEqual(len(events), 1)
            self.assertEqual(
                events[0]["id"],
                event_id,
            )
            self.assertEqual(
                events[0]["session_id"],
                session_id,
            )
            self.assertIn(
                "T",
                events[0]["timestamp"],
            )
            self.assertIn(
                ".",
                events[0]["timestamp"],
            )


if __name__ == "__main__":
    unittest.main()