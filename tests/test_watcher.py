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
from yula.core.watcher import YulaFileEventHandler


class FakeDatabase:
    def __init__(self):
        self.events = []

    def log_security_event(self, event_type, risk_level, target_path, description,session_id=None):
        self.events.append(
            {
                "event_type": event_type,
                "risk_level": risk_level,
                "target_path": target_path,
                "description": description,
                "session_id": session_id,
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


if __name__ == "__main__":
    unittest.main()