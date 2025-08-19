# src/utils/logger.py

import logging
import os
from pathlib import Path
from platformdirs import user_log_dir

APP_NAME = "Code Combiner for LLMs"
APP_AUTHOR = "AshutoshVijay"

def setup_logger():
    logger = logging.getLogger(APP_NAME)

    # Default: silence everything unless CC_DEBUG=1 is set
    if not os.environ.get("CC_DEBUG"):
        logger.setLevel(logging.CRITICAL)
        if not any(isinstance(h, logging.NullHandler) for h in logger.handlers):
            logger.addHandler(logging.NullHandler())
        logger.propagate = False
        return logger

    # Debug mode: write to user logs
    logger.setLevel(logging.INFO)
    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        log_dir = Path(user_log_dir(appname=APP_NAME, appauthor=APP_AUTHOR))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.debug.log"
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(fh)
    return logger

logger = setup_logger()
