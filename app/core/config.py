"""Configuration with automatic migration from the v1 config file."""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .atomic_io import atomic_write_json

_SETTINGS_LOCK = threading.RLock()

IS_FROZEN = getattr(sys, "frozen", False)
# PyInstaller unpacks data files into sys._MEIPASS (a fresh temp dir for
# one-file builds), so runtime resources must be resolved from there.
BASE_DIR = (Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
            if IS_FROZEN else Path(__file__).resolve().parents[2])
PROJECT_ROOT = BASE_DIR
MAIN_SCRIPT = BASE_DIR / "main.pyw"
ASSETS_DIR = BASE_DIR / "assets"
ICON_PATH = ASSETS_DIR / "update.ico"
UNRAR_DLL = ASSETS_DIR / "UnRAR64.dll"

_data_root = Path(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")) / "UpdateScripts"
DATA_DIR = _data_root
LOG_PATH = DATA_DIR / "logs" / "app.log"
CACHE_PATH = DATA_DIR / "cache.json"
# A frozen one-file exe is extracted anew on every launch, so settings belong
# in the user profile rather than beside the (temporary) code.
CONFIG_PATH = (DATA_DIR / "update-config.json" if IS_FROZEN
               else BASE_DIR / "update-config.json")


def pythonw_executable() -> str:
    """Return pythonw.exe when available, so restarts stay console-free."""
    exe = sys.executable
    if os.name != "nt":
        return exe
    candidate = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return candidate if os.path.isfile(candidate) else exe


def restart_command() -> tuple[str, list[str]]:
    """Program and arguments used to relaunch the app after an upgrade."""
    if IS_FROZEN:
        return sys.executable, []
    return pythonw_executable(), [str(MAIN_SCRIPT)]


def config_path_for_read() -> Path:
    """Also accept a config sitting beside the exe, easing migration to builds."""
    if CONFIG_PATH.is_file() or not IS_FROZEN:
        return CONFIG_PATH
    beside_exe = Path(sys.executable).resolve().parent / "update-config.json"
    return beside_exe if beside_exe.is_file() else CONFIG_PATH


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
    auto_install_updates: bool = True
    concurrency: int = 4
    timeout_seconds: int = 600
    download_dir: str = ""
    search_paths: list[str] = field(default_factory=default_search_paths)
    theme: str = "system"
    proxy: str = ""
    # app_id -> "proxy" | "direct"; a missing key falls back to AppSpec.proxy.
    proxy_rules: dict[str, str] = field(default_factory=dict)
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
        # v1's auto_update meant "update automatically", so it must map to
        # both the schedule switch and the unattended install switch.
        if "auto_update" in raw:
            if "schedule_enabled" not in raw:
                cfg.schedule_enabled = bool(raw.get("auto_update"))
            if "auto_install_updates" not in raw:
                cfg.auto_install_updates = bool(raw.get("auto_update"))
        cfg.schema = 2
        if not isinstance(cfg.proxy_rules, dict):
            cfg.proxy_rules = {}
        cfg.concurrency = max(1, min(16, int(cfg.concurrency)))
        cfg.schedule_minutes = max(5, int(cfg.schedule_minutes))
        return cfg


def load_settings() -> Settings:
    try:
        with open(config_path_for_read(), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError, TypeError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    settings = Settings.from_dict(raw)
    if raw.get("schema") != 2:
        # One-time, lossless upgrade from the v1 keys ignored_program/auto_update.
        try:
            save_settings(settings)
        except Exception as exc:
            logging.getLogger("updatescripts").warning(
                "配置迁移写入失败（继续使用内存配置）: %s", exc)
    return settings


def save_settings(settings: Settings) -> None:
    with _SETTINGS_LOCK:
        atomic_write_json(CONFIG_PATH, settings.to_dict())


def download_dir() -> Path:
    configured = load_settings().download_dir.strip()
    if configured:
        return Path(configured)
    return Path(os.path.join(os.path.expanduser("~"), "Desktop"))
