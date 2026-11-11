"""Main window: three-zone layout, Model/View table, detail drawer and log."""
from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMenu, QMessageBox, QPushButton, QSplitter, QTableView, QVBoxLayout,
    QWidget, QFrame,
)

from ..adapters.qt_process import QProcessPort
from ..apps.hooks import HOOKS
from ..core import cache, services
from ..core.config import (
    CONFIG_PATH, ICON_PATH, MAIN_SCRIPT, PROJECT_ROOT, Settings, load_settings,
    pythonw_executable, save_settings,
)
from ..core.models import ACTIVE_PHASES, AppSpec, Mode, ProgressEvent
from ..core.registry import spec_by_id, visible_specs
from ..workers.update_worker import TaskPool
from .table_model import (
    C_CATEGORY, C_CHECKED, C_LOCAL, C_NAME, C_PROGRESS, C_REMOTE, C_STATUS,
    AppFilterProxyModel, AppTableModel,
)
from .theme import palette, stylesheet
from .tray import Tray
from .widgets import (
    ActivityPanel, DetailPanel, ProgressDelegate, SettingsDialog, StatusDelegate,
)


class _AsyncSignals(QObject):
    archiveDone = Signal(bool, str)
    selfUpdateDone = Signal(bool, str)


class IgnoredDialog(QDialog):
    def __init__(self, ignored: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("已忽略的软件")
        self.setMinimumWidth(320)
        self.list = QListWidget()
        self.list.addItems(ignored)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        restore = QPushButton("恢复选中")
        restore_all = QPushButton("恢复全部")
        restore.clicked.connect(self._restore_selected)
        restore_all.clicked.connect(self.list.clear)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        row = QHBoxLayout()
        row.addWidget(restore)
        row.addWidget(restore_all)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(buttons)

    def _restore_selected(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def remaining(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, version_text: str = "",
                 parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.version_text = version_text
        self._force_quit = False
        self._done = 0
        self._total = 0
        self._async = _AsyncSignals()
        self._async.archiveDone.connect(self._on_archive_done)
        self._async.selfUpdateDone.connect(self._on_self_update_done)

        self.pool = TaskPool(settings, hooks=HOOKS, port=QProcessPort(), parent=self)
        self.pool.event.connect(self._on_event)
        self.pool.idle.connect(self._on_idle)

        self.model = AppTableModel(visible_specs(settings), self)
        self.model.apply_cache(cache.load_cache())
        self.proxy = AppFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)

        self.setWindowTitle("Update Scripts" + (f"  ·  {version_text}" if version_text else ""))
        self.resize(1080, 680)
        self.setMinimumSize(820, 500)
        if ICON_PATH.exists():
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setAcceptDrops(True)

        self._build_ui()
        self._build_tray()
        self._apply_theme(settings.theme)
        self._apply_schedule()
        self._update_stats()
        self._update_activity()
        self.activity.append_line(f"已加载 {self.model.rowCount()} 个软件，并发上限 {settings.concurrency}")

        if settings.run_on_start or settings.schedule_enabled:
            QTimer.singleShot(900, lambda: self._start(Mode.CHECK, all_visible=True))

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(10)

        header = QFrame()
        header.setObjectName("Card")
        head = QVBoxLayout(header)
        head.setContentsMargins(16, 12, 16, 12)
        head.setSpacing(10)
        top = QHBoxLayout()
        title = QLabel("Update Scripts")
        title.setObjectName("Title")
        version = QLabel(self.version_text or "2.0")
        version.setObjectName("Subtle")
        self.stats = QLabel("")
        self.stats.setObjectName("Stat")
        top.addWidget(title)
        top.addWidget(version)
        top.addStretch(1)
        top.addWidget(self.stats)
        head.addLayout(top)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.check_btn = QPushButton("全部检查")
        self.update_btn = QPushButton("全部更新")
        self.update_btn.setObjectName("Primary")
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.setEnabled(False)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索软件名称 / 标识 / 分类")
        self.search.setFixedWidth(240)
        self.filter = QComboBox()
        self.filter.addItems(["全部", "可更新", "运行中", "异常", "需手动"])
        self.settings_btn = QPushButton("设置")
        self.more_btn = QPushButton("更多")
        self.check_btn.clicked.connect(lambda: self._start(Mode.CHECK, all_visible=True))
        self.update_btn.clicked.connect(self._confirm_update_all)
        self.stop_btn.clicked.connect(self._stop)
        self.search.textChanged.connect(self._apply_filter)
        self.filter.currentTextChanged.connect(self._apply_filter)
        self.settings_btn.clicked.connect(self._open_settings)
        self.more_btn.setMenu(self._build_more_menu())
        for widget in (self.check_btn, self.update_btn, self.stop_btn):
            toolbar.addWidget(widget)
        toolbar.addStretch(1)
        toolbar.addWidget(self.search)
        toolbar.addWidget(self.filter)
        toolbar.addWidget(self.settings_btn)
        toolbar.addWidget(self.more_btn)
        head.addLayout(toolbar)
        root.addWidget(header)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.selectionModel().currentChanged.connect(self._on_selection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(C_NAME, QHeaderView.ResizeMode.Stretch)
        for col in (C_CATEGORY, C_LOCAL, C_REMOTE, C_CHECKED):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(C_STATUS, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(C_PROGRESS, 120)
        self.table.setColumnWidth(C_STATUS, 190)

        self.detail = DetailPanel()
        self.detail.actionRequested.connect(self._on_detail_action)
        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.addWidget(self.table)
        horizontal.addWidget(self.detail)
        horizontal.setStretchFactor(0, 1)
        horizontal.setSizes([760, 260])

        self.activity = ActivityPanel()
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
        menu.addAction("自更新 (git pull)", self._self_update)
        menu.addSeparator()
        menu.addAction("关于", self._about)
        return menu

    def _build_tray(self) -> None:
        self.tray = Tray(str(ICON_PATH), self)
        self.tray.restoreRequested.connect(self.restore_from_tray)
        self.tray.checkAllRequested.connect(
            lambda: self._start(Mode.CHECK, all_visible=True))
        self.tray.updateAllRequested.connect(self._confirm_update_all)
        self.tray.selfUpdateRequested.connect(self._self_update)
        self.tray.exitRequested.connect(self.quit_app)
        self.tray.show()

    # -------------------------------------------------------------- helpers
    def _selected_specs(self) -> list[AppSpec]:
        indexes = self.table.selectionModel().selectedRows()
        specs = []
        for proxy_index in indexes:
            source = self.proxy.mapToSource(proxy_index)
            value = self.model.data(self.model.index(source.row(), C_NAME),
                                    Qt.ItemDataRole.UserRole)
            if isinstance(value, AppSpec):
                specs.append(value)
        return specs

    def _specs_for(self, mode: Mode, specs: list[AppSpec] | None,
                   all_visible: bool) -> list[AppSpec]:
        if all_visible:
            return self.model.specs()
        if specs:
            return specs
        current = self.table.selectionModel().currentIndex()
        if current.isValid():
            source = self.proxy.mapToSource(current)
            value = self.model.data(self.model.index(source.row(), C_NAME),
                                    Qt.ItemDataRole.UserRole)
            if isinstance(value, AppSpec):
                return [value]
        return []

    def _start(self, mode: Mode, specs: list[AppSpec] | None = None,
               all_visible: bool = False) -> None:
        targets = [s for s in self._specs_for(mode, specs, all_visible)
                   if not self.pool.is_active(s.id)]
        if not targets:
            return
        if mode in (Mode.UPDATE, Mode.FORCE) and len(targets) > 1:
            answer = QMessageBox.question(
                self, "确认更新",
                f"即将更新 {len(targets)} 个软件，期间会关闭相关程序并静默安装。\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.model.reset_phases([s.id for s in targets])
        self._total = len(targets)
        self._done = 0
        self._set_busy(True)
        self.activity.append_line(
            f"开始「{mode.label}」，共 {len(targets)} 个软件："
            + ", ".join(s.id for s in targets[:8])
            + ("…" if len(targets) > 8 else "")
        )
        self.pool.submit(targets, mode)
        self._update_activity()

    def _confirm_update_all(self) -> None:
        updatable = [self.model.row_at(i).spec
                     for i in range(self.model.rowCount())
                     if self.model.row_at(i).needs_update]
        if not updatable:
            self.activity.append_line("尚无版本信息，先执行全量检查再选择要更新的软件")
            self._start(Mode.CHECK, all_visible=True)
            return
        self._start(Mode.UPDATE, updatable)

    def _stop(self) -> None:
        self.pool.cancel_all()
        self.activity.append_line("已发送停止请求")

    def _set_busy(self, busy: bool) -> None:
        self.check_btn.setEnabled(not busy)
        self.update_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)

    # --------------------------------------------------------------- events
    def _on_event(self, ev: ProgressEvent) -> None:
        self.model.apply_event(ev)
        self.activity.append_event(ev)
        index = self.model.index_of(ev.app_id)
        if index >= 0:
            self.detail.set_row(self.model.row_at(index))
        if ev.finished:
            self._done += 1
            if ev.error:
                self.statusBar().showMessage(
                    f"{ev.app_id}: {ev.error.message}", 8000)
        self._update_stats()
        self._update_activity()

    def _on_idle(self) -> None:
        self._set_busy(False)
        self.activity.append_line(f"本轮任务结束（{self._done}/{self._total}）")
        self.statusBar().showMessage("任务结束")
        self.tray.notify("Update Scripts", "本轮任务已结束")
        self._update_activity()

    def _on_selection(self, current, previous) -> None:
        if not current.isValid():
            self.detail.set_spec(None)
            return
        source = self.proxy.mapToSource(current)
        if not source.isValid():
            return
        row = self.model.row_at(source.row())
        self.detail.set_spec(row.spec, row)

    def _on_double_click(self, index) -> None:
        source = self.proxy.mapToSource(index)
        value = self.model.data(self.model.index(source.row(), C_NAME),
                                Qt.ItemDataRole.UserRole)
        if isinstance(value, AppSpec):
            self._start(Mode.CHECK, [value])

    def _show_context_menu(self, pos) -> None:
        if not self.table.indexAt(pos).isValid():
            return
        specs = self._selected_specs()
        if not specs:
            return
        menu = QMenu(self)
        for label, mode in (("检查更新", Mode.CHECK), ("更新", Mode.UPDATE),
                            ("强制更新", Mode.FORCE), ("仅下载安装包", Mode.DOWNLOAD_ONLY)):
            action = menu.addAction(label)
            action.triggered.connect(
                lambda _=False, m=mode, s=list(specs): self._start(m, s))
        menu.addSeparator()
        menu.addAction("停止所选任务", lambda: [self.pool.cancel(s.id) for s in specs])
        menu.addSeparator()
        menu.addAction("打开程序", lambda: [self._open_program(s) for s in specs])
        menu.addAction("打开程序目录", lambda: [self._open_dir(s) for s in specs])
        menu.addAction("打开软件主页", lambda: [services.open_url(s.homepage) for s in specs])
        menu.addSeparator()
        menu.addAction("忽略", lambda: [self._ignore(s.id) for s in specs])
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_detail_action(self, app_id: str, action: str) -> None:
        spec = spec_by_id(app_id)
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
    def _program_path(self, spec: AppSpec) -> str:
        if not spec.install_dirs:
            return ""
        try:
            root = services.find_install_dir(spec.install_dirs, self.settings)
        except Exception:
            return ""
        if spec.local and spec.local.kind in ("exe", "parts", "mtime"):
            return os.path.join(root, spec.local.target)
        return root

    def _open_program(self, spec: AppSpec) -> None:
        path = self._program_path(spec)
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
        self._rebuild_model()
        self.activity.append_line(f"已忽略 {app_id}，可在「更多 → 已忽略的软件」恢复")

    def _show_ignored(self) -> None:
        dialog = IgnoredDialog(list(self.settings.ignored), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings.ignored = dialog.remaining()
            save_settings(self.settings)
            self._rebuild_model()

    def _rebuild_model(self) -> None:
        self.model = AppTableModel(visible_specs(self.settings), self)
        self.model.apply_cache(cache.load_cache())
        self.proxy.setSourceModel(self.model)
        try:
            self.table.selectionModel().currentChanged.disconnect(self._on_selection)
        except (TypeError, RuntimeError):
            pass
        self.table.selectionModel().currentChanged.connect(self._on_selection)
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
        QMessageBox.about(
            self, "关于 Update Scripts",
            "Update Scripts 2.0\n\nPySide6 重构版：声明式配方 + 结构化事件，"
            "不再通过命令行逐脚本调用。\n旧版代码已归档至 legacy/。",
        )

    def _apply_filter(self) -> None:
        self.proxy.set_filter(self.search.text(), self.filter.currentText())

    def _resolve_theme(self, theme: str) -> str:
        if theme != "system":
            return theme
        try:
            scheme = QGuiApplication.styleHints().colorScheme()
            return "dark" if scheme == Qt.ColorScheme.Dark else "light"
        except Exception:
            return "light"

    def _apply_theme(self, theme: str) -> None:
        app = QApplication.instance()
        if app is None:
            return
        resolved = self._resolve_theme(theme)
        app.setStyleSheet(stylesheet(resolved))
        colors = palette(resolved)
        self._status_delegate = StatusDelegate(colors, self.table)
        self._progress_delegate = ProgressDelegate(colors, self.table)
        self.table.setItemDelegateForColumn(C_STATUS, self._status_delegate)
        self.table.setItemDelegateForColumn(C_PROGRESS, self._progress_delegate)

    def _update_stats(self) -> None:
        rows = [self.model.row_at(i) for i in range(self.model.rowCount())]
        updatable = sum(1 for r in rows if r.needs_update)
        ok = sum(1 for r in rows if r.status_kind == "success")
        bad = sum(1 for r in rows if r.status_kind == "error")
        self.stats.setText(
            f"共 {len(rows)}  ·  可更新 {updatable}  ·  已是最新 {ok}  ·  异常 {bad}")
        self.statusBar().showMessage(f"上次更新：{cache.last_update_time()}")

    def _update_activity(self) -> None:
        self.activity.set_progress(self._done, self._total,
                                   self.pool.active_count(),
                                   self.settings.concurrency)

    # ------------------------------------------------------ tray / schedule
    def restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._force_quit = True
        self.pool.cancel_all()
        self.pool.wait_for_done(1500)
        QApplication.instance().quit()

    def _apply_schedule(self) -> None:
        if not hasattr(self, "_scheduler"):
            self._scheduler = QTimer(self)
            self._scheduler.timeout.connect(
                lambda: self._start(Mode.CHECK, all_visible=True))
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

    # ------------------------------------------------------ self update / DnD
    def _self_update(self) -> None:
        self.activity.append_line("正在执行 git pull --rebase …")

        def work() -> None:
            try:
                result = subprocess.run(
                    ["git", "pull", "--rebase"], cwd=str(PROJECT_ROOT),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", timeout=120,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                self._async.selfUpdateDone.emit(
                    result.returncode == 0, (result.stdout or "")[-800:])
            except Exception as exc:
                self._async.selfUpdateDone.emit(False, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _on_self_update_done(self, ok: bool, message: str) -> None:
        self.activity.append_line("自更新：" + ("成功" if ok else "失败") + f" {message[:160]}")
        if not ok:
            QMessageBox.warning(self, "自更新失败", message[-600:])
            return
        answer = QMessageBox.question(
            self, "自更新完成", "代码已更新，是否重启应用？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            QProcess.startDetached(pythonw_executable(), [str(MAIN_SCRIPT)])
            self.quit_app()

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
        for spec in self.model.specs():
            handler = HOOKS["archive"].get(spec.archive_handler) if spec.archive_handler else None
            if not handler or not handler["match"](entries):
                continue
            answer = QMessageBox.question(
                self, "识别到安装包",
                f"{Path(path).name} 匹配「{spec.name}」。\n是否解压并覆盖安装？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.activity.append_line(f"拖放安装：{spec.name}")
            settings = self.settings

            def work(p=path, h=handler, name=spec.name) -> None:
                try:
                    h["install"](p, entries, settings)
                    self._async.archiveDone.emit(True, f"{name} 安装完成")
                except Exception as exc:
                    self._async.archiveDone.emit(False, f"{name} 安装失败：{exc}")

            threading.Thread(target=work, daemon=True).start()
            return
        QMessageBox.information(
            self, "未识别",
            "该压缩包没有匹配到支持拖放安装的应用（Beyond Compare / 微信）。")

    def _on_archive_done(self, ok: bool, message: str) -> None:
        self.activity.append_line(message)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "拖放安装", message)
