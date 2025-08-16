# src/config.py

import os

# Constants
PREDEFINED_EXCLUDED_FILES = {"combined_output.txt", "README.md"}

# More comprehensive default exclusions for common project folders
EXCLUDED_FOLDER_NAMES_DEFAULT = {
    "venv",
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    "build",
    "dist",
    "node_modules"
}

# Known binary file extensions to always exclude from content processing
BINARY_FILE_EXTENSIONS = {
    # Compiled/Object files
    ".pyc", ".pyo", ".pyd", ".o", ".a", ".so", ".lib", ".dll", ".exe",
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".tif", ".tiff", ".svg",
    # Archives
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".jar",
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    # Audio/Video
    ".mp3", ".wav", ".mp4", ".mov", ".avi",
    # Other
    ".db", ".sqlite3", ".dat", ".bin", ".lock", ".log"
}

SETTINGS_FILENAME = "exclusion_settings.json"

# Preview limits / chunking
PREVIEW_CHUNK_SIZE = 10240      # characters to read for preview
PREVIEW_MAX_BYTES = 2 * 1024 * 1024     # 2 MB

# Processing safeguard: skip huge files (write a note instead of content)
PROCESS_MAX_BYTES = 50 * 1024 * 1024    # 50 MB

# UI Constants
WINDOW_SIZE = "1200x800"
WINDOW_TITLE = "File Combiner Application"
