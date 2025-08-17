# src/ui_qt/dialogs/pattern_dialog.py
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QLabel, QCheckBox, QDialogButtonBox

class PatternDialog(QDialog):
    def __init__(self, parent, title: str, label: str, show_gitignore: bool = True):
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("e.g., *.log")
        lay.addWidget(QLabel(label))
        lay.addWidget(self.edit)
        self.chk = QCheckBox("Also append to .gitignore", self)
        self.chk.setChecked(True)
        self.chk.setVisible(show_gitignore)
        lay.addWidget(self.chk)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    @staticmethod
    def get(parent, title, label, show_gitignore=True):
        dlg = PatternDialog(parent, title, label, show_gitignore)
        ok = dlg.exec() == QDialog.Accepted
        return dlg.edit.text().strip(), dlg.chk.isChecked(), ok
