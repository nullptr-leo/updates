"""Per-app proxy policy: the context-menu submenu and the settings behind it.

A rule in ``Settings.proxy_rules`` ("proxy" | "direct") overrides the recipe
default; "auto" removes the rule again.
"""

from __future__ import annotations

from typing import Callable, Sequence

from PySide6.QtWidgets import QMenu

from ..core.config import Settings
from ..core.models import AppSpec

VALUES = ("auto", "proxy", "direct")


def rules_of(settings: Settings) -> dict[str, str]:
    rules = settings.proxy_rules
    if not isinstance(rules, dict):
        rules = {}
        settings.proxy_rules = rules
    return rules


def default_text(specs: Sequence[AppSpec]) -> str:
    """What the recipes do when no rule is set: 代理, 直连 or 混合."""
    defaults = {s.proxy for s in specs}
    if len(defaults) > 1:
        return "混合"
    return "代理" if True in defaults else "直连"


def label_for(specs: Sequence[AppSpec], value: str) -> str:
    if value == "auto":
        return f"默认({default_text(specs)})"
    return {"proxy": "代理", "direct": "直连"}[value]


def add_submenu(menu: QMenu, specs: Sequence[AppSpec], settings: Settings,
                on_changed: Callable[[Sequence[AppSpec], str], None]) -> None:
    """Add the "代理策略" submenu; choosing an entry calls ``on_changed``."""
    submenu = menu.addMenu("代理策略")
    rules = settings.proxy_rules
    if not isinstance(rules, dict):
        rules = {}
    for value in VALUES:
        action = submenu.addAction(label_for(specs, value))
        action.setCheckable(True)
        action.setChecked(all(rules.get(s.id, "auto") == value for s in specs))
        action.triggered.connect(lambda _=False, v=value: on_changed(specs, v))


def apply(specs: Sequence[AppSpec], value: str, settings: Settings) -> str:
    """Store the rule for every app ("auto" removes it); returns the label."""
    rules = rules_of(settings)
    for spec in specs:
        if value == "auto":
            rules.pop(spec.id, None)
        else:
            rules[spec.id] = value
    return label_for(specs, value)


def reset(settings: Settings) -> bool:
    """Drop every custom rule; False when there was nothing to drop."""
    rules = rules_of(settings)
    if not rules:
        return False
    rules.clear()
    return True
