"""CloakBrowser helpers for browser-workflow provider access."""

from __future__ import annotations

import base64
from importlib import metadata as importlib_metadata
from importlib import util as importlib_util
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from bs4 import BeautifulSoup

from .._cloakbrowser_runtime import import_cloakbrowser
from ..config import (
    CLOAKBROWSER_BINARY_PATH_ENV_VAR,
    CLOAKBROWSER_HEADLESS_ENV_VAR,
    CLOAKBROWSER_TIMEOUT_MS_ENV_VAR,
    CLOAKBROWSER_USER_DATA_DIR_ENV_VAR,
    build_browser_user_agent,
    parse_positive_int_env,
    resolve_user_data_dir,
)
from ..extraction.image_payloads import (
    image_dimensions_from_bytes,
    image_mime_type_from_bytes,
)
from ..extraction.html.signals import detect_html_block, summarize_html
from ..quality.html_availability import choose_parser, extract_page_title
from ..quality.html_signals import looks_like_abstract_redirect
from ..quality.reason_codes import REDIRECTED_TO_ABSTRACT
from ..reason_codes import ERROR, NOT_CONFIGURED, OK, READY
from ..runtime_browser import browser_context_options, browser_page_user_agent, cloakbrowser_binary_path_env
from ..utils import normalize_text, provider_display_name, sanitize_filename
from .browser_runtime.seed import (
    merge_browser_context_seeds,
    normalize_browser_cookies_for_playwright,
)
from .browser_runtime.types import (
    BrowserFetchedHtml,
    BrowserRuntimeConfig,
    BrowserRuntimeFailure,
)
from .base import (
    ProviderFailure,
    ProviderStatusResult,
    build_provider_status_check,
    provider_status_check_from_failure,
)
from .browser_workflow.fetchers.context import (
    _browser_response_headers,
    _browser_response_status,
)
from .browser_workflow.fetchers.readiness import wait_for_atypon_body_dom_ready
from .browser_workflow.fetchers.scripts import _LOADED_IMAGE_CANVAS_EXPORT_SCRIPT
from .browser_workflow.shared import BROWSER_HTML_BLOCKED_RESOURCE_TYPES

if TYPE_CHECKING:
    from ..runtime import RuntimeContext
    from .browser_runtime import BrowserImagePayload

logger = logging.getLogger("paper_fetch.providers.cloakbrowser")

DEFAULT_BROWSER_RUNTIME_MAX_TIMEOUT_MS = 120000
DEFAULT_BROWSER_RUNTIME_WAIT_SECONDS = 8
DEFAULT_BROWSER_RUNTIME_WARM_WAIT_SECONDS = 1
DEFAULT_CLOAKBROWSER_TIMEOUT_MS = DEFAULT_BROWSER_RUNTIME_MAX_TIMEOUT_MS
CLOAKBROWSER_STATUS_PROBE_ID = "probe://cloakbrowser/status"
_IMAGE_PAYLOAD_MIN_IMAGE_DIMENSION = 1
_IMAGE_RESPONSE_BLOCKED_BY_HTML_WRAPPER = "image_response_blocked_by_html_wrapper"
_IMAGE_PAYLOAD_RESPONSE_ATTR = "_paper_fetch_top_level_response"
_IMAGE_PAYLOAD_TIMEOUT_ATTR = "_paper_fetch_image_payload_timeout_ms"
_IMAGE_PAYLOAD_FAILURE_ATTR = "_paper_fetch_image_payload_failure"

CloakBrowserRuntimeConfig = BrowserRuntimeConfig
CloakBrowserFailure = BrowserRuntimeFailure


def _browser_workflow_label(provider: str) -> str:
    normalized = normalize_text(provider).lower()
    return f"{provider_display_name(normalized)} browser workflow"


def _dependency_available() -> bool:
    try:
        return importlib_util.find_spec("cloakbrowser") is not None
    except (ModuleNotFoundError, ValueError):
        return False


def _dependency_details() -> dict[str, Any]:
    details: dict[str, Any] = {"probe": "importlib.find_spec"}
    if _dependency_available():
        try:
            details["version"] = importlib_metadata.version("cloakbrowser")
        except importlib_metadata.PackageNotFoundError:
            details["version"] = None
    return details


def _import_cloakbrowser() -> Any:
    try:
        cloakbrowser = import_cloakbrowser()
    except Exception as exc:
        raise ProviderFailure(
            NOT_CONFIGURED,
            f"CloakBrowser Python package is not importable: {exc}",
        ) from exc
    return cloakbrowser


def _env_flag_false(value: str | None) -> bool:
    return normalize_text(value).lower() in {"0", "false", "no", "off"}


def _configured_binary_path(env: Mapping[str, str]) -> str | None:
    value = env.get(CLOAKBROWSER_BINARY_PATH_ENV_VAR, "").strip()
    return value or None


def _configured_user_data_dir(env: Mapping[str, str]) -> Path | None:
    value = env.get(CLOAKBROWSER_USER_DATA_DIR_ENV_VAR, "").strip()
    return Path(value).expanduser() if value else None


def _validate_binary_path(binary_path: str | None) -> None:
    if not binary_path:
        return
    path = Path(binary_path).expanduser()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ProviderFailure(
            NOT_CONFIGURED,
            f"{CLOAKBROWSER_BINARY_PATH_ENV_VAR} is set but does not point to an executable browser binary.",
        )


def load_runtime_config(env: Mapping[str, str], *, provider: str, doi: str) -> CloakBrowserRuntimeConfig:
    headless = not _env_flag_false(env.get(CLOAKBROWSER_HEADLESS_ENV_VAR))
    artifact_dir = resolve_user_data_dir(env) / "publisher-browser-artifacts" / provider / sanitize_filename(doi)
    binary_path = _configured_binary_path(env)
    _validate_binary_path(binary_path)
    return CloakBrowserRuntimeConfig(
        provider=provider,
        doi=doi,
        artifact_dir=artifact_dir,
        headless=headless,
        user_agent=build_browser_user_agent(env),
        timeout_ms=parse_positive_int_env(
            env,
            CLOAKBROWSER_TIMEOUT_MS_ENV_VAR,
            default=DEFAULT_CLOAKBROWSER_TIMEOUT_MS,
        ),
        binary_path=binary_path,
        user_data_dir=_configured_user_data_dir(env),
    )


def ensure_runtime_ready(config: CloakBrowserRuntimeConfig) -> None:
    _validate_binary_path(config.binary_path)
    try:
        _import_cloakbrowser()
    except ProviderFailure as exc:
        workflow_label = _browser_workflow_label(config.provider)
        raise ProviderFailure(
            NOT_CONFIGURED,
            f"{workflow_label} requires the cloakbrowser Python package. {exc.message}",
        ) from exc


def _runtime_probe_details(env: Mapping[str, str], config: CloakBrowserRuntimeConfig | None = None) -> dict[str, Any]:
    details: dict[str, Any] = {
        "headless": (
            config.headless
            if config is not None
            else not _env_flag_false(env.get(CLOAKBROWSER_HEADLESS_ENV_VAR))
        ),
        "timeout_ms": config.timeout_ms if config is not None else parse_positive_int_env(
            env,
            CLOAKBROWSER_TIMEOUT_MS_ENV_VAR,
            default=DEFAULT_CLOAKBROWSER_TIMEOUT_MS,
        ),
        "binary_path_configured": bool(config.binary_path if config is not None else _configured_binary_path(env)),
        "user_data_dir_configured": bool(config.user_data_dir if config is not None else _configured_user_data_dir(env)),
    }
    return details


def probe_runtime_status(
    env: Mapping[str, str],
    *,
    provider: str,
    doi: str = CLOAKBROWSER_STATUS_PROBE_ID,
) -> ProviderStatusResult:
    checks = []
    config: CloakBrowserRuntimeConfig | None = None
    runtime_details = _runtime_probe_details(env)
    dependency_available = _dependency_available()
    try:
        config = load_runtime_config(env, provider=provider, doi=doi)
        runtime_details = _runtime_probe_details(env, config)
        checks.append(
            build_provider_status_check(
                "runtime_env",
                OK if dependency_available else NOT_CONFIGURED,
                (
                    f"{provider} CloakBrowser runtime environment is configured."
                    if dependency_available
                    else f"{provider} CloakBrowser runtime requires the cloakbrowser Python package."
                ),
                details=runtime_details,
            )
        )
    except ProviderFailure as exc:
        checks.append(provider_status_check_from_failure("runtime_env", exc, details=runtime_details))
    except Exception as exc:
        checks.append(build_provider_status_check("runtime_env", ERROR, str(exc), details=runtime_details))

    dependency_details = _dependency_details()
    if dependency_available:
        checks.append(
            build_provider_status_check(
                "cloakbrowser_dependency",
                OK,
                "CloakBrowser Python package is importable; browser launch is not probed.",
                details=dependency_details,
            )
        )
    else:
        checks.append(
            build_provider_status_check(
                "cloakbrowser_dependency",
                NOT_CONFIGURED,
                "CloakBrowser Python package is not installed.",
                details=dependency_details,
            )
        )

    missing_env: list[str] = []
    for check in checks:
        for name in check.missing_env:
            if name not in missing_env:
                missing_env.append(name)

    if any(check.status == ERROR for check in checks):
        status = ERROR
    elif all(check.status == OK for check in checks):
        status = READY
    else:
        status = NOT_CONFIGURED

    return ProviderStatusResult(
        provider=provider,
        status=status,
        available=status == READY,
        official_provider=True,
        missing_env=missing_env,
        notes=[],
        checks=list(checks),
    )


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalized_content_type(value: str | None) -> str:
    return normalize_text(str(value or "")).split(";", 1)[0].lower()


def _response_body(response: Any) -> bytes | None:
    if response is None:
        return None
    try:
        body = response.body()
    except Exception:
        return None
    if not isinstance(body, (bytes, bytearray)) or not body:
        return None
    return bytes(body)


def _browser_image_payload_from_bytes(
    body: bytes | bytearray | None,
    *,
    content_type: str | None,
    url: str,
    status: int | None,
    width: int = 0,
    height: int = 0,
) -> BrowserImagePayload | None:
    if not isinstance(body, (bytes, bytearray)) or not body:
        return None
    payload_body = bytes(body)
    detected_type = image_mime_type_from_bytes(payload_body)
    if not detected_type:
        return None
    normalized_content_type = _normalized_content_type(content_type) or detected_type
    if not normalized_content_type.startswith("image/"):
        normalized_content_type = detected_type
    dimensions = image_dimensions_from_bytes(payload_body)
    if dimensions is not None:
        width = width or dimensions[0]
        height = height or dimensions[1]
    return {
        "bodyB64": base64.b64encode(payload_body).decode("ascii"),
        "contentType": normalized_content_type,
        "url": normalize_text(url),
        "status": status or 200,
        "width": max(0, _safe_int(width)),
        "height": max(0, _safe_int(height)),
    }


def _capture_expected_response(page: Any, request_url: str) -> Any:
    response = getattr(page, _IMAGE_PAYLOAD_RESPONSE_ATTR, None)
    if response is not None:
        return response
    timeout_ms = (
        _safe_int(getattr(page, _IMAGE_PAYLOAD_TIMEOUT_ATTR, None))
        or DEFAULT_CLOAKBROWSER_TIMEOUT_MS
    )
    try:
        expected_response = page.expect_response(
            lambda response: normalize_text(str(getattr(response, "url", "") or ""))
            == request_url,
            timeout=timeout_ms,
        )
    except Exception:
        return None
    if not hasattr(expected_response, "__enter__"):
        return getattr(expected_response, "value", expected_response)
    try:
        with expected_response as response_info:
            pass
        return getattr(response_info, "value", None)
    except Exception:
        return None


def _image_element_has_loaded_natural_size(image_element: Any) -> bool | None:
    try:
        image_info = image_element.evaluate(
            """
            (image) => ({
              width: image.naturalWidth || 0,
              height: image.naturalHeight || 0,
              complete: !!image.complete,
            })
            """
        )
    except Exception:
        return None
    if not isinstance(image_info, Mapping):
        return None
    return (
        bool(image_info.get("complete", True))
        and _safe_int(image_info.get("width")) > 0
        and _safe_int(image_info.get("height")) > 0
    )


def _payload_from_canvas_export(
    rendered: Any,
    *,
    fallback_url: str,
    status: int | None,
) -> BrowserImagePayload | None:
    if not isinstance(rendered, Mapping) or not rendered.get("ok"):
        return None
    body_b64 = normalize_text(str(rendered.get("bodyB64") or ""))
    content_type = (
        _normalized_content_type(str(rendered.get("contentType") or ""))
        or "image/png"
    )
    data_url = normalize_text(
        str(rendered.get("dataURL") or rendered.get("dataUrl") or "")
    )
    if data_url.startswith("data:") and "," in data_url:
        metadata, body_b64 = data_url.split(",", 1)
        content_type = (
            _normalized_content_type(metadata.removeprefix("data:").split(";", 1)[0])
            or content_type
        )
    try:
        body = base64.b64decode(body_b64, validate=True)
    except Exception:
        return None
    return _browser_image_payload_from_bytes(
        body,
        content_type=content_type,
        url=fallback_url,
        status=status,
        width=_safe_int(rendered.get("width")),
        height=_safe_int(rendered.get("height")),
    )


def _clear_image_payload_failure(page: Any) -> None:
    try:
        delattr(page, _IMAGE_PAYLOAD_FAILURE_ATTR)
    except Exception:
        pass


def _record_image_payload_failure(page: Any, values: Mapping[str, Any]) -> None:
    try:
        setattr(page, _IMAGE_PAYLOAD_FAILURE_ATTR, dict(values))
    except Exception:
        pass


def _capture_image_payload(
    page: Any,
    *,
    request_url: str,
    final_url: str,
) -> BrowserImagePayload | None:
    _clear_image_payload_failure(page)
    normalized_request_url = normalize_text(request_url)
    normalized_final_url = normalize_text(final_url) or normalized_request_url
    response = _capture_expected_response(page, normalized_request_url)
    status = _browser_response_status(response, zero_as_none=False) or 200
    headers = _browser_response_headers(response)
    content_type = _normalized_content_type(headers.get("content-type"))

    if content_type.startswith("image/"):
        payload = _browser_image_payload_from_bytes(
            _response_body(response),
            content_type=content_type,
            url=normalized_final_url,
            status=status,
        )
        if payload is not None:
            return payload

    html = ""
    try:
        html = str(page.content() or "")
    except Exception:
        html = ""
    if (
        _normalized_content_type(content_type) in {"image/svg+xml", ""}
        or normalize_text(html).startswith("<")
    ):
        svg_payload = _browser_image_payload_from_bytes(
            html.encode("utf-8"),
            content_type="image/svg+xml",
            url=normalized_final_url,
            status=status,
        )
        if svg_payload is not None and svg_payload["contentType"] == "image/svg+xml":
            return svg_payload

    image_element = None
    try:
        image_element = page.query_selector("img")
    except Exception:
        image_element = None
    if image_element is not None:
        loaded = _image_element_has_loaded_natural_size(image_element)
        if loaded is not False:
            try:
                rendered = page.evaluate(
                    _LOADED_IMAGE_CANVAS_EXPORT_SCRIPT,
                    [
                        normalized_request_url,
                        _IMAGE_PAYLOAD_MIN_IMAGE_DIMENSION,
                        _IMAGE_PAYLOAD_MIN_IMAGE_DIMENSION,
                    ],
                )
            except Exception:
                rendered = None
            payload = _payload_from_canvas_export(
                rendered,
                fallback_url=normalized_final_url,
                status=status,
            )
            if payload is not None:
                return payload

    try:
        title = normalize_text(str(page.title() or ""))
    except Exception:
        title = ""
    if not title and html:
        try:
            title = extract_page_title(BeautifulSoup(html, choose_parser()))
        except Exception:
            title = ""
    summary = summarize_html(html) if normalize_text(html) else ""
    detected = detect_html_block(title or "", summary, status)
    reason = (
        detected.reason
        if detected is not None
        else _IMAGE_RESPONSE_BLOCKED_BY_HTML_WRAPPER
    )
    _record_image_payload_failure(
        page,
        {
            "reason": reason,
            "url": normalized_final_url,
            "status": status,
            "content_type": content_type,
            "title": title,
            "summary": summary,
        },
    )
    return None


def _context_seed(context: Any, *, final_url: str, user_agent: str | None) -> dict[str, Any]:
    try:
        cookies = context.cookies()
    except Exception:
        cookies = []
    return {
        "browser_cookies": normalize_browser_cookies_for_playwright(
            list(cookies or []),
            fallback_url=final_url,
        ),
        "browser_user_agent": normalize_text(user_agent) or None,
        "browser_final_url": final_url,
    }


def _safe_close(value: Any) -> None:
    if value is None:
        return
    try:
        value.close()
    except Exception:
        pass


def _storage_state_path(config: CloakBrowserRuntimeConfig) -> Path | None:
    if config.user_data_dir is None:
        return None
    return config.user_data_dir / "storage-state.json"


def _storage_context_options(config: CloakBrowserRuntimeConfig) -> dict[str, Any]:
    storage_state_path = _storage_state_path(config)
    if storage_state_path is None or not storage_state_path.is_file():
        return {}
    return {"storage_state": str(storage_state_path)}


def _save_storage_state(context: Any, config: CloakBrowserRuntimeConfig) -> None:
    storage_state_path = _storage_state_path(config)
    if context is None or storage_state_path is None:
        return
    try:
        storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(storage_state_path))
    except Exception:
        logger.debug(
            "cloakbrowser_storage_state provider=%s action=save_failed path=%s",
            config.provider,
            storage_state_path,
            exc_info=True,
        )


def fetch_html_with_cloakbrowser(
    candidate_urls: list[str],
    *,
    publisher: str,
    config: CloakBrowserRuntimeConfig,
    wait_seconds: int = DEFAULT_BROWSER_RUNTIME_WAIT_SECONDS,
    warm_wait_seconds: int = DEFAULT_BROWSER_RUNTIME_WARM_WAIT_SECONDS,
    max_timeout_ms: int | None = None,
    return_image_payload: bool = False,
    return_screenshot: bool = False,
    disable_media: bool = False,
    runtime_context: RuntimeContext | None = None,
) -> BrowserFetchedHtml:
    del warm_wait_seconds
    if not candidate_urls:
        raise CloakBrowserFailure("empty_html_attempts", "No publisher HTML candidates were attempted.")
    if return_image_payload:
        disable_media = False

    try:
        cloakbrowser = _import_cloakbrowser()
    except ProviderFailure as exc:
        raise CloakBrowserFailure(NOT_CONFIGURED, exc.message) from exc

    last_failure: CloakBrowserFailure | None = None
    latest_browser_context_seed: Mapping[str, Any] | None = None
    timeout_ms = max_timeout_ms or config.timeout_ms
    artifact_dir = config.artifact_dir / "cloakbrowser"
    configured_user_agent = normalize_text(config.user_agent)

    browser = None
    browser_context = None
    page = None
    try:
        try:
            context_kwargs = browser_context_options(
                user_agent=configured_user_agent,
                **_storage_context_options(config),
            )
            if runtime_context is not None:
                browser_context = runtime_context.new_browser_context(
                    headless=config.headless,
                    **context_kwargs,
                )
            else:
                with cloakbrowser_binary_path_env(config.binary_path):
                    browser = cloakbrowser.launch(headless=config.headless, locale="en-US")
                browser_context = browser.new_context(**context_kwargs)
            page = browser_context.new_page()
        except Exception as exc:
            raise CloakBrowserFailure(
                "cloakbrowser_launch_failed",
                normalize_text(str(exc)) or "CloakBrowser failed to launch.",
            ) from exc

        def route_handler(route: Any) -> None:
            try:
                resource_type = normalize_text(str(route.request.resource_type or "")).lower()
                if disable_media and resource_type in BROWSER_HTML_BLOCKED_RESOURCE_TYPES:
                    route.abort()
                    return
                route.continue_()
            except Exception:
                try:
                    route.continue_()
                except Exception:
                    pass

        if disable_media:
            try:
                page.route("**/*", route_handler)
            except Exception:
                pass

        for url in candidate_urls:
            normalized_url = normalize_text(url)
            if not normalized_url:
                continue
            try:
                logger.debug(
                    "cloakbrowser_request provider=%s action=request wait_seconds=%s url=%s",
                    publisher,
                    wait_seconds,
                    normalized_url,
                )
                request_started = time.monotonic()
                response = None
                top_level_response = None
                if return_image_payload:
                    try:
                        setattr(page, _IMAGE_PAYLOAD_TIMEOUT_ATTR, timeout_ms)
                    except Exception:
                        pass
                    try:
                        with page.expect_response(
                            lambda candidate_response: normalize_text(
                                str(getattr(candidate_response, "url", "") or "")
                            )
                            == normalized_url,
                            timeout=timeout_ms,
                        ) as response_info:
                            response = page.goto(
                                normalized_url,
                                wait_until="domcontentloaded",
                                timeout=timeout_ms,
                            )
                        try:
                            top_level_response = response_info.value
                        except Exception:
                            top_level_response = response
                    except Exception:
                        if response is None:
                            raise
                        top_level_response = response
                else:
                    response = page.goto(
                        normalized_url,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                if top_level_response is None:
                    top_level_response = response
                if return_image_payload:
                    try:
                        setattr(page, _IMAGE_PAYLOAD_RESPONSE_ATTR, top_level_response)
                    except Exception:
                        pass
                readiness = None
                if not return_image_payload:
                    remaining_timeout_seconds = max(
                        0.0,
                        (float(timeout_ms) / 1000.0)
                        - (time.monotonic() - request_started),
                    )
                    readiness = wait_for_atypon_body_dom_ready(
                        page,
                        publisher,
                        timeout_seconds=min(
                            max(float(wait_seconds), 20.0),
                            remaining_timeout_seconds,
                        ),
                    )
                if (
                    (readiness is None or not readiness.attempted)
                    and wait_seconds > 0
                ):
                    page.wait_for_timeout(max(0, int(wait_seconds)) * 1000)
                final_url = normalize_text(str(getattr(page, "url", "") or "")) or normalized_url
                html = str(page.content() or "")
                title = normalize_text(str(page.title() or "")) or extract_page_title(
                    BeautifulSoup(html, choose_parser())
                )
                status = _browser_response_status(response, zero_as_none=False)
                headers = _browser_response_headers(response)
                summary = summarize_html(html)
                browser_context_seed = _context_seed(
                    browser_context,
                    final_url=final_url,
                    user_agent=configured_user_agent or browser_page_user_agent(page),
                )
                if browser_context_seed.get("browser_cookies") or browser_context_seed.get("browser_user_agent"):
                    latest_browser_context_seed = browser_context_seed
                image_payload = None
                if return_image_payload:
                    try:
                        image_payload = _capture_image_payload(
                            page,
                            request_url=normalized_url,
                            final_url=final_url,
                        )
                    except Exception:
                        image_payload = None
                    image_failure = getattr(page, _IMAGE_PAYLOAD_FAILURE_ATTR, None)
                    if isinstance(image_failure, Mapping):
                        headers = dict(headers)
                        headers[
                            "x-paper-fetch-image-payload-failure-reason"
                        ] = normalize_text(str(image_failure.get("reason") or ""))
            except Exception as exc:
                if isinstance(exc, CloakBrowserFailure):
                    last_failure = exc
                else:
                    last_failure = CloakBrowserFailure(
                        "cloakbrowser_request_failed",
                        normalize_text(str(exc)) or "CloakBrowser page request failed.",
                    )
                continue

            if looks_like_abstract_redirect(normalized_url, final_url):
                last_failure = CloakBrowserFailure(
                    REDIRECTED_TO_ABSTRACT,
                    "Publisher redirected the full-text URL to an abstract page.",
                    browser_context_seed=browser_context_seed,
                )
                continue

            detected = (
                None
                if readiness is not None and readiness.ready
                else detect_html_block(title or "", summary, status)
            )
            if detected is not None and not return_image_payload:
                last_failure = CloakBrowserFailure(
                    detected.reason,
                    detected.message,
                    browser_context_seed=browser_context_seed,
                )
                continue
            if not normalize_text(html) and image_payload is None:
                last_failure = CloakBrowserFailure(
                    "empty_html_response",
                    "CloakBrowser returned empty publisher HTML.",
                    browser_context_seed=browser_context_seed,
                )
                continue

            screenshot_b64 = None
            if return_screenshot:
                try:
                    screenshot_payload = page.screenshot(type="png", timeout=timeout_ms)
                    if isinstance(screenshot_payload, bytes):
                        screenshot_b64 = base64.b64encode(screenshot_payload).decode("ascii")
                    elif isinstance(screenshot_payload, str):
                        screenshot_b64 = screenshot_payload
                except Exception:
                    screenshot_b64 = None
            return BrowserFetchedHtml(
                source_url=normalized_url,
                final_url=final_url,
                html=html,
                response_status=status,
                response_headers=headers,
                title=title,
                summary=summary,
                browser_context_seed=browser_context_seed,
                screenshot_b64=screenshot_b64,
                image_payload=image_payload,
            )
    finally:
        _save_storage_state(browser_context, config)
        _safe_close(page)
        _safe_close(browser_context)
        _safe_close(browser)

    if last_failure is None and latest_browser_context_seed is not None:
        last_failure = CloakBrowserFailure(
            "empty_html_attempts",
            "No publisher HTML candidates were attempted.",
            browser_context_seed=latest_browser_context_seed,
        )
    if last_failure is None:
        last_failure = CloakBrowserFailure("empty_html_attempts", "No publisher HTML candidates were attempted.")
    if artifact_dir:
        try:
            artifact_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    raise last_failure


fetch_html_with_cloakbrowser.paper_fetch_html_fetcher_name = "cloakbrowser"  # type: ignore[attr-defined]


def fetch_html_with_cloakbrowser_fast(*args: Any, **kwargs: Any) -> BrowserFetchedHtml:
    return fetch_html_with_cloakbrowser(*args, **kwargs)


fetch_html_with_cloakbrowser_fast.paper_fetch_html_fetcher_name = "cloakbrowser_fast"  # type: ignore[attr-defined]


def warm_browser_context_with_cloakbrowser(
    candidate_urls: list[str],
    *,
    publisher: str,
    config: CloakBrowserRuntimeConfig,
    browser_context_seed: Mapping[str, Any] | None = None,
    runtime_context: RuntimeContext | None = None,
) -> dict[str, Any]:
    merged_seed = merge_browser_context_seeds(browser_context_seed)
    if not candidate_urls:
        return merged_seed

    try:
        result = fetch_html_with_cloakbrowser(
            candidate_urls,
            publisher=publisher,
            config=config,
            runtime_context=runtime_context,
        )
    except CloakBrowserFailure as exc:
        return merge_browser_context_seeds(merged_seed, exc.browser_context_seed)
    return merge_browser_context_seeds(merged_seed, result.browser_context_seed)
