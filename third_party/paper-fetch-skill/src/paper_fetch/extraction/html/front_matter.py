"""Shared front-matter vocabularies for HTML extraction and diagnostics."""

from __future__ import annotations

import re

ARTICLE_TYPE_FRONT_MATTER_PREFIXES = (
    "regular paper",
    "research article",
    "original article",
    "review article",
    "short communication",
    "brief communication",
    "case report",
    "letter to the editor",
)

COMMON_FRONT_MATTER_LINE_PATTERNS = (
    re.compile(r"^doi:\s*", flags=re.IGNORECASE),
    re.compile(r"^(vol\.?|volume)\b", flags=re.IGNORECASE),
    re.compile(r"^issue\b", flags=re.IGNORECASE),
)


__all__ = [
    "ARTICLE_TYPE_FRONT_MATTER_PREFIXES",
    "COMMON_FRONT_MATTER_LINE_PATTERNS",
]
