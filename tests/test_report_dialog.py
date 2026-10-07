import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from yula.gui.report_dialog import ReportDialog
from yula.storage.database import DatabaseManager


class TestReportDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_secili_calisma_ve_turkce_tarih_arayuzde_acilir(self):
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseManager(os.path.join(directory, "test.db"))
            session_id = database.create_monitoring_session([
                {"path": "/project/app.py", "type": "FILE"}
            ])
            database.log_security_event(
                event_type="MODIFIED",
                risk_level="LOW",
                target_path="/project/app.py",
                description="Değişiklik",
                session_id=session_id,
            )

            dialog = ReportDialog(database, session_id)
            try:
                self.assertEqual(dialog._selected_session_id(), session_id)
                self.assertEqual(dialog.start_edit.displayFormat(), "dd.MM.yyyy HH:mm")
                self.assertIn(
                    f"Çalışma #{session_id}",
                    dialog.preview_label.text(),
                )
            finally:
                dialog.close()


if __name__ == "__main__":
    unittest.main()
