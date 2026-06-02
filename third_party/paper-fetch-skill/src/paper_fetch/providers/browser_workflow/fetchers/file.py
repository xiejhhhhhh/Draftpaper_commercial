"""Supplementary file document fetchers for provider browser workflows."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Mapping

from ....extraction.html.assets import supplementary_response_block_reason
from ....extraction.html.shared import (
    html_text_snippet as _html_text_snippet,
    html_title_snippet as _html_title_snippet,
)
from ....logging_utils import emit_structured_log
from ....runtime import RuntimeContext
from ....utils import normalize_text
from .context import _BaseBrowserDocumentFetcher, _normalized_response_headers
from .diagnostics import _copy_failure_diagnostic

logger = logging.getLogger("paper_fetch.providers.browser_workflow")


class _SharedBrowserFileDocumentFetcher(_BaseBrowserDocumentFetcher):
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
        super().__init__(
            browser_context_seed_getter=browser_context_seed_getter,
            seed_urls_getter=seed_urls_getter,
            browser_user_agent=browser_user_agent,
            headless=headless,
            runtime_context=runtime_context,
            use_runtime_shared_browser=use_runtime_shared_browser,
        )

    def __call__(
        self, file_url: str, asset: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        normalized_url = normalize_text(file_url)
        if not normalized_url:
            return None
        if self._ensure_context(normalized_url) is None:
            return None

        self._sync_context_cookies()
        self._warm_seed_urls(force=False)
        for attempt in range(3):
            result = self._fetch_with_context_request(normalized_url)
            if result is not None:
                return result
            if attempt == 0:
                self._sync_context_cookies()
                self._warm_seed_urls(force=True)
                continue
            break
        return None

    def _record_response_failure(
        self,
        file_url: str,
        *,
        status: int | None,
        content_type: str,
        final_url: str,
        body: bytes | bytearray | None,
        reason: str,
    ) -> None:
        self._record_failure(
            file_url,
            status=status,
            content_type=content_type,
            final_url=final_url,
            title_snippet=_html_title_snippet(body),
            body_snippet=_html_text_snippet(body),
            reason=reason,
        )

    def _fetch_with_context_request(self, file_url: str) -> dict[str, Any] | None:
        if self._context is None:
            return None
        try:
            response = self._context.request.get(
                file_url,
                headers={"Accept": "*/*"},
                timeout=60000,
            )
        except Exception as exc:
            self._record_failure(
                file_url,
                reason=normalize_text(str(exc)) or exc.__class__.__name__,
            )
            return None

        try:
            headers = _normalized_response_headers(response.all_headers())
        except Exception:
            headers = _normalized_response_headers(
                getattr(response, "headers", {}) or {}
            )
        content_type = headers.get("content-type", "")
        final_url = normalize_text(getattr(response, "url", "") or "") or file_url
        status = int(getattr(response, "status", 0) or 0) or None
        try:
            body = response.body()
        except Exception:
            body = b""
        if not isinstance(body, (bytes, bytearray)) or not body:
            self._record_failure(
                file_url,
                status=status,
                content_type=content_type,
                final_url=final_url,
                reason="empty_response_body",
            )
            return None
        block_reason = supplementary_response_block_reason(content_type, body)
        if block_reason:
            self._record_response_failure(
                file_url,
                status=status,
                content_type=content_type,
                final_url=final_url,
                body=body,
                reason=block_reason,
            )
            return None
        return {
            "status_code": int(getattr(response, "status", 200) or 200),
            "headers": headers,
            "body": bytes(body),
            "url": final_url,
        }


class _ThreadLocalSharedBrowserFileDocumentFetcher:
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
        self._thread_local = threading.local()
        self._lock = threading.Lock()
        self._fetchers: list[_SharedBrowserFileDocumentFetcher] = []
        self._failure_by_url: dict[str, dict[str, Any]] = {}

    def _get_fetcher(self) -> _SharedBrowserFileDocumentFetcher:
        fetcher = getattr(self._thread_local, "fetcher", None)
        if isinstance(fetcher, _SharedBrowserFileDocumentFetcher):
            return fetcher
        fetcher = _SharedBrowserFileDocumentFetcher(
            browser_context_seed_getter=self._browser_context_seed_getter,
            seed_urls_getter=self._seed_urls_getter,
            browser_user_agent=self._browser_user_agent,
            headless=self._headless,
            runtime_context=self._runtime_context,
            use_runtime_shared_browser=self._use_runtime_shared_browser,
        )
        self._thread_local.fetcher = fetcher
        with self._lock:
            self._fetchers.append(fetcher)
        emit_structured_log(
            logger,
            logging.DEBUG,
            "browser_workflow_file_fetcher_thread_created",
            thread=threading.current_thread().name,
        )
        return fetcher

    def __call__(
        self, file_url: str, asset: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        normalized_url = normalize_text(file_url)
        fetcher = self._get_fetcher()
        try:
            payload = fetcher(file_url, asset)
            if normalized_url:
                if payload is None:
                    failure = fetcher.failure_for(normalized_url)
                    if isinstance(failure, Mapping):
                        with self._lock:
                            self._failure_by_url[normalized_url] = _copy_failure_diagnostic(failure)
                else:
                    with self._lock:
                        self._failure_by_url.pop(normalized_url, None)
            return payload
        finally:
            # Browser sync objects must be closed from their owning worker
            # thread. Closing these thread-local fetchers later from the caller
            # thread can leave Chromium subprocesses behind.
            self._close_fetcher_for_current_thread(fetcher)

    def failure_for(self, file_url: str) -> dict[str, Any] | None:
        fetcher = getattr(self._thread_local, "fetcher", None)
        if not isinstance(fetcher, _SharedBrowserFileDocumentFetcher):
            normalized_url = normalize_text(file_url)
            with self._lock:
                cached_failure = self._failure_by_url.get(normalized_url)
            return _copy_failure_diagnostic(cached_failure) if cached_failure else None
        failure = fetcher.failure_for(file_url)
        return _copy_failure_diagnostic(failure) if isinstance(failure, Mapping) else None

    def _close_fetcher_for_current_thread(self, fetcher: _SharedBrowserFileDocumentFetcher) -> None:
        try:
            fetcher.close()
        finally:
            with self._lock:
                self._fetchers = [item for item in self._fetchers if item is not fetcher]
            if getattr(self._thread_local, "fetcher", None) is fetcher:
                try:
                    delattr(self._thread_local, "fetcher")
                except AttributeError:
                    pass

    def close(self) -> None:
        with self._lock:
            fetchers = list(self._fetchers)
            self._fetchers.clear()
        for fetcher in fetchers:
            fetcher.close()


def _build_shared_browser_file_fetcher(
    *,
    browser_context_seed_getter: Callable[[], Mapping[str, Any] | None],
    seed_urls_getter: Callable[[], list[str]],
    browser_user_agent: str | None = None,
    headless: bool = True,
    runtime_context: RuntimeContext | None = None,
    use_runtime_shared_browser: bool = True,
    thread_local: bool = False,
) -> (
    _ThreadLocalSharedBrowserFileDocumentFetcher
    | _SharedBrowserFileDocumentFetcher
):
    fetcher_cls: (
        type[_ThreadLocalSharedBrowserFileDocumentFetcher]
        | type[_SharedBrowserFileDocumentFetcher]
    )
    fetcher_cls = (
        _ThreadLocalSharedBrowserFileDocumentFetcher
        if thread_local
        else _SharedBrowserFileDocumentFetcher
    )
    return fetcher_cls(
        browser_context_seed_getter=browser_context_seed_getter,
        seed_urls_getter=seed_urls_getter,
        browser_user_agent=browser_user_agent,
        headless=headless,
        runtime_context=runtime_context,
        use_runtime_shared_browser=use_runtime_shared_browser,
    )
