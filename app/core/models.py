"""Domain models and the structured event protocol.

This module deliberately has no Qt dependency: the business layer stays
testable and reusable from a CLI. The old GUI parsed stdout strings such as
``Download: 1.2MB / 3.4MB (35%)``; here every state change is a typed
``ProgressEvent`` emitted by the engine and forwarded to Qt signals.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
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


class Phase(Enum):
    IDLE = "等待中"
    QUEUED = "排队中"
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
    Phase.QUEUED, Phase.CHECKING, Phase.PREPARING,
    Phase.DOWNLOADING, Phase.INSTALLING,
})
TERMINAL_PHASES = frozenset({
    Phase.DONE, Phase.UPTODATE, Phase.SKIPPED, Phase.DOWNLOADED,
    Phase.MANUAL, Phase.FAILED, Phase.CANCELLED,
})
SUCCESS_PHASES = frozenset({Phase.DONE, Phase.UPTODATE, Phase.DOWNLOADED})
ERROR_PHASES = frozenset({Phase.FAILED, Phase.CANCELLED, Phase.SKIPPED})


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


@dataclass(frozen=True)
class LocalSpec:
    """How to read the installed version.

    kind: exe | appx | file | command | glob | parts | mtime | custom
    """
    kind: str = "exe"
    target: str = ""
    pattern: str = ""
    custom: str = ""


@dataclass(frozen=True)
class RemoteSpec:
    """How to resolve the newest version from a remote source.

    kind: regex | json | redirect | findall_max | headless | custom
    transform: "" | digits_dot | strip_last | groups_join | group_join
    """
    url: str = ""
    kind: str = "regex"
    pattern: str = ""
    headers: Mapping[str, str] | None = None
    transform: str = ""
    custom: str = ""


@dataclass(frozen=True)
class DownloadSpec:
    """Download URL resolution.

    ``url`` may contain ``{version}``; ``from_response`` is a ``regex:...``
    expression applied to the same response used for version detection;
    ``custom`` names a function in :mod:`app.apps.hooks`.
    """
    url: str = ""
    from_response: str = ""
    filename: str = ""
    custom: str = ""


@dataclass(frozen=True)
class InstallSpec:
    """How to apply a downloaded package.

    kind: installer | extract | copy | desktop | manual | custom
    mode: overwrite | copy_file | subdir | rmtree_first
    """
    kind: str = "installer"
    args: str = ""
    mode: str = "overwrite"
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
    post: tuple[str, ...] = ()
    manual_only: bool = False
    archive_handler: str = ""
    note: str = ""
    proxy: bool = True
    lexicographic: bool = False

    @property
    def downloadable(self) -> bool:
        return self.download is not None and not self.manual_only


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
