"""Short constructors that keep the catalog readable and purely declarative.

They take the typed DSL from ``app.core.models`` directly: a wrong kind,
mode or transform is a ``NameError`` at import time, not a failed update.
"""
from __future__ import annotations

from typing import Sequence

from ..core.models import (
    AddToPath, AppSpec, CustomPost, DeleteRegistryKey, DeployMode,
    DownloadSpec, InstallKind, InstallSpec, Kill, KillTree, LocalKind,
    LocalSpec, OpenInstallDir, OpenUrl, PostAction, RemoteKind, RemoteSpec,
    RemoveShortcut, ResponseKind, ResponsePattern,
)


def exe(target: str) -> LocalSpec:
    return LocalSpec(kind=LocalKind.EXE, target=target)


def product(target: str) -> LocalSpec:
    return LocalSpec(kind=LocalKind.PRODUCT, target=target)


def regex(url: str, pattern: str, **kwargs) -> RemoteSpec:
    return RemoteSpec(url=url, kind=RemoteKind.REGEX, pattern=pattern, **kwargs)


def redirect(url: str, pattern: str, **kwargs) -> RemoteSpec:
    return RemoteSpec(url=url, kind=RemoteKind.REDIRECT, pattern=pattern, **kwargs)


def custom_remote(name: str, url: str = "") -> RemoteSpec:
    return RemoteSpec(url=url, kind=RemoteKind.CUSTOM, custom=name)


def url(template: str) -> DownloadSpec:
    return DownloadSpec(url=template)


def from_response(kind: ResponseKind, pattern: str) -> DownloadSpec:
    return DownloadSpec(from_response=ResponsePattern(kind, pattern))


def installer(args: str = "") -> InstallSpec:
    return InstallSpec(kind=InstallKind.INSTALLER, args=args)


def extract(mode: DeployMode = DeployMode.OVERWRITE, subdir: str = "") -> InstallSpec:
    return InstallSpec(kind=InstallKind.EXTRACT, mode=mode, subdir=subdir)


def kill(image: str) -> Kill:
    return Kill(image=image)


def kill_tree(image: str) -> KillTree:
    return KillTree(image=image)


def add_to_path(target: str = "") -> AddToPath:
    return AddToPath(target=target)


def remove_shortcut(name: str) -> RemoveShortcut:
    return RemoveShortcut(name=name)


def delete_registry_key(key: str) -> DeleteRegistryKey:
    return DeleteRegistryKey(key=key)


def open_url(url: str = "") -> OpenUrl:
    return OpenUrl(url=url)


def open_install_dir() -> OpenInstallDir:
    return OpenInstallDir()


def custom_post(hook: str) -> CustomPost:
    return CustomPost(hook=hook)


def make(id: str, name: str, category: str, homepage: str, dirs,
         local, remote, download, install, post: Sequence[PostAction] = (),
         **kwargs) -> AppSpec:
    if isinstance(dirs, str):
        dirs = (dirs,)
    return AppSpec(
        id=id, name=name, category=category, homepage=homepage,
        install_dirs=tuple(dirs or ()), local=local, remote=remote,
        download=download, install=install, post=tuple(post), **kwargs,
    )
