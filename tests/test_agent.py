import os
import plistlib
import shutil
import stat
import sys
import tempfile
import time
import unittest

from yula.application.agent_controller import BackgroundAgentController
from yula.application.agent_worker import _reconcile_offline_changes
from yula.application.launch_agent import LAUNCH_AGENT_LABEL, install_launch_agent
from yula.core.scanner import scan_targets
from yula.core.watcher import YulaWatcher
from yula.storage.database import DatabaseManager


class TestBackgroundAgent(unittest.TestCase):
    def test_launch_agent_yapilandirmasini_guvenli_olusturur(self):
        with tempfile.TemporaryDirectory() as directory:
            launch_directory = os.path.join(directory, "LaunchAgents")
            log_directory = os.path.join(directory, "Logs")
            database_path = os.path.join(directory, "yula.db")

            plist_path = install_launch_agent(
                database_path=database_path,
                project_root=directory,
                python_executable=sys.executable,
                launch_agents_directory=launch_directory,
                log_directory=log_directory,
            )

            with open(plist_path, "rb") as plist_file:
                configuration = plistlib.load(plist_file)

            self.assertEqual(configuration["Label"], LAUNCH_AGENT_LABEL)
            self.assertTrue(configuration["RunAtLoad"])
            self.assertIn("--resume", configuration["ProgramArguments"])
            self.assertEqual(
                stat.S_IMODE(os.stat(plist_path).st_mode),
                0o600,
            )

    def test_kapali_suredeki_farki_acilista_kaydeder(self):
        with tempfile.TemporaryDirectory() as directory:
            watched_file = os.path.join(directory, "settings.txt")
            with open(watched_file, "w", encoding="utf-8") as file:
                file.write("trusted")

            database = DatabaseManager(os.path.join(directory, "yula.db"))
            session_id = database.create_monitoring_session([
                {"path": watched_file, "type": "FILE"}
            ])
            baseline = scan_targets([watched_file])
            path_id = database.add_monitored_path(watched_file)
            database.save_baseline_records(path_id, baseline)

            with open(watched_file, "w", encoding="utf-8") as file:
                file.write("changed while agent was offline")

            persisted_baseline = database.get_baseline_snapshots_for_targets(
                [watched_file]
            )
            watcher = YulaWatcher(
                [watched_file],
                persisted_baseline,
                database,
                session_id=session_id,
                event_context={"detected_after_restart": True},
            )
            _reconcile_offline_changes(
                watcher,
                persisted_baseline,
                [watched_file],
            )

            event = database.get_recent_events(1, session_id)[0]
            self.assertEqual(event["event_type"], "MODIFIED")
            self.assertIn("detected_after_restart", event["details_json"])

    @unittest.skipUnless(sys.platform == "darwin", "macOS ajan testi")
    def test_ajan_gui_surecinden_bagimsiz_olay_kaydeder(self):
        with tempfile.TemporaryDirectory(
            dir="/Users/aysecerendogan/Desktop/Yula"
        ) as directory:
            watched_directory = os.path.join(directory, "watched")
            os.mkdir(watched_directory)
            source_path = os.path.join(watched_directory, "source.txt")
            copy_path = os.path.join(watched_directory, "copy.txt")
            with open(source_path, "w", encoding="utf-8") as file:
                file.write("copy content")

            database = DatabaseManager(os.path.join(directory, "yula.db"))
            controller = BackgroundAgentController(
                database,
                install_autostart=False,
                log_directory=os.path.join(directory, "logs"),
            )

            try:
                session_id = controller.start([watched_directory])
                shutil.copy2(source_path, copy_path)

                deadline = time.monotonic() + 5
                events = []
                while time.monotonic() < deadline:
                    events = database.get_recent_events(20, session_id)
                    if any(
                        event["event_type"] == "POSSIBLE_COPY"
                        for event in events
                    ):
                        break
                    time.sleep(0.1)

                self.assertTrue(controller.is_running)
                self.assertTrue(any(
                    event["event_type"] == "POSSIBLE_COPY"
                    for event in events
                ))
            finally:
                if controller.is_running:
                    controller.stop()

            self.assertFalse(controller.is_running)


if __name__ == "__main__":
    unittest.main()
