"""Shared PDF validation and Markdown conversion helpers."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..common_patterns import WORD_TOKEN_PATTERN
from ..http import PDF_ACCEPT_HEADER, is_pdf_content_type
from ..utils import normalize_text
from .browser_runtime.seed import CLOUDFLARE_COOKIE_NAMES, _CLOUDFLARE_COOKIE_PREFIXES


@dataclass(frozen=True)
class PdfFetchResult:
    source_url: str
    final_url: str
    pdf_bytes: bytes
    markdown_text: str
    suggested_filename: str | None = None


class PdfFetchFailure(Exception):
    def __init__(self, kind: str, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.details = dict(details or {})


_CONTENT_DISPOSITION_FILENAME_PATTERN = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', flags=re.IGNORECASE)
_PDF_MARKDOWN_WORD_PATTERN = WORD_TOKEN_PATTERN
# IEEE PDF cover/license pages are the common failure mode this guard was
# calibrated against; keep the marker name provider-specific so callers do not
# treat it as a generic publisher-license classifier.
_IEEE_PDF_LICENSE_MARKERS = (
    "authorized licensed use limited to",
    "restrictions apply",
    "downloaded on",
    "from ieee xplore",
    "personal use is permitted",
)
_MIN_USABLE_PDF_MARKDOWN_WORDS = 250
_MIN_TRANSPARENT_TEXT_WORDS = 500
_TRANSPARENT_FALLBACK_WORD_FACTOR = 3
_PYMUPDF_SUBPROCESS_PATCH_LOCK = threading.RLock()


@dataclass(frozen=True)
class _PdfMarkdownQuality:
    word_count: int
    license_word_count: int
    license_only: bool
    has_text: bool

    @property
    def is_usable(self) -> bool:
        return self.word_count >= _MIN_USABLE_PDF_MARKDOWN_WORDS and not self.license_only


@dataclass(frozen=True)
class _PdfTextLayerStats:
    raw_words: int
    visible_words: int
    transparent_words: int


def sanitize_storage_state(path: Path) -> Path:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cookies = payload.get("cookies", []) or []
    filtered_cookies = [
        cookie
        for cookie in cookies
        if cookie.get("name") not in CLOUDFLARE_COOKIE_NAMES
        and not str(cookie.get("name", "")).startswith(_CLOUDFLARE_COOKIE_PREFIXES)
    ]
    payload["cookies"] = filtered_cookies

    fd, temp_path = tempfile.mkstemp(prefix="playwright_state_", suffix=".json")
    temp_file = Path(temp_path)
    os.close(fd)
    temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return temp_file


def filename_from_headers(headers: Mapping[str, str] | None) -> str | None:
    content_disposition = str((headers or {}).get("content-disposition") or "")
    if not content_disposition:
        return None
    match = _CONTENT_DISPOSITION_FILENAME_PATTERN.search(content_disposition)
    if not match:
        return None
    return normalize_text(match.group(1)) or None


def default_pdf_headers(user_agent: str, *, referer: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": PDF_ACCEPT_HEADER,
        "User-Agent": user_agent,
    }
    if referer:
        headers["Referer"] = referer
    return headers


def _pdf_word_count(text: str) -> int:
    return len(_PDF_MARKDOWN_WORD_PATTERN.findall(normalize_text(text)))


def _pdf_markdown_quality(markdown_text: str) -> _PdfMarkdownQuality:
    normalized = normalize_text(markdown_text)
    word_count = _pdf_word_count(normalized)
    lines = [line for line in normalized.splitlines() if normalize_text(line)]
    license_word_count = 0
    for line in lines:
        normalized_line = normalize_text(line).lower()
        if any(marker in normalized_line for marker in _IEEE_PDF_LICENSE_MARKERS):
            license_word_count += _pdf_word_count(line)
    license_only = license_word_count > 0 and (
        word_count < _MIN_USABLE_PDF_MARKDOWN_WORDS
        or license_word_count >= max(20, int(word_count * 0.6))
    )
    return _PdfMarkdownQuality(
        word_count=word_count,
        license_word_count=license_word_count,
        license_only=license_only,
        has_text=bool(normalized),
    )


class _SubprocessTextDecodeReplace:
    def __enter__(self) -> None:
        _PYMUPDF_SUBPROCESS_PATCH_LOCK.acquire()
        self._original_run = subprocess.run

        def run_with_replace(*args, **kwargs):
            if (
                "errors" not in kwargs
                and (
                    kwargs.get("text")
                    or kwargs.get("universal_newlines")
                    or kwargs.get("encoding") is not None
                )
            ):
                kwargs = dict(kwargs)
                kwargs["errors"] = "replace"
            return self._original_run(*args, **kwargs)

        subprocess.run = run_with_replace

    def __exit__(self, exc_type, exc, tb) -> None:
        subprocess.run = self._original_run
        _PYMUPDF_SUBPROCESS_PATCH_LOCK.release()


def _render_default_pdf_markdown(pdf_path: Path) -> str:
    try:
        import pymupdf4llm
    except Exception as exc:  # pragma: no cover - exercised by missing dependency integration tests
        raise PdfFetchFailure("missing_pymupdf4llm", "pymupdf4llm is not installed; cannot use PDF fallback.") from exc
    with _SubprocessTextDecodeReplace():
        return str(pymupdf4llm.to_markdown(str(pdf_path)) or "")


def _render_transparent_pdf_markdown(pdf_path: Path) -> str:
    try:
        from pymupdf4llm.helpers import pymupdf_rag
    except Exception as exc:  # pragma: no cover - exercised by missing dependency integration tests
        raise PdfFetchFailure("missing_pymupdf4llm", "pymupdf4llm is not installed; cannot use PDF fallback.") from exc
    with _SubprocessTextDecodeReplace():
        return str(pymupdf_rag.to_markdown(str(pdf_path), ignore_alpha=True, hdr_info=False) or "")


def _pdf_text_layer_stats(pdf_path: Path) -> _PdfTextLayerStats:
    try:
        import pymupdf
    except Exception:  # pragma: no cover - PyMuPDF is a pymupdf4llm dependency in supported installs
        try:
            import fitz as pymupdf
        except Exception:
            return _PdfTextLayerStats(raw_words=0, visible_words=0, transparent_words=0)

    raw_words = 0
    transparent_words = 0
    try:
        with pymupdf.open(str(pdf_path)) as document:
            for page in document:
                text_dict = page.get_text("dict")
                for block in text_dict.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            span_words = _pdf_word_count(str(span.get("text") or ""))
                            raw_words += span_words
                            alpha_value = span.get("alpha", 255)
                            if alpha_value is None:
                                alpha_value = 255
                            if int(alpha_value) == 0:
                                transparent_words += span_words
    except Exception:
        return _PdfTextLayerStats(raw_words=0, visible_words=0, transparent_words=0)
    return _PdfTextLayerStats(
        raw_words=raw_words,
        visible_words=max(0, raw_words - transparent_words),
        transparent_words=transparent_words,
    )


def _should_try_transparent_pdf_fallback(
    *,
    default_quality: _PdfMarkdownQuality,
    text_layer_stats: _PdfTextLayerStats,
) -> bool:
    if default_quality.is_usable:
        return False
    return (
        text_layer_stats.transparent_words >= _MIN_TRANSPARENT_TEXT_WORDS
        and text_layer_stats.raw_words >= default_quality.word_count * _TRANSPARENT_FALLBACK_WORD_FACTOR
    )


def _insufficient_pdf_markdown_failure(
    *,
    default_quality: _PdfMarkdownQuality,
    text_layer_stats: _PdfTextLayerStats,
    legacy_quality: _PdfMarkdownQuality | None = None,
) -> PdfFetchFailure:
    details: dict[str, Any] = {
        "default_words": default_quality.word_count,
        "default_license_words": default_quality.license_word_count,
        "default_license_only": default_quality.license_only,
        "raw_words": text_layer_stats.raw_words,
        "visible_words": text_layer_stats.visible_words,
        "transparent_words": text_layer_stats.transparent_words,
    }
    if legacy_quality is not None:
        details.update(
            {
                "legacy_words": legacy_quality.word_count,
                "legacy_license_words": legacy_quality.license_word_count,
                "legacy_license_only": legacy_quality.license_only,
            }
        )
    return PdfFetchFailure(
        "insufficient_pdf_markdown",
        "PDF fallback produced insufficient Markdown.",
        details=details,
    )


def render_pdf_markdown(pdf_path: Path) -> str:
    default_markdown = _render_default_pdf_markdown(pdf_path)
    default_quality = _pdf_markdown_quality(default_markdown)
    if default_quality.is_usable:
        return default_markdown

    text_layer_stats = _pdf_text_layer_stats(pdf_path)
    if _should_try_transparent_pdf_fallback(
        default_quality=default_quality,
        text_layer_stats=text_layer_stats,
    ):
        legacy_markdown = _render_transparent_pdf_markdown(pdf_path)
        legacy_quality = _pdf_markdown_quality(legacy_markdown)
        min_legacy_words = max(
            _MIN_USABLE_PDF_MARKDOWN_WORDS,
            default_quality.word_count * _TRANSPARENT_FALLBACK_WORD_FACTOR,
        )
        if legacy_quality.word_count >= min_legacy_words and not legacy_quality.license_only:
            return legacy_markdown
        raise _insufficient_pdf_markdown_failure(
            default_quality=default_quality,
            text_layer_stats=text_layer_stats,
            legacy_quality=legacy_quality,
        )

    if not default_quality.has_text:
        return default_markdown
    raise _insufficient_pdf_markdown_failure(
        default_quality=default_quality,
        text_layer_stats=text_layer_stats,
    )


def looks_like_pdf_payload(content_type: str | None, payload: bytes, final_url: str | None = None) -> bool:
    normalized_content_type = normalize_text(content_type).lower()
    normalized_final_url = normalize_text(final_url).lower()
    return (
        payload.startswith(b"%PDF-")
        or is_pdf_content_type(normalized_content_type)
        or normalized_final_url.endswith(".pdf")
    )


def _normalized_response_headers(response: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(key).lower(): str(value)
        for key, value in (response.get("headers") or {}).items()
    }


def pdf_fetch_result_from_response(
    response: Mapping[str, Any],
    *,
    artifact_dir: Path | None,
    source_url: str,
    not_pdf_message: str,
    final_url: str | None = None,
) -> PdfFetchResult:
    response_headers = _normalized_response_headers(response)
    resolved_final_url = normalize_text(str(final_url or response.get("url") or source_url)) or source_url
    try:
        status = int(response.get("status_code") or 0) or None
    except (TypeError, ValueError):
        status = None
    raw_body = response.get("body", b"")
    pdf_bytes = bytes(raw_body) if isinstance(raw_body, (bytes, bytearray)) else b""
    content_type = str(response_headers.get("content-type") or "")
    if not isinstance(raw_body, (bytes, bytearray)) or not looks_like_pdf_payload(
        content_type,
        pdf_bytes,
        resolved_final_url,
    ):
        raise PdfFetchFailure(
            "downloaded_file_not_pdf",
            not_pdf_message,
            details={
                "source_url": source_url,
                "final_url": resolved_final_url,
                "status": status,
                "content_type": content_type or None,
            },
        )

    return pdf_fetch_result_from_bytes(
        artifact_dir=artifact_dir,
        source_url=source_url,
        final_url=resolved_final_url,
        pdf_bytes=pdf_bytes,
        suggested_filename=filename_from_headers(response_headers),
    )


def pdf_fetch_result_from_bytes(
    *,
    artifact_dir: Path | None,
    source_url: str,
    final_url: str,
    pdf_bytes: bytes,
    suggested_filename: str | None = None,
) -> PdfFetchResult:
    temp_dir_cm = tempfile.TemporaryDirectory(prefix="paper_fetch_pdf_") if artifact_dir is None else nullcontext(None)
    with temp_dir_cm as temp_dir:
        active_dir = Path(temp_dir) if temp_dir is not None else artifact_dir
        assert active_dir is not None
        active_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = active_dir / "downloaded.pdf"
        pdf_path.write_bytes(pdf_bytes)
        if not pdf_bytes.startswith(b"%PDF-"):
            pdf_path.unlink(missing_ok=True)
            raise PdfFetchFailure(
                "downloaded_file_not_pdf",
                "PDF fallback did not produce a PDF file.",
                details={"source_url": source_url, "suggested_filename": suggested_filename},
            )

        markdown_text = render_pdf_markdown(pdf_path)
        if not normalize_text(markdown_text):
            raise PdfFetchFailure(
                "empty_pdf_markdown",
                "PDF fallback produced empty Markdown.",
                details={"source_url": source_url, "final_url": final_url},
            )

        return PdfFetchResult(
            source_url=source_url,
            final_url=final_url,
            pdf_bytes=pdf_bytes,
            markdown_text=markdown_text,
            suggested_filename=suggested_filename,
        )
