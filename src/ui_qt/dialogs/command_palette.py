# src/ui_qt/dialogs/command_palette.py
from typing import Dict, Callable
from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QAbstractItemView, QLineEdit
from PySide6.QtCore import Qt

class CommandPalette(QDialog):
    def __init__(self, parent, commands: Dict[str, Callable]):
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
        self.setModal(True)
        self.resize(600, 420)
        self.commands = commands
        v = QVBoxLayout(self)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Type a command…")
        self.list = QListWidget(self)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        v.addWidget(self.search)
        v.addWidget(self.list, 1)
        for name in sorted(self.commands.keys()):
            self.list.addItem(name)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._run_selected)
        self.list.itemDoubleClicked.connect(lambda _: self._run_selected())
        self.search.setFocus()

    def _filter(self, text: str):
        text = (text or "").lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(text not in it.text().lower())
        for i in range(self.list.count()):
            if not self.list.item(i).isHidden():
                self.list.setCurrentRow(i)
                break

    def _run_selected(self):
        it = self.list.currentItem()
        if not it:
            return
        name = it.text()
        fn = self.commands.get(name)
        if callable(fn):
            self.accept()
            fn()
