import os
import tempfile
import unittest

from yula.storage.database import DatabaseManager


class TestDatabaseManager(unittest.TestCase):
    def test_baglanti_foreign_key_kontrolunu_etkinlestirir(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "test.db")
            database = DatabaseManager(database_path)

            with database._get_connection() as connection:
                foreign_keys_enabled = connection.execute(
                    "PRAGMA foreign_keys"
                ).fetchone()[0]

            self.assertEqual(foreign_keys_enabled, 1)

    def test_oturum_tablolarini_ve_event_baglantisini_olusturur(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "test.db")
            database = DatabaseManager(database_path)

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

            self.assertIn("monitoring_sessions", table_names)
            self.assertIn("session_targets", table_names)
            self.assertIn("session_id", event_columns)

    def test_olay_kaydi_id_dondurur_ve_milisaniye_saklar(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "test.db")
            database = DatabaseManager(database_path)

            event_id = database.log_security_event(
                event_type="MODIFIED",
                risk_level="HIGH",
                target_path="/project/app.py",
                description="İçerik değişti",
            )

            event = database.get_recent_events(limit=1)[0]

            self.assertEqual(event_id, event["id"])
            self.assertIn("T", event["timestamp"])
            self.assertIn(".", event["timestamp"])
            self.assertIsNone(event["session_id"])


if __name__ == "__main__":
    unittest.main()