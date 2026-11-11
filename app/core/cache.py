"""Version snapshot cache so the table renders instantly at startup."""
from __future__ import annotations

import json
import os
import time
from typing import Any

from .config import CACHE_PATH


def _empty() -> dict[str, Any]:
    return {"apps": {}, "last_update": None}


def load_cache() -> dict[str, Any]:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return _empty()
        data.setdefault("apps", {})
        data.setdefault("last_update", None)
        return data
    except (OSError, ValueError):
        return _empty()


def save_cache(data: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, CACHE_PATH)


def app_cache(app_id: str) -> dict[str, Any]:
    return dict(load_cache()["apps"].get(app_id, {}))


def update_app_cache(app_id: str, **fields: Any) -> None:
    data = load_cache()
    entry = dict(data["apps"].get(app_id, {}))
    entry.update(fields)
    entry["checked_at"] = time.time()
    data["apps"][app_id] = entry
    save_cache(data)


def record_update_time() -> None:
    data = load_cache()
    data["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_cache(data)


def last_update_time() -> str:
    return load_cache().get("last_update") or "—"
