from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from qfluentwidgets import ComboBox
from src.utils.prefs import load_prefs, save_prefs
from src.ui_qt.theming import AVAILABLE_THEMES

if TYPE_CHECKING:
    from src.ui_qt.app_window import MainFluentWindow

log = logging.getLogger("settings")

class SettingsPage(QWidget):
    def __init__(self, appwin: "MainFluentWindow"):
        super().__init__(parent=appwin)
        self.setObjectName("SettingsPage")
        self.appwin = appwin

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Settings")
        title.setStyleSheet("font-size:20px; font-weight:600;")
        root.addWidget(title)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme:"))
        self.theme_combo = ComboBox(self)
        self.theme_combo.addItems(AVAILABLE_THEMES)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch(1)
        root.addLayout(theme_row)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("UI scale:"))
        self.scale_combo = ComboBox(self)
        self.scale_combo.addItems(["80%", "90%", "100%", "110%", "125%", "140%"])
        scale_row.addWidget(self.scale_combo)
        scale_row.addStretch(1)
        root.addLayout(scale_row)

        root.addStretch(1)

        prefs = load_prefs()
        theme_pref = prefs.get("theme_mode", "Dark")
        if theme_pref not in AVAILABLE_THEMES:
            theme_pref = "Dark"
        self.theme_combo.setCurrentText(theme_pref)

        scale_pref = int(prefs.get("ui_scale", 100))
        label = f"{scale_pref}%"
        items = [self.scale_combo.itemText(i) for i in range(self.scale_combo.count())]
        if label not in items:
            label = "100%"
        self.scale_combo.setCurrentText(label)
        self._apply_scale_now(label)

        self.theme_combo.currentTextChanged.connect(self._on_theme_change)
        self.scale_combo.currentTextChanged.connect(self._on_scale_change)

    def _on_theme_change(self, name: str):
        log.info("SettingsPage: theme changed to '%s'", name)
        self.appwin.update_theme(name)
        prefs = load_prefs()
        prefs["theme_mode"] = name
        save_prefs(prefs)

    def _apply_scale_now(self, label: str):
        try:
            pct = int(label.strip("%"))
        except Exception:
            pct = 100
        log.info("SettingsPage: UI scale -> %s (%d%%)", label, pct)
        self.appwin.apply_ui_scale(pct)

    def _on_scale_change(self, label: str):
        self._apply_scale_now(label)
        prefs = load_prefs()
        try:
            prefs["ui_scale"] = int(label.strip("%"))
        except Exception:
            prefs["ui_scale"] = 100
        save_prefs(prefs)
