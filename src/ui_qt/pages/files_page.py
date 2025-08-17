# src/ui_qt/pages/files_page.py
from __future__ import annotations

import os
import re
import sys
import subprocess
from typing import List, Tuple, Optional, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from src.ui_qt.app_window import MainFluentWindow

from PySide6.QtCore import Qt, QPoint, QUrl
from PySide6.QtGui import QFont, QTextOption, QAction, QShortcut, QKeySequence, QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QSplitter,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QMenu,
    QTextEdit, QProgressBar, QPushButton, QApplication, QCheckBox
)
from qfluentwidgets import (
    PrimaryPushButton, PushButton, InfoBar, InfoBarPosition,
    LineEdit, ComboBox, SwitchButton
)

# Optional syntax highlighting (graceful if missing)
try:
    from pygments import highlight
    from pygments.lexers import guess_lexer_for_filename
    from pygments.formatters import HtmlFormatter
    HAVE_PYGMENTS = True
except Exception:
    HAVE_PYGMENTS = False

from src.ui_qt.utils import resource_path
from src.core.file_scanner import FileScanner
from src.core.file_processor import FileProcessor
from src.core.settings_manager import SettingsManager
from src.utils.encoding_detector import detect_file_encoding
from src.utils.prefs import load_prefs, save_prefs
from src.utils.logger import logger
from src.config import (
    EXCLUDED_FOLDER_NAMES_DEFAULT, PREVIEW_CHUNK_SIZE, PREVIEW_MAX_BYTES,
    PROCESS_MAX_BYTES, WINDOW_TITLE
)
from src.ui_qt.workers.scan_worker import ScanWorker
from src.ui_qt.workers.process_worker import ProcessWorker
from src.ui_qt.workers.tree_worker import TreeWorker

def default_output_filename(base_folder: str) -> str:
    base = os.path.basename((base_folder or "").rstrip("\\/")) or "combined_output"
    name = re.sub(r"\s+", "_", base)
    name = re.sub(r"[^\w.\-]+", "_", name)
    name = name.strip("._-") or "combined_output"
    if not name.lower().endswith(".txt"):
        name += ".txt"
    return name

def hr_size(n: int) -> str:
    units = ["B","KB","MB","GB","TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units)-1:
        f /= 1024.0
        i += 1
    return f"{f:.1f} {units[i]}"

class FilesPage(QWidget):
    """Files + Preview + Actions page."""
    # ---- Type mapping helpers --------------------------------------------
    _EXT_TYPE_MAP = {
        ".py": "Python", ".pyw": "Python",
        ".json": "JSON", ".jsonc": "JSONC",
        ".toml": "TOML",
        ".yaml": "YAML", ".yml": "YAML",
        ".md": "Markdown", ".markdown": "Markdown",
        ".txt": "Text", ".rst": "reStructuredText",
        ".ini": "INI", ".cfg": "INI", ".conf": "Config",
        ".csv": "CSV", ".tsv": "TSV", ".log": "Log",
        ".xml": "XML",
        ".html": "HTML", ".htm": "HTML",
        ".css": "CSS",
        ".js": "JavaScript", ".mjs": "JavaScript",
        ".ts": "TypeScript", ".jsx": "JSX", ".tsx": "TSX",
        ".c": "C", ".h": "C Header",
        ".cc": "C++", ".cpp": "C++", ".cxx": "C++",
        ".hpp": "C++ Header", ".hh": "C++ Header",
        ".cs": "C#", ".java": "Java", ".kt": "Kotlin",
        ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
        ".php": "PHP", ".swift": "Swift",
        ".sh": "Shell", ".ps1": "PowerShell", ".bat": "Batch",
    }
    _NAME_TYPE_MAP = {
        "makefile": "Makefile",
        "dockerfile": "Dockerfile",
        ".gitignore": "gitignore",
        ".gitattributes": "gitattributes",
        "license": "License",
        "readme": "Readme",
    }

    def __init__(self, appwin: "MainFluentWindow"):
        super().__init__(parent=appwin)
        self.setObjectName("FilesPage")
        self.appwin = appwin
        self.state = appwin.state
        self.setAcceptDrops(True)

        self.scan_thread: Optional[ScanWorker] = None
        self.proc_thread: Optional[ProcessWorker] = None
        self.tree_thread: Optional[TreeWorker] = None
        self.last_output_path: Optional[str] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        title = QLabel("Files")
        title.setStyleSheet("font-size:20px; font-weight:600;")
        root.addWidget(title)

        top_row = QHBoxLayout()
        self.folder_edit = LineEdit(self)
        self.folder_edit.setPlaceholderText("Select or drop a folder here…")
        browse_btn = PrimaryPushButton("Browse")
        self.recent_combo = ComboBox(self); self.recent_combo.setFixedWidth(260)
        self.recent_combo.addItems(self._load_recent_folders())
        refresh_btn = PushButton("Refresh (F5)")
        self.cancel_scan_btn = PushButton("Cancel Scan")
        self.cancel_scan_btn.setEnabled(False)
        top_row.addWidget(self.folder_edit, 1)
        top_row.addWidget(browse_btn)
        top_row.addWidget(QLabel("Recent:"))
        top_row.addWidget(self.recent_combo)
        top_row.addWidget(refresh_btn)
        top_row.addWidget(self.cancel_scan_btn)
        root.addLayout(top_row)

        filter_row = QHBoxLayout()
        self.search_edit = LineEdit(self)
        self.search_edit.setPlaceholderText("Search filename or relative path… (Ctrl+F)")
        self.ext_filter = LineEdit(self)
        self.ext_filter.setPlaceholderText("Ext filter: e.g. .py,.md (leave empty = all)")
        clear_btn = PushButton("Clear")
        filter_row.addWidget(self.search_edit, 1)
        filter_row.addWidget(self.ext_filter)
        filter_row.addWidget(clear_btn)
        root.addLayout(filter_row)

        toggles = QHBoxLayout()
        self.sw_git = SwitchButton("Apply .gitignore", self)
        self.sw_defaults = SwitchButton("Use default folder excludes", self)
        self.sw_outputs  = SwitchButton("Auto-hide generated outputs", self)
        toggles.addWidget(self.sw_git); toggles.addWidget(self.sw_defaults); toggles.addWidget(self.sw_outputs)
        toggles.addStretch(1)
        root.addLayout(toggles)

        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)

        left = QWidget()
        left_lay = QVBoxLayout(left); left_lay.setContentsMargins(0,0,0,0)

        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["Filename", "Path", "Type"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_menu)
        left_lay.addWidget(self.table)

        act_row = QHBoxLayout()
        exclude_btn = PushButton("Exclude Selected (Del)")
        select_all_btn = PushButton("Select All (Ctrl+A)")
        deselect_all_btn = PushButton("Deselect All")
        self.copy_output_btn = PushButton("Copy Last Output"); self.copy_output_btn.setEnabled(False)
        act_row.addWidget(exclude_btn)
        act_row.addWidget(select_all_btn)
        act_row.addWidget(deselect_all_btn)
        act_row.addStretch(1)
        act_row.addWidget(self.copy_output_btn)
        left_lay.addLayout(act_row)

        split.addWidget(left)

        right = QWidget()
        right_lay = QVBoxLayout(right); right_lay.setContentsMargins(8, 0, 0, 0)
        prev_title = QLabel("Preview"); prev_title.setStyleSheet("font-weight:600;")
        right_lay.addWidget(prev_title)
        self.preview = QTextEdit(self); self.preview.setReadOnly(True)
        self.preview.setWordWrapMode(QTextOption.NoWrap)
        mono = QFont("Consolas"); mono.setStyleHint(QFont.Monospace)
        self.preview.setFont(mono)
        right_lay.addWidget(self.preview, 1)
        split.addWidget(right)

        gen_row = QHBoxLayout()
        generate_selected_btn = PrimaryPushButton("Generate Selected Output")
        generate_all_btn = PrimaryPushButton("Generate Combined Output")
        cancel_proc_btn = PushButton("Cancel Process")
        export_tree_btn = PushButton("Export File Tree")
        self.opt_markdown = QCheckBox("Markdown tree")
        self.opt_ascii = QCheckBox("ASCII tree")
        self.opt_sizes = QCheckBox("Include sizes")
        gen_row.addWidget(generate_selected_btn)
        gen_row.addWidget(generate_all_btn)
        gen_row.addWidget(cancel_proc_btn)
        gen_row.addStretch(1)
        gen_row.addWidget(export_tree_btn)
        gen_row.addWidget(self.opt_markdown)
        gen_row.addWidget(self.opt_ascii)
        gen_row.addWidget(self.opt_sizes)
        root.addLayout(gen_row)

        bar_row = QHBoxLayout()
        self.progress = QProgressBar(self); self.progress.setRange(0, 100)
        self.sel_stats = QLabel("")
        self.status = QLabel("Ready")
        bar_row.addWidget(self.progress, 1)
        bar_row.addWidget(self.sel_stats)
        bar_row.addWidget(self.status)
        root.addLayout(bar_row)

        # signals
        browse_btn.clicked.connect(self.pick_folder)
        refresh_btn.clicked.connect(self.refresh_files)
        self.cancel_scan_btn.clicked.connect(self._cancel_scan)
        clear_btn.clicked.connect(lambda: self.search_edit.setText(""))
        self.recent_combo.currentTextChanged.connect(self._recent_pick)
        self.copy_output_btn.clicked.connect(self._copy_last_output)

        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.ext_filter.textChanged.connect(self._apply_filter)

        select_all_btn.clicked.connect(self._select_all)
        deselect_all_btn.clicked.connect(self._deselect_all)
        exclude_btn.clicked.connect(self._exclude_selected)

        generate_selected_btn.clicked.connect(self._generate_selected)
        generate_all_btn.clicked.connect(self._generate_all)
        cancel_proc_btn.clicked.connect(self._cancel_process)
        export_tree_btn.clicked.connect(self._export_tree)

        self.sw_git.checkedChanged.connect(self._toggles_changed)
        self.sw_defaults.checkedChanged.connect(self._toggles_changed)
        self.sw_outputs.checkedChanged.connect(self._toggles_changed)

        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.search_edit.setFocus())
        QShortcut(QKeySequence("F5"), self, activated=self.refresh_files)
        QShortcut(QKeySequence("Delete"), self, activated=self._exclude_selected)
        QShortcut(QKeySequence("Ctrl+A"), self, activated=self._select_all)

        split.setSizes([700, 500])

    # lifecycle
    def bootstrap(self):
        self._init_from_prefs_or_settings()

    def _init_from_prefs_or_settings(self):
        prefs = load_prefs()
        self.state.apply_gitignore = bool(prefs.get("apply_gitignore", True))
        self.state.use_default_folder_names = bool(prefs.get("use_default_folder_names", False))
        self.state.auto_hide_outputs = bool(prefs.get("auto_hide_outputs", False))
        self.sw_git.setChecked(self.state.apply_gitignore)
        self.sw_defaults.setChecked(self.state.use_default_folder_names)
        self.sw_outputs.setChecked(self.state.auto_hide_outputs)

        last = prefs.get("last_folder")
        if last and os.path.isdir(last):
            self.set_folder(last)
            self.appwin.load_settings()
            self.refresh_files()
        else:
            self.status.setText("Select a folder to start.")

    def _load_recent_folders(self) -> List[str]:
        prefs = load_prefs()
        rec = prefs.get("recent_folders", [])
        return rec if isinstance(rec, list) else []

    def _push_recent(self, folder: str):
        prefs = load_prefs()
        rec = prefs.get("recent_folders", [])
        if not isinstance(rec, list):
            rec = []
        folder = os.path.abspath(folder)
        if folder in rec:
            rec.remove(folder)
        rec.insert(0, folder)
        prefs["recent_folders"] = rec[:8]
        save_prefs(prefs)
        self.recent_combo.blockSignals(True)
        self.recent_combo.clear()
        self.recent_combo.addItems(rec[:8])
        self.recent_combo.blockSignals(False)

    def _recent_pick(self, text: str):
        if text and os.path.isdir(text):
            self.set_folder(text)
            self.appwin.load_settings()
            self.refresh_files()

    # toggles
    def _toggles_changed(self, *_):
        self.state.apply_gitignore = self.sw_git.isChecked()
        self.state.use_default_folder_names = self.sw_defaults.isChecked()
        self.state.auto_hide_outputs = self.sw_outputs.isChecked()
        prefs = load_prefs()
        prefs["apply_gitignore"] = self.state.apply_gitignore
        prefs["use_default_folder_names"] = self.state.use_default_folder_names
        prefs["auto_hide_outputs"] = self.state.auto_hide_outputs
        save_prefs(prefs)
        self.refresh_files()

    # drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.isdir(p):
                self.set_folder(p)
                self.appwin.load_settings()
                self.refresh_files()
                InfoBar.success("Folder selected", p, parent=self.appwin, duration=2000, position=InfoBarPosition.TOP_RIGHT)
                break

    # folder / scan
    def set_folder(self, folder: str):
        folder = os.path.abspath(folder)
        self.state.selected_folder = folder
        self.state.scanner = FileScanner(folder)
        self.state.processor = FileProcessor(folder)
        self.state.settings_mgr = SettingsManager(folder)
        self.folder_edit.setText(folder)
        prefs = load_prefs()
        prefs["last_folder"] = folder
        save_prefs(prefs)
        self._push_recent(folder)

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", self.state.selected_folder or os.path.expanduser("~"))
        if not folder:
            return
        self.set_folder(folder)
        self.refresh_files()
        InfoBar.success("Folder selected", folder, parent=self.appwin, duration=2000, position=InfoBarPosition.TOP_RIGHT)

    def refresh_files(self):
        self._clear_table()
        st = self.state
        if not st.scanner or not st.selected_folder:
            self.status.setText("No folder selected.")
            return

        st.scanner.excluded_folders = set(st.excluded_folders)
        st.scanner.excluded_file_patterns = set(st.excluded_file_patterns)
        st.scanner.excluded_files = set(st.excluded_files_abs)
        st.scanner.apply_gitignore = bool(st.apply_gitignore)
        st.scanner.excluded_folder_names = set(EXCLUDED_FOLDER_NAMES_DEFAULT) if st.use_default_folder_names else set()

        self.progress.setValue(0)
        self.status.setText("Scanning files…")
        self._set_buttons_enabled(False)
        self.cancel_scan_btn.setEnabled(True)

        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.stop()
            self.scan_thread.wait()

        self.scan_thread = ScanWorker(st)
        self.scan_thread.batch.connect(self._append_batch)
        self.scan_thread.progress.connect(self._on_scan_progress)
        self.scan_thread.status.connect(self._set_status)
        self.scan_thread.finishedOk.connect(self._scan_finished)
        self.scan_thread.start()

    def _append_batch(self, rows: list):
        sorting = self.table.isSortingEnabled()
        if sorting:
            self.table.setSortingEnabled(False)
        for r in rows:
            fn, rel, typ = self._coerce_row(r)
            if not fn:
                continue
            self._add_file_row(fn, rel, typ)
        if sorting:
            self.table.setSortingEnabled(True)
        self._apply_filter()

    def _on_scan_progress(self, proc: int, total: int):
        pct = int((proc / max(1, total)) * 100)
        self.progress.setValue(pct)

    def _scan_finished(self):
        self._set_buttons_enabled(True)
        self.cancel_scan_btn.setEnabled(False)
        self._update_sel_stats()

    def _set_status(self, text: str):
        self.status.setText(text)

    def _cancel_scan(self):
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.stop()
            self.status.setText("Cancelling scan…")
            self.cancel_scan_btn.setEnabled(False)
        else:
            InfoBar.info("Nothing to cancel", "No running scan.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _clear_table(self):
        self.table.setRowCount(0)
        self.preview.clear()

    def _collect_table_files(self, selected_only: bool) -> List[Tuple[str, str, str]]:
        if selected_only:
            rows: Iterable[int] = {idx.row() for idx in self.table.selectionModel().selectedRows()}
        else:
            rows = range(self.table.rowCount())

        files: List[Tuple[str, str, str]] = []
        for row in rows:
            name_item = self.table.item(row, 0)
            if not name_item:
                continue
            fn = name_item.text()
            rel = name_item.data(Qt.UserRole)
            typ = name_item.data(Qt.UserRole + 1)
            if rel is None and self.table.item(row, 1):
                rel = self.table.item(row, 1).text()
            if typ is None:
                typ = (self.table.item(row, 2).text() if self.table.item(row, 2) else "Text").lower()
            files.append((fn, rel, typ))
        return files

    # filters / selection
    def _apply_filter(self, _=None):
        text = (self.search_edit.text() or "").lower()
        ext_text = (self.ext_filter.text() or "").strip()
        exts = [e.strip().lower() for e in ext_text.split(",") if e.strip()]

        def match_ext(name: str) -> bool:
            if not exts:
                return True
            ln = name.lower()
            return any(ln.endswith(e) for e in exts)

        for r in range(self.table.rowCount()):
            fn = self.table.item(r, 0).text() if self.table.item(r, 0) else ""
            rel = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            show = ((text in fn.lower()) or (text in rel.lower()) or (text == "")) and match_ext(fn)
            self.table.setRowHidden(r, not show)

        self._update_sel_stats()

    def _select_all(self):
        self.table.selectAll()

    def _deselect_all(self):
        self.table.clearSelection()

    def _update_sel_stats(self):
        rows = [i.row() for i in self.table.selectionModel().selectedRows()]
        total_sel = len(rows)
        total_size = 0
        base = self.state.selected_folder
        for r in rows:
            name_item = self.table.item(r, 0)
            if not name_item:
                continue
            rel = name_item.data(Qt.UserRole)
            if rel is None:
                continue
            full = os.path.join(base, rel) if base else rel
            try:
                total_size += os.path.getsize(full)
            except Exception:
                pass
        self.sel_stats.setText(f"Selected: {total_sel} | Size: {hr_size(total_size)}")

    # exclusions
    def _exclude_selected(self):
        items = self.table.selectionModel().selectedRows()
        if not items:
            InfoBar.warning("No selection", "Please select file(s) to exclude.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
            return

        count = 0
        to_remove = []
        for idx in items:
            row = idx.row()
            name_item = self.table.item(row, 0)
            if not name_item:
                continue
            rel = name_item.data(Qt.UserRole)
            if rel is None:
                continue
            abs_path = os.path.abspath(os.path.join(self.state.selected_folder, rel))
            self.state.excluded_files_abs.add(abs_path)
            to_remove.append(row)
            count += 1

        for row in sorted(to_remove, reverse=True):
            self.table.removeRow(row)

        self.appwin.exclusions_page.refresh_ui_lists()
        self.appwin.save_settings()
        self.status.setText(f"Excluded {count} file(s)")
        InfoBar.success("Excluded", f"Excluded {count} file(s) from processing.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    # context menu
    def _show_table_menu(self, pos: QPoint):
        if self.table.rowCount() == 0:
            return
        index = self.table.indexAt(pos)
        if index.isValid() and not self.table.selectionModel().isSelected(index):
            self.table.selectRow(index.row())

        rows = [i.row() for i in self.table.selectionModel().selectedRows()]
        if not rows and index.isValid():
            rows = [index.row()]
            self.table.selectRow(index.row())
        if not rows:
            return

        r0 = rows[0]
        name_item = self.table.item(r0, 0)
        if not name_item:
            return
        rel = name_item.data(Qt.UserRole)
        if rel is None:
            return

        full = os.path.abspath(os.path.join(self.state.selected_folder, rel))

        menu = QMenu(self)
        act_open = QAction("Open", self)
        act_reveal = QAction("Reveal in Explorer", self)
        act_copy_full = QAction("Copy full path", self)
        act_copy_rel = QAction("Copy relative path", self)

        act_open.triggered.connect(lambda: self._open_path(full))
        act_reveal.triggered.connect(lambda: self._reveal_in_explorer(full))
        act_copy_full.triggered.connect(lambda: QApplication.clipboard().setText(full))
        act_copy_rel.triggered.connect(lambda: QApplication.clipboard().setText(rel))

        menu.addAction(act_open)
        menu.addAction(act_reveal)
        menu.addSeparator()
        menu.addAction(act_copy_full)
        menu.addAction(act_copy_rel)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _open_path(self, path: str):
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as e:
            InfoBar.error("Open failed", str(e), parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _reveal_in_explorer(self, path: str):
        try:
            if sys.platform == "win32":
                if os.path.exists(path) and os.path.isfile(path):
                    subprocess.run(["explorer", "/select,", path], check=False)
                else:
                    folder = path if os.path.isdir(path) else os.path.dirname(path)
                    if folder:
                        subprocess.run(["explorer", folder], check=False)
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", path], check=False)
            else:
                folder = path if os.path.isdir(path) else os.path.dirname(path)
                subprocess.run(["xdg-open", folder], check=False)
        except Exception as e:
            InfoBar.error("Reveal failed", str(e), parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    # generate / export
    def _ask_output_path(self) -> str:
        suggested = default_output_filename(self.state.selected_folder)
        out, _ = QFileDialog.getSaveFileName(
            self, "Save Combined Output As",
            os.path.join(self.state.selected_folder or os.path.expanduser("~"), suggested),
            "Text files (*.txt);;All files (*.*)"
        )
        return out or ""

    def _generate_selected(self):
        if not self.table.selectionModel().hasSelection():
            InfoBar.warning("No selection", "Select some files first.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
            return
        out = self._ask_output_path()
        if not out:
            return
        files = self._collect_table_files(selected_only=True)
        self._start_process(files, out)

    def _generate_all(self):
        if self.table.rowCount() == 0:
            InfoBar.warning("No files", "There are no files to process.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
            return
        out = self._ask_output_path()
        if not out:
            return
        files = self._collect_table_files(selected_only=False)
        self._start_process(files, out)

    def _start_process(self, files: List[Tuple[str, str, str]], out_path: str):
        if self.state.auto_hide_outputs:
            self.state.excluded_files_abs.add(os.path.abspath(out_path))
            self.appwin.save_settings()

        self.progress.setValue(0)
        self.status.setText("Generating combined output…")
        self._set_buttons_enabled(False)

        if self.proc_thread and self.proc_thread.isRunning():
            InfoBar.info("Busy", "A generation is already running.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
            return

        self.proc_thread = ProcessWorker(self.state, files, out_path)
        self.proc_thread.progress.connect(self._on_proc_progress)
        self.proc_thread.status.connect(self._set_status)
        self.proc_thread.done.connect(self._proc_done)
        self.proc_thread.start()

    def _on_proc_progress(self, proc: int, total: int):
        pct = int((proc / max(1, total)) * 100)
        self.progress.setValue(pct)

    def _proc_done(self, ok: bool, path: str, err: str):
        self._set_buttons_enabled(True)
        self.progress.setValue(100 if ok else 0)
        if ok:
            self.last_output_path = path
            self.copy_output_btn.setEnabled(True)
            self.status.setText("Output generation complete")
            InfoBar.success("Saved", f"Combined output saved to:\n{path}", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT, duration=3000)
        else:
            self.status.setText("Failed to generate output")
            InfoBar.error("Error", err or "Failed to generate combined output.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _copy_last_output(self):
        if not self.last_output_path or not os.path.exists(self.last_output_path):
            InfoBar.info("Nothing to copy", "No recent output found.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
            return
        try:
            with open(self.last_output_path, "r", encoding="utf-8", errors="replace") as f:
                QApplication.clipboard().setText(f.read())
            InfoBar.success("Copied", "Output copied to clipboard.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
        except Exception as e:
            InfoBar.error("Copy failed", str(e), parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _cancel_process(self):
        if self.proc_thread and self.proc_thread.isRunning():
            self.proc_thread.cancel()
            self.status.setText("Cancelling process…")
        else:
            InfoBar.info("Nothing to cancel", "No running process.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _export_tree(self):
        if not self.state.selected_folder:
            InfoBar.warning("No folder", "Please select a folder first.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
            return

        base = os.path.splitext(default_output_filename(self.state.selected_folder))[0] + "_tree.txt"
        out, _ = QFileDialog.getSaveFileName(
            self, "Save File Tree As",
            os.path.join(self.state.selected_folder, base),
            "Text files (*.txt);;All files (*.*)"
        )
        if not out:
            return

        if self.state.auto_hide_outputs:
            self.state.excluded_files_abs.add(os.path.abspath(out))
            self.appwin.save_settings()

        style = "ascii" if self.opt_ascii.isChecked() else "unicode"
        md = bool(self.opt_markdown.isChecked())
        sizes = bool(self.opt_sizes.isChecked())

        self._set_buttons_enabled(False)
        self.progress.setValue(0)
        self.status.setText("Building file tree…")

        self.tree_thread = TreeWorker(self.state, out, style, md, sizes)
        self.tree_thread.progress.connect(self._on_proc_progress)
        self.tree_thread.status.connect(self._set_status)
        self.tree_thread.done.connect(self._tree_done)
        self.tree_thread.start()

    def _tree_done(self, ok: bool, path: str, err: str):
        self._set_buttons_enabled(True)
        self.progress.setValue(100 if ok else 0)
        if ok:
            self.status.setText("File tree exported")
            InfoBar.success("Saved", f"File tree saved to:\n{path}", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT, duration=3000)
        else:
            self.status.setText("Failed to export file tree")
            InfoBar.error("Error", err or "Failed to export file tree.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _set_buttons_enabled(self, enabled: bool):
        for btn in self.findChildren(QPushButton):
            if btn is self.cancel_scan_btn:
                continue
            btn.setEnabled(enabled)

    # helpers: table + preview
    def _add_file_row(self, filename: str, rel_path: str, file_type: str):
        dir_rel = os.path.dirname(rel_path).replace("\\", "/")
        path_display = dir_rel if dir_rel not in ("", ".") else "root"

        typ_role = (file_type or "").strip().lower()
        if typ_role not in ("text", "binary"):
            abs_guess = os.path.join(self.state.selected_folder or "", rel_path)
            typ_role = "binary" if self._is_binary(abs_guess) else "text"

        abs_full = os.path.join(self.state.selected_folder or "", rel_path)
        type_display = self._friendly_type_for(filename, abs_full, typ_role)

        row = self.table.rowCount()
        self.table.insertRow(row)

        name_item = QTableWidgetItem(filename)
        path_item = QTableWidgetItem(path_display)
        type_item = QTableWidgetItem(type_display)

        name_item.setData(Qt.UserRole, rel_path)
        name_item.setData(Qt.UserRole + 1, typ_role)

        for it in (name_item, path_item, type_item):
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)

        self.table.setItem(row, 0, name_item)
        self.table.setItem(row, 1, path_item)
        self.table.setItem(row, 2, type_item)

    def _on_table_selection_changed(self):
        self._update_sel_stats()
        row = self.table.currentRow()
        if row < 0:
            self._preview_show_text("")
            return

        name_item = self.table.item(row, 0)
        if not name_item:
            self._preview_show_text("")
            return

        rel_path = name_item.data(Qt.UserRole) or ""
        file_type = (name_item.data(Qt.UserRole + 1) or "").lower()
        if not rel_path:
            self._preview_show_text("File not found.")
            return

        base = self.state.selected_folder or ""
        full_path = os.path.normpath(os.path.join(base, rel_path))

        if file_type == "binary":
            self._preview_show_text("[ This is a binary file and cannot be previewed. ]")
            return
        if not os.path.isfile(full_path):
            self._preview_show_text("File not found.")
            return
        self._preview_file(full_path)

    def _is_binary(self, abs_path: str) -> bool:
        try:
            with open(abs_path, "rb") as f:
                return b"\0" in f.read(4096)
        except Exception:
            return False

    def _coerce_row(self, row) -> tuple[str, str, str]:
        fn, rel, typ = "", "", ""
        if isinstance(row, dict):
            rel = row.get("rel") or row.get("relative_path") or row.get("path") or ""
            fn = row.get("name") or (os.path.basename(rel) if rel else "")
            typ = (row.get("type") or "").lower()
        elif isinstance(row, (list, tuple)):
            if len(row) >= 3:
                a, b, c = row[0], row[1], row[2]
            elif len(row) == 2:
                a, b = row[0], row[1]; c = ""
            else:
                return "", "", ""
            if (isinstance(a, str) and (os.sep in a or "/" in a)) and not (os.sep in b or "/" in b):
                rel = a; fn = b or os.path.basename(a)
            else:
                fn = a or os.path.basename(b) if isinstance(b, str) else ""
                rel = b if isinstance(b, str) else ""
            typ = (c or "").lower()
        else:
            return "", "", ""

        if rel:
            base = os.path.basename(rel)
            if base.lower() != fn.lower():
                rel = os.path.normpath(os.path.join(rel, fn))
        else:
            rel = fn

        if not typ:
            abs_path = os.path.join(self.state.selected_folder or "", rel)
            typ = "binary" if self._is_binary(abs_path) else "text"
        return fn, rel, typ

    def _preview_show_text(self, text: str):
        self.preview.setPlainText(text)

    def _preview_file(self, path: str):
        try:
            try:
                sz = os.path.getsize(path)
            except OSError:
                sz = None

            if sz is not None and sz > PREVIEW_MAX_BYTES:
                mb = PREVIEW_MAX_BYTES / (1024 * 1024)
                self._preview_show_text(f"[Preview disabled: file exceeds {mb:.1f} MB]")
                return

            enc = detect_file_encoding(path) or "utf-8"
            with open(path, "r", encoding=enc, errors="replace") as f:
                content = f.read(PREVIEW_CHUNK_SIZE)

            base = os.path.basename(path).lower()
            ext = os.path.splitext(base)[1].lower()
            treat_plain = (base == ".gitignore") or (ext in {".txt", ""})

            if not HAVE_PYGMENTS or treat_plain:
                self._preview_show_text(content)
                return

            try:
                lexer = guess_lexer_for_filename(path, content)
            except Exception:
                self._preview_show_text(content)
                return

            fmt = HtmlFormatter(style="monokai", linenos=True, noclasses=False)
            css = fmt.get_style_defs('.highlight')
            css_fix = """
                .highlight { background: transparent; color: #ddd; }
                .highlight pre { margin: 0; }
                .linenos { opacity: .6; }
            """
            html_code = highlight(content, lexer, fmt)
            self.preview.setHtml(f"<style>{css}\n{css_fix}</style>{html_code}")
        except Exception as e:
            self._preview_show_text(f"Error reading file:\n{e}")

    def _friendly_type_for(self, filename: str, abs_path: str, text_or_binary: str) -> str:
        name = filename.lower()
        root, ext = os.path.splitext(name)
        if ext in self._EXT_TYPE_MAP:
            return self._EXT_TYPE_MAP[ext]
        if name in self._NAME_TYPE_MAP:
            return self._NAME_TYPE_MAP[name]
        if root in self._NAME_TYPE_MAP and not ext:
            return self._NAME_TYPE_MAP[root]
        return "Binary" if text_or_binary == "binary" else "Text"
