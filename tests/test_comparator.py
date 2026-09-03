import unittest
from yula.core.comparator import compare_with_baseline

class TestComparator(unittest.TestCase):
    def test_degisiklikleri_dogru_siniflandirir(self):
        # 1. Veritabanındaki eski güvenilir durum (Baseline)
        saved_baseline = {
            "/app/config.json": "hash_eski_111",
            "/app/index.py": "hash_ayni_222",
            "/app/silinecek.txt": "hash_silinecek_333"
        }

        # 2. Şu anki taze tarama durumu
        current_scan = {
            "/app/config.json": {"hash": "hash_yeni_999", "size": 100}, # DEĞİŞTİ!
            "/app/index.py": {"hash": "hash_ayni_222", "size": 200},    # AYNI
            "/app/yeni_dosya.php": {"hash": "hash_yeni_444", "size": 50} # YENİ!
            # silinecek.txt artık yok -> SİLİNDİ!
        }

        # Karşılaştırmayı çalıştır
        rapor = compare_with_baseline(current_scan, saved_baseline)

        # Doğrulamalar (Assertions)
        self.assertEqual(len(rapor["MODIFIED"]), 1)
        self.assertEqual(rapor["MODIFIED"][0]["path"], "/app/config.json")

        self.assertEqual(len(rapor["NEW"]), 1)
        self.assertEqual(rapor["NEW"][0]["path"], "/app/yeni_dosya.php")

        self.assertEqual(len(rapor["DELETED"]), 1)
        self.assertEqual(rapor["DELETED"][0]["path"], "/app/silinecek.txt")

        self.assertEqual(len(rapor["UNCHANGED"]), 1)
        self.assertEqual(rapor["UNCHANGED"][0]["path"], "/app/index.py")

if __name__ == "__main__":
    unittest.main()