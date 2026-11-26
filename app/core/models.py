"""Domain models and the structured event protocol.

This module deliberately has no Qt dependency: the business layer stays
testable and reusable from a CLI. The old GUI parsed stdout strings such as
``Download: 1.2MB / 3.4MB (35%)``; here every state change is a typed
``ProgressEvent`` emitted by the engine and forwarded to Qt signals.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Mapping


class UpdateError(Exception):
    """Base class for recoverable update failures."""


class NotInstalled(UpdateError):
    """The target application is not installed locally."""


class QueryFailed(UpdateError):
    """Remote version or download URL could not be resolved."""


class Cancelled(UpdateError):
    """The task was cancelled by the user."""


class TimedOut(UpdateError):
    """The task exceeded its time budget."""


class LogLevel(IntEnum):
    """Severity of a log record; higher value means more important."""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40

    @property
    def label(self) -> str:
        return {
            LogLevel.DEBUG: "调试",
            LogLevel.INFO: "信息",
            LogLevel.WARNING: "警告",
            LogLevel.ERROR: "错误",
        }[self]


class Phase(Enum):
    IDLE = "等待中"
    QUEUED = "等待中"
    WAITING_NETWORK = "等待连接"
    CHECKING = "检查中"
    PREPARING = "准备中"
    DOWNLOADING = "下载中"
    INSTALLING = "安装中"
    DONE = "完成"
    UPTODATE = "已是最新"
    SKIPPED = "未安装"
    DOWNLOADED = "已下载"
    MANUAL = "需手动更新"
    FAILED = "失败"
    CANCELLED = "已取消"


ACTIVE_PHASES = frozenset({
    Phase.QUEUED, Phase.WAITING_NETWORK, Phase.CHECKING, Phase.PREPARING,
    Phase.DOWNLOADING, Phase.INSTALLING,
})
TERMINAL_PHASES = frozenset({
    Phase.DONE, Phase.UPTODATE, Phase.SKIPPED, Phase.DOWNLOADED,
    Phase.MANUAL, Phase.FAILED, Phase.CANCELLED,
})
SUCCESS_PHASES = frozenset({Phase.DONE, Phase.UPTODATE, Phase.DOWNLOADED})
ERROR_PHASES = frozenset({Phase.FAILED, Phase.CANCELLED, Phase.SKIPPED})

# Phase levels control activity-log visibility. DEBUG records are still kept
# in the buffer and shown when the log filter is switched to "详细".
PHASE_LOG_LEVEL: dict[Phase, LogLevel] = {
    Phase.IDLE: LogLevel.DEBUG,
    Phase.QUEUED: LogLevel.DEBUG,
    Phase.WAITING_NETWORK: LogLevel.WARNING,
    Phase.CHECKING: LogLevel.DEBUG,
    Phase.PREPARING: LogLevel.DEBUG,
    Phase.DOWNLOADING: LogLevel.DEBUG,
    Phase.INSTALLING: LogLevel.INFO,
    Phase.DONE: LogLevel.INFO,
    Phase.UPTODATE: LogLevel.DEBUG,
    Phase.SKIPPED: LogLevel.DEBUG,
    Phase.DOWNLOADED: LogLevel.DEBUG,
    Phase.MANUAL: LogLevel.WARNING,
    Phase.FAILED: LogLevel.ERROR,
    Phase.CANCELLED: LogLevel.WARNING,
}


def level_for_phase(phase: Phase) -> LogLevel:
    return PHASE_LOG_LEVEL.get(phase, LogLevel.INFO)


class Mode(Enum):
    CHECK = "check"
    UPDATE = "update"
    FORCE = "force"
    DOWNLOAD_ONLY = "download_only"

    @property
    def is_force(self) -> bool:
        return self in (Mode.FORCE, Mode.DOWNLOAD_ONLY)

    @property
    def label(self) -> str:
        return {
            Mode.CHECK: "检查",
            Mode.UPDATE: "更新",
            Mode.FORCE: "强制更新",
            Mode.DOWNLOAD_ONLY: "仅下载",
        }[self]


# ---------------------------------------------------------------------------
# Recipe DSL: every "how" below is an enum member or a small typed object, so a
# typo in a recipe fails at import time instead of at update time.
# ---------------------------------------------------------------------------
class LocalKind(Enum):
    """How to read the installed version."""
    EXE = "exe"            # FileVersion of an .exe
    PRODUCT = "product"    # ProductVersion from the localized string table
    APPX = "appx"          # version of an AppX / MSIX package
    PARTS = "parts"        # FileVersion fields combined through a pattern
    FILE = "file"          # regex over a text file
    GLOB = "glob"          # regex over the first matching file name
    COMMAND = "command"    # regex over a command's stdout
    MTIME = "mtime"        # modification date of a file
    CUSTOM = "custom"      # hook in the "local" group


class RemoteKind(Enum):
    """Where the newest version comes from."""
    REGEX = "regex"
    JSON = "json"
    REDIRECT = "redirect"        # version parsed from the final URL
    FINDALL_MAX = "findall_max"  # highest of all regex hits
    HEADLESS = "headless"        # page rendered by headless Edge
    CUSTOM = "custom"            # hook in the "remote" group


class VersionTransform(Enum):
    """Post-processing of a raw version string."""
    DIGITS_DOT = "digits_dot"    # "1213" -> "1.2.1.3"
    STRIP_LAST = "strip_last"    # "1.2.3.4" -> "1.2.3"
    GROUPS_JOIN = "groups_join"  # join regex groups 2..n


class ResponseKind(Enum):
    """Kind of expression that locates the download URL in a response."""
    REGEX = "regex"
    JSON = "json"


class InstallKind(Enum):
    INSTALLER = "installer"    # run the downloaded package
    EXTRACT = "extract"        # unpack into the install directory
    COPY = "copy"              # copy the single downloaded file
    DESKTOP = "desktop"        # leave the package on the desktop
    MANUAL = "manual"          # only open the download page
    CUSTOM = "custom"          # hook in the "install" group


class DeployMode(Enum):
    """How extracted files land in the install directory."""
    OVERWRITE = "overwrite"        # copy the archive root over it
    SUBDIR = "subdir"              # copy one sub-directory by its name
    SUBDIR_GLOB = "subdir_glob"    # copy the first sub-directory matching a glob
    COPY_FILE = "copy_file"        # copy a single file found by glob
    RTREE_FIRST = "rmtree_first"   # delete the directory before copying


@dataclass(frozen=True)
class ResponsePattern:
    """Locates the download URL inside the response used for version detection."""
    kind: ResponseKind
    pattern: str


# Post-install actions (``AppSpec.post``). The engine dispatches on the type.
@dataclass(frozen=True)
class Kill:
    """End a process by image name."""
    image: str


@dataclass(frozen=True)
class KillTree:
    """End a process together with the children it started."""
    image: str


@dataclass(frozen=True)
class AddToPath:
    """Append to the machine-wide PATH.

    ``target`` is relative to the install directory; "" is the install
    directory itself, and an absolute path is used as is.
    """
    target: str = ""


@dataclass(frozen=True)
class RemoveShortcut:
    """Delete a shortcut from the desktop."""
    name: str


@dataclass(frozen=True)
class DeleteRegistryKey:
    key: str


@dataclass(frozen=True)
class OpenUrl:
    """Open a page in the default browser.

    "" falls back to ``RemoteInfo.extra["open_url"]``, which a remote hook
    may have set.
    """
    url: str = ""


@dataclass(frozen=True)
class OpenInstallDir:
    """Open the install directory in Explorer."""


@dataclass(frozen=True)
class CustomPost:
    """Hook in the "post" group, called as ``fn(ctx, info)``."""
    hook: str


PostAction = (Kill | KillTree | AddToPath | RemoveShortcut | DeleteRegistryKey
              | OpenUrl | OpenInstallDir | CustomPost)


@dataclass(frozen=True)
class LocalSpec:
    """How to read the installed version.

    ``target`` is the file (or command) to read, ``pattern`` the regex or
    format string the kind needs, ``custom`` the name of a "local" hook.
    """
    kind: LocalKind = LocalKind.EXE
    target: str = ""
    pattern: str = ""
    custom: str = ""


@dataclass(frozen=True)
class RemoteSpec:
    """How to resolve the newest version from a remote source.

    ``pattern`` is the regex (alternatives separated by ``||``), the JSON
    path or the name of a custom hook's kind-specific argument;
    ``transform`` post-processes the raw version string.
    """
    url: str = ""
    kind: RemoteKind = RemoteKind.REGEX
    pattern: str = ""
    headers: Mapping[str, str] | None = None
    transform: VersionTransform | None = None
    custom: str = ""


@dataclass(frozen=True)
class DownloadSpec:
    """Download URL resolution.

    ``url`` may contain ``{version}``; ``from_response`` locates the URL in
    the same response that was used for version detection; ``custom`` names
    a function in the application's "download" hooks.
    """
    url: str = ""
    from_response: ResponsePattern | None = None
    filename: str = ""
    custom: str = ""


@dataclass(frozen=True)
class InstallSpec:
    """How to apply a downloaded package.

    ``args`` are the installer's command-line arguments; ``subdir`` is the
    directory, glob or file name that ``DeployMode`` refers to; ``custom``
    names an "install" hook.
    """
    kind: InstallKind = InstallKind.INSTALLER
    args: str = ""
    mode: DeployMode = DeployMode.OVERWRITE
    subdir: str = ""
    custom: str = ""


@dataclass(frozen=True)
class AppSpec:
    """Declarative recipe for one application. Replaces 43 copied scripts."""
    id: str
    name: str
    category: str = "其他"
    homepage: str = ""
    install_dirs: tuple[str, ...] = ()
    local: LocalSpec | None = None
    remote: RemoteSpec | None = None
    download: DownloadSpec | None = None
    install: InstallSpec | None = None
    post: tuple[PostAction, ...] = ()
    manual_only: bool = False
    archive_handler: str = ""
    note: str = ""
    # Recipe-level proxy policy: True uses the configured proxy, False connects
    # directly. A per-app user rule (Settings.proxy_rules) takes precedence.
    proxy: bool = True
    lexicographic: bool = False

    @property
    def downloadable(self) -> bool:
        return self.download is not None and not self.manual_only

    @property
    def auto_installable(self) -> bool:
        """Whether an unattended sweep may install this app without a prompt."""
        return (self.local is not None
                and self.downloadable
                and (self.install is None or self.install.kind != InstallKind.MANUAL))


@dataclass(frozen=True)
class ErrorInfo:
    kind: str
    message: str
    detail: str = ""


@dataclass
class ProgressEvent:
    """The only channel between the engine and the UI."""
    app_id: str
    phase: Phase
    message: str = ""
    current: int = 0
    total: int = 0
    local_version: str = ""
    remote_version: str = ""
    needs_update: bool | None = None
    error: ErrorInfo | None = None
    finished: bool = False
    timestamp: float = field(default_factory=time.time)
    level: LogLevel | None = None

    @property
    def effective_level(self) -> LogLevel:
        return self.level if self.level is not None else level_for_phase(self.phase)

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return min(100.0, self.current * 100.0 / self.total)


@dataclass
class RemoteInfo:
    """Resolved remote data, shared by the version and download stages."""
    version: str = ""
    url: str = ""
    text: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
