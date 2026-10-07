import os
import tempfile
import unittest

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

from yula.core.hasher import calculate_sha256
from yula.core.file_snapshot import capture_file_snapshot
from yula.core.watcher import YulaFileEventHandler


class FakeDatabase:
    def __init__(self):
        self.events = []

    def log_security_event(
        self,
        event_type,
        risk_level,
        target_path,
        description,
        session_id=None,
        source_path=None,
        details=None,
        actor_name=None,
        actor_source=None,
    ):
        self.events.append(
            {
                "event_type": event_type,
                "risk_level": risk_level,
                "target_path": target_path,
                "description": description,
                "session_id": session_id,
                "source_path": source_path,
                "details": details,
                "actor_name": actor_name,
                "actor_source": actor_source,
            }
        )
        return len(self.events)


class TestYulaFileEventHandler(unittest.TestCase):
    def test_gercek_icerik_degisikligini_kaydeder_tekrar_bildirimi_atlar(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "app.py")
            with open(path, "w", encoding="utf-8") as file:
                file.write("trusted")
            baseline_hash = calculate_sha256(path)
            db = FakeDatabase()
            handler = YulaFileEventHandler({path: baseline_hash}, db, [path])

            with open(path, "w", encoding="utf-8") as file:
                file.write("changed")
            event = FileModifiedEvent(path)
            handler.on_modified(event)
            handler.on_modified(event)

            self.assertEqual(len(db.events), 1)
            self.assertEqual(db.events[0]["event_type"], "MODIFIED")
            self.assertEqual(db.events[0]["risk_level"], "HIGH")

    def test_baseline_icerigine_donusu_restored_olarak_kaydeder(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "app.py")
            with open(path, "w", encoding="utf-8") as file:
                file.write("trusted")
            baseline_hash = calculate_sha256(path)
            db = FakeDatabase()
            handler = YulaFileEventHandler({path: baseline_hash}, db, [path])

            with open(path, "w", encoding="utf-8") as file:
                file.write("changed")
            handler.on_modified(FileModifiedEvent(path))
            with open(path, "w", encoding="utf-8") as file:
                file.write("trusted")
            handler.on_modified(FileModifiedEvent(path))

            self.assertEqual(
                [event["event_type"] for event in db.events],
                ["MODIFIED", "RESTORED"],
            )

    def test_silinen_baseline_dosyasinin_geri_gelmesini_algilar(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "app.py")
            with open(path, "w", encoding="utf-8") as file:
                file.write("trusted")
            baseline_hash = calculate_sha256(path)
            db = FakeDatabase()
            handler = YulaFileEventHandler({path: baseline_hash}, db, [path])

            os.remove(path)
            handler.on_deleted(FileDeletedEvent(path))
            with open(path, "w", encoding="utf-8") as file:
                file.write("trusted")
            handler.on_created(FileCreatedEvent(path))

            self.assertEqual(
                [event["event_type"] for event in db.events],
                ["DELETED", "RESTORED"],
            )

    def test_editorun_atomik_kaydini_tasima_degil_degisiklik_sayar(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "app.py")
            temporary_path = os.path.join(directory, "app.py.tmp")
            with open(path, "w", encoding="utf-8") as file:
                file.write("trusted")
            baseline_hash = calculate_sha256(path)
            db = FakeDatabase()
            handler = YulaFileEventHandler({path: baseline_hash}, db, [directory])

            with open(temporary_path, "w", encoding="utf-8") as file:
                file.write("changed")
            os.replace(temporary_path, path)
            handler.on_moved(FileMovedEvent(temporary_path, path))

            self.assertEqual(len(db.events), 1)
            self.assertEqual(db.events[0]["event_type"], "MODIFIED")
            self.assertEqual(db.events[0]["risk_level"], "HIGH")

    def test_olayi_izleme_oturumuna_baglar(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "app.py")

            with open(path, "w", encoding="utf-8") as file:
                file.write("trusted")

            baseline_hash = calculate_sha256(path)
            database = FakeDatabase()

            handler = YulaFileEventHandler(
                baseline_data={path: baseline_hash},
                db=database,
                targets=[path],
                session_id=42,
            )

            with open(path, "w", encoding="utf-8") as file:
                file.write("changed")

            handler.on_modified(
                FileModifiedEvent(path)
            )

            self.assertEqual(
                len(database.events),
                1,
            )
            self.assertEqual(
                database.events[0]["session_id"],
                42,
            )

    def test_yalnizca_izin_degisikligini_guvenlik_olayi_yapar(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.conf")
            with open(path, "w", encoding="utf-8") as file:
                file.write("trusted")

            os.chmod(path, 0o600)
            baseline = capture_file_snapshot(path)
            database = FakeDatabase()
            handler = YulaFileEventHandler(
                {path: baseline},
                database,
                [path],
            )

            os.chmod(path, 0o666)
            handler.on_modified(FileModifiedEvent(path))
            handler.on_modified(FileModifiedEvent(path))

            self.assertEqual(len(database.events), 1)
            self.assertEqual(
                database.events[0]["event_type"],
                "PERMISSIONS_CHANGED",
            )
            self.assertEqual(
                database.events[0]["risk_level"],
                "HIGH",
            )
            self.assertIn("600 → 666", database.events[0]["description"])

    def test_symlink_hedef_degisikligini_ayri_olay_yapar(self):
        with tempfile.TemporaryDirectory() as directory:
            first_target = os.path.join(directory, "first.txt")
            second_target = os.path.join(directory, "second.txt")
            link_path = os.path.join(directory, "current")

            for path in (first_target, second_target):
                with open(path, "w", encoding="utf-8") as file:
                    file.write(path)

            os.symlink(first_target, link_path)
            baseline = capture_file_snapshot(link_path)
            database = FakeDatabase()
            handler = YulaFileEventHandler(
                {link_path: baseline},
                database,
                [link_path],
            )

            os.unlink(link_path)
            os.symlink(second_target, link_path)
            handler.on_modified(FileModifiedEvent(link_path))

            self.assertEqual(len(database.events), 1)
            self.assertEqual(
                database.events[0]["event_type"],
                "SYMLINK_CHANGED",
            )
            self.assertEqual(
                database.events[0]["risk_level"],
                "HIGH",
            )

    def test_ayni_icerikle_olusturulan_dosyayi_olasi_kopya_sayar(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = os.path.join(directory, "source.txt")
            destination_path = os.path.join(directory, "copy.txt")

            with open(source_path, "w", encoding="utf-8") as file:
                file.write("same content")

            baseline = {source_path: capture_file_snapshot(source_path)}
            database = FakeDatabase()
            handler = YulaFileEventHandler(
                baseline,
                database,
                [directory],
            )

            with open(destination_path, "w", encoding="utf-8") as file:
                file.write("same content")
            handler.on_created(FileCreatedEvent(destination_path))

            self.assertEqual(len(database.events), 1)
            self.assertEqual(
                database.events[0]["event_type"],
                "POSSIBLE_COPY",
            )
            self.assertEqual(
                database.events[0]["source_path"],
                source_path,
            )
            self.assertEqual(
                database.events[0]["target_path"],
                destination_path,
            )


if __name__ == "__main__":
    unittest.main()
