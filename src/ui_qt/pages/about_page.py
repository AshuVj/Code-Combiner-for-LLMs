# src/ui_qt/pages/about_page.py
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Dict

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QScrollArea
)
from qfluentwidgets import PrimaryPushButton, PushButton, InfoBar, InfoBarPosition

from src.utils.sysinfo import build_report
from src.ui_qt.utils import resource_path
from src.ui_qt.widgets.busy_overlay import BusyOverlay

if TYPE_CHECKING:
    from src.ui_qt.app_window import MainFluentWindow


# ---------- worker ----------

class SysinfoWorker(QThread):
    done = Signal(dict)
    def run(self):
        try:
            report = build_report()
        except Exception:
            report = {}
        self.done.emit(report)


def _resource_path(relative_path: str) -> str:
    # Keep compatibility wrapper but delegate to shared util
    return resource_path(relative_path)


# ---------- page ----------

class AboutPage(QWidget):
    def __init__(self, appwin: "MainFluentWindow"):
        super().__init__(parent=appwin)
        self.setObjectName("AboutPage")
        self.appwin = appwin

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        # Header with LARGER icon
        header = QHBoxLayout()
        icon_label = QLabel(self)
        icon_label.setFixedSize(128, 128)
        icon_label.setScaledContents(True)
        ico_path = _resource_path("assets/app.ico")
        if os.path.exists(ico_path):
            pix = QPixmap(ico_path)
            if not pix.isNull():
                icon_label.setPixmap(pix)
                self.setWindowIcon(QIcon(ico_path))

        titles = QVBoxLayout()
        title = QLabel("Code Combiner for LLMs")
        title.setStyleSheet("font-size:24px; font-weight:700;")
        subtitle = QLabel("Everything you need to prep code for LLMs — themed UI, diff tools, and rich system info.")
        subtitle.setStyleSheet("color:gray;")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        titles.addStretch(1)

        header.addWidget(icon_label)
        header.addSpacing(12)
        header.addLayout(titles, 1)

        # Buttons
        btns = QHBoxLayout()
        self.refresh_btn = PushButton("Refresh")
        self.copy_btn = PrimaryPushButton("Copy report")
        btns.addStretch(1)
        btns.addWidget(self.refresh_btn)
        btns.addWidget(self.copy_btn)

        topwrap = QVBoxLayout()
        topwrap.addLayout(header)
        topwrap.addSpacing(6)
        topwrap.addLayout(btns)
        root.addLayout(topwrap)

        # Scroll section
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        container = QWidget(self.scroll)
        self.scroll.setWidget(container)
        cv = QVBoxLayout(container)
        cv.setContentsMargins(0, 12, 0, 0)

        # System table
        self.sys_table = QTableWidget(0, 2, self)
        self.sys_table.setHorizontalHeaderLabels(["Property", "Value"])
        self._setup_table_basic(self.sys_table)
        self.sys_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.sys_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        cv.addWidget(QLabel("System"))
        cv.addWidget(self.sys_table)

        # GPU table
        self.gpu_table = QTableWidget(0, 4, self)
        self.gpu_table.setHorizontalHeaderLabels(["Name", "Driver", "VRAM", "Vendor"])
        self._setup_table_basic(self.gpu_table)
        for i in range(4):
            self.gpu_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.gpu_table.horizontalHeader().setStretchLastSection(True)
        cv.addWidget(QLabel("GPU"))
        cv.addWidget(self.gpu_table)

        # Tools table
        self.tools_table = QTableWidget(0, 4, self)
        self.tools_table.setHorizontalHeaderLabels(["Category", "Tool", "Version", "Path"])
        self._setup_table_basic(self.tools_table)
        self.tools_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tools_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tools_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tools_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        cv.addWidget(QLabel("Languages / Tools"))
        cv.addWidget(self.tools_table)

        cv.addStretch(1)
        root.addWidget(self.scroll, 1)

        # Busy overlay
        self.overlay = BusyOverlay(self)
        self.overlay.hide()

        # Wiring
        self.refresh_btn.clicked.connect(self.refresh_async)
        self.copy_btn.clicked.connect(self.copy_report)

        self._last_report: Dict[str, object] = {}
        self._worker: SysinfoWorker | None = None

        # First load
        self.refresh_async()

    # ---------- utils ----------

    def _setup_table_basic(self, t: QTableWidget):
        t.verticalHeader().setVisible(False)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.horizontalHeader().setStretchLastSection(False)

    # ---------- actions ----------

    def refresh_async(self):
        if self._worker and self._worker.isRunning():
            return  # ignore double-clicks
        self.refresh_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        self.overlay.show_message("Collecting system information…")

        self._worker = SysinfoWorker()
        self._worker.done.connect(self._on_report_ready)
        self._worker.start()

    def _on_report_ready(self, report: dict):
        self._last_report = report or {}
        self._fill_tables(self._last_report)
        self.overlay.stop()
        self.refresh_btn.setEnabled(True)
        self.copy_btn.setEnabled(True)
        InfoBar.success("Refreshed", "System inventory updated.",
                        parent=self.appwin, position=InfoBarPosition.TOP_RIGHT, duration=1200)

    def _fill_tables(self, report: dict):
        # System
        self.sys_table.setRowCount(0)
        for k, v in (report.get("System") or {}).items():
            r = self.sys_table.rowCount()
            self.sys_table.insertRow(r)
            self.sys_table.setItem(r, 0, QTableWidgetItem(k))
            self.sys_table.setItem(r, 1, QTableWidgetItem(str(v)))

        # GPUs
        self.gpu_table.setRowCount(0)
        for g in (report.get("GPUs") or []):
            r = self.gpu_table.rowCount()
            self.gpu_table.insertRow(r)
            self.gpu_table.setItem(r, 0, QTableWidgetItem(g.get("name", "")))
            self.gpu_table.setItem(r, 1, QTableWidgetItem(g.get("driver", "")))
            self.gpu_table.setItem(r, 2, QTableWidgetItem(g.get("vram", "")))
            self.gpu_table.setItem(r, 3, QTableWidgetItem(g.get("vendor", "")))

        # Tools
        self.tools_table.setRowCount(0)
        for cat in ["Languages & Runtimes", "Web / Package Managers", "Build Tools", "VCS"]:
            items = report.get(cat) or []
            for info in items:
                r = self.tools_table.rowCount()
                self.tools_table.insertRow(r)
                self.tools_table.setItem(r, 0, QTableWidgetItem(cat))
                self.tools_table.setItem(r, 1, QTableWidgetItem(info.get("name", "")))
                ver = info.get("version", "")
                ok = info.get("ok", False)
                ver_item = QTableWidgetItem(ver if ok else "—")
                if not ok:
                    ver_item.setForeground(Qt.red)
                self.tools_table.setItem(r, 2, ver_item)
                self.tools_table.setItem(r, 3, QTableWidgetItem(info.get("path", "")))

    def copy_report(self):
        from PySide6.QtWidgets import QApplication
        text = json.dumps(self._last_report, indent=2)
        QApplication.clipboard().setText(text)
        InfoBar.success("Copied", "Full report copied to clipboard.",
                        parent=self.appwin, position=InfoBarPosition.TOP_RIGHT)
