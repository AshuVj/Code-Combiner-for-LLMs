# src/utils/logger.py

import logging
from pathlib import Path
from platformdirs import user_log_dir

APP_NAME = "FileCombinerApp"
APP_AUTHOR = "AshutoshVijay"  # adjust if you want

def setup_logger():
    try:
        log_dir = Path(user_log_dir(appname=APP_NAME, appauthor=APP_AUTHOR))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"

        logger = logging.getLogger(APP_NAME)
        logger.setLevel(logging.INFO)

        # Avoid duplicate handlers if reimported
        if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setLevel(logging.INFO)
            fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            fh.setFormatter(fmt)
            logger.addHandler(fh)

        return logger
    except Exception:
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(APP_NAME)

logger = setup_logger()
