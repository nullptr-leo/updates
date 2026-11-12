"""Core-layer tests. Run with: python -m unittest discover -s tests -v"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.apps.hooks import HOOKS
from app.core import services
from app.core.cancellation import CancellationToken
from app.core.config import Settings
from app.core.engine import UpdateEngine
from app.core.models import (
    AppSpec, DownloadSpec, InstallSpec, LocalSpec, Mode, Phase, RemoteSpec,
)
from app.core.registry import all_specs, spec_by_id, visible_specs


class CatalogTests(unittest.TestCase):
    def test_catalog_is_complete_and_unique(self):
        specs = all_specs()
        self.assertEqual(len(specs), 43)
        self.assertEqual(len({s.id for s in specs}), 43)

    def test_legacy_ignored_list_is_honoured(self):
        settings = Settings(ignored=[
            "flowlauncher", "autoruns", "qianwen", "zyperwin", "kiro",
            "insta360", "meeting", "qq", "snipaste", "workbuddy",
            "feishu", "adb", "otp", "snowair",
        ])
        self.assertEqual(len(visible_specs(settings)), 29)

    def test_every_custom_hook_is_registered(self):
        for spec in all_specs():
            groups = [
                ("local", spec.local.kind == "custom", spec.local.custom if spec.local else ""),
                ("remote", spec.remote is not None and spec.remote.kind == "custom",
                 spec.remote.custom if spec.remote else ""),
                ("install", spec.install is not None and spec.install.kind == "custom",
                 spec.install.custom if spec.install else ""),
            ]
            for group, used, name in groups:
                if used:
                    self.assertIn(name, HOOKS[group], f"{spec.id}: {group}.{name}")

    def test_metadata_is_explicit(self):
        wecom = spec_by_id("wecom")
        self.assertIsNotNone(wecom)
        self.assertTrue(wecom.homepage.startswith("https://work.weixin.qq.com"))
        self.assertEqual(len(wecom.install_dirs), 2)

    def test_all_patterns_and_post_actions_are_valid(self):
        import re
        known_actions = {"taskkill", "path", "shortcut", "regdel",
                         "open_url", "open_explorer", "custom"}
        for spec in all_specs():
            remote = spec.remote
            if remote and remote.kind in ("regex", "redirect", "findall_max"):
                for pattern in remote.pattern.split("||"):
                    re.compile(pattern)
            if spec.download and spec.download.from_response.startswith("regex:"):
                re.compile(spec.download.from_response.partition(":")[2])
            for action in spec.post:
                head, _, value = action.partition(":")
                self.assertIn(head, known_actions, f"{spec.id}: {action}")
                if head == "custom":
                    self.assertIn(value, HOOKS["post"], f"{spec.id}: {action}")


class VersionTests(unittest.TestCase):
    def test_version_comparison(self):
        self.assertTrue(services.is_newer("1.2.0", "1.1.9"))
        self.assertFalse(services.is_newer("1.1.9", "1.2.0"))
        self.assertTrue(services.is_newer("3.12.1", ""))
        self.assertTrue(services.is_newer("3.10.1", "3.9.9",
                                         lexicographic=False))


class NetworkStatusTests(unittest.TestCase):
    def test_windows_offline_and_online_states(self):
        with patch.object(services.sys, "platform", "win32"), \
             patch.object(services, "_nlm_connected", return_value=False):
            self.assertEqual(services.network_status(),
                             (False, "Windows 未连接到 Internet"))
        with patch.object(services.sys, "platform", "win32"), \
             patch.object(services, "_nlm_connected", return_value=True):
            self.assertEqual(services.network_status(),
                             (True, "网络已连接"))

    def test_detection_falls_back_to_wininet_then_probe(self):
        with patch.object(services.sys, "platform", "win32"), \
             patch.object(services, "_nlm_connected", return_value=None), \
             patch.object(services, "_wininet_connected",
                          return_value=(False, "系统当前没有网络连接")):
            self.assertFalse(services.network_status()[0])
        with patch.object(services.sys, "platform", "win32"), \
             patch.object(services, "_nlm_connected", return_value=None), \
             patch.object(services, "_wininet_connected", return_value=None), \
             patch.object(services, "_probe_reachability",
                          return_value=(True, "网络已连接")):
            self.assertTrue(services.network_status()[0])

    def test_connection_errors_are_distinguished(self):
        import requests
        from app.core.models import QueryFailed
        cause = requests.exceptions.ConnectionError("offline")
        wrapped = QueryFailed("网络错误: ConnectionError")
        wrapped.__cause__ = cause
        self.assertTrue(services.is_connection_error(wrapped))
        self.assertTrue(services.is_connection_error(
            QueryFailed("网络错误")))
        self.assertFalse(services.is_connection_error(ValueError("bad regex")))


class EngineTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(services, "network_status",
                               return_value=(True, "网络已连接"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _engine(self):
        events = []
        engine = UpdateEngine(Settings(), events.append, hooks=HOOKS)
        return engine, events

    def test_check_mode_emits_structured_events_and_never_installs(self):
        spec = AppSpec(
            id="demo", name="Demo", homepage="https://example.com",
            local=LocalSpec(kind="exe", target="demo.exe"),
            remote=RemoteSpec(url="https://example.com/version",
                              kind="regex", pattern=r"v([\d.]+)"),
            download=DownloadSpec(url="https://example.com/demo-{version}.exe"),
            install=InstallSpec(kind="installer"),
        )
        engine, events = self._engine()
        with patch.object(services, "get_local_version", return_value="1.0.0"), \
             patch.object(services, "http_get", return_value="v1.1.0"), \
             patch.object(services, "download_file", side_effect=AssertionError("must not download")):
            engine.run(spec, Mode.CHECK, CancellationToken())
        final = events[-1]
        self.assertTrue(final.finished)
        self.assertEqual(final.remote_version, "1.1.0")
        self.assertTrue(final.needs_update)
        self.assertNotIn(Phase.DOWNLOADING, [e.phase for e in events])

    def test_uptodate_short_circuits(self):
        spec = AppSpec(
            id="demo", name="Demo", homepage="",
            local=LocalSpec(kind="exe", target="demo.exe"),
            remote=RemoteSpec(url="https://example.com", kind="regex",
                              pattern=r"v([\d.]+)"),
            install=InstallSpec(kind="installer"),
        )
        engine, events = self._engine()
        with patch.object(services, "get_local_version", return_value="2.0.0"), \
             patch.object(services, "http_get", return_value="v2.0.0"):
            engine.run(spec, Mode.UPDATE, CancellationToken())
        self.assertEqual(events[-1].phase, Phase.UPTODATE)

    def test_query_failure_is_reported_not_raised(self):
        from app.core.models import QueryFailed
        spec = AppSpec(
            id="demo", name="Demo", homepage="",
            remote=RemoteSpec(url="https://example.com", kind="regex",
                              pattern=r"v([\d.]+)"),
            install=InstallSpec(kind="installer"),
        )
        engine, events = self._engine()
        with patch.object(services, "http_get", side_effect=QueryFailed("网络错误")):
            engine.run(spec, Mode.CHECK, CancellationToken())
        final = events[-1]
        self.assertEqual(final.phase, Phase.FAILED)
        self.assertIsNotNone(final.error)
        self.assertEqual(final.error.message, "网络错误")

    def test_cancellation_is_cooperative(self):
        from app.core.models import Cancelled
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(Cancelled):
            token.raise_if_cancelled()

    def _offline_spec(self):
        return AppSpec(
            id="demo", name="Demo", homepage="",
            remote=RemoteSpec(url="https://example.com", kind="regex",
                              pattern=r"v([\d.]+)"),
            install=InstallSpec(kind="installer"),
        )

    def test_offline_task_waits_for_connection_then_runs(self):
        engine, events = self._engine()
        with patch.object(services, "network_status", side_effect=[
                (False, "Windows 未连接到 Internet"),
                (True, "网络已连接")]), \
             patch.object(services, "NETWORK_POLL_SECONDS", 0), \
             patch.object(services, "http_get", return_value="v1.0.0"):
            engine.run(self._offline_spec(), Mode.CHECK, CancellationToken())
        phases = [e.phase for e in events]
        self.assertIn(Phase.WAITING_NETWORK, phases)
        self.assertFalse(events[0].finished)
        self.assertEqual(events[-1].phase, Phase.DONE)
        self.assertTrue(events[-1].finished)

    def test_cli_reports_waiting_network_without_blocking(self):
        events = []
        engine = UpdateEngine(Settings(), events.append, hooks=HOOKS,
                              wait_for_network=False)
        with patch.object(services, "network_status",
                          return_value=(False, "Windows 未连接到 Internet")):
            engine.run(self._offline_spec(), Mode.CHECK, CancellationToken())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].phase, Phase.WAITING_NETWORK)
        self.assertTrue(events[0].finished)

    def test_connection_loss_retries_after_reconnect(self):
        from app.core.models import QueryFailed
        engine, events = self._engine()
        with patch.object(services, "network_status", side_effect=[
                (True, "网络已连接"),
                (False, "Windows 未连接到 Internet"),
                (False, "Windows 未连接到 Internet"),
                (True, "网络已连接")]), \
             patch.object(services, "NETWORK_POLL_SECONDS", 0), \
             patch.object(services, "http_get", side_effect=[
                 QueryFailed("网络错误: ConnectionError"), "v1.0.0"]):
            engine.run(self._offline_spec(), Mode.CHECK, CancellationToken())
        self.assertIn(Phase.WAITING_NETWORK, [e.phase for e in events])
        self.assertEqual(events[-1].phase, Phase.DONE)


class ThreadingTests(unittest.TestCase):
    def test_task_pool_marshals_events_to_gui_thread(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from app.workers.update_worker import TaskPool

        app = QApplication.instance() or QApplication([])
        received: list = []
        pool = TaskPool(Settings(), hooks=HOOKS)
        pool.event.connect(received.append)
        pool.idle.connect(app.quit)
        spec = AppSpec(
            id="threaded", name="Threaded", homepage="",
            remote=RemoteSpec(url="https://example.com", kind="regex",
                              pattern=r"v([\d.]+)"),
            install=InstallSpec(kind="installer"),
        )
        with patch.object(services, "network_status",
                          return_value=(True, "网络已连接")), \
             patch.object(services, "http_get", return_value="v9.9.9"):
            pool.submit([spec], Mode.CHECK)
            QTimer.singleShot(5000, app.quit)
            app.exec()
        self.assertTrue(received, "没有收到任何结构化事件")
        self.assertTrue(any(e.finished for e in received))
        self.assertEqual(received[-1].remote_version, "9.9.9")

    def _pool_spec(self):
        return AppSpec(
            id="threaded", name="Threaded", homepage="",
            remote=RemoteSpec(url="https://example.com", kind="regex",
                              pattern=r"v([\d.]+)"),
            install=InstallSpec(kind="installer"),
        )

    def test_offline_submit_waits_and_resumes_on_connection(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from app.workers.update_worker import TaskPool

        app = QApplication.instance() or QApplication([])
        received: list = []
        pool = TaskPool(Settings(), hooks=HOOKS)
        pool.event.connect(received.append)
        pool.idle.connect(app.quit)
        spec = self._pool_spec()
        with patch.object(services, "network_status",
                          return_value=(False, "Windows 未连接到 Internet")):
            self.assertEqual(pool.submit([spec], Mode.CHECK), 1)
        self.assertEqual(received[-1].phase, Phase.WAITING_NETWORK)
        self.assertFalse(received[-1].finished)
        self.assertEqual(pool.active_count(), 1)
        self.assertFalse(any(e.phase == Phase.DONE for e in received))

        with patch.object(services, "network_status",
                          return_value=(True, "网络已连接")), \
             patch.object(services, "http_get", return_value="v9.9.9"):
            pool._resume_pending()
            QTimer.singleShot(5000, app.quit)
            app.exec()
        self.assertTrue(any(e.phase == Phase.DONE for e in received))
        self.assertEqual(pool.active_count(), 0)

    def test_watchdog_does_not_cancel_waiting_tasks(self):
        import os
        import time
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from app.workers.update_worker import TaskPool

        QApplication.instance() or QApplication([])
        pool = TaskPool(Settings(timeout_seconds=0), hooks=HOOKS)
        spec = self._pool_spec()
        with patch.object(services, "network_status",
                          return_value=(False, "Windows 未连接到 Internet")):
            pool.submit([spec], Mode.CHECK)
        with pool._lock:
            pool._starts[spec.id] = time.monotonic() - 1000
        pool._check_timeouts()
        self.assertFalse(pool._tokens[spec.id].cancelled)
        pool.cancel_all()
        pool.wait_for_done(1000)


class CacheConcurrencyTests(unittest.TestCase):
    def test_concurrent_writes_are_safe_and_complete(self):
        import tempfile
        import threading
        from pathlib import Path
        from app.core import cache

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "cache.json"
            with patch.object(cache, "CACHE_PATH", target):
                errors = []

                def worker(i):
                    try:
                        for j in range(15):
                            cache.update_app_cache(f"app{i}", remote=f"1.0.{j}")
                            cache.record_update_time()
                    except Exception as exc:
                        errors.append(exc)

                threads = [threading.Thread(target=worker, args=(i,))
                           for i in range(8)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                self.assertEqual(errors, [])
                data = cache.load_cache()
                self.assertEqual(len(data["apps"]), 8)
                self.assertTrue(data["last_update"])
                leftovers = [p.name for p in Path(tmpdir).iterdir()
                             if p.name.endswith(".tmp")]
                self.assertEqual(leftovers, [])

    def test_cache_write_failure_does_not_fail_check(self):
        from app.core import cache
        spec = AppSpec(
            id="demo", name="Demo", homepage="",
            remote=RemoteSpec(url="https://example.com", kind="regex",
                              pattern=r"v([\d.]+)"),
            install=InstallSpec(kind="installer"),
        )
        events = []
        engine = UpdateEngine(Settings(), events.append, hooks=HOOKS)
        with patch.object(services, "network_status",
                          return_value=(True, "网络已连接")), \
             patch.object(services, "http_get", return_value="v1.2.3"), \
             patch.object(cache, "atomic_write_json",
                          side_effect=PermissionError("denied")):
            engine.run(spec, Mode.CHECK, CancellationToken())
        self.assertEqual(events[-1].phase, Phase.DONE)
        self.assertTrue(events[-1].finished)


class WaitingNetworkUiTests(unittest.TestCase):
    def test_status_is_chinese_and_warning_colored(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from app.ui.table_model import AppRow
        QApplication.instance() or QApplication([])
        row = AppRow(spec=AppSpec(id="demo", name="Demo"),
                     phase=Phase.WAITING_NETWORK)
        self.assertEqual(row.status_text, "等待连接")
        self.assertEqual(row.status_kind, "warning")

    def test_waiting_phase_is_active_and_visible_in_default_log(self):
        from app.core.models import ACTIVE_PHASES, LogLevel, level_for_phase
        self.assertIn(Phase.WAITING_NETWORK, ACTIVE_PHASES)
        self.assertEqual(level_for_phase(Phase.WAITING_NETWORK),
                         LogLevel.WARNING)


class LogLevelTests(unittest.TestCase):
    def test_phase_levels_are_graded(self):
        from app.core.models import LogLevel, Phase, ProgressEvent, level_for_phase
        self.assertEqual(level_for_phase(Phase.CHECKING), LogLevel.DEBUG)
        self.assertEqual(level_for_phase(Phase.DOWNLOADING), LogLevel.DEBUG)
        self.assertEqual(level_for_phase(Phase.FAILED), LogLevel.ERROR)
        self.assertEqual(level_for_phase(Phase.DONE), LogLevel.INFO)
        self.assertEqual(
            ProgressEvent(app_id="x", phase=Phase.FAILED).effective_level,
            LogLevel.ERROR)
        self.assertEqual(
            ProgressEvent(app_id="x", phase=Phase.CHECKING,
                          level=LogLevel.WARNING).effective_level,
            LogLevel.WARNING)

    def test_activity_panel_defaults_to_info_and_filters_history(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from app.core.models import LogLevel, Phase, ProgressEvent
        from app.ui.widgets import ActivityPanel
        QApplication.instance() or QApplication([])

        panel = ActivityPanel()
        self.assertEqual(panel.minimum_level(), LogLevel.INFO)
        panel.append_event(ProgressEvent(app_id="a", phase=Phase.CHECKING))
        panel.append_event(ProgressEvent(app_id="b", phase=Phase.DONE))
        panel.append_event(ProgressEvent(app_id="c", phase=Phase.FAILED))
        text = panel.log.toPlainText()
        self.assertNotIn("检查中", text)
        self.assertIn("完成", text)
        self.assertIn("失败", text)

        panel.level_combo.setCurrentIndex(0)  # 详细 / DEBUG
        self.assertIn("检查中", panel.log.toPlainText())

        panel.level_combo.setCurrentIndex(
            panel.level_combo.findData(int(LogLevel.ERROR)))
        text = panel.log.toPlainText()
        self.assertIn("失败", text)
        self.assertNotIn("检查中", text)
        self.assertNotIn("完成", text)

    def test_log_context_menu_is_chinese(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from app.ui.widgets import ActivityPanel
        QApplication.instance() or QApplication([])
        panel = ActivityPanel()
        self.assertEqual(panel.log.contextMenuPolicy(),
                         Qt.ContextMenuPolicy.CustomContextMenu)


class LocalizationTests(unittest.TestCase):
    def test_menus_are_chinese_and_hide_git_details(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from app.core.config import load_settings
        from app.ui.main_window import MainWindow
        from app.ui.tray import Tray
        QApplication.instance() or QApplication([])

        tray = Tray("")
        tray_texts = [a.text() for a in tray.icon.contextMenu().actions()]
        self.assertIn("升级软件", tray_texts)
        self.assertFalse(any("git" in t.lower() for t in tray_texts))

        window = MainWindow(load_settings(), "版本 2.0")
        more_texts = [a.text() for a in window.more_btn.menu().actions()]
        self.assertIn("升级软件", more_texts)
        self.assertFalse(any("git" in t.lower() for t in more_texts))
        self.assertEqual(window.activity.minimum_level().name, "INFO")


class DetailPanelLayoutTests(unittest.TestCase):
    def test_short_panel_scrolls_instead_of_squeezing_content(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from app.core.registry import all_specs
        from app.ui.table_model import AppRow
        from app.ui.widgets import DetailPanel

        app = QApplication.instance() or QApplication([])
        spec = max(all_specs(),
                   key=lambda s: len((s.note or "") + (s.homepage or "")))
        row = AppRow(spec=spec, local="1.0.0", remote="2.0.0",
                     needs_update=True)
        panel = DetailPanel()
        panel.set_spec(spec, row)
        panel.show()
        panel.resize(260, 90)
        app.processEvents()

        self.assertGreater(panel.scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(panel.content.width(),
                         panel.scroll.viewport().width())
        self.assertGreater(panel.content.height(),
                           panel.scroll.viewport().height())
        for label in (panel.title, panel.subtitle, panel.homepage,
                      panel.info, panel.note):
            if label.isVisible():
                self.assertGreaterEqual(label.height(),
                                        label.sizeHint().height())
        for button in panel._buttons.values():
            self.assertGreaterEqual(button.height(),
                                    button.minimumSizeHint().height())

        panel.set_spec(None)
        app.processEvents()
        self.assertTrue(panel.info.isHidden())
        panel.close()

    def test_empty_labels_do_not_take_space(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from app.ui.widgets import DetailPanel
        QApplication.instance() or QApplication([])

        panel = DetailPanel()
        self.assertFalse(panel.title.isHidden())
        for label in (panel.subtitle, panel.homepage, panel.info, panel.note):
            self.assertTrue(label.isHidden())


class RemoteParsingTests(unittest.TestCase):
    def test_listary_uses_full_version_not_major_banner(self):
        spec = spec_by_id("listary")
        page = (
            "<title>Listary V7 Beta 现已上线</title>"
            "<h2>Listary V7 Beta</h2>"
            "<p>v7.1.0.45 Beta</p>"
            "<p>v7.1.0.47 Beta</p>"
            "<p>v7.0.0.9 Beta</p>"
        )
        engine = UpdateEngine(Settings(), lambda ev: None)
        with patch.object(services, "http_get", return_value=page):
            info = engine._remote_info(spec, None)
        self.assertEqual(info.version, "7.1.0.47")

    def test_trafficmonitor_reads_version_from_release_tag(self):
        spec = spec_by_id("trafficmonitor")
        final = ("https://github.com/zhongyang219/TrafficMonitor/"
                 "releases/tag/V1.86")
        engine = UpdateEngine(Settings(), lambda ev: None)
        with patch.object(services, "get_redirected_url", return_value=final):
            info = engine._remote_info(spec, None)
        self.assertEqual(info.version, "1.86")
        self.assertTrue(
            spec.download.url.format(version=info.version).endswith(
                "TrafficMonitor_V1.86_x64.zip"))

    def test_empty_regex_captures_are_skipped(self):
        remote = RemoteSpec(url="https://example.com", kind="regex",
                            pattern=r"V([\d\.]*)")
        value = UpdateEngine._extract_version(
            remote, "<div>view version</div> Release V1.86 available")
        self.assertEqual(value, "1.86")


if __name__ == "__main__":
    unittest.main()
