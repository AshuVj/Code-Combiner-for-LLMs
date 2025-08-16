# src/ui_qt/main_window_qt.py
from __future__ import annotations

import os
import sys
import re
import time
import subprocess
import json
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Set, Iterable, Dict

from PySide6.QtCore import Qt, QThread, Signal, QSize, QPoint, QUrl
from PySide6.QtGui import (
    QIcon, QFont, QTextOption, QAction, QShortcut, QKeySequence, QDesktopServices
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
    QSplitter, QListWidget, QListWidgetItem, QTextEdit, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QFrame, QProgressBar, QPushButton,
    QLineEdit, QCheckBox, QMenu, QDialog, QDialogButtonBox, QComboBox
)

from qfluentwidgets import (
    FluentWindow, setTheme, Theme, NavigationItemPosition, FluentIcon,
    PrimaryPushButton, PushButton, InfoBar, InfoBarPosition, LineEdit, ComboBox, SwitchButton, MessageBox
)

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# --- Optional syntax highlighting (graceful if missing) ---
try:
    from pygments import highlight
    from pygments.lexers import guess_lexer_for_filename
    from pygments.formatters import HtmlFormatter
    HAVE_PYGMENTS = True
except Exception:
    HAVE_PYGMENTS = False

from pathspec import PathSpec

# --- Project imports ---
from src.core.file_scanner import FileScanner
from src.core.file_processor import FileProcessor
from src.core.settings_manager import SettingsManager
from src.core.tree_exporter import TreeExporter
from src.utils.encoding_detector import detect_file_encoding
from src.utils.logger import logger
from src.utils.prefs import load_prefs, save_prefs
from src.config import (
    EXCLUDED_FOLDER_NAMES_DEFAULT, PREVIEW_CHUNK_SIZE, PREVIEW_MAX_BYTES,
    PROCESS_MAX_BYTES, WINDOW_TITLE
)
try:
    from src.config import (
        EXCLUDED_FOLDER_NAMES_DEFAULT, PREVIEW_CHUNK_SIZE, PREVIEW_MAX_BYTES,
        PROCESS_MAX_BYTES, PREDEFINED_EXCLUDED_FILES, WINDOW_TITLE
    )
except Exception:
    # Fallbacks so the editor doesn’t scream if config is mid-edit
    EXCLUDED_FOLDER_NAMES_DEFAULT = {"node_modules", ".git", ".venv", "__pycache__"}
    PREVIEW_CHUNK_SIZE = 120_000
    PREVIEW_MAX_BYTES = 2_000_000
    PROCESS_MAX_BYTES = 50_000_000
    PREDEFINED_EXCLUDED_FILES = {
        "*.pyc", "*.pyo", "*.class", ".DS_Store", "Thumbs.db", "combined_output.txt"
    }
    WINDOW_TITLE = "Code Combiner for LLMs"
# =======================
# Shared App State
# =======================

@dataclass
class AppState:
    selected_folder: str = ""
    # show everything by default; folder-name excludes are opt-in via toggle
    excluded_folders: Set[str] = field(default_factory=set)             # relative to selected_folder
    excluded_folder_names: Set[str] = field(default_factory=set)        # start empty; toggle can add defaults
    excluded_file_patterns: Set[str] = field(default_factory=set)
    excluded_files_abs: Set[str] = field(default_factory=set)           # absolute paths

    # toggles
    apply_gitignore: bool = True
    use_default_folder_names: bool = False
    auto_hide_outputs: bool = False

    scanner: Optional[FileScanner] = None
    processor: Optional[FileProcessor] = None
    settings_mgr: Optional[SettingsManager] = None


# =======================
# Helpers
# =======================

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

class QtCancelEvent:
    def __init__(self):
        self._flag = False
    def is_set(self) -> bool:
        return self._flag
    def set(self):
        self._flag = True


# =======================
# Threads / Workers
# =======================

class ScanWorker(QThread):
    batch = Signal(list)                 # List[Tuple[str, str, str]]
    progress = Signal(int, int)          # processed, total
    status = Signal(str)
    finishedOk = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        st = self.state
        if not st.scanner:
            self.status.emit("Scanner not initialized.")
            self.finishedOk.emit()
            return

        # Configure scanner from state/toggles
        st.scanner.excluded_folders = set(st.excluded_folders)
        st.scanner.excluded_file_patterns = set(st.excluded_file_patterns)
        st.scanner.excluded_files = set(st.excluded_files_abs)
        st.scanner.apply_gitignore = bool(st.apply_gitignore)
        st.scanner.excluded_folder_names = set(EXCLUDED_FOLDER_NAMES_DEFAULT) if st.use_default_folder_names else set()

        # Pass 1: count
        total = 0
        for _ in st.scanner.yield_files():
            if self._stop:
                self.status.emit("Scan cancelled.")
                self.finishedOk.emit()
                return
            total += 1

        if total == 0:
            self.status.emit("No files found.")
            self.finishedOk.emit()
            return

        # Pass 2: stream
        processed = 0
        batch: List[Tuple[str, str, str]] = []
        chunk_size = 180

        for item in st.scanner.yield_files():
            if self._stop:
                self.status.emit("Scan cancelled.")
                break
            batch.append(item)
            processed += 1
            if len(batch) >= chunk_size:
                self.batch.emit(batch.copy())
                batch.clear()
                self.progress.emit(processed, total)
                self.status.emit(f"Scanning… {processed}/{total}")
                time.sleep(0.003)

        if not self._stop and batch:
            self.batch.emit(batch.copy())
            self.progress.emit(processed, total)
            self.status.emit(f"Scan complete. Found {processed} files.")

        self.finishedOk.emit()


class ProcessWorker(QThread):
    progress = Signal(int, int)
    status = Signal(str)
    done = Signal(bool, str, str)    # ok, out_path, err
    def __init__(self, state: AppState, files: List[Tuple[str, str, str]], out_path: str):
        super().__init__()
        self.state = state
        self.files = files
        self.out_path = out_path
        self.cancel_event = QtCancelEvent()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        st = self.state
        if not st.processor:
            self.done.emit(False, self.out_path, "Processor not initialized.")
            return

        def cb(proc, total):
            self.progress.emit(proc, max(1, total))
            self.status.emit(f"Processing file {proc}/{total}")

        try:
            ok = st.processor.process_files(self.files, self.out_path, cb, self.cancel_event)
            if ok:
                self.done.emit(True, self.out_path, "")
            else:
                self.done.emit(False, self.out_path, "Failed to generate combined output.")
        except Exception as e:
            self.done.emit(False, self.out_path, str(e))


class TreeWorker(QThread):
    progress = Signal(int, int)
    status = Signal(str)
    done = Signal(bool, str, str)  # ok, out_path, err

    def __init__(self, state: AppState, out_path: str, style: str, markdown: bool, sizes: bool):
        super().__init__()
        self.state = state
        self.out_path = out_path
        self.style = style
        self.markdown = markdown
        self.sizes = sizes

        # gitignore spec (respect toggle)
        self._git_spec = None
        gi = os.path.join(self.state.selected_folder or "", ".gitignore")
        if self.state.apply_gitignore and gi and os.path.isfile(gi):
            try:
                with open(gi, "r", encoding="utf-8", errors="ignore") as f:
                    self._git_spec = PathSpec.from_lines("gitwildmatch", f)
            except Exception:
                self._git_spec = None

    def _ignored_by_git(self, rel_path: str) -> bool:
        if not self.state.apply_gitignore or not self._git_spec:
            return False
        try:
            return self._git_spec.match_file(rel_path)
        except Exception:
            return False

    def _filtered_walk(self, root: str):
        """Strict exclusion-obeying os.walk that mirrors table view logic."""
        st = self.state
        base = os.path.abspath(root)
        for curr, dirs, files in os.walk(base):
            rel_dir = os.path.relpath(curr, base)
            if rel_dir == ".":
                rel_dir = ""

            # prune dirs by toggle-able default names + explicit rel paths + .gitignore
            dirs[:] = [
                d for d in dirs
                if not (
                    (st.use_default_folder_names and d in EXCLUDED_FOLDER_NAMES_DEFAULT) or
                    ((os.path.normpath(os.path.join(rel_dir, d)) if rel_dir else d) in st.excluded_folders) or
                    self._ignored_by_git(os.path.normpath(os.path.join(rel_dir, d)) if rel_dir else d)
                )
            ]

            keep_files = []
            for f in files:
                rel_file = os.path.normpath(os.path.join(rel_dir, f)) if rel_dir else f
                abs_f = os.path.join(curr, f)

                if self._ignored_by_git(rel_file):
                    continue

                if abs_f in st.excluded_files_abs:
                    continue

                # basic glob-like patterns only from user (no predefined auto-excludes)
                skip = False
                for pat in st.excluded_file_patterns:
                    if pat.startswith("*.") and f.lower().endswith(pat[1:].lower()):
                        skip = True; break
                    if pat.endswith("*") and f.lower().startswith(pat[:-1].lower()):
                        skip = True; break
                    if pat.startswith("*") and f.lower().endswith(pat[1:].lower()):
                        skip = True; break
                    if pat == f or pat == rel_file:
                        skip = True; break
                if not skip:
                    keep_files.append(f)

            yield curr, dirs, keep_files

    def _prefix(self, depth: int) -> str:
        if self.style == "ascii":
            return "|   " * (depth - 1) + ("|-- " if depth > 0 else "")
        else:
            return "│   " * (depth - 1) + ("├── " if depth > 0 else "")

    def run(self):
        st = self.state
        try:
            # Try project exporter first (if it already respects passed exclusions)
            used_fallback = False
            try:
                exporter = TreeExporter(
                    st.selected_folder,
                    excluded_folder_names=(EXCLUDED_FOLDER_NAMES_DEFAULT if st.use_default_folder_names else set()),
                    excluded_folders=st.excluded_folders,
                    excluded_file_patterns=st.excluded_file_patterns,
                    excluded_files=st.excluded_files_abs
                )
                total = max(1, exporter.count_nodes())

                def cb(done, tot):
                    self.progress.emit(done, max(1, tot))
                    self.status.emit(f"Generating tree {done}/{tot}")

                ok = False
                try:
                    ok = exporter.export(
                        self.out_path, style=self.style, progress=cb,
                        include_sizes=self.sizes, markdown=self.markdown, respect_exclusions=True
                    )
                except TypeError:
                    ok = exporter.export(
                        self.out_path, style=self.style, progress=cb,
                        include_sizes=self.sizes, markdown=self.markdown
                    )
                if not ok:
                    used_fallback = True
            except Exception:
                used_fallback = True

            if used_fallback:
                # Fallback: render from filtered os.walk mirroring table logic
                base = os.path.abspath(st.selected_folder)
                total = 0
                for _, _, files in self._filtered_walk(base):
                    total += 1 + len(files)
                total = max(1, total)

                done = 0
                with open(self.out_path, "w", encoding="utf-8", errors="replace") as w:
                    if self.markdown:
                        w.write("```text\n")

                    w.write(os.path.basename(base) + "/\n")
                    done += 1; self.progress.emit(done, total)

                    for curr, dirs, files in self._filtered_walk(base):
                        if curr == base:
                            pass
                        else:
                            depth = len(os.path.relpath(curr, base).split(os.sep))
                            w.write(self._prefix(depth) + os.path.basename(curr) + "/\n")
                            done += 1; self.progress.emit(done, total)

                        for f in sorted(files, key=str.lower):
                            p = os.path.join(curr, f)
                            if self.sizes:
                                try:
                                    s = os.path.getsize(p)
                                    line = f"{self._prefix((len(os.path.relpath(curr, base).split(os.sep)) if curr != base else 0)+1)}{f} ({hr_size(s)})\n"
                                except Exception:
                                    line = f"{self._prefix((len(os.path.relpath(curr, base).split(os.sep)) if curr != base else 0)+1)}{f}\n"
                            else:
                                line = f"{self._prefix((len(os.path.relpath(curr, base).split(os.sep)) if curr != base else 0)+1)}{f}\n"
                            w.write(line)
                            done += 1; self.progress.emit(done, total)

                    if self.markdown:
                        w.write("```\n")

            self.done.emit(True, self.out_path, "")
        except Exception as e:
            self.done.emit(False, self.out_path, str(e))


# =======================
# Small dialogs
# =======================

class PatternDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, label: str, show_gitignore: bool = True):
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


class CommandPalette(QDialog):
    def __init__(self, parent: "MainFluentWindow", commands: Dict[str, callable]):
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
        self.list.itemDoubleClicked.connect(lambda _: self._run_selected)
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


# =======================
# Pages
# =======================

class FilesPage(QWidget):
    """Files + Preview + Actions page."""
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

        # --- UI ---
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        title = QLabel("Files")
        title.setStyleSheet("font-size:20px; font-weight:600;")
        root.addWidget(title)

        # Row: Folder + Browse + Recent + Refresh + Cancel Scan
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

        # Row: Search + Type filter + toggles
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
        self.sw_outputs = SwitchButton("Auto-hide generated outputs", self)
        toggles.addWidget(self.sw_git); toggles.addWidget(self.sw_defaults); toggles.addWidget(self.sw_outputs)
        toggles.addStretch(1)
        root.addLayout(toggles)

        # Splitter: table (left) + preview (right)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)

        # Table
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["Filename", "Path", "Type"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        # Context menu
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_menu)

        left_lay.addWidget(self.table)

        # Row actions (left)
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

        # Preview (right)
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(8, 0, 0, 0)
        prev_title = QLabel("Preview"); prev_title.setStyleSheet("font-weight:600;")
        right_lay.addWidget(prev_title)
        self.preview = QTextEdit(self)
        self.preview.setReadOnly(True)
        self.preview.setWordWrapMode(QTextOption.NoWrap)
        mono = QFont("Consolas"); mono.setStyleHint(QFont.Monospace)
        self.preview.setFont(mono)
        right_lay.addWidget(self.preview, 1)
        split.addWidget(right)

        # Row: Generation / Export
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

        # Progress + status
        bar_row = QHBoxLayout()
        self.progress = QProgressBar(self); self.progress.setRange(0, 100)
        self.sel_stats = QLabel("")
        self.status = QLabel("Ready")
        bar_row.addWidget(self.progress, 1)
        bar_row.addWidget(self.sel_stats)
        bar_row.addWidget(self.status)
        root.addLayout(bar_row)

        # --- Signals ---
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

        # Toggle persistence
        self.sw_git.checkedChanged.connect(self._toggles_changed)
        self.sw_defaults.checkedChanged.connect(self._toggles_changed)
        self.sw_outputs.checkedChanged.connect(self._toggles_changed)

        # Shortcuts
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.search_edit.setFocus())
        QShortcut(QKeySequence("F5"), self, activated=self.refresh_files)
        QShortcut(QKeySequence("Delete"), self, activated=self._exclude_selected)
        QShortcut(QKeySequence("Ctrl+A"), self, activated=self._select_all)

        split.setSizes([700, 500])

    # ----- NEW/REPLACED METHODS START -----

    def _add_file_row(self, filename: str, rel_path: str, file_type: str):
        """Insert a row; show 'root' for Path when at project root and a friendly Type label."""
        # Path column: directory part or 'root'
        dir_rel = os.path.dirname(rel_path).replace("\\", "/")
        path_display = dir_rel if dir_rel not in ("", ".") else "root"

        # Keep internal role as 'text'/'binary' for preview logic
        typ_role = (file_type or "").strip().lower()
        if typ_role not in ("text", "binary"):
            abs_guess = os.path.join(self.state.selected_folder or "", rel_path)
            typ_role = "binary" if self._is_binary(abs_guess) else "text"

        # Friendly Type (Python/JSON/TOML/…)
        abs_full = os.path.join(self.state.selected_folder or "", rel_path)
        type_display = self._friendly_type_for(filename, abs_full, typ_role)

        row = self.table.rowCount()
        self.table.insertRow(row)

        name_item = QTableWidgetItem(filename)
        path_item = QTableWidgetItem(path_display)
        type_item = QTableWidgetItem(type_display)

        # Keep canonical data on the name cell for downstream logic
        name_item.setData(Qt.UserRole, rel_path)     # full relative path incl. filename
        name_item.setData(Qt.UserRole + 1, typ_role) # 'text' | 'binary' for preview

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
        """Very small heuristic: NUL byte in the first 4 KB => binary."""
        try:
            with open(abs_path, "rb") as f:
                return b"\0" in f.read(4096)
        except Exception:
            return False

    def _coerce_row(self, row) -> tuple[str, str, str]:
        """
        Accept (name, rel, type) OR (abs, rel, type) OR dict-like.
        Returns (filename, relative_path_including_filename, type_lowercase|'text'/'binary')
        """
        fn, rel, typ = "", "", ""

        if isinstance(row, dict):
            rel = row.get("rel") or row.get("relative_path") or row.get("path") or ""
            fn = row.get("name") or (os.path.basename(rel) if rel else "")
            typ = (row.get("type") or "").lower()
        elif isinstance(row, (list, tuple)):
            if len(row) >= 3:
                a, b, c = row[0], row[1], row[2]
            elif len(row) == 2:
                a, b = row[0], row[1]
                c = ""
            else:
                return "", "", ""
            # decide which looks like a path
            if (isinstance(a, str) and (os.sep in a or "/" in a)) and not (os.sep in b or "/" in b):
                # a is a path, b is a name
                rel = a
                fn = b or os.path.basename(a)
            else:
                # a is likely the name, b is the rel path
                fn = a or os.path.basename(b) if isinstance(b, str) else ""
                rel = b if isinstance(b, str) else ""
            typ = (c or "").lower()
        else:
            return "", "", ""

        # ensure rel includes the filename
        if rel:
            base = os.path.basename(rel)
            if base.lower() != fn.lower():
                # rel points to a folder; append filename
                rel = os.path.normpath(os.path.join(rel, fn))
        else:
            rel = fn

        # ensure type present
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

    # ----- NEW/REPLACED METHODS END -----

    # ----- toggles -----
    def _toggles_changed(self, *_):
        self.state.apply_gitignore = self.sw_git.isChecked()
        self.state.use_default_folder_names = self.sw_defaults.isChecked()
        self.state.auto_hide_outputs = self.sw_outputs.isChecked()
        # persist
        prefs = load_prefs()
        prefs["apply_gitignore"] = self.state.apply_gitignore
        prefs["use_default_folder_names"] = self.state.use_default_folder_names
        prefs["auto_hide_outputs"] = self.state.auto_hide_outputs
        save_prefs(prefs)
        self.refresh_files()

    # ----- Drag & drop -----
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

    # ----- lifecycle -----

    def bootstrap(self):
        self._init_from_prefs_or_settings()

    def _init_from_prefs_or_settings(self):
        prefs = load_prefs()
        # toggles
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

    # ----- recent folders -----

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

    # ----- folder / scan -----

    def set_folder(self, folder: str):
        folder = os.path.abspath(folder)
        self.state.selected_folder = folder
        self.state.scanner = FileScanner(folder)
        self.state.processor = FileProcessor(folder)
        self.state.settings_mgr = SettingsManager(folder)
        self.folder_edit.setText(folder)
        # Persist
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

        # push toggles to scanner
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
               # keep progress bar smooth
        self.scan_thread.progress.connect(self._on_scan_progress)
        self.scan_thread.status.connect(self._set_status)
        self.scan_thread.finishedOk.connect(self._scan_finished)
        self.scan_thread.start()

    def _append_batch(self, rows: list):
        # sorting during inserts can yield weird empty cells; pause it
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
            if rel is None:
                rel = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
            if typ is None:
                typ = (self.table.item(row, 2).text() if self.table.item(row, 2) else "Text").lower()
            files.append((fn, rel, typ))
        return files

    # ----- filters / selection -----

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

    # ----- exclusions -----

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

    # ----- context menu -----

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

    # ----- generate / export -----

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

    # ----- enable/disable -----

    def _set_buttons_enabled(self, enabled: bool):
        for btn in self.findChildren(QPushButton):
            if btn is self.cancel_scan_btn:
                continue
            btn.setEnabled(enabled)
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

    def _friendly_type_for(self, filename: str, abs_path: str, text_or_binary: str) -> str:
        """Return a pretty type label; fall back to Text/Binary."""
        name = filename.lower()
        root, ext = os.path.splitext(name)
        if ext in self._EXT_TYPE_MAP:
            return self._EXT_TYPE_MAP[ext]
        if name in self._NAME_TYPE_MAP:
            return self._NAME_TYPE_MAP[name]
        # special case: README, LICENSE without extension
        if root in self._NAME_TYPE_MAP and not ext:
            return self._NAME_TYPE_MAP[root]
        return "Binary" if text_or_binary == "binary" else "Text"


class ExclusionsPage(QWidget):
    """Exclusion settings page (folders, patterns, explicit files) + profiles (save/delete)."""
    def __init__(self, appwin: "MainFluentWindow"):
        super().__init__(parent=appwin)
        self.setObjectName("ExclusionsPage")
        self.appwin = appwin
        self.state = appwin.state

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Exclusions")
        title.setStyleSheet("font-size:20px; font-weight:600;")
        root.addWidget(title)

        # --- Profiles row ---
        prof_row = QHBoxLayout()
        prof_row.addWidget(QLabel("Profiles:"))
        self.profile_combo = ComboBox(self)
        self._reload_profiles_combo()
        apply_btn = PushButton("Apply")
        save_btn = PushButton("Save Current as Profile…")
        delete_btn = PushButton("Delete Profile")
        prof_row.addWidget(self.profile_combo)
        prof_row.addWidget(apply_btn)
        prof_row.addStretch(1)
        prof_row.addWidget(save_btn)
        prof_row.addWidget(delete_btn)
        root.addLayout(prof_row)

        # --- Folders (relative) ---
        root.addWidget(self._section_label("Excluded Folders (relative to root)"))
        folder_row = QHBoxLayout()
        self.folders_list = QListWidget(self)
        self.folders_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

        add_folder_btn = PrimaryPushButton("Add Folder…")
        remove_folder_btn = PushButton("Remove Selected")
        folder_btn_col = QVBoxLayout()
        folder_btn_col.addWidget(add_folder_btn)
        folder_btn_col.addWidget(remove_folder_btn)
        folder_btn_col.addStretch(1)

        folder_row.addWidget(self.folders_list, 1)
        folder_row.addLayout(folder_btn_col)
        root.addLayout(folder_row)

        # --- Patterns ---
        root.addWidget(self._section_label("Excluded File Patterns"))
        pattern_row = QHBoxLayout()
        self.patterns_list = QListWidget(self)
        self.patterns_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

        add_pattern_btn = PrimaryPushButton("Add Pattern")
        remove_pattern_btn = PushButton("Remove Selected")
        pattern_btn_col = QVBoxLayout()
        pattern_btn_col.addWidget(add_pattern_btn)
        pattern_btn_col.addWidget(remove_pattern_btn)
        pattern_btn_col.addStretch(1)

        pattern_row.addWidget(self.patterns_list, 1)
        pattern_row.addLayout(pattern_btn_col)
        root.addLayout(pattern_row)

        # --- Explicitly Excluded Files (absolute) – re-include ---
        root.addWidget(self._section_label("Explicitly Excluded Files"))
        files_row = QHBoxLayout()
        self.files_list = QListWidget(self)
        self.files_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

        files_btn_col = QVBoxLayout()
        sel_all_btn = PushButton("Select All")
        reincl_btn = PrimaryPushButton("Re-include Selected")
        files_btn_col.addWidget(sel_all_btn)   # Above Re-include
        files_btn_col.addWidget(reincl_btn)
        files_btn_col.addStretch(1)

        files_row.addWidget(self.files_list, 1)
        files_row.addLayout(files_btn_col)
        root.addLayout(files_row)

        # Optional: Ctrl+A selects all excluded files when that list has focus
        QShortcut(QKeySequence("Ctrl+A"), self.files_list, activated=self.files_list.selectAll)

        # --- Footnote about predefined patterns ---
        note = QLabel("Predefined patterns include: " + ", ".join(sorted(PREDEFINED_EXCLUDED_FILES)))
        note.setStyleSheet("color: gray;")
        root.addWidget(note)

        # --- Signals ---
        apply_btn.clicked.connect(self._apply_profile)
        save_btn.clicked.connect(self._save_profile)
        delete_btn.clicked.connect(self._delete_profile)

        add_folder_btn.clicked.connect(self._add_folder)
        remove_folder_btn.clicked.connect(self._remove_folders)

        add_pattern_btn.clicked.connect(self._add_pattern)
        remove_pattern_btn.clicked.connect(self._remove_patterns)

        sel_all_btn.clicked.connect(self.files_list.selectAll)
        reincl_btn.clicked.connect(self._reincl_files)

        # Initial fill
        self.refresh_ui_lists()
    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight:600; margin-top:8px;")
        return lbl

    def _reload_profiles_combo(self):
        prefs = load_prefs()
        profs = prefs.get("excl_profiles", {})
        names = ["(choose)"] + sorted(profs.keys())
        self.profile_combo.clear()
        self.profile_combo.addItems(names)

    def refresh_ui_lists(self):
        # folders
        self.folders_list.clear()
        for rel in sorted(self.state.excluded_folders, key=str.lower):
            self.folders_list.addItem(rel)

        # patterns
        self.patterns_list.clear()
        seen = set()
        for pat in sorted(self.state.excluded_file_patterns, key=str.lower):
            if pat not in seen:
                self.patterns_list.addItem(pat)
                seen.add(pat)

        # files
        self.files_list.clear()
        base = self.state.selected_folder or ""
        for ab in sorted(self.state.excluded_files_abs, key=str.lower):
            try:
                rel = os.path.relpath(ab, base) if base else ab
            except Exception:
                rel = ab
            self.files_list.addItem(rel)

    # ----- profiles -----

    def _apply_profile(self):
        name = self.profile_combo.currentText()
        if name == "(choose)" or not name:
            return
        prefs = load_prefs()
        profs = prefs.get("excl_profiles", {})
        p = profs.get(name)
        if not p:
            InfoBar.warning("Missing", "Profile not found.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
            return
        self.state.excluded_folder_names = set(p.get("folder_names", []))
        self.state.excluded_folders = set(p.get("folders", []))
        self.state.excluded_file_patterns = set(p.get("patterns", []))
        self.refresh_ui_lists()
        self.appwin.files_page.refresh_files()
        self.appwin.save_settings()
        InfoBar.success("Profile applied", name, parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _save_profile(self):
        text, ok = QInputSimple.get(self, "Save Profile", "Profile name:")
        if not ok or not text.strip():
            return
        name = text.strip()
        prefs = load_prefs()
        profs = prefs.get("excl_profiles", {})
        profs[name] = {
            "folder_names": sorted(self.state.excluded_folder_names),
            "folders": sorted(self.state.excluded_folders),
            "patterns": sorted(self.state.excluded_file_patterns),
        }
        prefs["excl_profiles"] = profs
        save_prefs(prefs)
        self._reload_profiles_combo()
        InfoBar.success("Saved", f"Profile '{name}' saved.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _delete_profile(self):
        name = self.profile_combo.currentText()
        if name == "(choose)" or not name:
            InfoBar.info("No selection", "Choose a profile to delete.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
            return
        msg = MessageBox("Delete Profile", f"Delete profile “{name}”? This cannot be undone.", self)
        if msg.exec() != MessageBox.StandardButton.Yes:
            return
        prefs = load_prefs()
        profs = prefs.get("excl_profiles", {})
        if name in profs:
            del profs[name]
            prefs["excl_profiles"] = profs
            save_prefs(prefs)
            self._reload_profiles_combo()
            InfoBar.success("Deleted", f"Profile '{name}' removed.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
        else:
            InfoBar.warning("Missing", "Profile not found on disk.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    # ----- actions -----

    def _add_folder(self):
        if not self.state.selected_folder:
            InfoBar.warning("No folder", "Pick a project folder first (Files page).", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
            return
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Exclude", self.state.selected_folder)
        if not folder:
            return
        abs_sel = os.path.abspath(folder)
        rel = os.path.normpath(os.path.relpath(abs_sel, self.state.selected_folder))
        if rel not in self.state.excluded_folders:
            self.state.excluded_folders.add(rel)
            self.refresh_ui_lists()
            self.appwin.files_page.refresh_files()
            self.appwin.save_settings()
            InfoBar.success("Folder excluded", rel, parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
        else:
            InfoBar.info("Already excluded", rel, parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _remove_folders(self):
        items = self.folders_list.selectedItems()
        if not items:
            InfoBar.info("No selection", "Select folder(s) to remove.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
            return
        removed = 0
        for it in items:
            rel = it.text()
            if rel in self.state.excluded_folders:
                self.state.excluded_folders.discard(rel)
                removed += 1
        self.refresh_ui_lists()
        self.appwin.files_page.refresh_files()
        self.appwin.save_settings()
        InfoBar.success("Removed", f"Removed {removed} folder(s).", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _add_pattern(self):
        txt, to_git, ok = PatternDialog.get(self, "Add Excluded Pattern", "Enter file pattern (e.g., *.log):", show_gitignore=True)
        if not ok or not txt:
            return
        pat = txt.strip()
        if pat not in self.state.excluded_file_patterns:
            self.state.excluded_file_patterns.add(pat)
            self.refresh_ui_lists()
            self.appwin.files_page.refresh_files()
            self.appwin.save_settings()
            # .gitignore write
            if to_git and self.state.selected_folder:
                try:
                    gi = os.path.join(self.state.selected_folder, ".gitignore")
                    existing = ""
                    if os.path.exists(gi):
                        with open(gi, "r", encoding="utf-8", errors="ignore") as f:
                            existing = f.read()
                    if pat not in existing:
                        with open(gi, "a", encoding="utf-8") as f:
                            if existing and not existing.endswith("\n"):
                                f.write("\n")
                            f.write(pat + "\n")
                except Exception:
                    pass
            InfoBar.success("Added", pat, parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
        else:
            InfoBar.info("Duplicate", "Pattern already in list.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _remove_patterns(self):
        items = self.patterns_list.selectedItems()
        if not items:
            InfoBar.info("No selection", "Select pattern(s) to remove.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
            return
        removed = 0
        for it in items:
            txt = it.text()
            if txt in self.state.excluded_file_patterns:
                self.state.excluded_file_patterns.discard(txt)
                removed += 1
        self.refresh_ui_lists()
        self.appwin.files_page.refresh_files()
        self.appwin.save_settings()
        InfoBar.success("Removed", f"Removed {removed} pattern(s).", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _reincl_files(self):
        items = self.files_list.selectedItems()
        if not items:
            InfoBar.info("No selection", "Select file(s) to re-include.", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
            return
        reincl = 0
        for it in items:
            rel = it.text()
            abs_path = os.path.abspath(os.path.join(self.state.selected_folder, rel))
            if abs_path in self.state.excluded_files_abs:
                self.state.excluded_files_abs.discard(abs_path)
                reincl += 1
        self.refresh_ui_lists()
        self.appwin.files_page.refresh_files()
        self.appwin.save_settings()
        InfoBar.success("Re-included", f"Re-included {reincl} file(s).", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)


class SettingsPage(QWidget):
    """Settings: theme + mica + UI scale."""
    def __init__(self, appwin: "MainFluentWindow"):
        super().__init__(parent=appwin)
        self.setObjectName("SettingsPage")
        self.appwin = appwin

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        title = QLabel("Settings")
        title.setStyleSheet("font-size:20px; font-weight:600;")
        root.addWidget(title)

        # theme
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme:"))
        self.theme_combo = ComboBox(self)
        self.theme_combo.addItems(["System", "Light", "Dark"])
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch(1)
        root.addLayout(theme_row)

        # effects
        mica_row = QHBoxLayout()
        self.mica_switch = SwitchButton("Mica effect", self)
        self.mica_switch.setChecked(True)
        mica_row.addWidget(self.mica_switch)
        mica_row.addStretch(1)
        root.addLayout(mica_row)

        # UI scale
        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("UI scale:"))
        self.scale_combo = ComboBox(self)
        self.scale_combo.addItems(["80%", "90%", "100%", "110%", "125%", "140%"])
        scale_row.addWidget(self.scale_combo)
        scale_row.addStretch(1)
        root.addLayout(scale_row)

        root.addStretch(1)

        # signals
        self.theme_combo.currentTextChanged.connect(self._on_theme_change)
        self.mica_switch.checkedChanged.connect(self._on_mica_toggle)
        self.scale_combo.currentTextChanged.connect(self._on_scale_change)

        prefs = load_prefs()
        theme_pref = prefs.get("theme_mode", "Dark")
        mica_pref = bool(prefs.get("mica_enabled", True))
        scale_pref = int(prefs.get("ui_scale", 100))

        self.theme_combo.setCurrentText(theme_pref if theme_pref in ["System", "Light", "Dark"] else "Dark")
        self.mica_switch.setChecked(mica_pref)
        label = f"{scale_pref}%"
        if label not in [self.scale_combo.itemText(i) for i in range(self.scale_combo.count())]:
            label = "100%"
        self.scale_combo.setCurrentText(label)

        self._on_theme_change(self.theme_combo.currentText())
        self._on_mica_toggle(self.mica_switch.isChecked())
        self._on_scale_change(self.scale_combo.currentText())

    def _on_theme_change(self, text: str):
        if text.lower() == "system":
            setTheme(Theme.AUTO)
        elif text.lower() == "light":
            setTheme(Theme.LIGHT)
        else:
            setTheme(Theme.DARK)
        prefs = load_prefs()
        prefs["theme_mode"] = text
        save_prefs(prefs)

    def _on_mica_toggle(self, on: bool):
        self.appwin.setMicaEffectEnabled(bool(on))
        prefs = load_prefs()
        prefs["mica_enabled"] = bool(on)
        save_prefs(prefs)

    def _on_scale_change(self, label: str):
        try:
            pct = int(label.strip("%"))
        except Exception:
            pct = 100
        self.appwin.apply_ui_scale(pct)
        prefs = load_prefs()
        prefs["ui_scale"] = pct
        save_prefs(prefs)


class AboutPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("AboutPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        title = QLabel("About")
        title.setStyleSheet("font-size:20px; font-weight:600;")
        root.addWidget(title)
        t = QLabel(
            "Code Combiner for LLMs — Fluent UI (Win11) port\n"
            "© 2025 Ashutosh Vijay — MIT License\n\n"
            "Built with PySide6 + QFluentWidgets."
        )
        t.setWordWrap(True)
        root.addWidget(t)
        root.addStretch(1)


# Simple input
class QInputSimple(QDialog):
    @staticmethod
    def get(parent, title, label):
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


# =======================
# Main Fluent Window
# =======================

class MainFluentWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        icon_path = resource_path("assets/app.ico")
        self.setWindowIcon(QIcon(icon_path))
        self.setWindowTitle(WINDOW_TITLE or "Code Combiner for LLMs")
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        prefs = load_prefs()
        theme_pref = prefs.get("theme_mode", "Dark")
        if theme_pref == "System":
            setTheme(Theme.AUTO)
        elif theme_pref == "Light":
            setTheme(Theme.LIGHT)
        else:
            setTheme(Theme.DARK)

        self.setMicaEffectEnabled(bool(prefs.get("mica_enabled", True)))

        self.state = AppState()
        # restore toggles from prefs (FilesPage also does it in bootstrap, but this keeps state correct early)
        self.state.apply_gitignore = bool(prefs.get("apply_gitignore", True))
        self.state.use_default_folder_names = bool(prefs.get("use_default_folder_names", False))
        self.state.auto_hide_outputs = bool(prefs.get("auto_hide_outputs", False))

        self.files_page = FilesPage(self)
        self.exclusions_page = ExclusionsPage(self)
        self.settings_page = SettingsPage(self)
        self.about_page = AboutPage()

        self.addSubInterface(self.files_page,      FluentIcon.FOLDER,  "Files",      NavigationItemPosition.TOP)
        self.addSubInterface(self.exclusions_page, FluentIcon.FILTER,  "Exclusions", NavigationItemPosition.TOP)
        self.addSubInterface(self.settings_page,   FluentIcon.SETTING, "Settings",   NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.about_page,      FluentIcon.INFO,    "About",      NavigationItemPosition.BOTTOM)

        self.ui_scale = int(prefs.get("ui_scale", 100))
        self.apply_ui_scale(self.ui_scale, first_time=True)

        self._restore_window_state()

        self.files_page.bootstrap()
        self.exclusions_page.refresh_ui_lists()

        # Command palette (Ctrl+Shift+P)
        QShortcut(QKeySequence("Ctrl+Shift+P"), self, activated=self._open_command_palette)

        InfoBar.success("Ready", "Welcome to your Fluent UI app.", parent=self, position=InfoBarPosition.TOP_RIGHT, duration=1500)

    # DnD at window level too
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.isdir(p):
                self.files_page.set_folder(p)
                self.load_settings()
                self.files_page.refresh_files()
                InfoBar.success("Folder selected", p, parent=self, duration=2000, position=InfoBarPosition.TOP_RIGHT)
                break

    # ----- Command palette -----

    def _open_command_palette(self):
        cmds = {
            "Refresh Files": self.files_page.refresh_files,
            "Browse Folder…": self.files_page.pick_folder,
            "Export File Tree": self.files_page._export_tree,
            "Generate Combined Output": self.files_page._generate_all,
            "Generate Selected Output": self.files_page._generate_selected,
            "Copy Last Output": self.files_page._copy_last_output,
            "Open Settings": lambda: self.switchTo(self.settings_page),
            "Open Exclusions": lambda: self.switchTo(self.exclusions_page),
            "Open Files": lambda: self.switchTo(self.files_page),
            "Toggle Mica": lambda: self.settings_page.mica_switch.setChecked(not self.settings_page.mica_switch.isChecked()),
        }
        CommandPalette(self, cmds).exec()

    # ----- UI scale -----

    def apply_ui_scale(self, percent: int, first_time: bool = False):
        percent = max(80, min(140, int(percent or 100)))
        self.ui_scale = percent
        base_px = int(13 * (percent / 100.0))
        app = QApplication.instance()
        if app:
            app.setStyleSheet(f"* {{ font-size: {base_px}px; }}")
        row_h = int(28 * (percent / 100.0))
        self.files_page.table.verticalHeader().setDefaultSectionSize(row_h)

    # ----- Settings load/save bridged for pages -----

    def save_settings(self):
        st = self.state
        if not st.settings_mgr:
            if st.selected_folder:
                st.settings_mgr = SettingsManager(st.selected_folder)
            else:
                return

        settings = {
            "selected_folder": st.selected_folder,
            "excluded_folders": list(st.excluded_folders),
            "excluded_folder_names": list(st.excluded_folder_names),
            "excluded_file_patterns": list(st.excluded_file_patterns),
            "excluded_files": [
                os.path.relpath(p, st.selected_folder) if st.selected_folder else p
                for p in st.excluded_files_abs
            ],
        }
        ok = st.settings_mgr.save_settings(settings)
        if ok:
            logger.info("Settings saved.")

        prefs = load_prefs()
        prefs["last_folder"] = st.selected_folder
        prefs["apply_gitignore"] = st.apply_gitignore
        prefs["use_default_folder_names"] = st.use_default_folder_names
        prefs["auto_hide_outputs"] = st.auto_hide_outputs
        save_prefs(prefs)

    def load_settings(self):
        st = self.state
        if not st.settings_mgr:
            if st.selected_folder:
                st.settings_mgr = SettingsManager(st.selected_folder)
            else:
                return

        s = st.settings_mgr.load_settings()
        if not s:
            return

        st.selected_folder = s.get("selected_folder", st.selected_folder) or st.selected_folder
        st.excluded_folders = set(s.get("excluded_folders", []))
        # NOTE: this is the *saved* folder-names set (from profiles); Files page toggle controls whether defaults are applied.
        st.excluded_folder_names = set(s.get("excluded_folder_names", []))
        st.excluded_file_patterns = set(s.get("excluded_file_patterns", []))

        excl_files_rel = s.get("excluded_files", [])
        abs_list = set()
        for rel in excl_files_rel:
            try:
                abs_list.add(os.path.abspath(os.path.join(st.selected_folder, rel)))
            except Exception:
                pass
        st.excluded_files_abs = abs_list

        if getattr(self, "exclusions_page", None):
            self.exclusions_page.refresh_ui_lists()

    # ----- Window state persistence -----

    def _restore_window_state(self):
        prefs = load_prefs()
        geom_hex = prefs.get("window_geometry_hex")
        maximized = bool(prefs.get("window_maximized", False))
        try:
            if geom_hex:
                self.restoreGeometry(bytes.fromhex(geom_hex))
        except Exception:
            pass
        if maximized:
            self.showMaximized()

    def _save_window_state(self):
        prefs = load_prefs()
        try:
            geom_hex = bytes(self.saveGeometry()).hex()
            prefs["window_geometry_hex"] = geom_hex
            prefs["window_maximized"] = self.isMaximized()
            save_prefs(prefs)
        except Exception:
            pass

    def closeEvent(self, event):
        self._save_window_state()
        super().closeEvent(event)


# =======================
# Entrypoint
# =======================

def launch_qt():
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainFluentWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(launch_qt())
