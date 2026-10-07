import os
import tempfile
import unittest
from datetime import datetime

from yula.reporting.pdf_report import generate_security_report


class TestPdfReport(unittest.TestCase):
    def test_turkce_guvenlik_raporu_olusturur(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = os.path.join(directory, "report.pdf")
            events = [{
                "timestamp": "2026-09-08T10:30:00.000",
                "risk_level": "HIGH",
                "event_type": "POSSIBLE_COPY",
                "target_path": "/project/kopya.txt",
                "source_path": "/project/kaynak.txt",
                "actor_name": "ceren",
                "description": "Olası dosya kopyası: kaynak.txt → kopya.txt",
            }]

            result = generate_security_report(
                output_path,
                events,
                datetime(2026, 9, 8, 9, 0),
                datetime(2026, 9, 8, 18, 0),
                include_times=True,
            )

            self.assertEqual(result, output_path)
            self.assertGreater(os.path.getsize(result), 1000)
            with open(result, "rb") as pdf_file:
                self.assertEqual(pdf_file.read(4), b"%PDF")


if __name__ == "__main__":
    unittest.main()
