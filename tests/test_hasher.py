import unittest
import os
from yula.core.hasher import calculate_sha256

class TestHasher(unittest.TestCase):
    def setUp(self):
        self.test_filename = "test_gecici.txt"
        with open(self.test_filename, "w", encoding="utf-8") as f:
            f.write("YULA_TEST_VERISI")

    def tearDown(self):
        if os.path.exists(self.test_filename):
            os.remove(self.test_filename)

    def test_ayni_icerik_ayni_hash(self):
        h1 = calculate_sha256(self.test_filename)
        h2 = calculate_sha256(self.test_filename)
        self.assertEqual(h1, h2)

    def test_degisen_icerik_farkli_hash(self):
        h1 = calculate_sha256(self.test_filename)
        with open(self.test_filename, "w", encoding="utf-8") as f:
            f.write("YULA_TEST_VERISI_DEGISTI")
        h2 = calculate_sha256(self.test_filename)
        self.assertNotEqual(h1, h2)

    def test_parcali_okuma_buyuk_dosya(self):
        buyuk = "buyuk.txt"
        with open(buyuk, "w", encoding="utf-8") as f:
            f.write("B" * 150000)
        h_kucuk = calculate_sha256(buyuk, chunk_size=1024)
        h_buyuk = calculate_sha256(buyuk, chunk_size=65536)
        if os.path.exists(buyuk):
            os.remove(buyuk)
        self.assertEqual(h_kucuk, h_buyuk)

if __name__ == "__main__":
    unittest.main()