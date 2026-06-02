"""Shared DOI and publisher identity helpers for the skill runtime."""

from __future__ import annotations

import re
import urllib.parse
import unicodedata

import idutils

from .normalize_journal_name import normalize_journal_name
from .provider_catalog import (
    doi_prefix_provider_map,
    ordered_provider_specs,
    provider_domain_matches,
)

PUBLISHER_PROVIDER_MAP: dict[str, str] | None = None
DOI_PREFIX_PROVIDER_MAP: dict[str, str] | None = None
DOI_CORE_PATTERN = r"10\.\d{4,9}/[^\s\"'<>]+"
ASCII_DOI_CORE_PATTERN = r"10\.\d{4,9}/[!-~]+"
DOI_PATTERN = re.compile(DOI_CORE_PATTERN, flags=re.IGNORECASE)
DOI_DASH_TRANSLATION = str.maketrans(
    {
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "−": "-",
        "﹣": "-",
        "－": "-",
    }
)


def _clean_doi_value(doi: str) -> str:
    value = unicodedata.normalize("NFKC", doi).strip().lower().translate(DOI_DASH_TRANSLATION)
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    value = re.sub(r"\s+", "", value)
    return value.rstrip(").,;")


def _idutils_normalized_doi(value: str) -> str:
    if not value:
        return ""
    try:
        if not idutils.is_doi(value):
            return ""
        normalized = idutils.normalize_doi(value)
    except Exception:
        return ""
    return _clean_doi_value(str(normalized or ""))


def normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    value = _clean_doi_value(doi)
    return _idutils_normalized_doi(value) or value


def extract_doi(text: str | None) -> str | None:
    if not text:
        return None
    match = DOI_PATTERN.search(text)
    if not match:
        return None
    return normalize_doi(match.group(0).rstrip(").,;"))


def infer_provider_from_doi(doi: str | None) -> str | None:
    normalized = normalize_doi(doi)
    global DOI_PREFIX_PROVIDER_MAP
    if DOI_PREFIX_PROVIDER_MAP is None:
        DOI_PREFIX_PROVIDER_MAP = doi_prefix_provider_map()
    for prefix, provider in DOI_PREFIX_PROVIDER_MAP.items():
        if normalized.startswith(prefix):
            return provider
    return None


def infer_provider_from_publisher(publisher: str | None) -> str | None:
    if not publisher:
        return None
    normalized = normalize_journal_name(publisher)
    global PUBLISHER_PROVIDER_MAP
    if PUBLISHER_PROVIDER_MAP is None:
        PUBLISHER_PROVIDER_MAP = {
            normalize_journal_name(alias): spec.name
            for spec in ordered_provider_specs()
            for alias in spec.publisher_aliases
        }
    return PUBLISHER_PROVIDER_MAP.get(normalized)


def infer_provider_from_url(url: str | None) -> str | None:
    if not url:
        return None
    hostname = (urllib.parse.urlparse(url).hostname or "").lower()
    for spec in ordered_provider_specs():
        if provider_domain_matches(spec.name, hostname):
            return spec.name
    return None


def ordered_provider_candidates(
    *,
    landing_urls: list[str | None] | None = None,
    publishers: list[str | None] | None = None,
    doi: str | None = None,
) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    for url in landing_urls or []:
        provider = infer_provider_from_url(url)
        if provider and provider not in seen:
            seen.add(provider)
            candidates.append((provider, "domain"))

    for publisher in publishers or []:
        provider = infer_provider_from_publisher(publisher)
        if provider and provider not in seen:
            seen.add(provider)
            candidates.append((provider, "publisher"))

    provider = infer_provider_from_doi(doi)
    if provider and provider not in seen:
        candidates.append((provider, "doi"))
    return candidates


def infer_provider_from_signals(
    *,
    landing_urls: list[str | None] | None = None,
    publishers: list[str | None] | None = None,
    doi: str | None = None,
) -> str | None:
    candidates = ordered_provider_candidates(
        landing_urls=landing_urls,
        publishers=publishers,
        doi=doi,
    )
    return candidates[0][0] if candidates else None
