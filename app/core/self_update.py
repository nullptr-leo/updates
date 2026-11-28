"""Self-update of a source checkout: ``git pull --rebase`` in the project root.

The UI only shows the outcome and offers a restart; everything that talks to
git lives here.
"""
from __future__ import annotations

import subprocess

from .config import PROJECT_ROOT
from .logging_setup import get_logger

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def git_head() -> str:
    """Current HEAD hash, or "" when git metadata is unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", timeout=30,
            creationflags=CREATE_NO_WINDOW,
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


def pull() -> tuple[bool, bool]:
    """Run ``git pull --rebase``; returns ``(ok, changed)``.

    ``changed`` is False whenever the pull failed. A pull that leaves HEAD
    where it was needs no restart; when HEAD cannot be read, git's own
    "up to date" wording decides.
    """
    try:
        before = git_head()
        result = subprocess.run(
            ["git", "pull", "--rebase"], cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", timeout=120,
            creationflags=CREATE_NO_WINDOW,
        )
        output = (result.stdout or "").strip()
        get_logger().info("升级软件输出：%s", output[-800:])
        after = git_head()
        ok = result.returncode == 0
        if ok and before and after:
            changed = before != after
        else:
            changed = ok and "up to date" not in output.lower()
        return ok, changed
    except Exception as exc:
        get_logger().warning("升级软件失败：%s", exc)
        return False, False
