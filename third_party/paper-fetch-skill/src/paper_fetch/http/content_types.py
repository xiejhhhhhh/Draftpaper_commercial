"""Shared MIME type constants and content-type helpers."""

from __future__ import annotations

PDF_MIME_TYPE = "application/pdf"
PDF_ACCEPT_HEADER = f"{PDF_MIME_TYPE},*/*;q=0.8"
STRUCTURED_TEXT_MIME_TYPES = (
    "application/json",
    "application/xml",
    "application/jats+xml",
)


def content_type_base(value: str | None) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def is_pdf_content_type(value: str | None) -> bool:
    return content_type_base(value) == PDF_MIME_TYPE


__all__ = [
    "PDF_ACCEPT_HEADER",
    "PDF_MIME_TYPE",
    "STRUCTURED_TEXT_MIME_TYPES",
    "content_type_base",
    "is_pdf_content_type",
]
