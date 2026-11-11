"""Atomic, concurrency-safe JSON persistence on Windows.

Each write uses a *unique* temp file followed by ``os.replace``. A shared,
fixed temp name (e.g. ``cache.json.tmp``) makes concurrent worker threads
trample each other and raises ``PermissionError [Errno 13]`` when one thread
replaces the file while another still has it open.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

_REPLACE_ATTEMPTS = 6


def atomic_write_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=f".{path.stem}-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        # Windows may briefly hold the destination open (AV / indexer).
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == _REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(0.01 * (attempt + 1))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
