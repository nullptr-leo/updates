"""The one HTTP client: a shared connection pool and a single place where
proxy, TLS and header policy are applied.

Every request goes through the same ``requests.Session``, so connections to a
host are reused across recipes and worker threads. Each call carries the
``settings`` and the ``spec`` it is made for: a per-app rule in
``Settings.proxy_rules`` beats the recipe default, which beats the global
proxy address. Failures leave here as typed exceptions (``QueryFailed`` /
``TimedOut`` / ``Cancelled``), never as ``requests`` errors.
"""
from __future__ import annotations

import os
import threading
from contextlib import closing
from typing import Callable, Mapping

import requests
from requests.adapters import HTTPAdapter

from .cancellation import CancellationToken
from .config import Settings
from .models import AppSpec, Cancelled, QueryFailed, TimedOut

DEFAULT_HEADERS: Mapping[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept-Encoding": "gzip, deflate",
}

# A refused or dropped connection. HTTP status failures (``HTTPError``) are
# deliberately not listed: a 404 is a bad response, not a connectivity
# problem, so it must not be retried as an outage.
NETWORK_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)

# Upper bound of Settings.concurrency: each worker may hold one connection.
MAX_WORKERS = 16


class HttpClient:
    """Thin wrapper over one ``requests.Session``."""

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        # The default adapter pools 10 connections per host and discards the
        # rest with a warning once the pool is full.
        adapter = HTTPAdapter(pool_connections=MAX_WORKERS,
                              pool_maxsize=MAX_WORKERS)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def close(self) -> None:
        self._session.close()

    # ------------------------------------------------------------ policy
    @staticmethod
    def use_proxy(settings: Settings | None,
                  spec: AppSpec | None = None) -> bool:
        rules = getattr(settings, "proxy_rules", None) or {}
        rule = rules.get(spec.id) if spec else None
        if rule == "proxy":
            return True
        if rule == "direct":
            return False
        return spec.proxy if spec else True

    @staticmethod
    def proxies(settings: Settings | None,
                spec: AppSpec | None = None) -> dict | None:
        if not HttpClient.use_proxy(settings, spec):
            return None
        addr = ((settings.proxy if settings else "")
                or os.environ.get("UPDATE_PROXY_ADDR", ""))
        if not addr:
            return None
        return {"http": addr, "https": addr}

    @staticmethod
    def verify(settings: Settings | None) -> bool:
        return bool(settings.verify_tls) if settings else True

    def _options(self, settings: Settings | None,
                 spec: AppSpec | None) -> dict:
        return {"proxies": self.proxies(settings, spec),
                "verify": self.verify(settings)}

    # ----------------------------------------------------------- requests
    def get_text(self, url: str, *, settings: Settings | None = None,
                 spec: AppSpec | None = None,
                 headers: Mapping[str, str] | None = None,
                 timeout: float = 30) -> str:
        """Fetch a URL and return its text. Raises QueryFailed, never exits."""
        try:
            response = self._session.get(
                url, headers=dict(headers or {}), timeout=(10, timeout),
                **self._options(settings, spec),
            )
            response.raise_for_status()
            return response.text
        except NETWORK_ERRORS as exc:
            raise QueryFailed(f"网络错误: {type(exc).__name__}") from exc
        except Exception as exc:
            raise QueryFailed(str(exc) or repr(exc)) from exc

    def final_url(self, url: str, *, settings: Settings | None = None,
                  spec: AppSpec | None = None) -> str:
        """Resolve the final URL after redirects (HEAD, then streaming GET)."""
        try:
            response = self._session.head(
                url, allow_redirects=True, timeout=(10, 30),
                **self._options(settings, spec),
            )
            if response.url and response.url != url:
                return response.url
            raise ValueError("HEAD did not redirect")
        except Exception:
            try:
                # Close the stream after reading the URL: an unread body keeps
                # its connection out of the pool for the next request.
                with closing(self._session.get(
                        url, stream=True, allow_redirects=True,
                        timeout=(10, 30),
                        **self._options(settings, spec))) as response:
                    return response.url
            except Exception as exc:
                raise QueryFailed(f"重定向查询失败: {exc}") from exc

    def download(self, url: str, dest: str, *,
                 settings: Settings | None = None,
                 spec: AppSpec | None = None,
                 token: CancellationToken | None = None,
                 headers: Mapping[str, str] | None = None,
                 on_progress: Callable[[int, int], None] | None = None) -> None:
        """Stream a download with cooperative cancellation and byte progress."""
        if not url:
            raise QueryFailed("下载地址为空")
        try:
            with closing(self._session.get(
                    url, stream=True, timeout=(30, 120),
                    headers=dict(headers or {}),
                    **self._options(settings, spec))) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length") or 0)
                current = 0
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if token is not None:
                            token.raise_if_cancelled()
                        if not chunk:
                            continue
                        fh.write(chunk)
                        current += len(chunk)
                        if on_progress:
                            on_progress(current, total)
            if on_progress:
                on_progress(current, total or current)
        except (Cancelled, TimedOut):
            raise
        except NETWORK_ERRORS as exc:
            raise QueryFailed(f"下载失败: {type(exc).__name__}") from exc
        except Exception as exc:
            raise QueryFailed(f"下载失败: {exc}") from exc


_LOCK = threading.Lock()
_CLIENT: HttpClient | None = None


def client() -> HttpClient:
    """The process-wide client, created on first use."""
    global _CLIENT
    if _CLIENT is None:
        with _LOCK:
            if _CLIENT is None:
                _CLIENT = HttpClient()
    return _CLIENT


def is_connection_error(exc: BaseException) -> bool:
    """Whether a failure is caused by connectivity rather than a bad response."""
    current: BaseException | None = exc
    for _ in range(5):
        if current is None:
            return False
        if isinstance(current, (requests.exceptions.ConnectionError,
                                requests.exceptions.Timeout,
                                ConnectionError, TimeoutError)):
            return True
        if isinstance(current, QueryFailed) and str(current).startswith("网络错误"):
            return True
        current = current.__cause__ or current.__context__
    return False
