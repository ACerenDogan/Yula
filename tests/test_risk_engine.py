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


if __name__ == "__main__":
    unittest.main()
