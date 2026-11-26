"""Application registry: a catalogue of recipes looked up by id.

The core defines what a registry can do but holds no recipes of its own. The
application layer builds one from its catalogue (``app/apps/__init__.py``),
so ``app.core`` never imports ``app.apps``.
"""
from __future__ import annotations

from typing import Sequence

from .config import Settings
from .models import AppSpec


class AppRegistry:
    def __init__(self, specs: Sequence[AppSpec]) -> None:
        self._specs: tuple[AppSpec, ...] = tuple(specs)
        self._by_id = {spec.id: spec for spec in self._specs}

    def all(self) -> tuple[AppSpec, ...]:
        return self._specs

    def visible(self, settings: Settings) -> list[AppSpec]:
        ignored = set(settings.ignored)
        return [s for s in self._specs if s.id not in ignored]

    def by_id(self, app_id: str) -> AppSpec | None:
        return self._by_id.get(app_id)

    def categories(self) -> list[str]:
        return sorted({s.category for s in self._specs})
