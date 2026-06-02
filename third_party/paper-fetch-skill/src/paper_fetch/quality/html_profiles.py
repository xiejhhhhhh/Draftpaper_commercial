"""Provider-neutral HTML availability profiles and access signals."""

from __future__ import annotations

from typing import Any

from ..extraction.html.provider_rules import (
    DEFAULT_SITE_RULE as DEFAULT_SITE_RULE,
    merged_site_rule as merged_site_rule,
    provider_html_rules as provider_html_rules,
)
from ..utils import normalize_text
from .html_signals import (
    AAAS_DATALAYER_PATTERN as AAAS_DATALAYER_PATTERN,
    HTML_STRONG_FULLTEXT_MARKERS as HTML_STRONG_FULLTEXT_MARKERS,
    HTML_STRUCTURE_MARKERS as HTML_STRUCTURE_MARKERS,
    PNAS_DATALAYER_PATTERN as PNAS_DATALAYER_PATTERN,
    WILEY_DATALAYER_PATTERN as WILEY_DATALAYER_PATTERN,
    dedupe_signals as dedupe_signals,
    default_positive_signals as default_positive_signals,
    load_aaas_datalayer as load_aaas_datalayer,
    load_pnas_datalayer as load_pnas_datalayer,
    load_wiley_datalayer as load_wiley_datalayer,
    looks_like_abstract_redirect as looks_like_abstract_redirect,
)


def _rules_for_publisher(publisher: str | None):
    return provider_html_rules(normalize_text(publisher or "").lower())


def site_rule_for_publisher(publisher: str | None) -> dict[str, Any]:
    return merged_site_rule(_rules_for_publisher(publisher))


def noise_profile_for_publisher(publisher: str | None) -> str:
    return _rules_for_publisher(publisher).noise_profile
