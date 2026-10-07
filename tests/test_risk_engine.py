import unittest

from yula.core.risk_engine import RiskEngine


class TestRiskEngine(unittest.TestCase):
    def test_env_dosyasi_kritik_sayilir(self):
        risk, _ = RiskEngine.evaluate_file_event("CREATED", "/project/.env")
        self.assertEqual(risk, "HIGH")

    def test_referans_duruma_donus_ayri_olaydir(self):
        risk, description = RiskEngine.evaluate_file_event("RESTORED", "/project/app.py")
        self.assertEqual(risk, "LOW")
        self.assertIn("referans", description)

    def test_baskalarina_yazma_izni_verilmesini_yuksek_risk_sayar(self):
        risk, description = RiskEngine.evaluate_file_event(
            "PERMISSIONS_CHANGED",
            "/project/settings.txt",
            previous_snapshot={"mode": 0o600},
            current_snapshot={"mode": 0o666},
        )

        self.assertEqual(risk, "HIGH")
        self.assertIn("600 → 666", description)

    def test_symlink_degisikligini_yuksek_risk_sayar(self):
        risk, description = RiskEngine.evaluate_file_event(
            "SYMLINK_CHANGED",
            "/project/current",
        )

        self.assertEqual(risk, "HIGH")
        self.assertIn("Sembolik", description)

    def test_izinleri_sikilastirmayi_dusuk_risk_sayar(self):
        risk, _ = RiskEngine.evaluate_file_event(
            "PERMISSIONS_CHANGED",
            "/project/notes.txt",
            previous_snapshot={"mode": 0o666},
            current_snapshot={"mode": 0o600},
        )

        self.assertEqual(risk, "LOW")

    def test_pano_kopyalamalarini_en_az_orta_risk_sayar(self):
        for event_type in ("CLIPBOARD_COPY", "CONTENT_CLIPBOARD_COPY"):
            with self.subTest(event_type=event_type):
                risk, _ = RiskEngine.evaluate_file_event(
                    event_type,
                    "/project/notes.txt",
                )
                self.assertEqual(risk, "MEDIUM")

                critical_risk, _ = RiskEngine.evaluate_file_event(
                    event_type,
                    "/project/settings.py",
                )
                self.assertEqual(critical_risk, "HIGH")


if __name__ == "__main__":
    unittest.main()
