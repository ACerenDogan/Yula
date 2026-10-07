import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta

from yula.storage.database import DatabaseManager


class TestDatabaseManager(unittest.TestCase):

    def test_eski_baseline_zamanini_nanosaniyeye_cevirir(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )
            monitored_file = os.path.join(
                directory,
                "legacy.txt",
            )

            path_id = database.add_monitored_path(directory)
            database.save_baseline_records(
                path_id,
                {
                    monitored_file: {
                        "hash": "legacy-hash",
                        "size": 10,
                        "last_modified": "1765538916.28403",
                    }
                },
            )

            snapshots = (
                database.get_baseline_snapshots_for_targets(
                    [directory]
                )
            )

            self.assertEqual(
                snapshots[monitored_file]["last_modified"],
                1765538916284030000,
            )
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

    def test_ayni_hedefin_olaylarini_gruplar(self):
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
                risk_level="LOW",
                target_path=target_path,
                description="İlk değişiklik",
                session_id=session_id,
            )

            database.log_security_event(
                event_type="MODIFIED",
                risk_level="HIGH",
                target_path=target_path,
                description="Kritik değişiklik",
                session_id=session_id,
            )

            database.log_security_event(
                event_type="RESTORED",
                risk_level="LOW",
                target_path=target_path,
                description="Baseline durumuna döndü",
                session_id=session_id,
            )

            groups = database.get_event_groups(
                session_id=session_id
            )

            self.assertEqual(len(groups), 1)
            self.assertEqual(
                groups[0]["target_path"],
                target_path,
            )
            self.assertEqual(
                groups[0]["event_count"],
                3,
            )
            self.assertEqual(
                groups[0]["highest_risk"],
                "HIGH",
            )
            self.assertEqual(
                groups[0]["event_type"],
                "RESTORED",
            )
            self.assertEqual(
                groups[0]["description"],
                "Baseline durumuna döndü",
            )

            events = database.get_events_for_target(
                session_id=session_id,
                target_path=target_path,
            )

            self.assertEqual(len(events), 3)

    def test_gruplar_farkli_izleme_calismalarini_karistirmaz(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            target_path = "/project/app.py"

            first_session = (
                database.create_monitoring_session([
                    {
                        "path": target_path,
                        "type": "FILE",
                    },
                ])
            )

            second_session = (
                database.create_monitoring_session([
                    {
                        "path": target_path,
                        "type": "FILE",
                    },
                ])
            )

            database.log_security_event(
                event_type="MODIFIED",
                risk_level="HIGH",
                target_path=target_path,
                description="Birinci çalışma",
                session_id=first_session,
            )

            database.log_security_event(
                event_type="RESTORED",
                risk_level="LOW",
                target_path=target_path,
                description="İkinci çalışma",
                session_id=second_session,
            )

            first_groups = database.get_event_groups(
                session_id=first_session
            )

            self.assertEqual(len(first_groups), 1)
            self.assertEqual(
                first_groups[0]["description"],
                "Birinci çalışma",
            )
    @unittest.skipIf(
        os.name == "nt",
        "Unix dosya izinleri Windows üzerinde uygulanmaz.",
    )
    def test_veritabani_dosyasini_sadece_sahibine_acar(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(
                directory,
                "test.db",
            )

            DatabaseManager(database_path)

            file_mode = stat.S_IMODE(
                os.stat(database_path).st_mode
            )

            self.assertEqual(
                file_mode,
                0o600,
            )

    def test_sembolik_baglanti_uzerinden_veritabani_acmaz(self):
        with tempfile.TemporaryDirectory() as directory:
            real_database_path = os.path.join(
                directory,
                "real.db",
            )
            linked_database_path = os.path.join(
                directory,
                "linked.db",
            )

            DatabaseManager(real_database_path)

            os.symlink(
                real_database_path,
                linked_database_path,
            )

            with self.assertRaises(ValueError):
                DatabaseManager(
                    linked_database_path
                )

    def test_gecersiz_guvenlik_olaylarini_reddeder(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(
                os.path.join(directory, "test.db")
            )

            invalid_events = [
                {
                    "event_type": "UNKNOWN",
                    "risk_level": "HIGH",
                    "target_path": "/project/app.py",
                    "description": "Geçersiz olay türü",
                },
                {
                    "event_type": "MODIFIED",
                    "risk_level": "CRITICAL",
                    "target_path": "/project/app.py",
                    "description": "Geçersiz risk seviyesi",
                },
                {
                    "event_type": "MODIFIED",
                    "risk_level": "HIGH",
                    "target_path": "   ",
                    "description": "Boş hedef",
                },
                {
                    "event_type": "MODIFIED",
                    "risk_level": "HIGH",
                    "target_path": "/project/app.py",
                    "description": "   ",
                },
            ]

            for invalid_event in invalid_events:
                with self.subTest(
                    invalid_event=invalid_event
                ):
                    with self.assertRaises(ValueError):
                        database.log_security_event(
                            **invalid_event
                        )

            self.assertEqual(
                database.get_recent_events(),
                [],
            )

    def test_olay_ayrintilarini_ve_kaynak_yolunu_saklar(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([
                {"path": directory, "type": "DIRECTORY"}
            ])

            database.log_security_event(
                event_type="POSSIBLE_COPY",
                risk_level="LOW",
                target_path=os.path.join(directory, "copy.txt"),
                source_path=os.path.join(directory, "source.txt"),
                description="Olası kopya",
                details={"detection": "HASH_MATCH"},
                actor_name="ceren",
                actor_source="CONSOLE_CONTEXT",
                session_id=session_id,
            )

            event = database.get_recent_events(session_id=session_id)[0]
            self.assertEqual(event["actor_name"], "ceren")
            self.assertEqual(event["actor_source"], "CONSOLE_CONTEXT")
            self.assertTrue(event["source_path"].endswith("source.txt"))
            self.assertIn("HASH_MATCH", event["details_json"])

    def test_tarih_saat_araligindaki_olaylari_getirir(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([
                {"path": directory, "type": "DIRECTORY"}
            ])
            before = datetime.now() - timedelta(seconds=1)
            database.log_security_event(
                event_type="CREATED",
                risk_level="LOW",
                target_path=os.path.join(directory, "new.txt"),
                description="Yeni dosya",
                session_id=session_id,
            )
            after = datetime.now() + timedelta(seconds=1)

            events = database.get_events_in_range(before, after)

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "CREATED")

            with self.assertRaises(ValueError):
                database.get_events_in_range(after, before)

    def test_izleme_calismalarini_hedefleri_ve_olay_sayisiyla_listeler(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(os.path.join(directory, "test.db"))
            first_session = database.create_monitoring_session([
                {"path": "/project/first.py", "type": "FILE"}
            ])
            second_session = database.create_monitoring_session([
                {"path": "/project/second", "type": "DIRECTORY"}
            ])
            database.log_security_event(
                event_type="MODIFIED",
                risk_level="LOW",
                target_path="/project/first.py",
                description="Değişiklik",
                session_id=first_session,
            )

            sessions = database.list_monitoring_sessions()

            self.assertEqual(
                [session["id"] for session in sessions],
                [second_session, first_session],
            )
            self.assertEqual(sessions[0]["event_count"], 0)
            self.assertEqual(sessions[1]["event_count"], 1)
            self.assertEqual(
                sessions[1]["targets"][0]["target_path"],
                "/project/first.py",
            )


if __name__ == "__main__":
    unittest.main()
