# src/core/settings_manager.py

import json
import os
from typing import Dict, Any
from src.utils.logger import logger
from src.config import SETTINGS_FILENAME

class SettingsManager:
    def __init__(self, base_folder: str):
        self.base_folder = base_folder
        self.settings_path = os.path.join(base_folder, SETTINGS_FILENAME)

    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """Save settings to a JSON file."""
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4)
            logger.info(f"Settings saved to {self.settings_path}")
            logger.debug(f"Saved settings: {settings}")  # Detailed log for debugging
            return True
        except Exception as e:
            logger.error(f"Failed to save settings: {str(e)}")
            return False

    def load_settings(self) -> Dict[str, Any]:
        """Load settings from a JSON file."""
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                
                # Validate settings
                required_keys = ["selected_folder", "excluded_folders", "excluded_folder_names", "excluded_file_patterns", "excluded_files"]
                for key in required_keys:
                    if key not in settings:
                        settings[key] = [] if key != "selected_folder" else ""
                        logger.warning(f"Missing key '{key}' in settings. Setting default value.")
                
                logger.info(f"Settings loaded from {self.settings_path}")
                logger.debug(f"Loaded settings: {settings}")  # Detailed log for debugging
                return settings
            logger.info("No settings file found to load.")
            return {}
        except Exception as e:
            logger.error(f"Failed to load settings: {str(e)}")
            return {}
