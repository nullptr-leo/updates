"""Main window: wires the header, app table, detail panel, activity log and
tray to the task pool.

Widget construction lives in the sibling modules (``header``, ``app_table``,
``dialogs``, ...) and recipe logic in ``app.core``; this class only
coordinates them and decides what a user action means.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QProcess, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QMainWindow, QMenu, QMessageBox, QSplitter,
    QVBoxLayout, QWidget,
)

from .. import __version__
from ..adapters.qt_process import QProcessPort
from ..apps import HOOKS, registry
from ..core import cache, drop_install, self_update, services
from ..core.config import (
    CONFIG_PATH, ICON_PATH, IS_FROZEN, Settings, restart_command, save_settings,
)
from ..core.engine import UpdateEngine
from ..core.models import AppSpec, ErrorInfo, LogLevel, Mode, Phase, ProgressEvent
from ..workers.update_worker import TaskPool
from . import proxy_menu
from .app_table import AppTable
from .dialogs import AboutDialog, IgnoredDialog
from .header import HeaderBar
from .taskbar import TaskbarProgress
from .theme import apply_theme
from .tray import Tray
from .widgets import ActivityPanel, DetailPanel, SettingsDialog, StatusDelegate


class _AsyncSignals(QObject):
    """Signals that worker threads use to hand a result back to the UI thread."""
    archiveDone = Signal(bool, str, str, str)
    selfUpdateDone = Signal(bool, bool)
    linksReady = Signal(object)


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, version_text: str = "",
                 parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.version_text = version_text
        self._force_quit = False
        self._taskbar = TaskbarProgress()
        self._async = _AsyncSignals()
        self._async.archiveDone.connect(self._on_archive_done)
        self._async.selfUpdateDone.connect(self._on_self_update_done)
        self._async.linksReady.connect(self._on_links_ready)

        self.pool = TaskPool(settings, hooks=HOOKS, port=QProcessPort(), parent=self)
        self.pool.event.connect(self._on_event)
        self.pool.taskFinished.connect(lambda _app_id: self._update_activity())
        self.pool.idle.connect(self._on_idle)

        self.table = AppTable(registry.visible(settings), cache.load_cache(),
                              settings, self)
        self.table.currentChanged.connect(self._on_selection)
        self.table.sortChanged.connect(self._on_sort_changed)
        self.table.contextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_double_click)

        self.setWindowTitle("Update Scripts" + (f"  ·  {version_text}" if version_text else ""))
        self.resize(1080, 680)
        self.setMinimumSize(820, 500)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setAcceptDrops(True)

        self._build_ui()
        self._build_tray()
        self._apply_theme(settings.theme)
        self._apply_schedule()
        self._update_stats()
        self._update_activity()
        self.activity.append_line(f"已加载 {self.table.row_count()} 个软件")

        if settings.run_on_start:
            QTimer.singleShot(900, self._run_cycle)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(10)

        self.header = HeaderBar(self.version_text or "2.0")
        self.header.updateRequested.connect(self._check_and_update_all)
        self.header.stopRequested.connect(self._stop)
        self.header.searchChanged.connect(self._apply_filter)
        self.header.filterChanged.connect(self._apply_filter)
        self.header.settingsRequested.connect(self._open_settings)
        self.header.more_btn.setMenu(self._build_more_menu())
        root.addWidget(self.header)

        self.detail = DetailPanel()
        self.detail.actionRequested.connect(self._on_detail_action)
        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.addWidget(self.table.view)
        horizontal.addWidget(self.detail)
        horizontal.setStretchFactor(0, 1)
        horizontal.setSizes([760, 260])

        self.activity = ActivityPanel(registry)
        vertical = QSplitter(Qt.Orientation.Vertical)
        vertical.addWidget(horizontal)
        vertical.addWidget(self.activity)
        vertical.setStretchFactor(0, 1)
        vertical.setSizes([430, 160])
        root.addWidget(vertical, 1)
        self.statusBar().showMessage("就绪")

    def _build_more_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction("打开配置文件", lambda: services.open_path(str(CONFIG_PATH)))
        menu.addAction("已忽略的软件…", self._show_ignored)
        menu.addAction("升级软件", self._self_update)
        menu.addAction("恢复代理策略", self._reset_proxy_rules)
        menu.addSeparator()
        menu.addAction("关于", self._about)
        return menu

    def _build_tray(self) -> None:
        self.tray = Tray(str(ICON_PATH), self)
        self.tray.restoreRequested.connect(self.restore_from_tray)
        self.tray.checkUpdateAllRequested.connect(self._check_and_update_all)
        self.tray.selfUpdateRequested.connect(self._self_update)
        self.tray.exitRequested.connect(self.quit_app)
        self.tray.show()

    # -------------------------------------------------------------- helpers
    def _selected_specs(self) -> list[AppSpec]:
        return self.table.selected_specs()

    def _specs_for(self, mode: Mode, specs: list[AppSpec] | None,
                   all_visible: bool) -> list[AppSpec]:
        if all_visible:
            return self.table.specs()
        if specs is not None:
            return specs
        current = self.table.current_spec()
        return [current] if current is not None else []

    def _start(self, mode: Mode, specs: list[AppSpec] | None = None,
               all_visible: bool = False, *, auto: bool = False) -> bool:
        targets = [s for s in self._specs_for(mode, specs, all_visible)
                   if not self.pool.is_active(s.id)]
        if not targets:
            return False
        self.table.reset_phases([s.id for s in targets])
        self.header.set_busy(True)
        self.activity.append_line(
            ("自动检查更新：" if auto else "")
            + f"开始「{mode.label}」，共 {len(targets)} 个软件："
            + ", ".join(s.id for s in targets[:8])
            + ("…" if len(targets) > 8 else ""),
            level=LogLevel.DEBUG,
        )
        self.pool.submit(targets, mode)
        self._update_activity()
        return True

    def _start_update_all(self, *, auto: bool = False) -> None:
        self._start(Mode.UPDATE, all_visible=True, auto=auto)

    def _check_and_update_all(self) -> None:
        """Check and update every visible app in one sweep."""
        if self.pool.active_count():
            self.activity.append_line("上一轮任务尚未结束")
            return
        self._start_update_all()

    def _stop(self) -> None:
        self.pool.cancel_all()
        self.activity.append_line("已发送停止请求")

    # --------------------------------------------------------------- events
    def _on_event(self, ev: ProgressEvent) -> None:
        if (ev.phase == Phase.DOWNLOADING and not ev.finished
                and not ev.error):
            # Byte-level progress only drives the table cell; keep the log
            # buffer, stats and detail panel free of 5Hz redraws.
            self.table.apply_event(ev)
            return
        self.table.apply_event(ev)
        self.activity.append_event(ev)
        row = self.table.row_of(ev.app_id)
        if row is not None:
            self.detail.set_row(row)
        if ev.finished and ev.error:
            self.statusBar().showMessage(
                f"{ev.app_id}: {ev.error.message}", 8000)
        self._update_stats()
        if ev.phase == Phase.WAITING_NETWORK:
            self.statusBar().showMessage(ev.message or "网络未连接，任务等待连接…")
        self._update_activity()

    def _on_idle(self) -> None:
        self.header.set_busy(False)
        done, total = self.pool.progress()
        self.activity.append_line(f"任务进度（{done}/{total}）",
                                  level=LogLevel.DEBUG)
        self.statusBar().showMessage("任务结束")
        self._update_activity()

    def _on_selection(self, row) -> None:
        if row is None:
            self.detail.set_spec(None)
        else:
            self.detail.set_spec(row.spec, row)

    def _on_double_click(self, index) -> None:
        spec = self.table.spec_at(index)
        if spec is not None:
            self._start(Mode.UPDATE, [spec])

    def _show_context_menu(self, pos) -> None:
        if not self.table.has_row_at(pos):
            return
        specs = self._selected_specs()
        if not specs:
            return
        menu = QMenu(self)
        for label, mode in (("检查更新", Mode.UPDATE), ("检查远程版本", Mode.CHECK),
                            ("强制更新", Mode.FORCE), ("仅下载安装包", Mode.DOWNLOAD_ONLY)):
            action = menu.addAction(label)
            action.triggered.connect(
                lambda _=False, m=mode, s=list(specs): self._start(m, s))
        menu.addAction("复制下载链接",
                       lambda: self._copy_download_links(list(specs)))
        menu.addSeparator()
        proxy_menu.add_submenu(menu, specs, self.settings, self._set_proxy_rules)
        menu.addSeparator()
        menu.addAction("停止所选任务", lambda: [self.pool.cancel(s.id) for s in specs])
        menu.addSeparator()
        menu.addAction("打开程序", lambda: [self._open_program(s) for s in specs])
        menu.addAction("打开程序目录", lambda: [self._open_dir(s) for s in specs])
        menu.addAction("打开软件主页", lambda: [services.open_url(s.homepage) for s in specs])
        menu.addSeparator()
        menu.addAction("忽略", lambda: [self._ignore(s.id) for s in specs])
        menu.exec(self.table.map_to_global(pos))

    def _copy_download_links(self, specs: list[AppSpec]) -> None:
        self.activity.append_line("正在解析下载链接…")

        def work() -> None:
            engine = UpdateEngine(self.settings, emit=lambda ev: None,
                                  hooks=HOOKS, wait_for_network=False)
            links: list[str] = []
            errors: list[str] = []
            for spec in specs:
                try:
                    url = engine.resolve_download_url(spec)
                    if url:
                        links.append(url)
                    else:
                        errors.append(f"{spec.id}（无直接下载链接）")
                except Exception as exc:
                    errors.append(f"{spec.id}（{exc}）")
            self._async.linksReady.emit((links, errors))

        threading.Thread(target=work, daemon=True).start()

    def _on_links_ready(self, payload: tuple[list[str], list[str]]) -> None:
        links, errors = payload
        if links:
            QGuiApplication.clipboard().setText("\n".join(links))
            self.activity.append_line(f"已复制 {len(links)} 个下载链接到剪贴板")
        if errors:
            self.activity.append_line("未获取到下载链接：" + "、".join(errors))

    def _set_proxy_rules(self, specs: list[AppSpec], value: str) -> None:
        text = proxy_menu.apply(specs, value, self.settings)
        save_settings(self.settings)
        self.activity.append_line(
            f"代理策略 → {text}：" + ", ".join(s.id for s in specs))

    def _reset_proxy_rules(self) -> None:
        if not proxy_menu.reset(self.settings):
            self.activity.append_line("当前没有自定义代理策略")
            return
        save_settings(self.settings)
        self.activity.append_line("已恢复所有软件为配方默认代理策略")

    def _on_detail_action(self, app_id: str, action: str) -> None:
        spec = registry.by_id(app_id)
        if spec is None:
            return
        if action == "check":
            self._start(Mode.CHECK, [spec])
        elif action == "update":
            self._start(Mode.UPDATE, [spec])
        elif action == "force":
            self._start(Mode.FORCE, [spec])
        elif action == "download":
            self._start(Mode.DOWNLOAD_ONLY, [spec])
        elif action == "open_exe":
            self._open_program(spec)
        elif action == "open_dir":
            self._open_dir(spec)
        elif action == "open_home":
            services.open_url(spec.homepage)
        elif action == "ignore":
            self._ignore(app_id)

    # --------------------------------------------------------------- actions
    def _open_program(self, spec: AppSpec) -> None:
        path = services.program_path(spec, self.settings)
        if path:
            services.open_path(path)
        else:
            self.activity.append_line(f"{spec.name}: 未找到安装目录")

    def _open_dir(self, spec: AppSpec) -> None:
        if not spec.install_dirs:
            return
        try:
            services.open_explorer(
                services.find_install_dir(spec.install_dirs, self.settings))
        except Exception as exc:
            self.activity.append_line(f"{spec.name}: {exc}")

    def _ignore(self, app_id: str) -> None:
        if app_id not in self.settings.ignored:
            self.settings.ignored.append(app_id)
            save_settings(self.settings)
        self._rebuild_table()
        self.activity.append_line(f"已忽略 {app_id}，可在「更多 → 已忽略的软件」恢复")

    def _show_ignored(self) -> None:
        dialog = IgnoredDialog(list(self.settings.ignored), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings.ignored = dialog.remaining()
            save_settings(self.settings)
            self._rebuild_table()

    def _rebuild_table(self) -> None:
        self.table.rebuild(registry.visible(self.settings), cache.load_cache())
        self.detail.set_spec(None)
        self._update_stats()
        self._update_activity()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.settings = dialog.values()
        save_settings(self.settings)
        self.pool.engine.settings = self.settings
        self.pool.settings = self.settings
        self.pool.set_concurrency(self.settings.concurrency)
        self._apply_theme(self.settings.theme)
        self._apply_schedule()
        self._update_activity()
        self.activity.append_line("设置已保存")

    def _about(self) -> None:
        AboutDialog(__version__, self).exec()

    def _apply_filter(self, *_args) -> None:
        self.table.set_filter(self.header.search_text(), self.header.filter_text())

    def _on_sort_changed(self, column: int, descending: bool) -> None:
        self.settings.sort_column = column
        self.settings.sort_desc = descending
        save_settings(self.settings)

    def _apply_theme(self, theme: str) -> None:
        app = QApplication.instance()
        if app is None:
            return
        colors = apply_theme(app, theme)
        self._status_delegate = StatusDelegate(colors, self.table.view)
        self.table.set_status_delegate(self._status_delegate)
        self.activity.set_colors(colors)

    def _update_stats(self) -> None:
        total, updatable, ok, bad = self.table.counts()
        self.header.set_stats(
            f"共 {total}  ·  可更新 {updatable}  ·  已是最新 {ok}  ·  异常 {bad}")
        self.statusBar().showMessage(f"上次更新：{cache.last_update_time()}")

    def _update_activity(self) -> None:
        done, total = self.pool.progress()
        self.activity.set_progress(done, total)
        if total:
            self._taskbar.set_progress(int(self.winId()), done, total)

    # ------------------------------------------------------ tray / schedule
    def restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._update_activity()

    def quit_app(self) -> None:
        self._force_quit = True
        self.pool.cancel_all()
        self.pool.wait_for_done(1500)
        QApplication.instance().quit()

    def _run_cycle(self) -> None:
        """One check/update sweep, triggered by startup or the schedule."""
        if self.pool.active_count():
            self.activity.append_line("上一轮检查更新尚未结束，跳过本次")
            return
        if self.settings.auto_install_updates:
            self._start_update_all(auto=True)
        else:
            self._start(Mode.CHECK, all_visible=True, auto=True)

    def _apply_schedule(self) -> None:
        if not hasattr(self, "_scheduler"):
            self._scheduler = QTimer(self)
            self._scheduler.timeout.connect(self._run_cycle)
        if self.settings.schedule_enabled:
            self._scheduler.start(self.settings.schedule_minutes * 60 * 1000)
        else:
            self._scheduler.stop()

    def closeEvent(self, event) -> None:
        if (self.settings.minimize_to_tray and not self._force_quit
                and self.tray.icon.isVisible()):
            self.hide()
            event.ignore()
            return
        self.pool.cancel_all()
        self.pool.wait_for_done(1500)
        event.accept()
        QApplication.instance().quit()

    # ------------------------------------------------------------- self-update
    def _self_update(self) -> None:
        if IS_FROZEN:
            self.activity.append_line("当前为独立安装包，请获取新版本安装程序")
            QMessageBox.information(
                self, "升级软件",
                "当前为独立安装包，暂不支持在线升级，请获取新版本的安装程序。")
            return
        self.activity.append_line("正在检查并获取最新版本…")

        def work() -> None:
            ok, changed = self_update.pull()
            self._async.selfUpdateDone.emit(ok, changed)

        threading.Thread(target=work, daemon=True).start()

    def _on_self_update_done(self, ok: bool, changed: bool = True) -> None:
        if not ok:
            self.activity.append_line("升级软件：未完成")
            QMessageBox.warning(
                self, "升级失败",
                "暂时无法获取最新版本，请检查网络连接后重试。",
            )
            return
        if not changed:
            self.activity.append_line("升级软件：已是最新版本，无需重启")
            return
        self.activity.append_line("升级软件：已完成")
        answer = QMessageBox.question(
            self, "升级完成", "已升级到最新版本，是否现在重启应用？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            QProcess.startDetached(*restart_command())
            self.quit_app()

    # ---------------------------------------------------------- drag & drop
    def dragEnterEvent(self, event) -> None:
        mime = event.mimeData()
        if mime.hasUrls() and any(
            u.toLocalFile().lower().endswith((".zip", ".7z", ".rar"))
            for u in mime.urls()
        ):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".zip", ".7z", ".rar")):
                self._handle_archive(path)
                break
        event.acceptProposedAction()

    def _handle_archive(self, path: str) -> None:
        try:
            entries = services.list_archive(path)
        except Exception as exc:
            QMessageBox.warning(self, "读取压缩包失败", str(exc))
            return
        found = drop_install.match(self.table.specs(), entries, HOOKS["archive"])
        if found is None:
            supported = " / ".join(
                s.name for s in self.table.specs() if s.archive_handler)
            QMessageBox.information(
                self, "未识别",
                f"该压缩包没有匹配到支持拖放安装的应用（{supported}）。")
            return
        spec, handler = found
        if self.pool.is_active(spec.id):
            self.activity.append_line(
                f"{spec.name} 正在更新中，跳过拖放安装",
                level=LogLevel.WARNING,
            )
            return
        self.table.set_phase(spec.id, Phase.INSTALLING)
        self._update_stats()
        self.activity.append_line(f"拖放安装：{spec.name}")
        settings = self.settings

        def work() -> None:
            result = drop_install.install(path, entries, spec, handler, settings,
                                          self.pool.engine)
            self._async.archiveDone.emit(result.ok, result.message,
                                         result.app_id, result.local)

        threading.Thread(target=work, daemon=True).start()

    def _on_archive_done(self, ok: bool, message: str,
                         app_id: str = "", local: str = "") -> None:
        self.activity.append_line(message)
        if ok and app_id:
            if local:
                spec = registry.by_id(app_id)
                phase, needs = drop_install.state_after_install(
                    app_id, local,
                    lexicographic=bool(spec and spec.lexicographic))
                self.table.set_local(app_id, local, needs_update=needs, phase=phase)
                fields: dict[str, object] = {"local": local}
                if needs is not None:
                    fields["needs_update"] = needs
                cache.update_app_cache(app_id, **fields)
                state = ("可更新" if needs else
                         "已是最新" if needs is False else "已刷新")
                self.activity.append_line(
                    f"{app_id} 本地版本已刷新：{local}（{state}）",
                    level=LogLevel.DEBUG)
            else:
                self.table.set_phase(
                    app_id, Phase.DONE, "安装完成，本地版本读取失败")
                self.activity.append_line(
                    f"{app_id} 本地版本读取失败，未刷新", level=LogLevel.WARNING)
            self._update_stats()
        elif not ok and app_id:
            self.table.set_phase(
                app_id, Phase.FAILED, message,
                ErrorInfo(kind="DragDropInstall", message=message),
            )
            self._update_stats()
        if not ok:
            QMessageBox.warning(self, "拖放安装", message)
