"""Version snapshot cache so the table renders instantly at startup.

All read-modify-write cycles are serialised by an in-process lock and every
write goes through :func:`atomic_write_json`. Cache persistence is only an
optimisation: a failure is logged and ignored, never surfaced as a failed
update task.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from .atomic_io import atomic_write_json
from .config import CACHE_PATH
from .logging_setup import get_logger

_LOCK = threading.RLock()
_last_update: str = ""


def _empty() -> dict[str, Any]:
    return {"apps": {}, "last_update": None}


def load_cache() -> dict[str, Any]:
    with _LOCK:
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                return _empty()
            if not isinstance(data.get("apps"), dict):
                data["apps"] = {}
            data.setdefault("last_update", None)
            return data
        except (OSError, ValueError, TypeError):
            return _empty()


def save_cache(data: dict[str, Any]) -> None:
    with _LOCK:
        try:
            atomic_write_json(CACHE_PATH, data)
        except Exception as exc:
            get_logger().warning("缓存写入失败（已忽略）: %s", exc)


def app_cache(app_id: str) -> dict[str, Any]:
    return dict(load_cache()["apps"].get(app_id, {}))


def update_app_cache(app_id: str, **fields: Any) -> None:
    with _LOCK:
        try:
            data = load_cache()
            entry = dict(data["apps"].get(app_id, {}))
            entry.update(fields)
            entry["checked_at"] = time.time()
            data["apps"][app_id] = entry
            save_cache(data)
        except Exception as exc:
            get_logger().warning("更新应用缓存失败（已忽略）: %s", exc)


def record_update_time() -> None:
    global _last_update
    with _LOCK:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        _last_update = stamp
        try:
            data = load_cache()
            data["last_update"] = stamp
            save_cache(data)
        except Exception as exc:
            get_logger().warning("记录更新时间失败（已忽略）: %s", exc)


def last_update_time() -> str:
    global _last_update
    with _LOCK:
        if not _last_update:
            _last_update = load_cache().get("last_update") or ""
        return _last_update or "—"
