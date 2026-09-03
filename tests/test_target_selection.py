import os
import tempfile
import unittest

os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

from PySide6.QtWidgets import QApplication

from yula.gui.target_selection import (
    TargetSelectionDialog,
)


class TestTargetSelectionDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = (
            QApplication.instance()
            or QApplication([])
        )

    def test_birden_fazla_hedefi_korur(self):
        with tempfile.TemporaryDirectory() as directory:
            first_file = os.path.join(
                directory,
                "first.txt",
            )
            second_file = os.path.join(
                directory,
                "second.txt",
            )

            dialog = TargetSelectionDialog()
            dialog.add_targets([
                first_file,
                second_file,
            ])

            self.assertEqual(
                dialog.selected_targets(),
                [
                    os.path.abspath(first_file),
                    os.path.abspath(second_file),
                ],
            )

            dialog.close()

    def test_ayni_hedefi_iki_kez_eklemez(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(
                directory,
                "app.py",
            )

            dialog = TargetSelectionDialog()
            dialog.add_targets([
                target,
                target,
            ])

            self.assertEqual(
                dialog.selected_targets(),
                [os.path.abspath(target)],
            )

            self.assertEqual(
                dialog.target_list.count(),
                1,
            )

            dialog.close()


if __name__ == "__main__":
    unittest.main()