"""Declarative application recipes."""
from ..core.models import AppSpec
from ..core.registry import AppRegistry
from .catalog import SPECS
from .hooks import HOOKS

registry = AppRegistry(SPECS)

__all__ = ["AppSpec", "HOOKS", "registry", "SPECS"]
