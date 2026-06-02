"""Browser-neutral runtime contract for provider workflows."""

from .seed import (
    CLOUDFLARE_COOKIE_NAMES,
    _CLOUDFLARE_COOKIE_PREFIXES,
    merge_browser_context_seeds,
    normalize_browser_cookie_for_playwright,
    normalize_browser_cookies_for_playwright,
    parse_optional_int,
)
from .types import (
    BrowserFetchedHtml,
    BrowserImagePayload,
    BrowserRuntimeConfig,
    BrowserRuntimeFailure,
)
from .api import (
    DEFAULT_BROWSER_RUNTIME_MAX_TIMEOUT_MS,
    DEFAULT_BROWSER_RUNTIME_WAIT_SECONDS,
    DEFAULT_BROWSER_RUNTIME_WARM_WAIT_SECONDS,
    ensure_runtime_ready,
    fetch_html_with_browser,
    load_runtime_config,
    probe_runtime_status,
    warm_browser_context,
)

__all__ = [
    "BrowserFetchedHtml",
    "BrowserImagePayload",
    "BrowserRuntimeConfig",
    "BrowserRuntimeFailure",
    "CLOUDFLARE_COOKIE_NAMES",
    "DEFAULT_BROWSER_RUNTIME_MAX_TIMEOUT_MS",
    "DEFAULT_BROWSER_RUNTIME_WAIT_SECONDS",
    "DEFAULT_BROWSER_RUNTIME_WARM_WAIT_SECONDS",
    "_CLOUDFLARE_COOKIE_PREFIXES",
    "ensure_runtime_ready",
    "fetch_html_with_browser",
    "load_runtime_config",
    "merge_browser_context_seeds",
    "normalize_browser_cookie_for_playwright",
    "normalize_browser_cookies_for_playwright",
    "parse_optional_int",
    "probe_runtime_status",
    "warm_browser_context",
]
