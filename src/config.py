# src/config.py

# App settings file name (per-project)
SETTINGS_FILENAME = "exclusion_settings.json"
# Nothing is hidden by default – user decides in the UI.
PREDEFINED_EXCLUDED_FILES: set[str] = {SETTINGS_FILENAME}

# Toggleable “common junk” folder names (exposed via checkbox on the Files page)
EXCLUDED_FOLDER_NAMES_DEFAULT = {
    "venv",
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    "build",
    "dist",
    "node_modules",
}

# Known binary file extensions (for preview/type)
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
    ".db", ".sqlite3", ".dat", ".bin", ".lock", ".log",
}

SETTINGS_FILENAME = "exclusion_settings.json"

# Preview limits / chunking
PREVIEW_CHUNK_SIZE = 10240                # characters for preview
PREVIEW_MAX_BYTES = 2 * 1024 * 1024       # 2 MB

# Processing safeguard: skip huge files (write a note)
PROCESS_MAX_BYTES = 50 * 1024 * 1024      # 50 MB

# UI
WINDOW_SIZE = "1200x800"
WINDOW_TITLE = "Code Combiner for LLMs"
