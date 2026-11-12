"""Custom hooks for recipes that cannot be expressed declaratively.

Only 6 of 43 recipes need a custom resolver; everything else is data in
``catalog.py``. Hooks receive a :class:`~app.core.engine.Context` facade and
never call ``sys.exit`` / ``print``.
"""
from __future__ import annotations

import glob
import html
import json
import os
import re
import shutil
import tempfile
import time
from typing import Any

from ..core import services
from ..core.models import NotInstalled, QueryFailed, RemoteInfo

try:
    from packaging.version import parse as parse_version
except ImportError:  # pragma: no cover
    parse_version = None


# --------------------------------------------------------------------------
# remote resolvers
# --------------------------------------------------------------------------
def remote_ffmpeg(ctx) -> RemoteInfo:
    text = ctx.get("https://github.com/BtbN/FFmpeg-Builds/releases/latest")
    match = re.search(r"Auto-Build (\(*)(\d*)-(\d*)-(\d*)", text, flags=re.M)
    if not match:
        raise QueryFailed("ffmpeg 版本解析失败")
    return RemoteInfo(version=match.group(2) + match.group(3) + match.group(4),
                      text=text)


def remote_insta360(ctx) -> RemoteInfo:
    page = "https://www.insta360.com/cn/download/insta360-x4"
    text = ctx.get(page)
    urls = re.findall(
        r'(https://wassets\.insta360\.com/[^"]*Insta360_Studio_[^"]*\.exe)', text
    )
    if not urls:
        raise QueryFailed("未找到 Insta360 Studio 下载链接")

    def ver(u: str):
        m = re.search(r"Insta360_Studio_([\d.]+)", u)
        return parse_version(m.group(1) if m else "0")

    best = max(urls, key=ver)
    m = re.search(r"Insta360_Studio_([\d.]+)", best)
    return RemoteInfo(version=m.group(1) if m else "", url=best, text=text)


def remote_wps(ctx) -> RemoteInfo:
    text = ctx.get("https://www.wps.cn/platformUrlsv2")
    products = json.loads(text)["productList"]
    win64 = next(
        (p for p in products
         if p.get("productOs") == 1 and "x64" in p.get("productButtonUrl", "")),
        None,
    )
    if not win64:
        raise QueryFailed("未找到 WPS 64 位安装包")
    return RemoteInfo(version=str(win64["productVcode"]),
                      url=win64["productButtonUrl"], text=text)


def remote_qianwen(ctx) -> RemoteInfo:
    api = ("https://download.qianwen.com/pcdownload/qianwenpc"
           "?ch=pcqwen@homepage_official&platform=pc")
    text = ctx.get(api)
    link = json.loads(text)["data"]["url"]
    match = re.search(r"QianwenPC_V([\d\.]+)", link)
    return RemoteInfo(version=match.group(1) if match else "", url=link, text=text)


def remote_vlc(ctx) -> RemoteInfo:
    base = "https://artifacts.videolan.org/vlc-3.0/nightly-win64/"
    index = ctx.get(base)
    date_match = re.search(r"(\d{8}-\d{4})", index, flags=re.M | re.I)
    if not date_match:
        raise QueryFailed("VLC 构建目录解析失败")
    date = date_match.group(1)
    listing = base + date + "/"
    text = ctx.get(listing)
    package = re.search(r'([^"]*\.7z)', text, flags=re.M | re.I)
    if not package:
        raise QueryFailed("VLC 安装包解析失败")
    info = package.group(1)
    version = info.split("-")[1]
    remote_date = date.split("-")[0]
    local_date = "0"
    try:
        vlc_path = os.path.join(ctx.install_dir(), "vlc.exe")
        local_date = time.strftime("%Y%m%d", time.localtime(os.path.getmtime(vlc_path)))
    except Exception:
        pass
    return RemoteInfo(
        version=version, url=listing + info, text=text,
        extra={"force_update": remote_date > local_date,
               "remote_date": remote_date, "local_date": local_date},
    )


def remote_weixin(ctx) -> RemoteInfo:
    base = ("https://www.52pojie.cn/forum.php?mod=forumdisplay&fid=16"
            "&typeid=231&filter=typeid&typeid=231")
    pattern = r'(forum\.php[^"]*)[^>]*>微信Windows版 v+([\d\.]*)'
    fetchers = (ctx.get, ctx.rendered)
    for fetch in fetchers:
        for page in (1, 2):
            try:
                text = fetch(f"{base}&page={page}")
            except Exception:
                continue
            match = re.search(pattern, text, flags=re.M)
            if match:
                link = "https://www.52pojie.cn/" + html.unescape(match.group(1))
                return RemoteInfo(version=match.group(2), text=text,
                                  extra={"open_url": link})
    raise QueryFailed("未查询到微信版本（论坛可能有反爬限制）")


# --------------------------------------------------------------------------
# local resolvers
# --------------------------------------------------------------------------
def local_heukms(ctx) -> str:
    matches = glob.glob(os.path.join(ctx.install_dir(), "HEU_KMS_Activator*"))
    if not matches:
        raise NotInstalled("HEU KMS Activator 主程序不存在")
    return services.get_file_version(matches[0])


# --------------------------------------------------------------------------
# install hooks
# --------------------------------------------------------------------------
def install_vlc(ctx, info: RemoteInfo, dest: str) -> None:
    tmp = tempfile.mkdtemp(prefix="us-vlc-")
    try:
        services.extract_archive(dest, tmp, settings=ctx.settings)
        candidates = [p for p in glob.glob(os.path.join(tmp, "vlc-*"))
                      if os.path.isdir(p)]
        if not candidates:
            raise QueryFailed("VLC 解压目录不存在")
        target = ctx.install_dir(create=True)
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(candidates[0], target, dirs_exist_ok=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# post hooks
# --------------------------------------------------------------------------
def post_heukms_cleanup(ctx, info: RemoteInfo) -> None:
    files = glob.glob(os.path.join(ctx.install_dir(), "HEU_KMS_Activator*"))
    if len(files) < 2:
        return
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for old in files[1:]:
        try:
            os.remove(old)
        except OSError:
            pass


def post_weixin_cleanup(ctx, info: RemoteInfo) -> None:
    root = ctx.install_dir()
    if not os.path.isdir(root):
        return
    versions = []
    for name in os.listdir(root):
        full = os.path.join(root, name)
        if os.path.isdir(full) and re.match(r"^(\d+(?:\.\d+)*)$", name):
            try:
                versions.append((parse_version(name), full))
            except Exception:
                pass
    if len(versions) >= 2:
        versions.sort(key=lambda t: t[0])
        for _, path in versions[:-1]:
            shutil.rmtree(path, ignore_errors=True)


# --------------------------------------------------------------------------
# drag & drop archive handlers
# --------------------------------------------------------------------------
def bcompare_match(entries: list[str]) -> bool:
    return any(n.replace("\\", "/") in ("Beyond_Compare", "Beyond_Compare/")
               or n.replace("\\", "/").startswith("Beyond_Compare/")
               for n in entries)


def bcompare_install(path: str, entries: list[str], settings) -> str:
    target = services.find_install_dir(("Beyond Compare",), settings)
    tmp = tempfile.mkdtemp(prefix="us-drop-")
    try:
        services.kill_process("BCompare.exe")
        services.extract_archive(path, tmp, settings=settings)
        candidates = glob.glob(os.path.join(tmp, "Beyond_Compare", "BCompare"))
        source = candidates[0] if candidates else tmp
        for cfg in ("BCPreferences.xml", "BCSettings.xml", "BCState.xml"):
            candidate = os.path.join(source, cfg)
            if os.path.isfile(candidate):
                os.remove(candidate)
        shutil.copytree(source, target, dirs_exist_ok=True)
        return "Beyond Compare"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def weixin_match(entries: list[str]) -> bool:
    for raw in entries:
        n = raw.replace("\\", "/")
        if n in ("Weixin", "Weixin.exe") or n.startswith("Weixin/"):
            return True
    return False


def weixin_install(path: str, entries: list[str], settings) -> str:
    target = services.find_install_dir((r"Tencent\Weixin",), settings)
    tmp = tempfile.mkdtemp(prefix="us-drop-")
    try:
        services.kill_process("Weixin.exe")
        services.extract_archive(path, tmp, settings=settings)
        candidates = glob.glob(os.path.join(tmp, "Weixin"))
        source = candidates[0] if candidates else tmp
        shutil.copytree(source, target, dirs_exist_ok=True)
        post_weixin_cleanup(_SimpleContext(target, settings), RemoteInfo())
        return "微信"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class _SimpleContext:
    def __init__(self, install_dir: str, settings) -> None:
        self._install_dir = install_dir
        self.settings = settings

    def install_dir(self, create: bool = False) -> str:
        return self._install_dir


ARCHIVE_HANDLERS: dict[str, dict[str, Any]] = {
    "bcompare": {"match": bcompare_match, "install": bcompare_install},
    "weixin": {"match": weixin_match, "install": weixin_install},
}

HOOKS: dict[str, dict[str, Any]] = {
    "remote": {
        "ffmpeg": remote_ffmpeg,
        "insta360": remote_insta360,
        "wps": remote_wps,
        "qianwen": remote_qianwen,
        "vlc": remote_vlc,
        "weixin": remote_weixin,
    },
    "local": {"heukms": local_heukms},
    "download": {},
    "install": {"vlc": install_vlc},
    "post": {
        "heukms_cleanup": post_heukms_cleanup,
        "weixin_cleanup": post_weixin_cleanup,
    },
    "archive": ARCHIVE_HANDLERS,
}
