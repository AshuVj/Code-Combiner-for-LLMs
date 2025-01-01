# src/config.py

import os

# Constants
PREDEFINED_EXCLUDED_FILES = {"combined_output.txt", "README.md"}
EXCLUDED_FOLDER_NAMES_DEFAULT = {"venv"}
SETTINGS_FILENAME = "exclusion_settings.json"
LOG_FILENAME = os.path.join("logs", "file_combiner_app.log")
PREVIEW_CHUNK_SIZE = 10240  # Number of characters to read for preview

# UI Constants
WINDOW_SIZE = "1200x800"
WINDOW_TITLE = "File Combiner Application"
