"""Browser context helpers for browser workflow fetchers."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ....runtime import RuntimeContext
from ....runtime_browser import browser_context_options
from ....utils import normalize_text
from ..._pdf_candidates import BROWSER_WORKFLOW_PDF_URL_TOKENS
from ...browser_runtime.seed import parse_optional_int
from .diagnostics import (
    _compact_failure_diagnostic,
    _context_failure_diagnostic as _build_context_failure_diagnostic,
)


def _looks_like_pdf_navigation_url(url: str | None) -> bool:
    normalized = normalize_text(url).lower()
    if not normalized:
        return False
    return any(token in normalized for token in BROWSER_WORKFLOW_PDF_URL_TOKENS)


def _choose_browser_seed_url(*candidates: str | None) -> str | None:
    normalized_candidates = [
        normalize_text(candidate)
        for candidate in candidates
        if normalize_text(candidate)
    ]
    for candidate in normalized_candidates:
        if not _looks_like_pdf_navigation_url(candidate):
            return candidate
    return normalized_candidates[0] if normalized_candidates else None


def _normalized_response_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    if not isinstance(headers, Mapping):
        return {}
    return {
        normalize_text(str(key)).lower(): str(value)
        for key, value in headers.items()
        if normalize_text(str(key))
    }


def _browser_response_headers(response: Any | None) -> dict[str, str]:
    if response is None:
        return {}
    try:
        return _normalized_response_headers(response.all_headers())
    except Exception:
        return _normalized_response_headers(getattr(response, "headers", {}) or {})


def _browser_response_status(
    response: Any | None, *, zero_as_none: bool = True
) -> int | None:
    if response is None:
        return None
    try:
        status = parse_optional_int(getattr(response, "status", None))
    except Exception:
        return None
    if zero_as_none and status == 0:
        return None
    return status


def _new_browser_context(
    *,
    runtime_context: RuntimeContext | None,
    headless: bool,
    user_agent: str | None,
    use_runtime_shared_browser: bool = True,
) -> tuple[Any | None, Any | None, Any]:
    context_kwargs = browser_context_options(user_agent=user_agent)
    if runtime_context is not None and use_runtime_shared_browser:
        return (
            None,
            None,
            runtime_context.new_browser_context(headless=headless, **context_kwargs),
        )

    from ....runtime_browser import BrowserContextManager

    manager = BrowserContextManager()
    try:
        browser_context = manager.new_context(headless=headless, **context_kwargs)
    except Exception:
        manager.close()
        raise
    return manager, None, browser_context

class _BaseBrowserDocumentFetcher:
    def __init__(
        self,
        *,
        browser_context_seed_getter: Callable[[], Mapping[str, Any] | None],
        seed_urls_getter: Callable[[], list[str]],
        browser_user_agent: str | None = None,
        headless: bool = True,
        runtime_context: RuntimeContext | None = None,
        use_runtime_shared_browser: bool = True,
    ) -> None:
        self._browser_context_seed_getter = browser_context_seed_getter
        self._seed_urls_getter = seed_urls_getter
        self._browser_user_agent = browser_user_agent
        self._headless = headless
        self._runtime_context = runtime_context
        self._use_runtime_shared_browser = use_runtime_shared_browser
        self._browser_manager = None
        self._context = None
        self._page = None
        self._warmed_seed_urls: set[str] = set()
        self._last_failure_by_url: dict[str, dict[str, Any]] = {}
        self._last_context_failure: dict[str, Any] = {}

    def failure_for(self, source_url: str) -> dict[str, Any] | None:
        diagnostic = self._last_failure_by_url.get(normalize_text(source_url))
        return dict(diagnostic) if diagnostic else None

    def close(self) -> None:
        if self._page is not None:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser_manager is not None:
            try:
                self._browser_manager.close()
            except Exception:
                pass
            self._browser_manager = None

    def _current_seed(self) -> Mapping[str, Any]:
        seed = self._browser_context_seed_getter()
        return seed if isinstance(seed, Mapping) else {}

    def _ensure_context(self, source_url: str | None = None):
        if self._context is not None:
            return self._context

        active_user_agent = (
            normalize_text(self._current_seed().get("browser_user_agent"))
            or normalize_text(self._browser_user_agent)
        )
        try:
            self._browser_manager, _unused_browser, self._context = _new_browser_context(
                runtime_context=self._runtime_context,
                headless=self._headless,
                user_agent=active_user_agent,
                use_runtime_shared_browser=self._use_runtime_shared_browser,
            )
            self._sync_context_cookies()
            self._page = self._context.new_page()
            self._last_context_failure = {}
        except Exception as exc:
            self._last_context_failure = self._context_failure_diagnostic(exc)
            if source_url:
                self._record_failure(source_url, **self._last_context_failure)
            self.close()
            return None
        return self._context

    def _ensure_page(self, source_url: str | None = None):
        if self._page is not None:
            return self._page
        if self._ensure_context(source_url) is None:
            return None
        return self._page

    def _sync_context_cookies(self) -> None:
        if self._context is None:
            return
        cookies = list(self._current_seed().get("browser_cookies") or [])
        if not cookies:
            return
        try:
            self._context.add_cookies(cookies)
        except Exception:
            pass

    def _seed_urls(self) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for candidate in self._seed_urls_getter() or []:
            normalized = normalize_text(candidate)
            if normalized and normalized not in seen:
                seen.add(normalized)
                ordered.append(normalized)
        return ordered

    def _warm_seed_urls(self, *, force: bool) -> None:
        page = self._page
        if page is None:
            return
        for seed_url in self._seed_urls():
            if not force and seed_url in self._warmed_seed_urls:
                continue
            try:
                page.goto(seed_url, wait_until="domcontentloaded", timeout=30000)
                self._warmed_seed_urls.add(seed_url)
            except Exception:
                continue

    def _record_failure(self, source_url: str, **values: Any) -> None:
        normalized_url = normalize_text(source_url)
        if not normalized_url:
            return
        diagnostic = _compact_failure_diagnostic(
            {"source_url": normalized_url, **values}
        )
        if diagnostic:
            self._last_failure_by_url[normalized_url] = diagnostic

    def _context_failure_diagnostic(self, exc: Exception) -> dict[str, Any]:
        return _build_context_failure_diagnostic(exc)
