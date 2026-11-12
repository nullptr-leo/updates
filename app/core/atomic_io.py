"""Atomic, concurrency-safe JSON persistence and temp cleanup on Windows.

Each write uses a *unique* temp file followed by ``os.replace``. A shared,
fixed temp name (e.g. ``cache.json.tmp``) makes concurrent worker threads
trample each other and raises ``PermissionError [Errno 13]`` when one thread
replaces the file while another still has it open.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator

_REPLACE_ATTEMPTS = 6
_CLEANUP_ATTEMPTS = 8
_CLEANUP_BACKOFF = 0.05


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


def rmtree_with_retry(path: str) -> bool:
    """Best-effort removal of a temp dir Windows may still have locked.

    A freshly written archive is often held open briefly by an AV scanner,
    the indexing service or a just-finished extractor, so an immediate
    ``shutil.rmtree`` fails with WinError 32. Retrying with backoff is enough;
    a leftover temp dir must never turn a successful update into a failure.
    """
    for attempt in range(_CLEANUP_ATTEMPTS):
        try:
            shutil.rmtree(path)
            return True
        except FileNotFoundError:
            return True
        except OSError as exc:
            if attempt == _CLEANUP_ATTEMPTS - 1:
                from .logging_setup import get_logger
                get_logger().warning(
                    "临时目录清理失败（残留文件将由系统清理）：%s: %s", path, exc)
                return False
            time.sleep(_CLEANUP_BACKOFF * (attempt + 1))
    return False


@contextlib.contextmanager
def temporary_workspace(prefix: str) -> Iterator[str]:
    """Like ``TemporaryDirectory``, but cleanup never masks the real error."""
    path = tempfile.mkdtemp(prefix=prefix)
    try:
        yield path
    finally:
        rmtree_with_retry(path)
