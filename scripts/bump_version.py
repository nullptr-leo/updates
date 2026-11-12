"""Bump the project version in both metadata and runtime sources.

The last component is always the current git commit count, no matter which
bump level (or explicit version) is requested. The major/minor rules are
unchanged.

Usage:
    python scripts/bump_version.py              # patch:  2.0.0 -> 2.0.<count>
    python scripts/bump_version.py minor        # 2.0.0 -> 2.1.<count>
    python scripts/bump_version.py major        # 2.0.0 -> 3.0.<count>
    python scripts/bump_version.py 2.1.0        # 2.0.0 -> 2.1.<count>

Only rewrites the two version lines. It never stages, commits or tags.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = {
    ROOT / "pyproject.toml": re.compile(r'(?m)^(version = ")([^"]+)("\r?)$'),
    ROOT / "app" / "__init__.py": re.compile(r'(?m)^(__version__ = ")([^"]+)("\r?)$'),
}


def read_version(path: Path, pattern: re.Pattern[str]) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        match = pattern.search(f.read())
    if match is None:
        raise SystemExit(f"找不到版本号: {path}")
    return match.group(2)


def git_commit_count() -> int:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, check=True,
            timeout=10, creationflags=flags)
        return int(result.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(f"无法获取 git 提交数: {exc}") from exc


def parse_version(version: str) -> list[int]:
    nums = version.split(".")
    if len(nums) != 3 or not all(n.isdigit() for n in nums):
        raise SystemExit(f"版本号格式应为 x.y.z，当前是 {version!r}")
    return [int(n) for n in nums]


def resolve_version(old: str, arg: str, commit_count: int) -> str:
    if arg in ("major", "minor", "patch"):
        major, minor, _ = parse_version(old)
        if arg == "major":
            major, minor = major + 1, 0
        elif arg == "minor":
            minor += 1
    else:
        major, minor, _ = parse_version(arg)
    return f"{major}.{minor}.{commit_count}"


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "patch"
    versions = {path: read_version(path, pattern)
                for path, pattern in TARGETS.items()}
    if len(set(versions.values())) != 1:
        detail = ", ".join(f"{p.name}={v}" for p, v in versions.items())
        raise SystemExit(f"两处版本号不一致，请先手工对齐: {detail}")

    commit_count = git_commit_count()
    old = next(iter(versions.values()))
    new = resolve_version(old, arg, commit_count)
    if not re.fullmatch(r"\d+\.\d+\.\d+", new) or new == old:
        raise SystemExit(f"目标版本号非法或没有变化: {new!r}")

    updates: list[tuple[Path, str]] = []
    for path, pattern in TARGETS.items():
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        new_text, replacements = pattern.subn(
            lambda m: m.group(1) + new + m.group(3), text, count=1)
        if replacements != 1:
            raise SystemExit(f"替换失败: {path}")
        updates.append((path, new_text))

    for path, new_text in updates:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)

    print(f"{old} -> {new}  (git 提交数: {commit_count})")
    print("已更新 pyproject.toml 和 app/__init__.py，确认后再 git add:")
    print("  git diff pyproject.toml app/__init__.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
