# src/core/snippets_store.py
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional
from uuid import uuid4
from platformdirs import user_config_dir

APP_NAME = "Code Combiner for LLMs"
APP_AUTHOR = "AshutoshVijay"

_SNIPPETS_FILE = Path(user_config_dir(appname=APP_NAME, appauthor=APP_AUTHOR)) / "snippets.json"
_SNIPPETS_FILE.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class Snippet:
    id: str
    name: str
    text: str
    model: str = ""
    source: str = ""   # e.g., "ChatGPT"
    tags: List[str] = None
    created: str = ""  # ISO 8601


def _load() -> dict:
    if _SNIPPETS_FILE.exists():
        try:
            return json.loads(_SNIPPETS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"snippets": []}
    return {"snippets": []}


def _save(data: dict):
    _SNIPPETS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_snippets() -> List[Snippet]:
    data = _load()
    out: List[Snippet] = []
    for s in data.get("snippets", []):
        out.append(Snippet(**{**{"tags": []}, **s}))
    return out


def add_snippet(name: str, text: str, model: str = "", source: str = "", tags: Optional[List[str]] = None) -> Snippet:
    from datetime import datetime, timezone
    snip = Snippet(
        id=str(uuid4()),
        name=name,
        text=text,
        model=model,
        source=source,
        tags=tags or [],
        created=datetime.now(timezone.utc).isoformat()
    )
    data = _load()
    lst = data.setdefault("snippets", [])
    lst.insert(0, asdict(snip))
    _save(data)
    return snip


def get_snippet(snippet_id: str) -> Optional[Snippet]:
    for s in _load().get("snippets", []):
        if s.get("id") == snippet_id:
            return Snippet(**{**{"tags": []}, **s})
    return None


def delete_snippet(snippet_id: str) -> bool:
    data = _load()
    lst = data.get("snippets", [])
    new = [s for s in lst if s.get("id") != snippet_id]
    if len(new) != len(lst):
        data["snippets"] = new
        _save(data)
        return True
    return False
