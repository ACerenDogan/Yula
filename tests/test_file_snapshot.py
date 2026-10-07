import os
import tempfile
import unittest

from yula.core.file_snapshot import (
    capture_file_snapshot,
)
from yula.core.scanner import scan_targets


class TestFileSnapshot(unittest.TestCase):
    def test_normal_dosyanin_guvenlik_bilgilerini_cikarir(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = os.path.join(
                directory,
                "app.py",
            )

            with open(
                file_path,
                "w",
                encoding="utf-8",
            ) as file:
                file.write("trusted")

            os.chmod(file_path, 0o640)

            snapshot = capture_file_snapshot(
                file_path
            )

            self.assertEqual(
                snapshot["kind"],
                "FILE",
            )
            self.assertFalse(
                snapshot["is_symlink"]
            )
            self.assertIsNone(
                snapshot["symlink_target"]
            )
            self.assertEqual(
                snapshot["mode"],
                0o640,
            )
            self.assertEqual(
                snapshot["uid"],
                os.getuid(),
            )
            self.assertEqual(
                snapshot["gid"],
                os.getgid(),
            )
            self.assertEqual(
                len(snapshot["hash"]),
                64,
            )

    def test_izin_degisikligini_hash_degisikliginden_ayirir(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = os.path.join(
                directory,
                "config.txt",
            )

            with open(
                file_path,
                "w",
                encoding="utf-8",
            ) as file:
                file.write("same content")

            os.chmod(file_path, 0o600)
            first_snapshot = capture_file_snapshot(
                file_path
            )

            os.chmod(file_path, 0o644)
            second_snapshot = capture_file_snapshot(
                file_path
            )

            self.assertEqual(
                first_snapshot["hash"],
                second_snapshot["hash"],
            )
            self.assertNotEqual(
                first_snapshot["mode"],
                second_snapshot["mode"],
            )

    def test_symlinki_hedef_dosya_gibi_okumaz(self):
        with tempfile.TemporaryDirectory() as directory:
            target_path = os.path.join(
                directory,
                "secret.txt",
            )
            link_path = os.path.join(
                directory,
                "shortcut",
            )

            with open(
                target_path,
                "w",
                encoding="utf-8",
            ) as file:
                file.write("sensitive content")

            os.symlink(
                target_path,
                link_path,
            )

            snapshot = capture_file_snapshot(
                link_path
            )

            self.assertEqual(
                snapshot["kind"],
                "SYMLINK",
            )
            self.assertTrue(
                snapshot["is_symlink"]
            )
            self.assertEqual(
                snapshot["symlink_target"],
                target_path,
            )
            self.assertEqual(
                len(snapshot["hash"]),
                64,
            )

    def test_klasor_icindeki_symlink_dizinini_takip_etmez(self):
        with tempfile.TemporaryDirectory() as directory:
            selected_directory = os.path.join(
                directory,
                "selected",
            )
            outside_directory = os.path.join(
                directory,
                "outside",
            )

            os.mkdir(selected_directory)
            os.mkdir(outside_directory)

            outside_file = os.path.join(
                outside_directory,
                "secret.txt",
            )

            with open(
                outside_file,
                "w",
                encoding="utf-8",
            ) as file:
                file.write("secret")

            linked_directory = os.path.join(
                selected_directory,
                "external",
            )

            os.symlink(
                outside_directory,
                linked_directory,
                target_is_directory=True,
            )

            scan = scan_targets([
                selected_directory
            ])

            self.assertIn(
                linked_directory,
                scan,
            )
            self.assertEqual(
                scan[linked_directory]["kind"],
                "SYMLINK",
            )
            self.assertNotIn(
                outside_file,
                scan,
            )


if __name__ == "__main__":
    unittest.main()