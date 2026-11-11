"""Application registry: replaces glob + AST parsing of script sources."""
from __future__ import annotations

from ..apps.catalog import SPECS
from .config import Settings
from .models import AppSpec

_BY_ID = {spec.id: spec for spec in SPECS}


def all_specs() -> tuple[AppSpec, ...]:
    return SPECS


def visible_specs(settings: Settings) -> list[AppSpec]:
    ignored = set(settings.ignored)
    return [s for s in SPECS if s.id not in ignored]


def spec_by_id(app_id: str) -> AppSpec | None:
    return _BY_ID.get(app_id)


def categories() -> list[str]:
    return sorted({s.category for s in SPECS})
