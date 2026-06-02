"""Browser lifecycle manager."""

from __future__ import annotations

from contextlib import contextmanager
import os
import threading
from dataclasses import dataclass, field
from typing import Any

from ._cloakbrowser_runtime import import_cloakbrowser
from .config import CLOAKBROWSER_BINARY_PATH_ENV_VAR

DEFAULT_BROWSER_LOCALE = "en-US"
DEFAULT_BROWSER_VIEWPORT = {"width": 1440, "height": 1600}
_CLOAKBROWSER_BINARY_PATH_ENV_LOCK = threading.RLock()


def browser_context_options(
    *,
    user_agent: str | None = None,
    locale: str = DEFAULT_BROWSER_LOCALE,
    viewport: dict[str, int] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "locale": locale,
        "viewport": dict(DEFAULT_BROWSER_VIEWPORT if viewport is None else viewport),
    }
    active_user_agent = str(user_agent or "").strip()
    if active_user_agent:
        options["user_agent"] = active_user_agent
    options.update(extra)
    return options


def browser_page_user_agent(page: Any) -> str | None:
    try:
        user_agent = page.evaluate("() => navigator.userAgent")
    except Exception:
        return None
    normalized = str(user_agent or "").strip()
    return normalized or None


@contextmanager
def cloakbrowser_binary_path_env(binary_path: str | None):
    active_path = str(binary_path or "").strip()
    with _CLOAKBROWSER_BINARY_PATH_ENV_LOCK:
        if not active_path:
            yield
            return

        previous = os.environ.get(CLOAKBROWSER_BINARY_PATH_ENV_VAR)
        os.environ[CLOAKBROWSER_BINARY_PATH_ENV_VAR] = active_path
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop(CLOAKBROWSER_BINARY_PATH_ENV_VAR, None)
            else:
                os.environ[CLOAKBROWSER_BINARY_PATH_ENV_VAR] = previous


@dataclass
class BrowserContextManager:
    """Owns a shared CloakBrowser-launched browser for one fetch runtime."""

    binary_path: str | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _browser: Any | None = field(default=None, init=False, repr=False)
    _headless: bool | None = field(default=None, init=False, repr=False)

    def browser(self, *, headless: bool = True) -> Any:
        active_headless = bool(headless)
        with self._lock:
            if self._browser is not None and self._headless == active_headless:
                return self._browser
            if self._browser is not None:
                self.close()

            cloakbrowser = import_cloakbrowser()
            with cloakbrowser_binary_path_env(self.binary_path):
                browser = cloakbrowser.launch(headless=active_headless, locale="en-US")
            self._browser = browser
            self._headless = active_headless
            return browser

    def new_context(self, *, headless: bool = True, **context_kwargs: Any) -> Any:
        with self._lock:
            return self.browser(headless=headless).new_context(**context_kwargs)

    def close(self) -> None:
        with self._lock:
            browser = self._browser
            self._browser = None
            self._headless = None
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

    def __del__(self) -> None:  # pragma: no cover - defensive cleanup at GC/interpreter shutdown
        try:
            self.close()
        except Exception:
            pass

__all__ = [
    "BrowserContextManager",
    "browser_context_options",
    "browser_page_user_agent",
    "cloakbrowser_binary_path_env",
]
