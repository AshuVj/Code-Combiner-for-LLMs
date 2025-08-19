import os
import sys
import logging
from datetime import datetime

# ---------- Logging ----------
LOG_PATH = os.path.join(os.path.dirname(__file__), "ui.log")

# Nuke any prior logging config so our INFO logs show up
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, encoding="utf-8")
    ],
    force=True,  # <= important
)
logging.info("=== App start %s ===", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
logging.info("Python %s", sys.version)

# ---------- Route Qt messages into logging ----------
from PySide6.QtCore import qInstallMessageHandler, QtMsgType

def _qt_msg_handler(mode, context, message):
    lg = logging.getLogger("qt")
    if mode == QtMsgType.QtDebugMsg:
        lg.debug(message)
    elif mode == QtMsgType.QtInfoMsg:
        lg.info(message)
    elif mode == QtMsgType.QtWarningMsg:
        lg.warning(message)
    elif mode == QtMsgType.QtCriticalMsg:
        lg.error(message)
    elif mode == QtMsgType.QtFatalMsg:
        lg.critical(message)

qInstallMessageHandler(_qt_msg_handler)

# Optional: silence super-noisy categories if you like
# os.environ["QT_LOGGING_RULES"] = "*.debug=false;qml=false"

# ---------- (Optional) “nuclear” mica block ----------
# If you still see hasMica=True in logs after theme changes, uncomment this block.
# try:
#     from qfluentwidgets import FluentWindow, FluentTitleBar
#     def _no_mica(*_a, **_k): return None
#     FluentWindow.setMicaEffectEnabled = _no_mica
#     FluentTitleBar.setMicaEffectEnabled = _no_mica
#     logging.info("Monkey-patched setMicaEffectEnabled -> no-op")
# except Exception as e:
#     logging.warning("Mica monkey-patch not applied: %s", e)

# ---------- Start app ----------
try:
    # Show exactly which files are being imported (helps catch stale copies)
    import inspect
    import src.ui_qt.app_window as app_window
    import src.ui_qt.theming as theming
    logging.info("Import app_window from: %s", inspect.getsourcefile(app_window))
    logging.info("Import theming   from: %s", inspect.getsourcefile(theming))
except Exception as e:
    logging.exception("Failed to import app modules: %s", e)
    raise

if __name__ == "__main__":
    try:
        from src.ui_qt.app_window import launch_qt
        rc = launch_qt()
        logging.info("App exited with code %s", rc)
        sys.exit(rc)
    except Exception as e:
        logging.exception("Fatal error running app: %s", e)
        raise
