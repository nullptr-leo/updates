"""Build a standalone UpdateScripts.exe with PyInstaller.

Usage: python build_exe.py
Output: dist/UpdateScripts.exe
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEP = os.pathsep  # ";" on Windows, ":" elsewhere


def available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def main() -> int:
    from PyInstaller.__main__ import run as pyinstaller_run
    from PySide6.QtCore import QLibraryInfo

    translations = Path(
        QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    args = [
        "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", "UpdateScripts",
        "--icon", str(ROOT / "assets" / "update.ico"),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build" / "work"),
        "--specpath", str(ROOT / "build"),
        "--add-data", f"{ROOT / 'assets'}{SEP}assets",
    ]
    for name in ("qtbase_zh_CN.qm", "qt_zh_CN.qm"):
        qm = translations / name
        if qm.is_file():
            args += ["--add-data", f"{qm}{SEP}translations"]
    for module in (
        "py7zr", "unrar", "unrar.rarfile",
        "winrt", "winrt.windows.management.deployment",
        "winsdk", "winsdk.windows.management.deployment",
        "PySide6.QtNetwork",
    ):
        if available(module):
            args += ["--hidden-import", module]
    args.append(str(ROOT / "main.pyw"))

    print("输出:", ROOT / "dist" / "UpdateScripts.exe")
    pyinstaller_run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
