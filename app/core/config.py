"""Configuration with automatic migration from the v1 config file."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"
LEGACY_DIR = PROJECT_ROOT / "legacy"
CONFIG_PATH = PROJECT_ROOT / "update-config.json"
ICON_PATH = ASSETS_DIR / "update.ico"
UNRAR_DLL = ASSETS_DIR / "UnRAR64.dll"

_data_root = Path(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")) / "UpdateScripts"
DATA_DIR = _data_root
LOG_PATH = DATA_DIR / "logs" / "app.log"
CACHE_PATH = DATA_DIR / "cache.json"


def default_search_paths() -> list[str]:
    """Build install roots dynamically; the legacy code hardcoded a username."""
    roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ]
    roots += [f"{d}:\\Program Files" for d in "DEF"]
    roots += [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs"),
        r"C:\Program Files\WindowsApps",
    ]
    return list(dict.fromkeys(p for p in roots if p and p.strip()))


@dataclass
class Settings:
    schema: int = 2
    ignored: list[str] = field(default_factory=list)
    schedule_enabled: bool = False
    schedule_minutes: int = 60
    run_on_start: bool = False
    concurrency: int = 4
    timeout_seconds: int = 600
    download_dir: str = ""
    search_paths: list[str] = field(default_factory=default_search_paths)
    theme: str = "system"
    proxy: str = ""
    verify_tls: bool = True
    minimize_to_tray: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Settings":
        cfg = cls()
        known = {f for f in cfg.to_dict()}
        for key in known:
            if key in raw:
                setattr(cfg, key, raw[key])
        # v1 keys -> v2
        if "ignored_program" in raw and "ignored" not in raw:
            cfg.ignored = list(raw.get("ignored_program") or [])
        if "auto_update" in raw and "schedule_enabled" not in raw:
            cfg.schedule_enabled = bool(raw.get("auto_update"))
        cfg.schema = 2
        cfg.concurrency = max(1, min(16, int(cfg.concurrency)))
        cfg.schedule_minutes = max(5, int(cfg.schedule_minutes))
        return cfg


def load_settings() -> Settings:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError, TypeError):
        return Settings()
    settings = Settings.from_dict(raw)
    if raw.get("schema") != 2:
        # One-time, lossless upgrade from the v1 keys ignored_program/auto_update.
        save_settings(settings)
    return settings


def save_settings(settings: Settings) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(settings.to_dict(), fh, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


def download_dir() -> Path:
    configured = load_settings().download_dir.strip()
    if configured:
        return Path(configured)
    return Path(os.path.join(os.path.expanduser("~"), "Desktop"))
