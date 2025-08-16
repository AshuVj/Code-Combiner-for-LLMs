import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from qfluentwidgets import (
    FluentWindow, setTheme, Theme,
    InfoBar, InfoBarPosition, NavigationItemPosition, FluentIcon
)

class Page(QWidget):
    def __init__(self, title: str, obj_name: str):
        super().__init__()
        self.setObjectName(obj_name)           # required before addSubInterface()
        lay = QVBoxLayout(self)
        lbl = QLabel(title)
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)

class AppWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Win11 Fluent Smoke Test")
        self.resize(1000, 700)

        # Win11 vibe
        setTheme(Theme.DARK)
        self.setMicaEffectEnabled(True)   # gracefully falls back if unsupported

        # Pages
        home = Page("Home", "home")
        settings = Page("Settings", "settings")
        about = Page("About", "about")

        # Left Navigation (like Windows Settings)
        self.addSubInterface(home,    FluentIcon.HOME,    "Home",    NavigationItemPosition.TOP)
        self.addSubInterface(settings,FluentIcon.SETTING, "Settings",NavigationItemPosition.TOP)
        self.addSubInterface(about,   FluentIcon.INFO,    "About",   NavigationItemPosition.BOTTOM)

        # Optional toast
        InfoBar.success(
            title='Loaded',
            content='QFluentWidgets is working.',
            position=InfoBarPosition.TOP_RIGHT,
            parent=self
        )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = AppWindow()
    w.show()
    sys.exit(app.exec())
