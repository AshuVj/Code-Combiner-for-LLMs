from __future__ import annotations
from typing import Dict, Optional, List
import logging

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, QTimer
from qfluentwidgets import setTheme, Theme, setThemeColor

log = logging.getLogger("theming")

# -----------------------------
# Public API
# -----------------------------

AVAILABLE_THEMES: List[str] = [
    "System",
    "Light",
    "Light – Porcelain",
    "Light – Cement",
    "Dark",
    "Space Black (beta)",
    "Blackhole Black (beta)",
    "Pitch Black (beta)",
]

# -----------------------------
# Palettes
# -----------------------------

_LIGHT_VARIANTS: Dict[str, Dict[str, str]] = {
    "Light": {
        "bg": "#F4F5F7", "pane": "#F9FAFB", "alt": "#EFF1F4",
        "grid": "#E1E5EA", "fg": "#111111", "head": "#EFF1F4", "accent": "#2563EB",
    },
    "Light – Porcelain": {
        "bg": "#F0F2F4", "pane": "#FFFFFF", "alt": "#ECEFF1",
        "grid": "#DDE2E6", "fg": "#121314", "head": "#ECEFF1", "accent": "#2563EB",
    },
    "Light – Cement": {
        "bg": "#ECECEF", "pane": "#FAFAFB", "alt": "#E6E7EA",
        "grid": "#D8DADE", "fg": "#111213", "head": "#E6E7EA", "accent": "#2563EB",
    },
}

_DARK_VARIANTS: Dict[str, Dict[str, str]] = {
    "Dark": {
        "page": "#1E1E1E", "alt": "#2A2A2A", "fg": "#EDEDED", "muted": "#A7B0BA",
        "grid": "#333333", "accent": "#3B82F6", "accent2": "#60A5FA",
    },
}

_PAGE_TINTS: Dict[str, Dict[str, str]] = {
    "Space Black (beta)": {
        "page": "#0E1113", "alt": "#15191E", "fg": "#E7ECF2", "muted": "#A7B0BA",
        "grid": "#262C33", "accent": "#3B82F6", "accent2": "#60A5FA",
    },
    "Blackhole Black (beta)": {
        "page": "#000000", "alt": "#0B0C0E", "fg": "#F2F5F7", "muted": "#B6BFC9",
        "grid": "#23282E", "accent": "#22C55E", "accent2": "#34D399",
    },
    "Pitch Black (beta)": {
        "page": "#050506", "alt": "#0E0F12", "fg": "#FFFFFF", "muted": "#C9CFD6",
        "grid": "#262A30", "accent": "#8B5CF6", "accent2": "#A78BFA",
    },
}

# -----------------------------
# Helpers
# -----------------------------

def _disable_effects(widget: QWidget | None):
    """Forcefully disables Mica/Acrylic effects where available."""
    if not widget:
        return
    for obj in (widget, getattr(widget, "titleBar", None), getattr(widget, "navigationInterface", None)):
        if obj and hasattr(obj, "setMicaEffectEnabled"):
            try:
                obj.setMicaEffectEnabled(False)
                log.info("EFFECTS: setMicaEffectEnabled(False) on %s", obj.metaObject().className())
            except Exception:
                pass
        if obj and hasattr(obj, "setAcrylicEnabled"):
            try:
                obj.setAcrylicEnabled(False)
                log.info("EFFECTS: setAcrylicEnabled(False) on %s", obj.metaObject().className())
            except Exception:
                pass

def _clear_styles(widget: QWidget | None) -> None:
    if widget:
        try:
            widget.setStyleSheet("")
        except Exception:
            pass

def _apply_css(widget: Optional[QWidget], css: str) -> None:
    if widget:
        widget.setAttribute(Qt.WA_StyledBackground, True)
        widget.setStyleSheet(css)

def _pages(window: Optional[QWidget]) -> list[QWidget]:
    if not window:
        return []
    names = ("files_page", "exclusions_page", "settings_page", "compare_page", "about_page")
    out = []
    for n in names:
        w = getattr(window, n, None)
        if isinstance(w, QWidget):
            out.append(w)
    return out

def _content_dark_css(p: Dict[str, str]) -> str:
    return f"""
QWidget {{ background: {p['page']}; color: {p['fg']}; }}
QPlainTextEdit, QTextEdit, QTextBrowser,
QLineEdit, QListWidget, QListView, QTreeWidget, QTreeView,
QTableWidget, QTableView, QComboBox, QMenu, QDialog {{
    background: {p['page']}; color: {p['fg']};
    border: 1px solid {p['grid']}; border-radius: 6px;
    selection-background-color: {p['accent']}; selection-color: #ffffff;
}}
QTableView, QTreeView, QTableWidget {{
    alternate-background-color: {p['alt']}; gridline-color: {p['grid']};
}}
QHeaderView::section {{
    background: {p['alt']}; color: {p['fg']}; border: 0px;
    border-bottom: 1px solid {p['grid']}; padding: 6px 8px;
}}
"""

def _content_light_css(p: Dict[str, str]) -> str:
    return f"""
QWidget {{ background: {p['bg']}; color: {p['fg']}; }}
QPlainTextEdit, QTextEdit, QTextBrowser,
QLineEdit, QListWidget, QListView, QTreeWidget, QTreeView,
QTableWidget, QTableView, QComboBox, QMenu, QDialog {{
    background: {p['pane']}; color: {p['fg']};
    border: 1px solid {p['grid']}; border-radius: 6px;
    selection-background-color: {p['accent']}; selection-color: #ffffff;
}}
QTableView, QTreeView, QTableWidget {{
    alternate-background-color: {p['alt']}; gridline-color: {p['grid']};
}}
QHeaderView::section {{
    background: {p['head']}; color: {p['fg']}; border: 0px;
    border-bottom: 1px solid {p['grid']}; padding: 6px 8px;
}}
"""

def _window_chrome_qss(bg: str, alt: str, fg: str, grid: str) -> str:
    return f"""
QLabel[styleClass="sectionHeader"] {{
    background: {alt};
    color: {fg};
    border-bottom: 1px solid {grid};
}}
QMenu, QToolTip {{
    background: {alt};
    color: {fg};
    border: 1px solid {grid};
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {bg};
    border: 1px solid {grid};
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {alt};
    min-width: 24px; min-height: 24px;
    border: 1px solid {grid};
    border-radius: 6px;
}}
"""

def _titlebar_qss(bg: str, fg: str, grid: str) -> str:
    return f"""
FluentTitleBar#titleBar {{
    background-color: {bg};
    color: {fg};
    border: 0px;
    border-bottom: 1px solid {grid};
}}
#titleBar QLabel, #titleBar QToolButton {{
    color: {fg};
    background: transparent;
    border: 0;
}}
"""

def _nav_qss(bg: str, alt: str, fg: str, grid: str, accent: str) -> str:
    return f"""
#navigationInterface {{
    background-color: {bg};
    border-right: 1px solid {grid};
}}
#navigationInterface NavigationPushButton, #navigationInterface QToolButton {{
    background-color: transparent;
    color: {fg};
    border: 0;
}}
#navigationInterface NavigationPushButton {{
    padding: 6px 10px;
}}
#navigationInterface NavigationPushButton:hover, #navigationInterface QToolButton:hover {{
    background-color: {alt};
}}
#navigationInterface NavigationPushButton:checked,
#navigationInterface NavigationPushButton[isActived="true"] {{
    background-color: {alt};
    border-left: 3px solid {accent};
}}
"""

def _peek(label: str, w: QWidget, expect_hex: str | None = None):
    ss = w.styleSheet() or ""
    head = ss[:180].replace("\n", " ")
    contains = expect_hex in ss if expect_hex else None
    cname = w.metaObject().className()
    oname = w.objectName()
    try:
        has_mica = bool(getattr(w, "isMicaEffectEnabled")()) if hasattr(w, "isMicaEffectEnabled") else None
    except Exception:
        has_mica = None
    log.info(
        "THEME: %s -> %s(objectName='%s') ss_len=%d mica=%s head='%s'%s",
        label, cname, oname, len(ss), has_mica,
        head,
        f" contains({expect_hex})={contains}" if expect_hex else ""
    )

def _reassert(label: str, w: QWidget | None, qss: str, expect_hex: str | None = None):
    """Apply now, then re-apply at 0ms and 150ms to beat late library styling."""
    if not w:
        return
    def apply_once(tag: str):
        try:
            w.setAttribute(Qt.WA_StyledBackground, True)
            w.setStyleSheet(qss)
            w.update()
            _peek(f"{label}:{tag}", w, expect_hex)
        except Exception as e:
            log.warning("THEME: reassert(%s) failed: %s", label, e)
    apply_once("now")
    QTimer.singleShot(0, lambda: apply_once("later0"))
    QTimer.singleShot(150, lambda: apply_once("later150"))

# -----------------------------
# Entry point
# -----------------------------

def apply_theme_by_name(name: str, window: Optional[QWidget] = None) -> None:
    """Apply theme colors and effects, with logs."""
    name = (name or "Dark").strip()
    if not window:
        return

    title_bar = getattr(window, "titleBar", None)
    nav = getattr(window, "navigationInterface", None)

    log.info("apply_theme_by_name(name=%s)", name)

    # Clear any prior per-instance styles
    for page in _pages(window):
        _clear_styles(page)
    _clear_styles(title_bar)
    _clear_styles(nav)
    window.setStyleSheet("")

    # Ensure objectNames are right (QSS anchors)
    if title_bar and not title_bar.objectName():
        title_bar.setObjectName("titleBar")
    if nav and not nav.objectName():
        nav.setObjectName("navigationInterface")

    # Base theme & effects off
    if name == "System":
        setTheme(Theme.AUTO)
        setThemeColor(QColor("#2563EB"))
        _disable_effects(window)
        _peek("window:system", window)
        if title_bar: _peek("titleBar:system", title_bar)
        if nav: _peek("nav:system", nav)
        return

    # Light family
    if name.startswith("Light"):
        setTheme(Theme.LIGHT)
        _disable_effects(window)
        spec = _LIGHT_VARIANTS.get(name, _LIGHT_VARIANTS["Light"])
        setThemeColor(QColor(spec["accent"]))

        # Content pages
        for page in _pages(window):
            _apply_css(page, _content_light_css(spec))

        # Window chrome (menus/scrollbars)
        _reassert("window", window, _window_chrome_qss(spec["bg"], spec["alt"], spec["fg"], spec["grid"]), spec["bg"])
        # Title bar / nav
        if title_bar:
            _reassert("titleBar", title_bar, _titlebar_qss(spec["bg"], spec["fg"], spec["grid"]), spec["bg"])
        if nav:
            _reassert("nav", nav, _nav_qss(spec["bg"], spec["alt"], spec["fg"], spec["grid"], spec["accent"]), spec["bg"])
        return

    # Stock Dark
    if name == "Dark":
        setTheme(Theme.DARK)
        _disable_effects(window)
        spec = _DARK_VARIANTS["Dark"]
        setThemeColor(QColor(spec["accent"]))

        for page in _pages(window):
            _apply_css(page, _content_dark_css(spec))

        _reassert("window", window, _window_chrome_qss(spec["page"], spec["alt"], spec["fg"], spec["grid"]), spec["page"])
        if title_bar:
            _reassert("titleBar", title_bar, _titlebar_qss(spec["page"], spec["fg"], spec["grid"]), spec["page"])
        if nav:
            _reassert("nav", nav, _nav_qss(spec["page"], spec["alt"], spec["fg"], spec["grid"], spec["accent"]), spec["page"])
        return

    # Custom ultra-dark variants
    spec = _PAGE_TINTS.get(name)
    if not spec:
        log.warning("apply_theme_by_name: unknown theme name '%s'", name)
        return

    setTheme(Theme.DARK)
    _disable_effects(window)
    setThemeColor(QColor(spec["accent"]))

    # Content pages
    for page in _pages(window):
        _apply_css(page, _content_dark_css(spec))

    # Window chrome + bars (with delayed reassert)
    _reassert("window", window, _window_chrome_qss(spec["page"], spec["alt"], spec["fg"], spec["grid"]), spec["page"])
    if title_bar:
        _reassert("titleBar", title_bar, _titlebar_qss(spec["page"], spec["fg"], spec["grid"]), spec["page"])
    if nav:
        _reassert("nav", nav, _nav_qss(spec["page"], spec["alt"], spec["fg"], spec["grid"], spec["accent"]), spec["page"])
