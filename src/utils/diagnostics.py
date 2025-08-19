# src/utils/diagnostics.py
from __future__ import annotations
import json
import os
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from platformdirs import user_log_dir, user_config_dir

APP_NAME = "Code Combiner for LLMs"
APP_AUTHOR = "AshutoshVijay"

def build_diagnostics_zip(dest_zip_path: str, extra_files: list[str] | None = None) -> str:
    """Create a diagnostics zip (logs + prefs + settings pointers). Returns path."""
    dest = Path(dest_zip_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    log_dir = Path(user_log_dir(appname=APP_NAME, appauthor=APP_AUTHOR))
    cfg_dir = Path(user_config_dir(appname=APP_NAME, appauthor=APP_AUTHOR))
    prefs = cfg_dir / "prefs.json"

    with ZipFile(dest, "w", compression=ZIP_DEFLATED) as z:
        # Logs
        if log_dir.exists():
            for p in log_dir.glob("*.log"):
                z.write(p, f"logs/{p.name}")
        # Prefs
        if prefs.exists():
            z.write(prefs, "prefs.json")

        # Marker for settings file(s) – we don't know the current workspace here,
        # but the app can pass them in extra_files when available.
        if extra_files:
            for f in extra_files:
                f = Path(f)
                if f.exists():
                    z.write(f, f"settings/{f.name}")

        # metadata
        meta = {
            "app": APP_NAME,
            "author": APP_AUTHOR,
        }
        z.writestr("meta.json", json.dumps(meta, indent=2))

    return str(dest.resolve())
