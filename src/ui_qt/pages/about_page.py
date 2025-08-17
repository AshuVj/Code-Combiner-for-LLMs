# src/ui_qt/pages/about_page.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

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
