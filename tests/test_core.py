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


class EngineTests(unittest.TestCase):
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
        with patch.object(services, "http_get", return_value="v9.9.9"):
            pool.submit([spec], Mode.CHECK)
            QTimer.singleShot(5000, app.quit)
            app.exec()
        self.assertTrue(received, "没有收到任何结构化事件")
        self.assertTrue(any(e.finished for e in received))
        self.assertEqual(received[-1].remote_version, "9.9.9")


if __name__ == "__main__":
    unittest.main()
