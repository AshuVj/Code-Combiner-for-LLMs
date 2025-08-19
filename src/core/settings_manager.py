# src/core/settings_manager.py

import json
import os
from typing import Dict, Any
from src.utils.logger import logger
from src.config import SETTINGS_FILENAME

def _ensure_gitignore_rule(base_folder: str, rule: str) -> None:
    try:
        gi = os.path.join(base_folder, ".gitignore")
        existing = ""
        if os.path.exists(gi):
            with open(gi, "r", encoding="utf-8", errors="ignore") as f:
                existing = f.read()
        if rule not in existing.splitlines():
            with open(gi, "a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write(rule + "\n")
    except Exception:
        # Best-effort; never crash on ignore add
        pass

def _hide_on_windows(path: str) -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x2
        FILE_ATTRIBUTE_SYSTEM = 0x4
        GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
        SetFileAttributesW = ctypes.windll.kernel32.SetFileAttributesW
        GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
        SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]

        attrs = GetFileAttributesW(path)
        if attrs == 0xFFFFFFFF:
            return  # file not found or error
        new_attrs = attrs | FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM
        SetFileAttributesW(path, new_attrs)
    except Exception:
        # Best-effort; never crash on attribute set
        pass

class SettingsManager:
    def __init__(self, base_folder: str):
        self.base_folder = base_folder
        self.settings_path = os.path.join(base_folder, SETTINGS_FILENAME)

    def save_settings(self, settings: Dict[str, Any]) -> bool:
        try:
            os.makedirs(self.base_folder, exist_ok=True)
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4)

            # Make sure Git ignores it and Windows hides it
            _ensure_gitignore_rule(self.base_folder, SETTINGS_FILENAME)
            _hide_on_windows(self.settings_path)

            logger.info(f"Settings saved to {self.settings_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save settings: {str(e)}")
            return False

    def load_settings(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.settings_path):
                # Re-hide if a previous version forgot
                _hide_on_windows(self.settings_path)
                _ensure_gitignore_rule(self.base_folder, SETTINGS_FILENAME)

                with open(self.settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                required = ["selected_folder","excluded_folders","excluded_folder_names","excluded_file_patterns","excluded_files"]
                for k in required:
                    if k not in settings:
                        settings[k] = [] if k != "selected_folder" else ""
                logger.info(f"Settings loaded from {self.settings_path}")
                return settings
            logger.info("No settings file found to load.")
            return {}
        except Exception as e:
            logger.error(f"Failed to load settings: {str(e)}")
            return {}
