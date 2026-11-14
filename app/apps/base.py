"""Short constructors that keep the catalog readable and purely declarative."""
from __future__ import annotations

from ..core.models import (
    AppSpec, DownloadSpec, InstallSpec, LocalSpec, RemoteSpec,
)


def exe(target: str) -> LocalSpec:
    return LocalSpec(kind="exe", target=target)


def product(target: str) -> LocalSpec:
    return LocalSpec(kind="product", target=target)


def regex(url: str, pattern: str, **kwargs) -> RemoteSpec:
    return RemoteSpec(url=url, kind="regex", pattern=pattern, **kwargs)


def redirect(url: str, pattern: str, **kwargs) -> RemoteSpec:
    return RemoteSpec(url=url, kind="redirect", pattern=pattern, **kwargs)


def custom_remote(name: str, url: str = "") -> RemoteSpec:
    return RemoteSpec(url=url, kind="custom", custom=name)


def url(template: str) -> DownloadSpec:
    return DownloadSpec(url=template)


def from_response(expression: str) -> DownloadSpec:
    return DownloadSpec(from_response=expression)


def installer(args: str = "") -> InstallSpec:
    return InstallSpec(kind="installer", args=args)


def extract(mode: str = "overwrite", subdir: str = "") -> InstallSpec:
    return InstallSpec(kind="extract", mode=mode, subdir=subdir)


def make(id: str, name: str, category: str, homepage: str, dirs,
         local, remote, download, install, post=(), **kwargs) -> AppSpec:
    if isinstance(dirs, str):
        dirs = (dirs,)
    return AppSpec(
        id=id, name=name, category=category, homepage=homepage,
        install_dirs=tuple(dirs or ()), local=local, remote=remote,
        download=download, install=install, post=tuple(post), **kwargs,
    )
