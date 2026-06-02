"""Shared failure, status, and route/content-kind reason codes."""

from __future__ import annotations

NO_RESULT = "no_result"
NO_ACCESS = "no_access"
NOT_CONFIGURED = "not_configured"
NOT_SUPPORTED = "not_supported"
RATE_LIMITED = "rate_limited"
ERROR = "error"

ABSTRACT_ONLY = "abstract_only"
METADATA_ONLY = "metadata_only"
PDF_FALLBACK = "pdf_fallback"

OK = "ok"
PARTIAL = "partial"
READY = "ready"


__all__ = [
    "ABSTRACT_ONLY",
    "ERROR",
    "METADATA_ONLY",
    "NO_ACCESS",
    "NO_RESULT",
    "NOT_CONFIGURED",
    "NOT_SUPPORTED",
    "OK",
    "PARTIAL",
    "PDF_FALLBACK",
    "RATE_LIMITED",
    "READY",
]
