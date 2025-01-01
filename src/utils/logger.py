# src/utils/logger.py

import os
import logging
from pathlib import Path

def setup_logger():
    """
    Set up a minimal logger that writes to the user's AppData directory.
    """
    try:
        # Define the log directory within LOCALAPPDATA
        local_app_data = Path(os.getenv('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
        log_dir = local_app_data / 'FileCombinerApp' / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)  # Create the directory if it doesn't exist

        log_file = log_dir / 'app.log'

        # Configure the logger
        logger = logging.getLogger("FileCombinerApp")
        logger.setLevel(logging.INFO)  # Set to INFO for minimal logging

        # Create a file handler
        handler = logging.FileHandler(log_file, encoding='utf-8')
        handler.setLevel(logging.INFO)

        # Create a simple formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)

        # Add the handler to the logger if not already added
        if not logger.handlers:
            logger.addHandler(handler)

        return logger

    except Exception as e:
        # Fallback: Log to console if file logging fails
        logging.basicConfig(level=logging.INFO)
        logging.error(f"Failed to set up file logger: {e}")
        return logging.getLogger("FileCombinerApp")

# Initialize the logger
logger = setup_logger()
