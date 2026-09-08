import unittest

from yula.core.paths import should_ignore_path


class TestPaths(unittest.TestCase):
    def test_sqlite_gecici_dosyalarini_yok_sayar(self):
        for file_name in (
            "yula.db-journal",
            "yula.db-shm",
            "yula.db-wal",
        ):
            with self.subTest(file_name=file_name):
                self.assertTrue(
                    should_ignore_path(
                        f"/project/{file_name}"
                    )
                )

    def test_guvenlik_acisindan_onemli_gizli_dosyayi_izler(self):
        self.assertFalse(
            should_ignore_path("/project/.env")
        )


if __name__ == "__main__":
    unittest.main()
