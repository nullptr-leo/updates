"""PySide6 entry point (windowless console).

On Windows a .pyw file is opened by pythonw.exe, so double-clicking it or
running `pythonw main.pyw` never shows the black console window. The GUI
window is shown normally; pass --hidden to start in the system tray only.
"""
import os
import sys

# pythonw.exe has no stdout/stderr; a stray print() would otherwise raise.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from app.bootstrap import run

if __name__ == "__main__":
    raise SystemExit(run())
