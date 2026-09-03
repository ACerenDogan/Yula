from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from yula.core.paths import normalize_path


class TargetSelectionDialog(QDialog):
    """İzlenecek dosya ve klasörlerin seçildiği pencere."""

    def __init__(
        self,
        parent=None,
        initial_targets: Iterable[str] | None = None,
    ):
        super().__init__(parent)

        self.setWindowTitle("İzleme Hedeflerini Seç")
        self.setMinimumSize(680, 440)
        self.setModal(True)

        self._build_ui()

        if initial_targets is not None:
            self.add_targets(initial_targets)

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        title = QLabel("İzleme hedefleri")
        title.setObjectName("dialogTitle")

        description = QLabel(
            "Bütünlüğünü izlemek istediğiniz dosyaları veya "
            "klasörleri ekleyin. Birden fazla hedef seçebilirsiniz."
        )
        description.setWordWrap(True)
        description.setObjectName("dialogDescription")

        main_layout.addWidget(title)
        main_layout.addWidget(description)

        self.target_list = QListWidget()
        self.target_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        self.target_list.setAlternatingRowColors(True)

        main_layout.addWidget(self.target_list)

        action_layout = QHBoxLayout()

        self.add_files_button = QPushButton("Dosya Ekle")
        self.add_files_button.clicked.connect(
            self._select_files
        )

        self.add_directory_button = QPushButton(
            "Klasör Ekle"
        )
        self.add_directory_button.clicked.connect(
            self._select_directory
        )

        self.remove_button = QPushButton(
            "Seçileni Kaldır"
        )
        self.remove_button.clicked.connect(
            self._remove_selected
        )

        action_layout.addWidget(self.add_files_button)
        action_layout.addWidget(
            self.add_directory_button
        )
        action_layout.addWidget(self.remove_button)
        action_layout.addStretch()

        main_layout.addLayout(action_layout)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        start_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Ok
        )
        start_button.setText("İzlemeyi Başlat")

        cancel_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        cancel_button.setText("İptal")

        self.button_box.accepted.connect(
            self._accept_selection
        )
        self.button_box.rejected.connect(self.reject)

        main_layout.addWidget(self.button_box)

        self.setStyleSheet("""
            QDialog {
                background-color: #f8fafc;
            }

            QLabel#dialogTitle {
                color: #0f172a;
                font-size: 22px;
                font-weight: 700;
            }

            QLabel#dialogDescription {
                color: #475569;
                font-size: 13px;
            }

            QListWidget {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #0f172a;
                padding: 6px;
            }

            QListWidget::item {
                min-height: 32px;
                padding-left: 6px;
            }

            QListWidget::item:selected {
                background-color: #dbeafe;
                color: #1e3a8a;
            }

            QPushButton {
                min-height: 30px;
                padding: 2px 14px;
            }
        """)

    def add_targets(
        self,
        targets: Iterable[str],
    ) -> None:
        """Yeni hedefleri normalize ederek listeye ekler."""
        existing_targets = set(
            self.selected_targets()
        )

        for target in targets:
            normalized = normalize_path(target)

            if normalized in existing_targets:
                continue

            item = QListWidgetItem(normalized)
            item.setData(
                Qt.ItemDataRole.UserRole,
                normalized,
            )
            item.setToolTip(normalized)

            self.target_list.addItem(item)
            existing_targets.add(normalized)

    def selected_targets(self) -> list[str]:
        """Listedeki bütün hedef yollarını döndürür."""
        return [
            self.target_list.item(index).data(
                Qt.ItemDataRole.UserRole
            )
            for index in range(
                self.target_list.count()
            )
        ]

    def _select_files(self) -> None:
        selected_files, _ = QFileDialog.getOpenFileNames(
            self,
            "İzlenecek Dosyaları Seç",
            str(Path.home()),
            "Tüm Dosyalar (*)",
        )

        self.add_targets(selected_files)

    def _select_directory(self) -> None:
        selected_directory = (
            QFileDialog.getExistingDirectory(
                self,
                "İzlenecek Klasörü Seç",
                str(Path.home()),
            )
        )

        if selected_directory:
            self.add_targets([
                selected_directory
            ])

    def _remove_selected(self) -> None:
        for item in self.target_list.selectedItems():
            row = self.target_list.row(item)
            self.target_list.takeItem(row)

    def _accept_selection(self) -> None:
        if not self.selected_targets():
            QMessageBox.warning(
                self,
                "Hedef Seçilmedi",
                "İzlemeyi başlatmak için en az bir "
                "dosya veya klasör seçmelisiniz.",
            )
            return

        self.accept()