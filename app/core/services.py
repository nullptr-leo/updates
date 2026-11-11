"""Reusable, side-effect-explicit services.

Everything here is a plain function: no ``sys.argv``, no ``print``, no
``sys.exit``. Failures are raised as typed exceptions so the GUI can never be
killed by a library call (the legacy ``find_install_dir`` called ``sys.exit``).
"""
from __future__ import annotations

import glob
import html
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from typing import Callable, Iterable, Sequence

import requests
from packaging import version as pkg_version

from .cancellation import CancellationToken
from .config import Settings, UNRAR_DLL
from .models import Cancelled, LocalSpec, NotInstalled, QueryFailed, TimedOut
from .ports import CREATE_NO_WINDOW, ProcessPort, SubprocessPort

try:
    import win32api
except ImportError:  # pragma: no cover - allows core import on non-Windows
    win32api = None

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept-Encoding": "gzip, deflate",
}

_NETWORK_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.RequestException,
)


# --------------------------------------------------------------------------
# network
# --------------------------------------------------------------------------
def _proxies(settings: Settings | None) -> dict | None:
    addr = (settings.proxy if settings else "") or os.environ.get("UPDATE_PROXY_ADDR", "")
    if not addr:
        return None
    return {"http": addr, "https": addr}


def _verify(settings: Settings | None) -> bool:
    return bool(settings.verify_tls) if settings else True


def http_get(
    url: str,
    *,
    settings: Settings | None = None,
    headers: dict | None = None,
    timeout: int = 30,
) -> str:
    """Fetch a URL and return its text. Raises QueryFailed, never exits."""
    try:
        response = requests.get(
            url,
            headers={**DEFAULT_HEADERS, **(headers or {})},
            proxies=_proxies(settings),
            verify=_verify(settings),
            timeout=(10, timeout),
        )
        response.raise_for_status()
        return response.text
    except _NETWORK_ERRORS as exc:
        raise QueryFailed(f"网络错误: {type(exc).__name__}") from exc
    except Exception as exc:
        raise QueryFailed(str(exc) or repr(exc)) from exc


def get_redirected_url(url: str, *, settings: Settings | None = None) -> str:
    """Resolve the final URL after redirects (HEAD, then streaming GET)."""
    try:
        response = requests.head(
            url,
            headers=DEFAULT_HEADERS,
            proxies=_proxies(settings),
            verify=_verify(settings),
            allow_redirects=True,
            timeout=(10, 30),
        )
        if response.url and response.url != url:
            return response.url
        raise ValueError("HEAD did not redirect")
    except Exception:
        try:
            with closing_get(url, settings=settings) as response:
                return response.url
        except Exception as exc:
            raise QueryFailed(f"重定向查询失败: {exc}") from exc


def closing_get(url: str, *, settings: Settings | None = None):
    return requests.get(
        url,
        headers=DEFAULT_HEADERS,
        proxies=_proxies(settings),
        verify=_verify(settings),
        stream=True,
        allow_redirects=True,
        timeout=(10, 30),
    )


def query_rendered(url: str, *, timeout: int = 40) -> str:
    """Render a JS-challenged page with headless Edge, as a separate process."""
    candidates = [
        os.environ.get("MSEdgePath", ""),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    edge = next((p for p in candidates if p and os.path.isfile(p)), "")
    if not edge:
        raise QueryFailed("未找到 msedge.exe，无法渲染页面")
    profile = os.path.join(tempfile.gettempdir(), "update-scripts-edge-profile")
    args = [
        edge, "--headless", "--disable-gpu", "--no-sandbox",
        f"--user-data-dir={profile}", "--dump-dom", url,
    ]
    try:
        result = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout, creationflags=CREATE_NO_WINDOW,
        )
        return result.stdout.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        raise TimedOut("页面渲染超时") from exc
    except Exception as exc:
        raise QueryFailed(f"页面渲染失败: {exc}") from exc


def download_file(
    url: str,
    dest: str,
    *,
    settings: Settings | None = None,
    token: CancellationToken | None = None,
    headers: dict | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    """Stream a download with cooperative cancellation and byte progress."""
    if not url:
        raise QueryFailed("下载地址为空")
    try:
        response = requests.get(
            url,
            headers={**DEFAULT_HEADERS, **(headers or {})},
            proxies=_proxies(settings),
            verify=_verify(settings),
            stream=True,
            timeout=(30, 120),
        )
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or 0)
        current = 0
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if token is not None:
                    token.raise_if_cancelled()
                if not chunk:
                    continue
                fh.write(chunk)
                current += len(chunk)
                if on_progress:
                    on_progress(current, total)
        if on_progress:
            on_progress(current, total or current)
    except (Cancelled, TimedOut):
        raise
    except _NETWORK_ERRORS as exc:
        raise QueryFailed(f"下载失败: {type(exc).__name__}") from exc
    except Exception as exc:
        raise QueryFailed(f"下载失败: {exc}") from exc


# --------------------------------------------------------------------------
# local filesystem / versions
# --------------------------------------------------------------------------
def desktop_dir() -> str:
    return os.path.join(os.path.expanduser("~"), "Desktop")


def find_install_dir(names: str | Sequence[str], settings: Settings | None = None,
                     create: bool = False) -> str:
    if isinstance(names, str):
        names = [names]
    roots = (settings.search_paths if settings else []) or [
        r"C:\Program Files", r"C:\Program Files (x86)"
    ]
    for name in names:
        for root in roots:
            path = os.path.join(root, name)
            if os.path.isdir(path):
                return path
    if create:
        path = os.path.join(roots[0], names[0])
        os.makedirs(path, exist_ok=True)
        return path
    raise NotInstalled("未安装: " + ", ".join(names))


def get_file_version_parts(exe_path: str) -> tuple[int, int, int, int]:
    if win32api is None:
        raise QueryFailed("需要 pywin32 才能读取文件版本")
    if not os.path.isfile(exe_path):
        raise NotInstalled(f"找不到主程序: {exe_path}")
    info = win32api.GetFileVersionInfo(exe_path, os.sep)
    ms, ls = info["FileVersionMS"], info["FileVersionLS"]
    return win32api.HIWORD(ms), win32api.LOWORD(ms), win32api.HIWORD(ls), win32api.LOWORD(ls)


def get_file_version(exe_path: str) -> str:
    return "%d.%d.%d.%d" % get_file_version_parts(exe_path)


def get_appx_version(package_name: str) -> str:
    try:
        from winsdk.windows.management.deployment import PackageManager  # type: ignore
        from winsdk.windows.applicationmodel import Package  # type: ignore
        _ = Package
    except ImportError:
        try:
            from winrt.windows.management.deployment import PackageManager  # type: ignore
        except ImportError as exc:
            raise QueryFailed("需要 winsdk/winrt 才能读取 AppX 版本") from exc
    try:
        packages = PackageManager().find_packages_for_user("")
        for package in packages:
            if package.id.name == package_name:
                v = package.id.version
                return f"{v.major}.{v.minor}.{v.build}.{v.revision}"
    except Exception as exc:
        raise QueryFailed(f"AppX 版本读取失败: {exc}") from exc
    raise NotInstalled(f"未找到 AppX 包: {package_name}")


def get_local_version(local: LocalSpec | None, install_dir: str = "",
                      *, hooks: dict | None = None, ctx=None) -> str:
    if local is None:
        return ""
    kind = local.kind
    if kind == "custom":
        fn = (hooks or {}).get(local.custom)
        if fn is None:
            raise QueryFailed(f"未注册的本地版本钩子: {local.custom}")
        return str(fn(ctx))
    if kind == "exe":
        return get_file_version(os.path.join(install_dir, local.target))
    if kind == "appx":
        return get_appx_version(local.target)
    if kind == "parts":
        parts = get_file_version_parts(os.path.join(install_dir, local.target))
        return local.pattern % parts if local.pattern else "%d.%d.%d.%d" % parts
    if kind == "file":
        path = os.path.join(install_dir, local.target)
        if not os.path.isfile(path):
            raise NotInstalled(f"找不到版本文件: {path}")
        text = open(path, "r", encoding="utf-8", errors="replace").read()
        match = re.search(local.pattern, text, flags=re.M)
        if not match:
            raise QueryFailed("版本文件解析失败")
        return match.group(1)
    if kind == "command":
        result = subprocess.run(
            shlex.split(local.target), stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=20,
            creationflags=CREATE_NO_WINDOW,
        )
        text = result.stdout.decode("utf-8", errors="replace")
        match = re.search(local.pattern, text, flags=re.M) if local.pattern else None
        return match.group(1) if match else text.splitlines()[0] if text else ""
    if kind == "glob":
        matches = glob.glob(os.path.join(install_dir, local.target))
        if not matches:
            raise NotInstalled(f"找不到版本文件: {local.target}")
        name = os.path.basename(matches[0])
        match = re.search(local.pattern, name) if local.pattern else None
        return match.group(1) if match else name
    if kind == "mtime":
        path = os.path.join(install_dir, local.target)
        if not os.path.isfile(path):
            raise NotInstalled(f"找不到主程序: {path}")
        return time.strftime("%Y%m%d", time.localtime(os.path.getmtime(path)))
    raise QueryFailed(f"未知的本地版本方式: {kind}")


def is_newer(remote: str, local: str, *, lexicographic: bool = False) -> bool:
    if not remote:
        return False
    if not local or local == "0":
        return True
    try:
        if lexicographic:
            return remote > local
        return pkg_version.parse(remote) > pkg_version.parse(local)
    except Exception:
        return remote != local


# --------------------------------------------------------------------------
# archives
# --------------------------------------------------------------------------
def list_archive(path: str) -> list[str]:
    lower = path.lower()
    if lower.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            return zf.namelist()
    if lower.endswith(".7z"):
        try:
            import py7zr
            with py7zr.SevenZipFile(path, "r") as zf:
                return zf.getnames()
        except ImportError as exc:
            raise QueryFailed("需要 py7zr 才能读取 .7z 压缩包") from exc
    if lower.endswith(".rar"):
        try:
            import unrar  # noqa: F401
            from unrar import rarfile
            os.environ.setdefault("UNRAR_LIB_PATH", str(UNRAR_DLL))
            with rarfile.RarFile(path) as rf:
                return rf.namelist()
        except ImportError as exc:
            raise QueryFailed("需要 unrar 才能读取 .rar 压缩包") from exc
    raise QueryFailed(f"不支持的压缩包: {path}")


def _winrar_extract(path: str, dest: str, settings: Settings | None) -> None:
    winrar = os.path.join(find_install_dir("WinRAR", settings), "WinRAR.exe")
    if not os.path.isfile(winrar):
        raise QueryFailed("找不到 WinRAR.exe，且缺少对应的 Python 解压库")
    SubprocessPort().run(
        [winrar, "x", "-o+", "-inul", "-ibck", path, dest + os.sep],
        timeout=300,
    )


def extract_archive(path: str, dest: str, *, settings: Settings | None = None) -> None:
    os.makedirs(dest, exist_ok=True)
    lower = path.lower()
    if lower.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            zf.extractall(dest)
        return
    if lower.endswith(".7z"):
        try:
            import py7zr
        except ImportError:
            _winrar_extract(path, dest, settings)
        else:
            with py7zr.SevenZipFile(path, "r") as zf:
                zf.extractall(dest)
        return
    if lower.endswith(".rar"):
        try:
            from unrar import rarfile
            os.environ.setdefault("UNRAR_LIB_PATH", str(UNRAR_DLL))
            with rarfile.RarFile(path) as rf:
                rf.extractall(dest)
            return
        except ImportError:
            _winrar_extract(path, dest, settings)
            return
    _winrar_extract(path, dest, settings)


# --------------------------------------------------------------------------
# processes / system side effects
# --------------------------------------------------------------------------
def run_process(args: Sequence[str], *, port: ProcessPort | None = None,
                timeout: int = 300, token: CancellationToken | None = None,
                on_output: Callable[[str], None] | None = None) -> int:
    return (port or SubprocessPort()).run(
        list(args), timeout=timeout, token=token, on_output=on_output
    )


def kill_process(image_name: str) -> None:
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", image_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30, creationflags=CREATE_NO_WINDOW, check=False,
        )
    except Exception:
        pass


def append_env_var(name: str, values: Iterable[str]) -> bool:
    """Append to a machine-wide env var. Returns False when not elevated."""
    try:
        import winreg
        subkey = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey, 0,
                           winreg.KEY_READ | winreg.KEY_WRITE) as key:
            try:
                current, regtype = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                current, regtype = "", winreg.REG_EXPAND_SZ
            parts = [p for p in current.split(";") if p]
            changed = False
            for value in values:
                if value and value not in parts:
                    parts.append(value)
                    changed = True
            if changed:
                winreg.SetValueEx(key, name, 0, regtype, ";".join(parts))
        try:
            import ctypes
            ctypes.windll.user32.SendMessageTimeoutW(
                0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None
            )
        except Exception:
            pass
        return changed
    except Exception:
        return False


def delete_registry_key(key: str) -> None:
    try:
        subprocess.run(
            ["reg", "delete", key, "/f"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30, creationflags=CREATE_NO_WINDOW, check=False,
        )
    except Exception:
        pass


def remove_desktop_shortcut(name: str) -> None:
    for candidate in (name, name + ".lnk"):
        path = os.path.join(desktop_dir(), candidate)
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


def open_path(path: str) -> None:
    if not path or not os.path.exists(path):
        return
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def open_url(url: str) -> None:
    if not url:
        return
    target = html.unescape(url)
    if sys.platform == "win32":
        os.startfile(target)  # type: ignore[attr-defined]
    else:
        import webbrowser
        webbrowser.open(target)


def open_explorer(path: str) -> None:
    if path and os.path.isdir(path):
        subprocess.Popen(["explorer", path], creationflags=CREATE_NO_WINDOW)
