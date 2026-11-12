"""The update engine: one pipeline, driven by declarative AppSpec.

Replaces ``sys.executable -u update-xxx.py`` plus stdout regex parsing. All
state changes are emitted as :class:`ProgressEvent`; nothing here touches Qt.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shlex
import shutil
import traceback
from typing import Any, Callable, Mapping

from . import cache, services
from .atomic_io import temporary_workspace
from .cancellation import CancellationToken
from .config import Settings, download_dir
from .logging_setup import get_logger
from .models import (
    AppSpec, Cancelled, ErrorInfo, InstallSpec, LogLevel, Mode, NotInstalled,
    Phase, ProgressEvent, QueryFailed, RemoteInfo, RemoteSpec,
)
from .ports import ProcessPort, SubprocessPort

Emit = Callable[[ProgressEvent], None]
Hooks = Mapping[str, Mapping[str, Callable[..., Any]]]

# How many times a task may be restarted after a connection loss.
NETWORK_ATTEMPTS = 3


def _transform(raw: str, transform: str) -> str:
    if transform == "digits_dot":
        return ".".join(raw)
    if transform == "strip_last":
        parts = raw.split(".")
        return ".".join(parts[:-1]) if len(parts) > 1 else raw
    return raw


def _json_path(text: str, path: str) -> Any:
    data = json.loads(text)
    value: Any = data
    for part in path.split("."):
        if isinstance(value, dict):
            value = value[part]
        elif isinstance(value, list):
            value = value[int(part)]
        else:
            raise KeyError(part)
    return value


def _friendly(exc: BaseException) -> str:
    name = type(exc).__name__
    if any(token in name for token in ("Connection", "Timeout", "HTTP", "Proxy")):
        return "网络错误"
    return str(exc) or name


def _version_label(version: str, date: Any) -> str:
    """Display helper: ``3.0.22`` + build date -> ``3.0.22 (2026-11-12)``.

    Only used for the UI strings: version comparison, download URLs and
    package names keep using the plain version.
    """
    stamp = str(date or "").strip()
    if not version or not stamp or not stamp.strip("0"):
        return version
    if len(stamp) == 8 and stamp.isdigit():
        stamp = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
    return f"{version} ({stamp})"


class Context:
    """Small facade passed to custom recipe hooks."""

    def __init__(self, engine: "UpdateEngine", spec: AppSpec,
                 token: CancellationToken) -> None:
        self.engine = engine
        self.spec = spec
        self.settings = engine.settings
        self.token = token
        self.port = engine.port

    def get(self, url: str, **kwargs: Any) -> str:
        self.token.raise_if_cancelled()
        kwargs.setdefault("settings", self.settings)
        kwargs.setdefault("spec", self.spec)
        return services.http_get(url, **kwargs)

    def redirected(self, url: str) -> str:
        self.token.raise_if_cancelled()
        return services.get_redirected_url(
            url, settings=self.settings, spec=self.spec)

    def rendered(self, url: str) -> str:
        self.token.raise_if_cancelled()
        return services.query_rendered(url)

    def install_dir(self, create: bool = False) -> str:
        return services.find_install_dir(self.spec.install_dirs, self.settings, create)

    def log(self, message: str) -> None:
        get_logger().info("[%s] %s", self.spec.id, message)
        self.engine.emit(
            ProgressEvent(app_id=self.spec.id, phase=Phase.CHECKING, message=message)
        )


class UpdateEngine:
    def __init__(
        self,
        settings: Settings,
        emit: Emit,
        port: ProcessPort | None = None,
        hooks: Hooks | None = None,
        *,
        wait_for_network: bool = True,
    ) -> None:
        self.settings = settings
        self.emit = emit
        self.port = port or SubprocessPort()
        self.hooks: Hooks = hooks or {}
        self.log = get_logger()
        # One-shot CLI runs report "等待连接" instead of blocking forever.
        self.wait_for_network = wait_for_network

    # ------------------------------------------------------------------
    def _hook(self, group: str, name: str) -> Callable[..., Any]:
        fn = self.hooks.get(group, {}).get(name)
        if fn is None:
            raise QueryFailed(f"未注册的钩子: {group}.{name}")
        return fn

    def _send(self, spec: AppSpec, phase: Phase, **kwargs: Any) -> None:
        self.emit(ProgressEvent(app_id=spec.id, phase=phase, **kwargs))

    @staticmethod
    def _extension(url: str, spec: AppSpec) -> str:
        for ext in (".msixbundle", ".zip", ".7z", ".rar", ".exe", ".msi"):
            if ext in url.lower():
                return ext
        return ".exe" if spec.install and spec.install.kind == "installer" else ".zip"

    # ------------------------------------------------------------------
    # pipeline stages
    # ------------------------------------------------------------------
    def _local_version(self, spec: AppSpec, mode: Mode, ctx: Context) -> str:
        if mode.is_force:
            return "0" if spec.local is not None else ""
        if spec.local is None:
            return ""
        install_dir = ctx.install_dir() if spec.install_dirs else ""
        return services.get_local_version(
            spec.local, install_dir,
            hooks=self.hooks.get("local", {}), ctx=ctx,
        )

    def _remote_info(self, spec: AppSpec, ctx: Context) -> RemoteInfo:
        remote: RemoteSpec | None = spec.remote
        if remote is None:
            return RemoteInfo()
        if remote.kind == "custom":
            result = self._hook("remote", remote.custom)(ctx)
            return result if isinstance(result, RemoteInfo) else RemoteInfo(version=str(result))
        if remote.kind == "redirect":
            final = services.get_redirected_url(
                remote.url, settings=self.settings, spec=spec)
            return RemoteInfo(version=self._extract_version(remote, final),
                              url=final, text=final)
        if remote.kind == "headless":
            text = services.query_rendered(remote.url)
        else:
            text = services.http_get(
                remote.url, settings=self.settings, spec=spec,
                headers=dict(remote.headers or {}),
            )
        if remote.kind == "findall_max":
            found = [v if isinstance(v, str) else (v or "0")
                     for v in re.findall(remote.pattern, text, flags=re.M)]
            if not found:
                raise QueryFailed("未在页面找到版本号")
            return RemoteInfo(version=_max_version(found), text=text)
        if remote.kind == "json":
            value = _json_path(text, remote.pattern)
            return RemoteInfo(version=_transform(str(value), remote.transform), text=text)
        return RemoteInfo(version=self._extract_version(remote, text), text=text)

    @staticmethod
    def _extract_version(remote: RemoteSpec, text: str) -> str:
        last_error: Exception | None = None
        for pattern in remote.pattern.split("||"):
            try:
                for match in re.finditer(pattern, text, flags=re.M | re.I):
                    groups = match.groups()
                    if remote.transform == "groups_join":
                        value = "".join(g or "" for g in groups[1:])
                    else:
                        raw = (groups[0] or "") if groups else match.group(0)
                        value = _transform(raw, remote.transform)
                    if value and value.strip():
                        return value
            except Exception as exc:
                last_error = exc
        raise QueryFailed(f"版本解析失败: {remote.url}") from last_error

    def _download_url(self, spec: AppSpec, info: RemoteInfo, ctx: Context) -> str:
        dl = spec.download
        if dl is None:
            return info.url
        if dl.custom:
            return str(self._hook("download", dl.custom)(ctx, info))
        if dl.from_response:
            kind, _, pattern = dl.from_response.partition(":")
            if kind == "regex":
                match = re.search(pattern, info.text, flags=re.M)
                if match:
                    return match.group(1) if match.groups() else match.group(0)
            elif kind == "json":
                return str(_json_path(info.text, pattern))
            raise QueryFailed("下载地址解析失败")
        if dl.url == "{remote_url}":
            return info.url
        return dl.url.replace("{version}", info.version).replace(
            "{remote_version}", info.version
        )

    def _download(self, url: str, dest: str, spec: AppSpec,
                  token: CancellationToken) -> None:
        last_pct = -1.0

        def progress(current: int, total: int) -> None:
            nonlocal last_pct
            pct = current * 100.0 / total if total else 0.0
            if pct - last_pct < 1.0 and pct < 99.9:
                return
            last_pct = pct
            text = (f"{current / 1048576:.1f}M / {total / 1048576:.1f}M"
                    if total else f"{current / 1048576:.1f}M")
            self._send(spec, Phase.DOWNLOADING, message=text,
                       current=current, total=total)

        services.download_file(url, dest, settings=self.settings, spec=spec,
                               token=token, on_progress=progress)

    @staticmethod
    def _extract_source(root: str, inst: InstallSpec) -> str:
        if inst.mode in ("subdir_glob", "subdir"):
            found = [p for p in glob.glob(os.path.join(root, inst.subdir))
                     if os.path.isdir(p)]
            if found:
                return found[0]
        if inst.mode == "copy_file":
            found = glob.glob(os.path.join(root, "**", inst.subdir), recursive=True)
            if found:
                return found[0]
        return root

    def _install(self, spec: AppSpec, dest: str, info: RemoteInfo,
                 ctx: Context, token: CancellationToken) -> None:
        inst: InstallSpec | None = spec.install
        if inst is None or inst.kind == "manual":
            return
        if inst.kind == "custom":
            self._hook("install", inst.custom)(ctx, info, dest)
            return
        if inst.kind == "desktop":
            filename = (spec.download.filename if spec.download and spec.download.filename
                        else f"{info.version}{self._extension(dest, spec)}")
            os.makedirs(services.desktop_dir(), exist_ok=True)
            shutil.copy2(dest, os.path.join(services.desktop_dir(), filename))
            return
        if inst.kind == "installer":
            args = [dest] + shlex.split(inst.args)
            code = services.run_process(
                args, port=self.port, timeout=self.settings.timeout_seconds,
                token=token,
                on_output=lambda line: self._send(
                    spec, Phase.INSTALLING, message=line[:120]
                ),
            )
            if code != 0:
                raise QueryFailed(f"安装程序退出码 {code}")
            return
        if inst.kind == "copy":
            target_dir = ctx.install_dir(create=True)
            shutil.copy2(dest, os.path.join(target_dir, inst.subdir))
            return
        if inst.kind == "extract":
            target_dir = ctx.install_dir(create=True)
            with temporary_workspace(prefix="us-extract-") as tmp:
                services.extract_archive(dest, tmp, settings=self.settings)
                source = self._extract_source(tmp, inst)
                if inst.mode == "rmtree_first":
                    shutil.rmtree(target_dir, ignore_errors=True)
                if inst.mode == "copy_file":
                    name = (os.path.basename(source)
                            if any(c in inst.subdir for c in "*?")
                            else inst.subdir)
                    shutil.copy2(source, os.path.join(target_dir, name))
                else:
                    shutil.copytree(source, target_dir, dirs_exist_ok=True)
            return
        raise QueryFailed(f"未知的安装方式: {inst.kind}")

    def _post(self, spec: AppSpec, info: RemoteInfo, ctx: Context,
              token: CancellationToken) -> None:
        for action in spec.post:
            token.raise_if_cancelled()
            head, _, value = action.partition(":")
            if head == "taskkill":
                services.kill_process(value)
            elif head == "path":
                base = ctx.install_dir() if spec.install_dirs else ""
                if value in ("", "self", "."):
                    path = base
                elif os.path.isabs(value):
                    path = value
                else:
                    path = os.path.join(base, value)
                services.append_env_var("PATH", [path])
            elif head == "shortcut":
                services.remove_desktop_shortcut(value)
            elif head == "regdel":
                services.delete_registry_key(value)
            elif head == "open_url":
                services.open_url(value or info.extra.get("open_url", ""))
            elif head == "open_explorer":
                if spec.install_dirs:
                    try:
                        services.open_explorer(ctx.install_dir())
                    except NotInstalled:
                        pass
            elif head == "custom":
                self._hook("post", value)(ctx, info)

    def _manual(self, spec: AppSpec, info: RemoteInfo, ctx: Context,
                token: CancellationToken) -> None:
        self._post(spec, info, ctx, token)
        if not any(a.startswith("open_url") for a in spec.post):
            services.open_url(spec.homepage)

    def _finish_error(self, spec: AppSpec, phase: Phase, exc: BaseException,
                      local: str, remote: str) -> None:
        if phase == Phase.CANCELLED:
            self.log.info("[%s] 任务已取消", spec.id)
            self._send(
                spec, phase, message="已取消", local_version=local,
                remote_version=remote, finished=True,
                error=ErrorInfo(kind="Cancelled", message="已取消"),
            )
            return
        self.log.error("[%s] %s: %s\n%s", spec.id, phase.value, exc,
                       traceback.format_exc())
        self._send(
            spec, phase, message=_friendly(exc),
            local_version=local, remote_version=remote, finished=True,
            error=ErrorInfo(kind=type(exc).__name__, message=_friendly(exc),
                            detail=traceback.format_exc()),
        )

    # ------------------------------------------------------------------
    # network gating
    # ------------------------------------------------------------------
    @staticmethod
    def _network_status() -> tuple[bool, str]:
        try:
            return services.network_status()
        except Exception as exc:
            get_logger().warning("读取 Windows 网络状态失败: %s", exc)
            return True, "网络状态未知"

    def _await_network(self, spec: AppSpec, token: CancellationToken,
                       *, hold: bool = False) -> None:
        """Suspend the task in WAITING_NETWORK until Windows is online again."""
        online, detail = self._network_status()
        if online and not hold:
            return
        self._send(spec, Phase.WAITING_NETWORK,
                   message=f"{detail}，等待连接…")
        while True:
            token.raise_if_cancelled()
            if token.wait(services.NETWORK_POLL_SECONDS):
                raise Cancelled("任务已取消")
            online, _ = self._network_status()
            if online:
                break
        self.log.info("[%s] 网络已连接，继续执行", spec.id)
        self._send(spec, Phase.QUEUED, message="网络已连接，继续任务")

    # ------------------------------------------------------------------
    def run(self, spec: AppSpec, mode: Mode, token: CancellationToken) -> None:
        ctx = Context(self, spec, token)
        if not self.wait_for_network:
            online, detail = self._network_status()
            if not online:
                self._send(spec, Phase.WAITING_NETWORK,
                           message=f"{detail}，等待连接", finished=True)
                return
        retry_after_outage = False
        for attempt in range(NETWORK_ATTEMPTS):
            local = remote = ""
            needs: bool | None = None
            not_installed = False
            try:
                self._await_network(spec, token, hold=retry_after_outage)
                retry_after_outage = False
                token.raise_if_cancelled()
                self._send(spec, Phase.CHECKING, message="读取本地版本")
                try:
                    local = self._local_version(spec, mode, ctx)
                except NotInstalled:
                    if mode != Mode.CHECK:
                        raise
                    local = ""
                    not_installed = True
                # Do not publish the plain version here: the remote resolver
                # supplies the build date, and sending a bare "3.0.25" would
                # overwrite the date-decorated label already in the table.
                self._send(spec, Phase.CHECKING, message="查询最新版本")

                info = self._remote_info(spec, ctx)
                version = info.version
                needs = services.is_newer(version, local,
                                          lexicographic=spec.lexicographic)
                if mode.is_force or info.extra.get("force_update"):
                    needs = True
                # An app that is not installed must never be reported as
                # updatable: is_newer(remote, "") would otherwise return True
                # and an unattended sweep could install it from scratch.
                if not_installed:
                    needs = False
                # Build dates are display-only; version comparison, download
                # URLs and package names keep using the plain version string.
                local = _version_label(local, info.extra.get("local_date"))
                remote = _version_label(version, info.extra.get("remote_date"))
                self._send(spec, Phase.CHECKING, message="", local_version=local,
                           remote_version=remote, needs_update=needs)
                cache.update_app_cache(spec.id, local=local, remote=remote,
                                       needs_update=needs)
                self.log.info("[%s] local=%s remote=%s needs=%s",
                              spec.id, local, remote, needs)

                if mode == Mode.CHECK:
                    if not_installed:
                        phase, message = Phase.SKIPPED, "未安装"
                    elif needs:
                        phase, message = Phase.DONE, "检查完成"
                    else:
                        phase, message = Phase.UPTODATE, ""
                    self._send(spec, phase, message=message,
                               local_version=local, remote_version=remote,
                               needs_update=needs, finished=True,
                               level=(LogLevel.INFO if phase == Phase.UPTODATE
                                      else None))
                    return
                if not needs:
                    self._send(spec, Phase.UPTODATE, local_version=local,
                               remote_version=remote, needs_update=False,
                               finished=True)
                    return
                if spec.manual_only or (spec.install and spec.install.kind == "manual"):
                    self._manual(spec, info, ctx, token)
                    self._send(spec, Phase.MANUAL, message="已打开下载页面",
                               local_version=local, remote_version=remote,
                               finished=True)
                    return

                self._send(spec, Phase.PREPARING, message="准备下载",
                           local_version=local, remote_version=remote,
                           needs_update=True)
                url = self._download_url(spec, info, ctx)
                self._send(spec, Phase.DOWNLOADING,
                           local_version=local, remote_version=remote,
                           needs_update=True)
                with temporary_workspace(prefix="us-") as tmp:
                    ext = self._extension(url, spec)
                    dest = os.path.join(tmp, f"{spec.id}{ext}")
                    self._download(url, dest, spec, token)
                    if mode == Mode.DOWNLOAD_ONLY:
                        target_dir = download_dir()
                        os.makedirs(target_dir, exist_ok=True)
                        filename = (f"{spec.id}-{version}{ext}" if version
                                    else f"{spec.id}{ext}")
                        shutil.copy2(dest, os.path.join(target_dir, filename))
                        self._send(spec, Phase.DOWNLOADED, message=filename,
                                   local_version=local, remote_version=remote,
                                   finished=True)
                        return
                    self._send(spec, Phase.INSTALLING, message="正在安装",
                               local_version=local, remote_version=remote)
                    self._install(spec, dest, info, ctx, token)
                    self._post(spec, info, ctx, token)
                cache.record_update_time()
                self._send(spec, Phase.DONE, message="更新完成",
                           local_version=local, remote_version=remote,
                           needs_update=False, finished=True)
            except Cancelled as exc:
                self._finish_error(spec, Phase.CANCELLED, exc, local, remote)
                return
            except NotInstalled as exc:
                self.log.info("[%s] skipped: %s", spec.id, exc)
                self._send(spec, Phase.SKIPPED, message=str(exc),
                           local_version=local, remote_version=remote,
                           needs_update=needs, finished=True,
                           error=ErrorInfo(kind="NotInstalled", message=str(exc)))
                return
            except Exception as exc:
                if (self.wait_for_network
                        and attempt + 1 < NETWORK_ATTEMPTS
                        and services.is_connection_error(exc)
                        and not self._network_status()[0]):
                    self.log.info("[%s] 网络中断，等待连接后重试", spec.id)
                    retry_after_outage = True
                    continue
                self._finish_error(spec, Phase.FAILED, exc, local, remote)
                return


def _max_version(values: list[str]) -> str:
    from packaging.version import parse
    return str(max(values, key=lambda v: parse(v or "0")))
