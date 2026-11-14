"""Reusable widgets: status badge, inline progress, detail drawer, activity
panel and settings dialog."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import replace
from urllib.parse import urlsplit

from PySide6.QtCore import QEvent, QRect, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QStyle, QStyleOptionViewItem, QStyledItemDelegate,
    QVBoxLayout, QGridLayout, QWidget,
)

from ..core.config import Settings
from ..core.models import AppSpec, LogLevel, ProgressEvent
from ..core.registry import spec_by_id
from .table_model import PROGRESS_ROLE, AppRow


class StatusDelegate(QStyledItemDelegate):
    def __init__(self, colors: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self.colors = colors

    def paint(self, painter: QPainter, option, index) -> None:
        value = index.data(Qt.ItemDataRole.UserRole)
        text, kind = value if isinstance(value, tuple) else (str(value or ""), "idle")
        painter.save()
        self._paint_background(painter, option, index)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect
        progress = index.data(PROGRESS_ROLE)
        if isinstance(progress, tuple) and progress[1]:
            self._paint_progress(painter, rect, float(progress[0]))
        dot = QRect(rect.left() + 9, rect.center().y() - 4, 8, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self.colors.get(kind, self.colors["idle"]))))
        painter.drawEllipse(dot)
        painter.setPen(QPen(QColor(self.colors["text"])))
        text_rect = rect.adjusted(25, 0, -6, 0)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter |
                                        Qt.AlignmentFlag.AlignLeft), text)
        painter.restore()

    def _paint_background(self, painter: QPainter, option, index) -> None:
        """Draw the item background through the style so selection matches
        the other cells (QSS selection-background-color applies here)."""
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter,
                          widget)

    def _paint_progress(self, painter: QPainter, rect: QRect,
                        percent: float) -> None:
        bar = rect.adjusted(2, 2, -2, -2)
        if bar.width() <= 0 or bar.height() <= 0:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        track = QColor(self.colors["running"])
        track.setAlpha(14)
        painter.setBrush(QBrush(track))
        painter.drawRoundedRect(bar, 4, 4)
        width = int(bar.width() * min(100.0, max(3.0, percent)) / 100.0)
        fill = QColor(self.colors["running"])
        fill.setAlpha(46)
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(
            QRect(bar.left(), bar.top(), width, bar.height()), 4, 4)
        if percent > 0 and width > 6:
            edge = QColor(self.colors["running"])
            edge.setAlpha(120)
            painter.setBrush(QBrush(edge))
            painter.drawRoundedRect(
                QRect(bar.left() + width - 2, bar.top(), 2, bar.height()), 1, 1)


class _DetailScrollArea(QScrollArea):
    """Pin detail content to the viewport width and keep its natural height.

    A regular ``widgetResizable`` scroll area still squeezes word-wrapped
    labels when the panel is short, and an unbreakable URL can make the
    content wider than the visible area. Here the panel scrolls vertically
    instead of deforming its children.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailScroll")
        self.setWidgetResizable(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.viewport().setObjectName("DetailViewport")
        self.viewport().setAutoFillBackground(False)
        self.viewport().installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.viewport() and event.type() == QEvent.Type.Resize:
            self.fit_content()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_content()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.fit_content()

    def fit_content(self) -> None:
        content = self.widget()
        if content is None or not self.isVisible():
            return
        width = self.viewport().width()
        if width <= 0:
            return
        if content.width() != width:
            content.resize(width, content.height())
        layout = content.layout()
        needed = layout.totalHeightForWidth(width) if layout else -1
        if needed < 0:
            needed = content.sizeHint().height()
        height = max(self.viewport().height(), needed)
        if content.height() != height:
            content.resize(width, height)


class DetailPanel(QFrame):
    actionRequested = Signal(str, str)

    ACTIONS = (
        ("check", "检查更新"), ("update", "更新"), ("force", "强制更新"),
        ("download", "仅下载安装包"), ("open_exe", "打开程序"),
        ("open_dir", "打开程序目录"), ("open_home", "打开软件主页"),
        ("ignore", "忽略此软件"),
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumWidth(250)
        self._spec: AppSpec | None = None

        self.scroll = _DetailScrollArea(self)

        self.content = QWidget()
        self.content.setObjectName("DetailContent")
        self.content.setAutoFillBackground(False)
        root = QVBoxLayout(self.content)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)
        self.scroll.setWidget(self.content)

        self.title = QLabel("选择一个软件")
        self.title.setObjectName("Title")
        self.title.setWordWrap(True)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subtle")
        self.subtitle.setWordWrap(True)
        self.homepage = QLabel("")
        self.homepage.setOpenExternalLinks(True)
        self.homepage.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        self.homepage.setWordWrap(True)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setContentsMargins(0, 8, 0, 8)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setObjectName("Subtle")
        self.note.setContentsMargins(0, 0, 0, 8)
        self._labels = (self.title, self.subtitle, self.homepage,
                        self.info, self.note)
        for widget in self._labels:
            widget.setSizePolicy(QSizePolicy.Policy.Preferred,
                                 QSizePolicy.Policy.Minimum)
            root.addWidget(widget)

        grid = QGridLayout()
        grid.setSpacing(6)
        self._buttons: dict[str, QPushButton] = {}
        for i, (key, label) in enumerate(self.ACTIONS):
            button = QPushButton(label)
            button.setEnabled(False)
            button.setSizePolicy(QSizePolicy.Policy.Preferred,
                                 QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _=False, k=key: self._emit(k))
            self._buttons[key] = button
            grid.addWidget(button, i // 2, i % 2)
        root.addLayout(grid)
        root.addStretch(1)
        self._sync_visibility()

    @staticmethod
    def _set_text(label: QLabel, text: str) -> None:
        label.setText(text)
        label.setVisible(bool(text))

    def _sync_visibility(self) -> None:
        for label in self._labels:
            label.setVisible(bool(label.text()))

    def _emit(self, action: str) -> None:
        if self._spec:
            self.actionRequested.emit(self._spec.id, action)

    def set_spec(self, spec: AppSpec | None, row: AppRow | None = None) -> None:
        self._spec = spec
        for button in self._buttons.values():
            button.setEnabled(spec is not None)
        if spec is None:
            self._set_text(self.title, "选择一个软件")
            for label in self._labels[1:]:
                self._set_text(label, "")
            self.homepage.setToolTip("")
            self.scroll.fit_content()
            return
        url = spec.homepage or ""
        host = urlsplit(url).netloc or url
        self._set_text(self.title, spec.name)
        self._set_text(self.subtitle, f"{spec.category} · {spec.id}")
        self._set_text(self.homepage,
                       f'网址：<a href="{url}">{host}</a>' if url else "")
        self.homepage.setToolTip(url)
        self._set_text(self.note, spec.note or "")
        self._buttons["download"].setEnabled(spec.downloadable)
        self._buttons["ignore"].setText("忽略此软件")
        if row:
            self.set_row(row)
        else:
            self.scroll.fit_content()

    def set_row(self, row: AppRow) -> None:
        if self._spec is None or row.spec.id != self._spec.id:
            return
        self._set_text(
            self.info,
            f"本地版本：{row.local or '—'}\n"
            f"最新版本：{row.remote or '—'}\n"
            f"当前状态：{row.status_text}",
        )
        self.scroll.fit_content()


class ActivityPanel(QFrame):
    """Live log with severity filtering. Default level: INFO ("常规").

    All records are kept in memory so switching the level re-renders history
    instead of only affecting future lines.
    """
    LEVEL_CHOICES = (
        (LogLevel.DEBUG, "详细"),
        (LogLevel.INFO, "常规"),
        (LogLevel.WARNING, "重要"),
        (LogLevel.ERROR, "仅错误"),
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._records: deque[tuple[LogLevel, str]] = deque(maxlen=3000)
        self._min_level = LogLevel.INFO
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        head = QHBoxLayout()
        title = QLabel("活动")
        title.setObjectName("Title")
        self.summary = QLabel("就绪")
        self.summary.setObjectName("Subtle")
        self.progress = QProgressBar()
        self.progress.setFixedHeight(8)
        self.progress.setTextVisible(False)
        self.level_combo = QComboBox()
        for level, label in self.LEVEL_CHOICES:
            self.level_combo.addItem(label, int(level))
        self.level_combo.setFixedWidth(96)
        self.level_combo.setCurrentIndex(1)
        self.level_combo.currentIndexChanged.connect(self._on_level_changed)
        clear = QPushButton("清空日志")
        export = QPushButton("导出日志")
        clear.clicked.connect(self.clear_log)
        export.clicked.connect(self.export_log)
        head.addWidget(title)
        head.addWidget(self.summary, 1)
        head.addWidget(self.progress, 2)
        head.addWidget(QLabel("日志等级"))
        head.addWidget(self.level_combo)
        head.addWidget(clear)
        head.addWidget(export)
        root.addLayout(head)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setMinimumHeight(110)
        self.log.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.log.customContextMenuRequested.connect(self._show_log_menu)
        root.addWidget(self.log)

    # ------------------------------------------------------------- levels
    def minimum_level(self) -> LogLevel:
        return self._min_level

    def _on_level_changed(self, index: int) -> None:
        value = self.level_combo.itemData(index)
        if value is None:
            return
        self._min_level = LogLevel(int(value))
        self._refresh()

    def _refresh(self) -> None:
        self.log.setPlainText(
            "\n".join(text for level, text in self._records
                      if level >= self._min_level)
        )
        self.log.moveCursor(QTextCursor.MoveOperation.End)

    def _record(self, level: LogLevel, text: str) -> None:
        self._records.append((level, text))
        if level >= self._min_level:
            self.log.appendPlainText(text)

    def clear_log(self) -> None:
        self._records.clear()
        self.log.clear()

    # ------------------------------------------------------------- append
    def append_event(self, ev: ProgressEvent) -> None:
        stamp = time.strftime("%H:%M:%S", time.localtime(ev.timestamp))
        level = ev.effective_level
        spec = spec_by_id(ev.app_id)
        appname = spec.name if spec is not None else ev.app_id
        tail = f" {ev.message}" if ev.message else ""
        self._record(
            level,
            f"[{stamp}] [{level.label}] {appname}{tail}",
        )

    def append_line(self, text: str,
                    level: LogLevel = LogLevel.INFO) -> None:
        stamp = time.strftime("%H:%M:%S")
        self._record(level, f"[{stamp}] [{level.label}] {text}")

    def set_progress(self, done: int, total: int, active: int,
                     concurrency: int) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.summary.setText(
            f"整体 {done}/{total} · 同时进行 {active}/{concurrency}" if total
            else f"就绪 · 同时最多处理 {concurrency} 个"
        )

    # ------------------------------------------------------------ actions
    def _show_log_menu(self, pos) -> None:
        menu = QMenu(self)
        copy = menu.addAction("复制")
        copy.setEnabled(self.log.textCursor().hasSelection())
        copy.triggered.connect(self.log.copy)
        menu.addAction("全选", self.log.selectAll)
        menu.addSeparator()
        menu.addAction("清空日志", self.clear_log)
        menu.addAction("导出日志…", self.export_log)
        menu.exec(self.log.viewport().mapToGlobal(pos))

    def export_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", "update-scripts.log", "文本文件 (*.log *.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(text for _, text in self._records))


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(440)
        self._result = replace(settings)
        form = QFormLayout()
        form.setSpacing(10)

        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 16)
        self.concurrency.setValue(settings.concurrency)
        self.timeout = QSpinBox()
        self.timeout.setRange(30, 7200)
        self.timeout.setSuffix(" 秒")
        self.timeout.setValue(settings.timeout_seconds)
        self.theme = QComboBox()
        self.theme.addItems(["跟随系统", "浅色", "深色"])
        self.theme.setCurrentIndex({"system": 0, "light": 1, "dark": 2}
                                   .get(settings.theme, 0))
        self.proxy = QLineEdit(settings.proxy)
        self.proxy.setPlaceholderText("例如 http://127.0.0.1:7890，留空则不使用代理")
        self.verify = QCheckBox("校验 HTTPS 证书")
        self.verify.setChecked(settings.verify_tls)
        self.schedule = QCheckBox("启用定时检查")
        self.schedule.setChecked(settings.schedule_enabled)
        self.auto_install = QCheckBox("检查到更新后自动安装")
        self.auto_install.setToolTip(
            "定时巡检与启动巡检均适用：发现更新后自动下载并安装，"
            "必要时自动关闭相关程序。\n"
            "需手动更新或未安装的软件会被跳过；个别无静默参数的"
            "安装器仍可能弹出安装界面，需要人工确认。")
        self.auto_install.setChecked(settings.auto_install_updates)
        self.minutes = QSpinBox()
        self.minutes.setRange(5, 1440)
        self.minutes.setSuffix(" 分钟")
        self.minutes.setValue(settings.schedule_minutes)
        self.run_on_start = QCheckBox("启动时立即巡检一次")
        self.run_on_start.setChecked(settings.run_on_start)
        self.tray = QCheckBox("关闭窗口时最小化到托盘")
        self.tray.setChecked(settings.minimize_to_tray)
        self.download_dir = QLineEdit(settings.download_dir)
        self.download_dir.setPlaceholderText("留空则保存到桌面")

        form.addRow("并发数", self.concurrency)
        form.addRow("单任务超时", self.timeout)
        form.addRow("主题", self.theme)
        form.addRow("代理地址", self.proxy)
        form.addRow("", self.verify)
        form.addRow("仅下载保存目录", self.download_dir)
        form.addRow("", self.schedule)
        form.addRow("", self.auto_install)
        form.addRow("巡检间隔", self.minutes)
        form.addRow("", self.run_on_start)
        form.addRow("", self.tray)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def values(self) -> Settings:
        return self._result

    def accept(self) -> None:
        self._result = replace(
            self._result,
            concurrency=self.concurrency.value(),
            timeout_seconds=self.timeout.value(),
            theme=["system", "light", "dark"][self.theme.currentIndex()],
            proxy=self.proxy.text().strip(),
            verify_tls=self.verify.isChecked(),
            schedule_enabled=self.schedule.isChecked(),
            schedule_minutes=self.minutes.value(),
            auto_install_updates=self.auto_install.isChecked(),
            run_on_start=self.run_on_start.isChecked(),
            minimize_to_tray=self.tray.isChecked(),
            download_dir=self.download_dir.text().strip(),
        )
        super().accept()
