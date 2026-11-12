"""Application bootstrap: single instance, theme, logging and CLI mode.

``main.pyw`` is launched by pythonw.exe (no console window). Use ``--hidden``
to start in the system tray without showing the main window. Qt is imported
lazily so ``--cli`` runs on the pure-Python core only.
"""
from __future__ import annotations

import subprocess
import sys

from .core.config import PROJECT_ROOT, load_settings
from .core.logging_setup import setup_logging

INSTANCE_KEY = "UpdateScripts.SingleInstance.v2"


def git_version() -> str:
    if getattr(sys, "frozen", False):
        return ""
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        count = subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"], cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL, text=True, timeout=10,
            creationflags=flags).strip()
        date = subprocess.check_output(
            ["git", "log", "-1", "--format=%ci"], cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL, text=True, timeout=10,
            creationflags=flags).strip()
        return f"rev.{count} ({date.split()[0]})"
    except Exception:
        return ""


def _already_running() -> bool:
    from PySide6.QtNetwork import QLocalSocket
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_KEY)
    if socket.waitForConnected(300):
        socket.write(b"show")
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return True
    return False


def run_cli(argv: list[str]) -> int:
    """Headless check/update without Qt: python main.pyw --cli check [ids...]."""
    from .apps.hooks import HOOKS
    from .core.cancellation import CancellationToken
    from .core.engine import UpdateEngine
    from .core.models import Mode
    from .core.registry import all_specs, spec_by_id

    settings = load_settings()
    if len(argv) < 2:
        print("用法: python main.pyw --cli check|update|force|download_only [app-id ...]")
        return 2
    try:
        mode = Mode(argv[1].lower())
    except ValueError:
        mode = Mode.CHECK
    ids = argv[2:]
    specs = ([spec_by_id(i) for i in ids if spec_by_id(i)] if ids
             else list(all_specs()))
    if not specs:
        print("没有匹配的应用")
        return 1

    def emit(event) -> None:
        line = f"{event.app_id:<18} {event.phase.value:<8}"
        if event.local_version or event.remote_version:
            line += f" {event.local_version or '—'} -> {event.remote_version or '—'}"
        if event.message:
            line += f"  {event.message}"
        print(line, flush=True)
        if event.error:
            print("   " + event.error.message, flush=True)

    engine = UpdateEngine(settings, emit=emit, hooks=HOOKS,
                          wait_for_network=False)
    for spec in specs:
        engine.run(spec, mode, CancellationToken())
    return 0


def _install_chinese_translator(app) -> None:
    """Translate Qt's built-in labels (OK / Cancel / Copy / ...) to Chinese."""
    import PySide6
    from pathlib import Path
    from PySide6.QtCore import QLibraryInfo, QTranslator

    translator = QTranslator(app)
    folders = []
    if getattr(sys, "frozen", False):
        folders.append(Path(getattr(sys, "_MEIPASS", "")) / "translations")
    folders += [
        Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)),
        Path(PySide6.__file__).resolve().parent / "translations",
    ]
    for folder in folders:
        if (translator.load("qtbase_zh_CN", str(folder))
                or translator.load("qt_zh_CN", str(folder))):
            app.installTranslator(translator)
            return


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    setup_logging()
    hidden = "--hidden" in argv
    argv = [a for a in argv if a != "--hidden"]
    if argv and argv[0] == "--cli":
        return run_cli(argv)

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtNetwork import QLocalServer
    from PySide6.QtWidgets import QApplication
    from . import __version__
    from .core.config import ICON_PATH
    from .core.logging_setup import get_logger
    from .ui.main_window import MainWindow
    from .ui.theme import stylesheet

    app = QApplication(sys.argv)
    app.setApplicationName("Update Scripts")
    app.setOrganizationName("Update Scripts")
    app.setQuitOnLastWindowClosed(False)
    _install_chinese_translator(app)

    if _already_running():
        return 0
    server = QLocalServer()
    if not server.listen(INSTANCE_KEY):
        # Only clear a stale endpoint when binding actually failed, so a live
        # instance's server is never removed.
        QLocalServer.removeServer(INSTANCE_KEY)
        server.listen(INSTANCE_KEY)

    settings = load_settings()
    theme = settings.theme
    if theme == "system":
        try:
            theme = ("dark" if QGuiApplication.styleHints().colorScheme()
                     == Qt.ColorScheme.Dark else "light")
        except Exception:
            theme = "light"
    app.setStyleSheet(stylesheet(theme))
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    get_logger().info("启动 Update Scripts %s（%s）", __version__, git_version())
    window = MainWindow(settings, f"版本 {__version__}")
    server.newConnection.connect(lambda: (
        window.restore_from_tray(),
        server.nextPendingConnection().close(),
    ))
    if hidden and window.tray.icon.isVisible():
        window.hide()
    else:
        window.show()
    return app.exec()
