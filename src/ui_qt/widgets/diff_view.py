# src/ui_qt/widgets/diff_view.py
from __future__ import annotations

from typing import List
from PySide6.QtCore import Qt
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QTextBrowser, QFrame,
    QStackedLayout, QPlainTextEdit
)

from src.core.diff_engine import DiffRow, compute_diff, unified_patch

# Monospace stack
MONO = 'Consolas, "Cascadia Mono", "Fira Code", ui-monospace, monospace'


def _rgba(c: QColor) -> str:
    return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"


def _theme_colors(pal: QPalette) -> dict:
    """Return a small palette that works in both dark and light themes."""
    # detect dark via window color lightness
    dark = pal.color(QPalette.Window).lightness() < 128

    if dark:
        add_bg_chip = QColor(46, 160, 67, int(255 * 0.28))   # green chip
        del_bg_chip = QColor(248, 81, 73, int(255 * 0.28))   # red chip
        chg_bg_chip = QColor(250, 208, 0,  int(255 * 0.26))  # amber chip
        gutter_add  = QColor(63, 185, 80)                    # green bar
        gutter_del  = QColor(255, 99, 86)                    # red bar
        gutter_chg  = QColor(246, 193, 0)                    # amber bar
        meta_fg     = QColor(120, 170, 255)
    else:
        add_bg_chip = QColor(198, 248, 207, 255)             # soft green
        del_bg_chip = QColor(255, 205, 205, 255)             # soft red
        chg_bg_chip = QColor(255, 241, 174, 255)             # soft amber
        gutter_add  = QColor(31, 136, 61)
        gutter_del  = QColor(207, 34, 46)
        gutter_chg  = QColor(157, 118, 0)
        meta_fg     = QColor(9, 105, 218)

    return dict(
        dark=dark,
        add_bg_chip=add_bg_chip,
        del_bg_chip=del_bg_chip,
        chg_bg_chip=chg_bg_chip,
        gutter_add=gutter_add,
        gutter_del=gutter_del,
        gutter_chg=gutter_chg,
        meta_fg=meta_fg,
    )


# ---- Unified (git-style) syntax highlighter ----------------------------------
class UnifiedDiffHighlighter(QSyntaxHighlighter):
    def __init__(self, doc, colors: dict):
        super().__init__(doc)
        self.c = colors

    def highlightBlock(self, text: str) -> None:
        fmt = QTextCharFormat()
        # Headers and hunk markers
        if text.startswith("@@"):
            fmt.setForeground(self.c["meta_fg"])
            fmt.setFontWeight(QFont.Bold)
            self.setFormat(0, len(text), fmt)
            return
        if text.startswith(("diff ", "index ", "--- ", "+++ ")):
            fmt.setForeground(QColor("#6e7781"))
            self.setFormat(0, len(text), fmt)
            return
        # Added/Removed (leave foreground default for contrast; tint background lightly)
        if text.startswith("+") and not text.startswith("+++"):
            fmt.setBackground(self.c["add_bg_chip"])
            self.setFormat(0, len(text), fmt)
            return
        if text.startswith("-") and not text.startswith("---"):
            fmt.setBackground(self.c["del_bg_chip"])
            self.setFormat(0, len(text), fmt)
            return
        # Context lines unchanged


class DiffView(QWidget):
    """
    Diff viewer with two modes:
      - 'side'    : side-by-side, gutter accents for line changes + inline chips for char changes
      - 'unified' : git-style unified view with +/- prefixes
    """
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._left_text = ""
        self._right_text = ""
        self._opts = dict(ignore_ws=True, ignore_case=False, normalize_eol=True, inline=True)
        self._mode = "side"

        self._stack = QStackedLayout(self)

        # --- side-by-side table
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["L#", "Left", "R#", "Right"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(False)
        self.table.setWordWrap(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet(f"QTableWidget {{ font-family: {MONO}; font-size: 13px; }}")
        self._stack.addWidget(self.table)

        # --- unified editor
        self.unified = QPlainTextEdit(self)
        self.unified.setReadOnly(True)
        self.unified.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.unified.setStyleSheet(f"QPlainTextEdit {{ font-family: {MONO}; font-size: 13px; }}")
        self._highlighter = UnifiedDiffHighlighter(self.unified.document(), _theme_colors(self.palette()))
        self._stack.addWidget(self.unified)

        self._stack.setCurrentIndex(0)  # side-by-side by default

    # -- public API -------------------------------------------------------------
    def set_mode(self, mode: str):
        mode = (mode or "").lower()
        if mode not in ("side", "unified"):
            mode = "side"
        if mode != self._mode:
            self._mode = mode
            self._render_current()

    def set_texts(self, left_text: str, right_text: str, **opts):
        self._left_text = left_text or ""
        self._right_text = right_text or ""
        if opts:
            self._opts.update(opts)
        self._render_current()

    def copy_unified_to_clipboard(self, left_name: str = "left", right_name: str = "right"):
        from PySide6.QtWidgets import QApplication
        txt = unified_patch(self._left_text, self._right_text, left_name, right_name)
        QApplication.clipboard().setText(txt or "")

    # -- internals --------------------------------------------------------------
    def _render_current(self):
        colors = _theme_colors(self.palette())
        # refresh unified highlighter with up-to-date palette
        self._highlighter = UnifiedDiffHighlighter(self.unified.document(), colors)

        if self._mode == "unified":
            self._render_unified()
        else:
            self._render_side(colors)

    def _render_unified(self):
        patch = unified_patch(self._left_text, self._right_text, "left", "right")
        self.unified.setPlainText(patch)
        self._stack.setCurrentIndex(1)

    def _inline_css(self, colors: dict) -> str:
        """CSS injected into each QTextBrowser to style inline spans only."""
        add = _rgba(colors["add_bg_chip"])
        rem = _rgba(colors["del_bg_chip"])
        chg = _rgba(colors["chg_bg_chip"])
        return (
            "<style>"
            "  pre{margin:0; white-space:pre-wrap; word-wrap:break-word;}"
            f"  .ins,.add,.diff-add,[data-op='ins']{{background:{add};"
            "     border-radius:3px; padding:0 2px; }}"
            f"  .del,.rem,.diff-del,[data-op='del']{{background:{rem};"
            "     border-radius:3px; padding:0 2px; text-decoration:none; }}"
            f"  .rep,.chg,.change,.diff-chg,[data-op='chg']{{background:{chg};"
            "     border-radius:3px; padding:0 2px; }}"
            "</style>"
        )

    def _apply_gutter(self, w: QTextBrowser, tag: str, colors: dict):
        """Color only the gutter (left border) per line tag; keep background transparent."""
        if tag == "insert":
            col = colors["gutter_add"]
        elif tag == "delete":
            col = colors["gutter_del"]
        elif tag == "replace":
            col = colors["gutter_chg"]
        else:
            col = None

        base = f"font-family:{MONO}; font-size:13px; padding-left:8px; border-left: 4px solid transparent; background: transparent;"
        if col is not None:
            w.setStyleSheet(base + f" border-left-color: rgb({col.red()},{col.green()},{col.blue()});")
        else:
            w.setStyleSheet(base)

    def _render_side(self, colors: dict):
        rows = compute_diff(self._left_text, self._right_text, **self._opts)
        self.table.setRowCount(0)
        css = self._inline_css(colors)

        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # Line numbers
            lno = QTableWidgetItem("" if r.left_no is None else str(r.left_no))
            rno = QTableWidgetItem("" if r.right_no is None else str(r.right_no))
            lno.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            rno.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Left cell
            ltxt = QTextBrowser()
            ltxt.setFrameShape(QFrame.NoFrame)
            ltxt.setOpenExternalLinks(False)
            ltxt.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            ltxt.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            ltxt.setMaximumHeight(1200000)
            ltxt.setHtml(f"{css}<pre>{(r.left_html or '')}</pre>")
            self._apply_gutter(ltxt, r.tag, colors)

            # Right cell
            rtxt = QTextBrowser()
            rtxt.setFrameShape(QFrame.NoFrame)
            rtxt.setOpenExternalLinks(False)
            rtxt.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            rtxt.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            rtxt.setMaximumHeight(1200000)
            rtxt.setHtml(f"{css}<pre>{(r.right_html or '')}</pre>")
            self._apply_gutter(rtxt, r.tag, colors)

            self.table.setItem(row, 0, lno)
            self.table.setCellWidget(row, 1, ltxt)
            self.table.setItem(row, 2, rno)
            self.table.setCellWidget(row, 3, rtxt)

        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 68)
        self.table.setColumnWidth(2, 68)
        self._stack.setCurrentIndex(0)
