# src/ui_qt/app_window.py
from __future__ import annotations
import os
import sys
from dataclasses import dataclass, field
from typing import Optional, Set

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication

from qfluentwidgets import FluentWindow, setTheme, Theme, NavigationItemPosition, FluentIcon, InfoBar, InfoBarPosition

from src.ui_qt.utils import resource_path
from src.ui_qt.pages.files_page import FilesPage
from src.ui_qt.pages.exclusions_page import ExclusionsPage
from src.ui_qt.pages.settings_page import SettingsPage
from src.ui_qt.pages.about_page import AboutPage
from src.ui_qt.dialogs.command_palette import CommandPalette

from src.core.settings_manager import SettingsManager
from src.utils.prefs import load_prefs, save_prefs
from src.config import WINDOW_TITLE

@dataclass
class AppState:
    selected_folder: str = ""
    excluded_folders: Set[str] = field(default_factory=set)
    excluded_folder_names: Set[str] = field(default_factory=set)
    excluded_file_patterns: Set[str] = field(default_factory=set)
    excluded_files_abs: Set[str] = field(default_factory=set)

    apply_gitignore: bool = True
    use_default_folder_names: bool = False
    auto_hide_outputs: bool = False

    scanner: Optional[object] = None
    processor: Optional[object] = None
    settings_mgr: Optional[SettingsManager] = None

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

    def apply_ui_scale(self, percent: int, first_time: bool = False):
        percent = max(80, min(140, int(percent or 100)))
        self.ui_scale = percent
        base_px = int(13 * (percent / 100.0))
        app = QApplication.instance()
        if app:
            app.setStyleSheet(f"* {{ font-size: {base_px}px; }}")
        row_h = int(28 * (percent / 100.0))
        self.files_page.table.verticalHeader().setDefaultSectionSize(row_h)

    # Settings load/save
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
        st.settings_mgr.save_settings(settings)

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

    # window state
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

def launch_qt():
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainFluentWindow()
    win.show()
    return app.exec()
