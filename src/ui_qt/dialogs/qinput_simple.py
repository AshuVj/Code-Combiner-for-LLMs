# src/ui_qt/dialogs/qinput_simple.py
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox

class QInputSimple(QDialog):
    @staticmethod
    def get(parent, title: str, label: str):
        dlg = QDialog(parent)
        dlg.setWindowTitle(title)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(label))
        e = QLineEdit(dlg)
        v.addWidget(e)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dlg)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        ok = dlg.exec() == QDialog.Accepted
        return e.text(), ok
