# src/ui_qt/pages/exclusions_page.py
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QListWidget,
    QAbstractItemView, QVBoxLayout as QVBLay
)
from qfluentwidgets import (
    PrimaryPushButton, PushButton, ComboBox, InfoBar, InfoBarPosition, MessageBox
)

from src.utils.prefs import load_prefs, save_prefs
from src.config import PREDEFINED_EXCLUDED_FILES
from src.ui_qt.dialogs.qinput_simple import QInputSimple
from src.ui_qt.dialogs.pattern_dialog import PatternDialog

# Import only for type checking to avoid runtime circular deps
if TYPE_CHECKING:
    from src.ui_qt.app_window import MainFluentWindow


class ExclusionsPage(QWidget):
    """Exclusion settings page (folders, patterns, explicit files) + profiles."""
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

        # Profiles
        prof_row = QHBoxLayout()
        prof_row.addWidget(QLabel("Profiles:"))
        self.profile_combo = ComboBox(self)
        self._reload_profiles_combo()
        apply_btn  = PushButton("Apply")
        save_btn   = PushButton("Save Current as Profile…")
        delete_btn = PushButton("Delete Profile")
        prof_row.addWidget(self.profile_combo)
        prof_row.addWidget(apply_btn)
        prof_row.addStretch(1)
        prof_row.addWidget(save_btn)
        prof_row.addWidget(delete_btn)
        root.addLayout(prof_row)

        # Folders (relative)
        root.addWidget(self._section_label("Excluded Folders (relative to root)"))
        folder_row = QHBoxLayout()
        self.folders_list = QListWidget(self)
        self.folders_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

        add_folder_btn    = PrimaryPushButton("Add Folder…")
        remove_folder_btn = PushButton("Remove Selected")
        folder_btn_col = QVBLay()
        folder_btn_col.addWidget(add_folder_btn)
        folder_btn_col.addWidget(remove_folder_btn)
        folder_btn_col.addStretch(1)

        folder_row.addWidget(self.folders_list, 1)
        folder_row.addLayout(folder_btn_col)
        root.addLayout(folder_row)

        # Patterns
        root.addWidget(self._section_label("Excluded File Patterns"))
        pattern_row = QHBoxLayout()
        self.patterns_list = QListWidget(self)
        self.patterns_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

        add_pattern_btn    = PrimaryPushButton("Add Pattern")
        remove_pattern_btn = PushButton("Remove Selected")
        pattern_btn_col = QVBLay()
        pattern_btn_col.addWidget(add_pattern_btn)
        pattern_btn_col.addWidget(remove_pattern_btn)
        pattern_btn_col.addStretch(1)

        pattern_row.addWidget(self.patterns_list, 1)
        pattern_row.addLayout(pattern_btn_col)
        root.addLayout(pattern_row)

        # Explicit files (absolute) – re-include
        root.addWidget(self._section_label("Explicitly Excluded Files"))
        files_row = QHBoxLayout()
        self.files_list = QListWidget(self)
        self.files_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

        files_btn_col = QVBLay()
        sel_all_btn = PushButton("Select All")
        reincl_btn  = PrimaryPushButton("Re-include Selected")
        files_btn_col.addWidget(sel_all_btn)
        files_btn_col.addWidget(reincl_btn)
        files_btn_col.addStretch(1)

        files_row.addWidget(self.files_list, 1)
        files_row.addLayout(files_btn_col)
        root.addLayout(files_row)

        # Shortcut: Ctrl+A selects all excluded files (when list has focus)
        QShortcut(QKeySequence("Ctrl+A"), self.files_list, activated=self.files_list.selectAll)

        note = QLabel("Predefined patterns include: " + ", ".join(sorted(PREDEFINED_EXCLUDED_FILES)))
        note.setStyleSheet("color: gray;")
        root.addWidget(note)

        # Signals
        apply_btn.clicked.connect(self._apply_profile)
        save_btn.clicked.connect(self._save_profile)
        delete_btn.clicked.connect(self._delete_profile)

        add_folder_btn.clicked.connect(self._add_folder)
        remove_folder_btn.clicked.connect(self._remove_folders)

        add_pattern_btn.clicked.connect(self._add_pattern)
        remove_pattern_btn.clicked.connect(self._remove_patterns)

        sel_all_btn.clicked.connect(self.files_list.selectAll)
        reincl_btn.clicked.connect(self._reincl_files)

        # Fill lists once
        self.refresh_ui_lists()

    # --- helpers/UI refresh ---
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

    # --- profiles ---
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
        self.state.excluded_folder_names   = set(p.get("folder_names", []))
        self.state.excluded_folders        = set(p.get("folders", []))
        self.state.excluded_file_patterns  = set(p.get("patterns", []))
        
        # BUGFIX: Save settings *before* refreshing files page
        self.appwin.save_settings()
        self.refresh_ui_lists()
        self.appwin.files_page.refresh_files()
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
            "folders":      sorted(self.state.excluded_folders),
            "patterns":     sorted(self.state.excluded_file_patterns),
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

    # --- actions ---
    def _add_folder(self):
        from PySide6.QtWidgets import QFileDialog
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
            
            # BUGFIX: Save settings *before* refreshing files page
            self.appwin.save_settings()
            self.refresh_ui_lists()
            self.appwin.files_page.refresh_files()
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
        
        # BUGFIX: Save settings *before* refreshing files page
        self.appwin.save_settings()
        self.refresh_ui_lists()
        self.appwin.files_page.refresh_files()
        InfoBar.success("Removed", f"Removed {removed} folder(s).", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)

    def _add_pattern(self):
        txt, to_git, ok = PatternDialog.get(self, "Add Excluded Pattern", "Enter file pattern (e.g., *.log):", show_gitignore=True)
        if not ok or not txt:
            return
        pat = txt.strip()
        if pat not in self.state.excluded_file_patterns:
            self.state.excluded_file_patterns.add(pat)

            # BUGFIX: Save settings *before* refreshing files page
            self.appwin.save_settings()
            self.refresh_ui_lists()
            self.appwin.files_page.refresh_files()
            
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
        
        # BUGFIX: Save settings *before* refreshing files page
        self.appwin.save_settings()
        self.refresh_ui_lists()
        self.appwin.files_page.refresh_files()
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
        
        # BUGFIX: Save settings *before* refreshing files page
        self.appwin.save_settings()
        self.refresh_ui_lists()
        self.appwin.files_page.refresh_files()
        InfoBar.success("Re-included", f"Re-included {reincl} file(s).", parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
