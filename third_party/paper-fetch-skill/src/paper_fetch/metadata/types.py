"""Typed metadata payload schemas shared by metadata and provider adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from typing_extensions import TypedDict

from ..utils import normalize_text


class FulltextLink(TypedDict, total=False):
    url: str
    content_type: str | None
    content_version: str | None
    intended_application: str | None


class ReferenceMetadata(TypedDict, total=False):
    label: str | None
    raw: str
    doi: str | None
    title: str | None
    year: str | None


class ProviderMetadata(TypedDict, total=False):
    status: str
    provider: str
    official_provider: bool
    source_url: str
    doi: str | None
    title: str | None
    journal_title: str | None
    publisher: str | None
    article_type: str | None
    authors: list[str]
    keywords: list[str]
    abstract: str | None
    published: str | None
    landing_page_url: str | None
    citation_fulltext_html_url: str | None
    citation_abstract_html_url: str | None
    license_urls: list[str]
    fulltext_links: list[FulltextLink]
    references: list[ReferenceMetadata]


class CrossrefMetadata(ProviderMetadata, total=False):
    pass


class HtmlLookupHints(TypedDict, total=False):
    lookup_title: str | None
    redirect_url: str | None
    identifier_value: str | None


class HtmlMetadata(ProviderMetadata, total=False):
    raw_meta: dict[str, list[str]]
    lookup_title: str | None
    lookup_redirect_url: str | None
    identifier_value: str | None


@dataclass(frozen=True)
class MetadataMergeRule:
    """Field-level merge behavior for ordered provider metadata layers."""

    fill_empty: tuple[str, ...] = ()
    overwrite: tuple[str, ...] = ()
    concat_unique: tuple[str, ...] = ()
    take_first_non_empty: tuple[str, ...] = ()


def _metadata_value_is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _metadata_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        values = list(value)
    elif isinstance(value, tuple):
        values = list(value)
    else:
        values = [value]
    return [item for item in values if not _metadata_value_is_empty(item)]


def _metadata_unique_key(value: Any) -> Any:
    if isinstance(value, str):
        return ("text", normalize_text(value).lower())
    try:
        hash(value)
    except TypeError:
        return ("repr", repr(value))
    return ("value", value)


def _concat_unique_metadata_values(*groups: Any) -> list[Any]:
    result: list[Any] = []
    seen: set[Any] = set()
    for group in groups:
        for value in _metadata_values(group):
            candidate = normalize_text(value) if isinstance(value, str) else value
            if _metadata_value_is_empty(candidate):
                continue
            key = _metadata_unique_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            result.append(candidate)
    return result


def merge_metadata_layers(
    layers: Sequence[Mapping[str, Any] | None],
    *,
    rule: MetadataMergeRule,
) -> dict[str, Any]:
    """Merge layers in order; undeclared fields default to fill-empty behavior."""

    merged: dict[str, Any] = {}
    fill_empty = set(rule.fill_empty)
    overwrite = set(rule.overwrite)
    concat_unique = set(rule.concat_unique)
    take_first_non_empty = set(rule.take_first_non_empty)
    declared = fill_empty | overwrite | concat_unique | take_first_non_empty

    for layer in layers:
        if not isinstance(layer, Mapping):
            continue
        for key, raw_value in layer.items():
            if _metadata_value_is_empty(raw_value):
                continue
            if key in concat_unique:
                merged[key] = _concat_unique_metadata_values(merged.get(key), raw_value)
                continue
            if key in overwrite:
                merged[key] = raw_value
                continue
            if key in fill_empty or key in take_first_non_empty or key not in declared:
                if _metadata_value_is_empty(merged.get(key)):
                    merged[key] = raw_value
    return merged


__all__ = [
    "CrossrefMetadata",
    "FulltextLink",
    "HtmlLookupHints",
    "HtmlMetadata",
    "MetadataMergeRule",
    "ProviderMetadata",
    "ReferenceMetadata",
    "merge_metadata_layers",
]
