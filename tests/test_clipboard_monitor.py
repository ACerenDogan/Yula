import os
import shutil
import sys
import tempfile
import unittest

from yula.core.clipboard_monitor import ClipboardFileMonitor
from yula.core.scanner import scan_targets
from yula.storage.database import DatabaseManager
 
class FakeSignal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback

    def emit(self):
        if self.callback is not None:
            self.callback()


class FakeUrl:
    def __init__(self, path):
        self.path = path

    def isLocalFile(self):
        return True

    def toLocalFile(self):
        return self.path


class FakeMimeData:
    def __init__(self, paths=None, text=None):
        self.paths = paths or []
        self.copied_text = text

    def hasUrls(self):
        return bool(self.paths)

    def urls(self):
        return [FakeUrl(path) for path in self.paths]

    def hasText(self):
        return self.copied_text is not None

    def text(self):
        return self.copied_text or ""


class FakeClipboard:
    def __init__(self):
        self.changed = FakeSignal()
        self.paths = []
        self.text = None

    def mimeData(self):
        return FakeMimeData(self.paths, self.text)

    def copy_files(self, paths):
        self.paths = paths
        self.text = None
        self.changed.emit()

    def copy_text(self, text):
        self.paths = []
        self.text = text
        self.changed.emit()


class TestClipboardFileMonitor(unittest.TestCase):
    def test_cmd_c_ile_dosyanin_panoya_kopyalanmasini_kaydeder(self):
        with tempfile.TemporaryDirectory() as directory:
            watched_file = os.path.join(directory, "app.py")
            with open(watched_file, "w", encoding="utf-8") as file:
                file.write("print('hello')")

            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([
                {"path": watched_file, "type": "FILE"}
            ])
            clipboard = FakeClipboard()
            monitor = ClipboardFileMonitor(
                clipboard,
                database,
                [watched_file],
                session_id,
            )

            self.assertEqual(monitor.poll(), [])
            clipboard.copy_files([watched_file])
            event_ids = monitor.poll()

            self.assertEqual(len(event_ids), 1)
            event = database.get_recent_events(1, session_id)[0]
            self.assertEqual(event["event_type"], "CLIPBOARD_COPY")
            self.assertEqual(event["target_path"], watched_file)
            self.assertIn("yapıştırma hedefi henüz bilinmiyor", event["description"])

    def test_izleme_disindaki_dosyayi_kaydetmez(self):
        with tempfile.TemporaryDirectory() as directory:
            watched_directory = os.path.join(directory, "watched")
            outside_file = os.path.join(directory, "outside.txt")
            os.mkdir(watched_directory)
            with open(outside_file, "w", encoding="utf-8") as file:
                file.write("outside")

            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([
                {"path": watched_directory, "type": "DIRECTORY"}
            ])
            clipboard = FakeClipboard()
            monitor = ClipboardFileMonitor(
                clipboard,
                database,
                [watched_directory],
                session_id,
            )

            monitor.poll()
            clipboard.copy_files([outside_file])
            self.assertEqual(monitor.poll(), [])
            self.assertEqual(database.get_recent_events(1, session_id), [])

    def test_dosya_icinden_kopyalanan_metni_icerigi_saklamadan_kaydeder(self):
        with tempfile.TemporaryDirectory() as directory:
            watched_file = os.path.join(directory, "notes.txt")
            copied_text = "yalnızca seçilen önemli güvenlik satırı"
            with open(watched_file, "w", encoding="utf-8") as file:
                file.write(f"başlangıç\n{copied_text}\nbitiş")

            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([
                {"path": watched_file, "type": "FILE"}
            ])
            path_id = database.add_monitored_path(watched_file)
            database.save_baseline_records(path_id, scan_targets([watched_file]))

            clipboard = FakeClipboard()
            monitor = ClipboardFileMonitor(
                clipboard,
                database,
                [watched_file],
                session_id,
            )

            monitor.poll()
            clipboard.copy_text(copied_text)
            event_ids = monitor.poll()

            self.assertEqual(len(event_ids), 1)
            event = database.get_recent_events(1, session_id)[0]
            self.assertEqual(event["event_type"], "CONTENT_CLIPBOARD_COPY")
            self.assertEqual(event["target_path"], watched_file)
            self.assertNotIn(copied_text, event["details_json"])
            self.assertIn('"raw_content_stored": false', event["details_json"])

    @unittest.skipUnless(
        sys.platform == "darwin" and shutil.which("textutil"),
        "macOS RTF içerik testi",
    )
    def test_rtf_belgesinden_kopyalanan_icerigi_kaydeder(self):
        with tempfile.TemporaryDirectory() as directory:
            watched_file = os.path.join(directory, "notes.rtf")
            copied_text = "RTF document copied content"
            with open(watched_file, "w", encoding="ascii") as file:
                file.write(r"{\rtf1\ansi RTF document copied content}")

            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([
                {"path": watched_file, "type": "FILE"}
            ])
            path_id = database.add_monitored_path(watched_file)
            database.save_baseline_records(path_id, scan_targets([watched_file]))

            clipboard = FakeClipboard()
            monitor = ClipboardFileMonitor(
                clipboard,
                database,
                [watched_file],
                session_id,
            )
            monitor.poll()
            clipboard.copy_text(copied_text)

            self.assertEqual(len(monitor.poll()), 1)
            event = database.get_recent_events(1, session_id)[0]
            self.assertEqual(event["event_type"], "CONTENT_CLIPBOARD_COPY")

    def test_pano_sinyali_gelmese_bile_icerik_degisikligini_fark_eder(self):
        with tempfile.TemporaryDirectory() as directory:
            watched_file = os.path.join(directory, "notes.txt")
            copied_text = "sinyalsiz pano değişikliği"
            with open(watched_file, "w", encoding="utf-8") as file:
                file.write(copied_text)

            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([
                {"path": watched_file, "type": "FILE"}
            ])
            path_id = database.add_monitored_path(watched_file)
            database.save_baseline_records(path_id, scan_targets([watched_file]))
            clipboard = FakeClipboard()
            monitor = ClipboardFileMonitor(
                clipboard,
                database,
                [watched_file],
                session_id,
            )

            monitor.poll()
            clipboard.text = copied_text

            self.assertEqual(len(monitor.poll()), 1)

    def test_kopyalamadan_hemen_sonraki_gecikmeli_kaydi_yeniden_eslestirir(self):
        with tempfile.TemporaryDirectory() as directory:
            watched_file = os.path.join(directory, "notes.txt")
            copied_text = "henüz diske yazılmamış içerik"
            with open(watched_file, "w", encoding="utf-8") as file:
                file.write("eski içerik")

            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([
                {"path": watched_file, "type": "FILE"}
            ])
            path_id = database.add_monitored_path(watched_file)
            database.save_baseline_records(path_id, scan_targets([watched_file]))
            clipboard = FakeClipboard()
            monitor = ClipboardFileMonitor(
                clipboard,
                database,
                [watched_file],
                session_id,
            )

            monitor.poll()
            clipboard.copy_text(copied_text)
            self.assertEqual(monitor.poll(), [])

            with open(watched_file, "w", encoding="utf-8") as file:
                file.write(copied_text)

            self.assertEqual(len(monitor.poll()), 1)


if __name__ == "__main__":
    unittest.main()
