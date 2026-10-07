import unittest

from yula.gui.time_format import format_tr_datetime


class TestTurkishTimeFormat(unittest.TestCase):
    def test_iso_zamani_turkce_sirayla_gosterir(self):
        self.assertEqual(
            format_tr_datetime("2026-09-11T08:07:06.123"),
            "11.09.2026 08:07:06",
        )


if __name__ == "__main__":
    unittest.main()
