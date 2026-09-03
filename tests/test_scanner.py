import os
import tempfile
import unittest

from yula.core.scanner import scan_targets


class TestScanner(unittest.TestCase):
    def test_kritik_gizli_dosyayi_tararken_uygulama_artifaktlarini_atlar(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = os.path.join(directory, ".env")
            pyc_path = os.path.join(directory, "cache.pyc")
            git_directory = os.path.join(directory, ".git")
            os.mkdir(git_directory)

            with open(env_path, "w", encoding="utf-8") as file:
                file.write("SECRET=value")
            with open(pyc_path, "wb") as file:
                file.write(b"cache")
            with open(os.path.join(git_directory, "config"), "w", encoding="utf-8") as file:
                file.write("git config")

            scan = scan_targets([directory])

            self.assertIn(os.path.abspath(env_path), scan)
            self.assertNotIn(os.path.abspath(pyc_path), scan)
            self.assertEqual(len(scan), 1)

    def test_dosya_ve_klasor_secimini_tek_baseline_altinda_birlestirir(self):
        with tempfile.TemporaryDirectory() as directory:
            selected_file = os.path.join(directory, "selected.txt")
            nested_directory = os.path.join(directory, "nested")
            nested_file = os.path.join(nested_directory, "nested.txt")
            os.mkdir(nested_directory)

            for path in (selected_file, nested_file):
                with open(path, "w", encoding="utf-8") as file:
                    file.write(path)

            scan = scan_targets([selected_file, nested_directory])

            self.assertEqual(set(scan), {selected_file, nested_file})


if __name__ == "__main__":
    unittest.main()
