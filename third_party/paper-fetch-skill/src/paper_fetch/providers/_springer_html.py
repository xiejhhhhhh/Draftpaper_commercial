"""Compatibility facade for SPRINGER provider HTML helpers."""

from __future__ import annotations

from typing import Any

from . import _springer_dom as _impl
from . import _springer_markdown as _markdown_impl

from ._springer_authors import (
    _AUTHOR_PIPELINE as _AUTHOR_PIPELINE,
    extract_authors as extract_authors,
    normalize_display_authors as normalize_display_authors,
)

from ._springer_references import (
    extract_numbered_references_from_html as extract_numbered_references_from_html,
)

from ._springer_assets import (
    SPRINGER_SUPPLEMENTARY_SECTION_TITLES as SPRINGER_SUPPLEMENTARY_SECTION_TITLES,
    extract_asset_html_scopes as extract_asset_html_scopes,
    extract_source_data_html_scope as extract_source_data_html_scope,
    extract_springer_table_image_url as extract_springer_table_image_url,
    extract_html_assets as extract_html_assets,
    extract_scoped_html_assets as extract_scoped_html_assets,
    download_assets_for_springer as download_assets_for_springer,
    figure_download_candidates as figure_download_candidates,
)

from ._springer_markdown import (
    clean_markdown as clean_markdown,
    _remove_springer_ai_alt_disclaimers as _remove_springer_ai_alt_disclaimers,
    extract_article_markdown as extract_article_markdown,
)

from ._springer_dom import (
    decode_html as decode_html,
    parse_html_metadata as parse_html_metadata,
    merge_html_metadata as merge_html_metadata,
    extract_html_extraction_sidecars as extract_html_extraction_sidecars,
)


def extract_html_payload(
    html_text: str,
    source_url: str,
    *,
    title: str | None = None,
) -> dict[str, Any]:
    _markdown_impl.extract_article_markdown = extract_article_markdown
    _markdown_impl.extract_authors = extract_authors
    _markdown_impl.extract_numbered_references_from_html = extract_numbered_references_from_html
    return _markdown_impl.extract_html_payload(html_text, source_url, title=title)


def __getattr__(name: str) -> Any:
    return getattr(_impl, name)

__all__ = [
    "_AUTHOR_PIPELINE",
    "extract_authors",
    "normalize_display_authors",
    "extract_numbered_references_from_html",
    "SPRINGER_SUPPLEMENTARY_SECTION_TITLES",
    "extract_asset_html_scopes",
    "extract_source_data_html_scope",
    "extract_springer_table_image_url",
    "extract_html_assets",
    "extract_scoped_html_assets",
    "download_assets_for_springer",
    "figure_download_candidates",
    "clean_markdown",
    "_remove_springer_ai_alt_disclaimers",
    "extract_html_payload",
    "decode_html",
    "parse_html_metadata",
    "merge_html_metadata",
    "extract_html_extraction_sidecars",
    "extract_article_markdown",
]
