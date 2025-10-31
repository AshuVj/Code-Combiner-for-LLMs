# src/core/settings_manager.py

import json
import os
import hashlib
import re
from pathlib import Path
from typing import Dict, Any

from platformdirs import user_config_dir
from src.utils.logger import logger
from src.config import SETTINGS_FILENAME
from src.utils.prefs import APP_NAME, APP_AUTHOR

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

def _project_slug(path: str) -> str:
    norm = os.path.abspath(path)
    tail = Path(norm).name or "project"
    safe_tail = re.sub(r"[^A-Za-z0-9._-]+", "_", tail)[:40] or "project"
    digest = hashlib.sha1(norm.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"{safe_tail}-{digest}"

class SettingsManager:
    def __init__(self, base_folder: str):
        self.base_folder = os.path.abspath(base_folder)
        self.base_path = Path(self.base_folder) / SETTINGS_FILENAME
        slug = _project_slug(self.base_folder)
        self.fallback_dir = Path(user_config_dir(appname=APP_NAME, appauthor=APP_AUTHOR)) / "projects" / slug
        self.fallback_path = self.fallback_dir / SETTINGS_FILENAME
        self.storage_path = self.base_path
        self.using_fallback = False
        self.last_error: str | None = None
        self.last_warning: str | None = None

    def save_settings(self, settings: Dict[str, Any]) -> bool:
        self.last_error = None
        self.last_warning = None

        candidates: list[tuple[Path, bool]]
        if self.using_fallback:
            candidates = [(self.fallback_path, False)]
        else:
            candidates = [(self.base_path, True), (self.fallback_path, False)]

        last_exc: Exception | None = None

        for path, is_base in candidates:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("w", encoding="utf-8") as f:
                    json.dump(settings, f, indent=4)

                if is_base:
                    _ensure_gitignore_rule(self.base_folder, SETTINGS_FILENAME)
                    self.using_fallback = False
                    self.storage_path = path
                    self.last_error = None
                    logger.info("Settings saved to %s", path)
                    return True

                # fallback success
                self.using_fallback = True
                self.storage_path = path
                self.last_error = None
                self.last_warning = (
                    f"Project settings saved to {path} because the project folder is not writable."
                )
                logger.info("Settings saved to fallback path %s", path)
                return True
            except Exception as e:
                last_exc = e
                continue

        if last_exc:
            self.last_error = str(last_exc)
            logger.error("Failed to save settings: %s", last_exc, exc_info=True)
        return False

    def load_settings(self) -> Dict[str, Any]:
        self.last_error = None
        self.last_warning = None

        paths: list[tuple[Path, bool]] = [(self.base_path, True), (self.fallback_path, False)]
        if self.using_fallback:
            paths.insert(0, paths.pop(1))  # ensure fallback checked first

        for path, is_base in paths:
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8") as f:
                    settings = json.load(f)
                required = [
                    "selected_folder",
                    "excluded_folders",
                    "excluded_folder_names",
                    "excluded_file_patterns",
                    "excluded_files",
                ]
                for k in required:
                    if k not in settings:
                        settings[k] = [] if k != "selected_folder" else ""

                if is_base:
                    _ensure_gitignore_rule(self.base_folder, SETTINGS_FILENAME)
                    self.using_fallback = False
                else:
                    self.using_fallback = True
                    self.last_warning = (
                        f"Loaded project settings from {path} because the project folder is not writable."
                    )
                self.storage_path = path
                logger.info("Settings loaded from %s", path)
                return settings
            except Exception as e:
                self.last_error = str(e)
                logger.error("Failed to load settings from %s: %s", path, e, exc_info=True)

        logger.info("No settings file found to load.")
        return {}
