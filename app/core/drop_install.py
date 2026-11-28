"""Installing a release archive the user dropped onto the window.

A few recipes (``AppSpec.archive_handler``) accept a manually downloaded
archive. This module finds the recipe an archive belongs to, installs it and
works out the resulting state. It is blocking and free of Qt: the UI runs
:func:`install` on a thread and shows the :class:`DropResult`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from . import cache, services
from .config import Settings
from .engine import UpdateEngine
from .models import AppSpec, Phase

ArchiveHandler = Mapping[str, Callable[..., Any]]


@dataclass(frozen=True)
class DropResult:
    ok: bool
    message: str
    app_id: str = ""
    # Installed version read back after the install; "" when it could not be.
    local: str = ""


def match(specs: Sequence[AppSpec], entries: Sequence[str],
          handlers: Mapping[str, ArchiveHandler]) -> tuple[AppSpec, ArchiveHandler] | None:
    """The first recipe whose archive handler recognises the archive's entries."""
    for spec in specs:
        handler = handlers.get(spec.archive_handler) if spec.archive_handler else None
        if handler and handler["match"](entries):
            return spec, handler
    return None


def install(path: str, entries: Sequence[str], spec: AppSpec,
            handler: ArchiveHandler, settings: Settings,
            engine: UpdateEngine) -> DropResult:
    """Install ``path`` for ``spec`` and read back the installed version."""
    try:
        handler["install"](path, entries, settings)
    except Exception as exc:
        return DropResult(False, f"{spec.name} 安装失败：{exc}", spec.id)
    return DropResult(True, f"{spec.name} 安装完成", spec.id,
                       engine.installed_version(spec))


def state_after_install(app_id: str, local: str, *,
                        lexicographic: bool = False) -> tuple[Phase, bool | None]:
    """``(phase, needs_update)`` once ``local`` was installed by hand.

    Compared against the remote version found by the last check. Without a
    known remote version the previous ``needs_update`` from the cache is kept.
    """
    entry = cache.app_cache(app_id)
    remote = entry.get("remote", "") or ""
    needs = entry.get("needs_update")
    if remote:
        try:
            needs = services.is_newer(remote, local, lexicographic=lexicographic)
        except Exception:
            pass
    phase = (Phase.DONE if needs else
             Phase.UPTODATE if needs is False else Phase.DONE)
    return phase, needs
