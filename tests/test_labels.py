import unittest

from yula.gui.labels import (
    event_type_label,
    risk_label,
    session_status_label,
)


class TestTurkishLabels(unittest.TestCase):
    def test_risk_duzeylerini_turkcelestirir(self):
        self.assertEqual(risk_label("HIGH"), "Yüksek")
        self.assertEqual(risk_label("MEDIUM"), "Orta")
        self.assertEqual(risk_label("LOW"), "Düşük")

    def test_olay_turlerini_turkcelestirir(self):
        self.assertEqual(event_type_label("MODIFIED"), "Değiştirildi")
        self.assertEqual(event_type_label("CREATED"), "Oluşturuldu")
        self.assertEqual(event_type_label("DELETED"), "Silindi")
        self.assertEqual(
            event_type_label("RESTORED"),
            "Referans duruma döndü",
        )
        self.assertEqual(
            event_type_label("MOVED"),
            "Taşındı / yeniden adlandırıldı",
        )
        self.assertEqual(
            event_type_label("PERMISSIONS_CHANGED"),
            "İzinleri değişti",
        )
        self.assertEqual(
            event_type_label("OWNERSHIP_CHANGED"),
            "Sahibi / grubu değişti",
        )
        self.assertEqual(
            event_type_label("SYMLINK_CHANGED"),
            "Sembolik bağlantı değişti",
        )
        self.assertEqual(
            event_type_label("POSSIBLE_COPY"),
            "Dosya kopyası oluşturuldu",
        )
        self.assertEqual(
            event_type_label("CLIPBOARD_COPY"),
            "Dosya kopyalandı",
        )
        self.assertEqual(
            event_type_label("CONTENT_CLIPBOARD_COPY"),
            "İçerik kopyalandı",
        )

    def test_calisma_durumlarini_turkcelestirir(self):
        self.assertEqual(session_status_label("PREPARING"), "Hazırlanıyor")
        self.assertEqual(session_status_label("RUNNING"), "İzleniyor")
        self.assertEqual(session_status_label("STOPPED"), "Durduruldu")
        self.assertEqual(session_status_label("ERROR"), "Hata")

    def test_bilinmeyen_teknik_degeri_degistirmez(self):
        self.assertEqual(risk_label("UNKNOWN"), "UNKNOWN")
        self.assertEqual(event_type_label("UNKNOWN"), "UNKNOWN")
        self.assertEqual(session_status_label("UNKNOWN"), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
