# src/ui_qt/pages/settings_page.py
from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from qfluentwidgets import ComboBox, SwitchButton, setTheme, Theme
from src.utils.prefs import load_prefs, save_prefs

# Import only for type checking to avoid runtime circular deps
if TYPE_CHECKING:
    from src.ui_qt.app_window import MainFluentWindow


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

        # load prefs
        prefs = load_prefs()
        theme_pref = prefs.get("theme_mode", "Dark")
        mica_pref  = bool(prefs.get("mica_enabled", True))
        scale_pref = int(prefs.get("ui_scale", 100))

        self.theme_combo.setCurrentText(theme_pref if theme_pref in ["System", "Light", "Dark"] else "Dark")
        self.mica_switch.setChecked(mica_pref)
        label = f"{scale_pref}%"
        if label not in [self.scale_combo.itemText(i) for i in range(self.scale_combo.count())]:
            label = "100%"
        self.scale_combo.setCurrentText(label)

        # apply
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
