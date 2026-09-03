import os
import tempfile
import unittest

from yula.storage.database import DatabaseManager


class TestDatabaseManager(unittest.TestCase):
    def test_baglanti_foreign_key_kontrolunu_etkinlestirir(self):
        with tempfile.TemporaryDirectory() as directory:
            db = DatabaseManager(os.path.join(directory, "test.db"))
            with db._get_connection() as connection:
                enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]

            self.assertEqual(enabled, 1)

    def test_olay_kaydi_id_dondurur_ve_milisaniye_saklar(self):
        with tempfile.TemporaryDirectory() as directory:
            db = DatabaseManager(os.path.join(directory, "test.db"))

            event_id = db.log_security_event(
                "MODIFIED",
                "HIGH",
                "/project/app.py",
                "İçerik değişti",
            )
            event = db.get_recent_events(limit=1)[0]

            self.assertEqual(event_id, event["id"])
            self.assertIn("T", event["timestamp"])
            self.assertIn(".", event["timestamp"])


if __name__ == "__main__":
    unittest.main()
