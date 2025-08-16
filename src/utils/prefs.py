# src/utils/prefs.py

import json
from pathlib import Path
from platformdirs import user_config_dir

APP_NAME = "FileCombinerApp"
APP_AUTHOR = "AshutoshVijay"

def _prefs_path() -> Path:
    cfg_dir = Path(user_config_dir(appname=APP_NAME, appauthor=APP_AUTHOR))
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / "prefs.json"

def load_prefs() -> dict:
    p = _prefs_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_prefs(data: dict) -> None:
    p = _prefs_path()
    try:
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass
