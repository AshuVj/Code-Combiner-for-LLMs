# src/ui_qt/pages/compare_page.py
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QFileDialog, QTextEdit
)
from qfluentwidgets import (
    InfoBar, InfoBarPosition, PrimaryPushButton, PushButton, ComboBox, SwitchButton
)

from src.ui_qt.widgets.diff_view import DiffView

if TYPE_CHECKING:
    from src.ui_qt.app_window import MainFluentWindow


class ComparePage(QWidget):
    """Compare: file/clipboard or manual two-pane, with side/unified views."""
    def __init__(self, appwin: "MainFluentWindow"):
        super().__init__(parent=appwin)
        self.setObjectName("ComparePage")
        self.appwin = appwin

        # Inputs for file/clipboard mode
        self.left_path_edit = QLineEdit(self)
        self.right_mode_combo = ComboBox(self)

        # Options
        self.ignore_ws_chk = SwitchButton("Ignore whitespace", self)
        self.ignore_case_chk = SwitchButton("Ignore case", self)
        self.normalize_eol_chk = SwitchButton("Normalize line endings", self)
        self.view_combo = ComboBox(self)  # Side / Unified

        # Manual mode
        self.manual_switch = SwitchButton("Manual edit mode", self)
        self.manual_box = QWidget(self)
        self.left_editor = QTextEdit(self)
        self.right_editor = QTextEdit(self)

        self.diff = DiffView(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Compare")
        title.setStyleSheet("font-size:20px; font-weight:600;")
        root.addWidget(title)

        # --- Top row (file/clipboard)
        top = QHBoxLayout()
        self.left_path_edit.setPlaceholderText("Left: file path (defaults to current selected file)")
        browse_left_btn = PushButton("Browse…")
        use_sel_btn = PushButton("Use Selected from Files")
        top.addWidget(self.left_path_edit, 2)
        top.addWidget(browse_left_btn)
        top.addWidget(use_sel_btn)

        top.addSpacing(12)
        top.addWidget(QLabel("Right:"))
        self.right_mode_combo.addItems(["Clipboard", "File…"])
        load_right_btn = PrimaryPushButton("Load & Compare")
        top.addWidget(self.right_mode_combo)
        top.addWidget(load_right_btn)
        root.addLayout(top)

        # --- Options row
        opts = QHBoxLayout()
        self.ignore_ws_chk.setChecked(True)
        self.normalize_eol_chk.setChecked(True)
        self.ignore_case_chk.setChecked(False)
        opts.addWidget(self.ignore_ws_chk)
        opts.addWidget(self.normalize_eol_chk)
        opts.addWidget(self.ignore_case_chk)

        opts.addSpacing(20)
        opts.addWidget(QLabel("View:"))
        self.view_combo.addItems(["Side-by-side", "Unified (git-style)"])
        opts.addWidget(self.view_combo)

        opts.addStretch(1)
        copy_patch_btn = PushButton("Copy unified diff")
        swap_btn = PushButton("Swap Sides")
        opts.addWidget(self.manual_switch)
        opts.addWidget(copy_patch_btn)
        opts.addWidget(swap_btn)
        root.addLayout(opts)

        # --- Manual edit box
        mb = QVBoxLayout(self.manual_box)
        editors = QHBoxLayout()
        self.left_editor.setPlaceholderText("Paste or type LEFT text…")
        self.right_editor.setPlaceholderText("Paste or type RIGHT text…")
        editors.addWidget(self.left_editor, 1)
        editors.addWidget(self.right_editor, 1)
        mb.addLayout(editors)

        mbtns = QHBoxLayout()
        compare_btn = PrimaryPushButton("Compare")
        clear_btn = PushButton("Clear")
        paste_left_btn = PushButton("Paste → Left")
        paste_right_btn = PushButton("Paste → Right")
        mbtns.addWidget(paste_left_btn)
        mbtns.addWidget(paste_right_btn)
        mbtns.addStretch(1)
        mbtns.addWidget(clear_btn)
        mbtns.addWidget(compare_btn)
        mb.addLayout(mbtns)

        self.manual_box.setVisible(False)
        root.addWidget(self.manual_box)

        # --- Diff area
        root.addWidget(self.diff, 1)

        # Events (file/clipboard)
        browse_left_btn.clicked.connect(self._browse_left)
        use_sel_btn.clicked.connect(self._use_selected)
        load_right_btn.clicked.connect(self._load_and_diff)

        # Options events
        self.ignore_ws_chk.checkedChanged.connect(lambda _on: self._recompute())
        self.ignore_case_chk.checkedChanged.connect(lambda _on: self._recompute())
        self.normalize_eol_chk.checkedChanged.connect(lambda _on: self._recompute())
        self.view_combo.currentTextChanged.connect(self._on_view_change)

        copy_patch_btn.clicked.connect(self._copy_patch)
        swap_btn.clicked.connect(self._swap_sides)

        # Manual mode events
        self.manual_switch.checkedChanged.connect(self._toggle_manual)
        compare_btn.clicked.connect(self._compare_manual)
        clear_btn.clicked.connect(lambda: (self.left_editor.clear(), self.right_editor.clear()))
        paste_left_btn.clicked.connect(self._paste_left)
        paste_right_btn.clicked.connect(self._paste_right)

        # Try to seed left with Files selection
        self._use_selected(silent=True)

        # Default view: side-by-side
        self._on_view_change(self.view_combo.currentText())

    # ---------- Mode & View

    def _on_view_change(self, label: str):
        mode = "unified" if "Unified" in label else "side"
        self.diff.set_mode(mode)
        self._recompute()

    def _toggle_manual(self, on: bool):
        self.manual_box.setVisible(on)
        self._recompute()

    def _recompute(self):
        if self.manual_switch.isChecked():
            self._compare_manual(silent=True)
        else:
            self._load_and_diff(silent=True)

    # ---------- File/clipboard mode

    def _browse_left(self):
        base = self.appwin.state.selected_folder or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Choose left file", base, "All files (*.*)")
        if path:
            self.left_path_edit.setText(path)
            self._load_and_diff()

    def _use_selected(self, silent: bool = False):
        try:
            fp = self._current_selected_abs_path()
            if fp and os.path.isfile(fp):
                self.left_path_edit.setText(fp)
                if not silent:
                    InfoBar.success("Selected", os.path.relpath(fp, self.appwin.state.selected_folder),
                                    parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
                if not self.manual_switch.isChecked():
                    self._load_and_diff(silent=True)
            elif not silent:
                InfoBar.info("No selection", "Select a file in the Files page first.",
                             parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
        except Exception:
            if not silent:
                InfoBar.info("No selection", "Select a file in the Files page first.",
                             parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _current_selected_abs_path(self) -> Optional[str]:
        files_page = getattr(self.appwin, "files_page", None)
        if not files_page or not hasattr(files_page, "table"):
            return None
        sel = files_page.table.selectionModel().selectedRows()
        if not sel:
            return None
        row = sel[0].row()
        name_item = files_page.table.item(row, 0)
        if not name_item:
            return None
        rel = name_item.data(Qt.UserRole)
        if not rel:
            return None
        base = self.appwin.state.selected_folder or ""
        return os.path.abspath(os.path.join(base, rel))

    def _read_text_file(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as e:
            InfoBar.error("Read failed", f"{path}\n{e}", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
            return ""

    def _load_and_diff(self, silent: bool = False):
        if self.manual_switch.isChecked():
            return

        left_path = self.left_path_edit.text().strip() or ""
        if not left_path or not os.path.isfile(left_path):
            return

        left = self._read_text_file(left_path)

        mode = self.right_mode_combo.currentText()
        if mode == "Clipboard":
            from PySide6.QtWidgets import QApplication
            right = QApplication.clipboard().text()
            right_name = "clipboard"
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Choose right file",
                                                  os.path.dirname(left_path) or os.path.expanduser("~"),
                                                  "All files (*.*)")
            if not path:
                return
            right = self._read_text_file(path)
            right_name = os.path.basename(path)

        self.diff.set_texts(
            left, right,
            ignore_ws=self.ignore_ws_chk.isChecked(),
            ignore_case=self.ignore_case_chk.isChecked(),
            normalize_eol=self.normalize_eol_chk.isChecked(),
            inline=True
        )
        if not silent:
            InfoBar.success("Diff ready",
                            f"{os.path.basename(left_path)}  ↔  {right_name}",
                            parent=self.appwin, position=InfoBarPosition.TOP_RIGHT, duration=1500)

    # ---------- Manual mode

    def _paste_left(self):
        from PySide6.QtWidgets import QApplication
        self.left_editor.paste() if self.left_editor.hasFocus() else self.left_editor.setPlainText(QApplication.clipboard().text())

    def _paste_right(self):
        from PySide6.QtWidgets import QApplication
        self.right_editor.paste() if self.right_editor.hasFocus() else self.right_editor.setPlainText(QApplication.clipboard().text())

    def _compare_manual(self, silent: bool = False):
        if not self.manual_switch.isChecked():
            return
        left = self.left_editor.toPlainText()
        right = self.right_editor.toPlainText()
        self.diff.set_texts(
            left, right,
            ignore_ws=self.ignore_ws_chk.isChecked(),
            ignore_case=self.ignore_case_chk.isChecked(),
            normalize_eol=self.normalize_eol_chk.isChecked(),
            inline=True
        )
        if not silent:
            InfoBar.success("Diff ready", "Manual panes compared.",
                            parent=self.appwin, position=InfoBarPosition.TOP_RIGHT, duration=1200)

    # ---------- Shared actions

    def _copy_patch(self):
        left_path = self.left_path_edit.text().strip() or "left"
        left_name = os.path.basename(left_path)
        self.diff.copy_unified_to_clipboard(left_name=left_name, right_name="right")
        InfoBar.success("Copied", "Unified diff copied to clipboard.",
                        parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _swap_sides(self):
        if self.manual_switch.isChecked():
            l = self.left_editor.toPlainText()
            r = self.right_editor.toPlainText()
            self.left_editor.setPlainText(r)
            self.right_editor.setPlainText(l)
            self._compare_manual(silent=True)
            return

        left_path = self.left_path_edit.text().strip() or ""
        if not left_path or not os.path.isfile(left_path):
            return
        left = self._read_text_file(left_path)

        mode = self.right_mode_combo.currentText()
        if mode == "Clipboard":
            from PySide6.QtWidgets import QApplication
            right = QApplication.clipboard().text()
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Choose new LEFT (swap)",
                                                  os.path.dirname(left_path) or os.path.expanduser("~"),
                                                  "All files (*.*)")
            if not path:
                return
            right = self._read_text_file(path)
            self.left_path_edit.setText(path)

        self.diff.set_texts(
            right, left,
            ignore_ws=self.ignore_ws_chk.isChecked(),
            ignore_case=self.ignore_case_chk.isChecked(),
            normalize_eol=self.normalize_eol_chk.isChecked(),
            inline=True
        )
