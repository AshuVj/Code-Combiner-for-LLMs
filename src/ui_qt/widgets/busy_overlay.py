# src/ui_qt/widgets/busy_overlay.py
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QProgressBar

try:
    # QFluentWidgets spinner (if available)
    from qfluentwidgets import ProgressRing
    HAVE_RING = True
except Exception:
    HAVE_RING = False


class BusyOverlay(QFrame):
    """A lightweight, reusable overlay with spinner + message."""
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("BusyOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setWindowFlags(Qt.Widget)
        self.setStyleSheet("""
            #BusyOverlay {
                background: rgba(0,0,0,0.35);
                border: none;
            }
        """)
        self.hide()

        box = QVBoxLayout(self)
        box.setAlignment(Qt.AlignCenter)

        if HAVE_RING:
            self.spinner = ProgressRing(self)
            self.spinner.setFixedSize(QSize(56, 56))
        else:
            self.spinner = QProgressBar(self)
            self.spinner.setRange(0, 0)
            self.spinner.setFixedWidth(240)
        box.addWidget(self.spinner, 0, Qt.AlignHCenter)

        self.msg = QLabel("Working…", self)
        self.msg.setStyleSheet("font-size:15px; font-weight:600; color: white;")
        box.addSpacing(8)
        box.addWidget(self.msg, 0, Qt.AlignHCenter)

    def show_message(self, text: str = "Working…"):
        self.msg.setText(text)
        self._reposition()
        self.raise_()
        self.show()

    def stop(self):
        self.hide()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reposition()

    def _reposition(self):
        if not self.parent():
            return
        self.setGeometry(self.parent().rect())
