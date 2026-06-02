"""AMS asset extraction helpers."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from ..common_patterns import TABLE_LABEL_PATTERN
from ..extraction.html.parsing import choose_parser
from ..utils import normalize_text
from ._ams_dom import (
    _ams_full_image_src,
    _ams_gallery_href,
    _ams_inline_image,
    _normalize_ams_dom,
    _render_ams_inline_text,
)
from ._ams_markdown import _normalize_ams_label_text

from bs4 import BeautifulSoup, Tag


def _normalize_ams_asset_html(html_text: str) -> str:
    soup = BeautifulSoup(html_text, choose_parser())
    _normalize_ams_dom(soup)
    return str(soup)


def _table_label_text(node: Any) -> str:
    if not isinstance(node, Tag):
        return "Table"
    for selector in (".tableWrapLabel", ".label"):
        candidate = node.select_one(selector)
        if isinstance(candidate, Tag):
            text = _normalize_ams_label_text(
                candidate.get_text(" ", strip=True), kind="table"
            )
            if text:
                return text
    title = _normalize_ams_label_text(str(node.get("title") or ""), kind="table")
    match = TABLE_LABEL_PATTERN.search(title)
    if match:
        return f"Table {match.group(1)}."
    text = _normalize_ams_label_text(node.get_text(" ", strip=True), kind="table")
    match = TABLE_LABEL_PATTERN.search(text)
    if match:
        return f"Table {match.group(1)}."
    return "Table"


def _table_caption_text(node: Any, label: str) -> str:
    if not isinstance(node, Tag):
        return ""
    candidates: list[str] = []
    for selector in (".tableWrapCaption", ".caption", "figcaption", "caption"):
        caption_node = node.select_one(selector)
        if isinstance(caption_node, Tag):
            text = _render_ams_inline_text(caption_node)
            if text:
                candidates.append(text)
    title = normalize_text(str(node.get("title") or ""))
    if title:
        candidates.append(title)
    label_text = normalize_text(label).rstrip(".")
    for text in candidates:
        if label_text:
            text = re.sub(
                rf"^{re.escape(label_text)}\.?\s*", "", text, flags=re.IGNORECASE
            )
        text = normalize_text(text).lstrip(".:;,-) ]")
        if text:
            return text
    return ""


def _absolute_url(source_url: str, value: str) -> str:
    return urllib.parse.urljoin(source_url, normalize_text(value))


def _ams_asset_url_keys(asset: dict[str, str]) -> set[str]:
    return {
        normalize_text(str(asset.get(field) or ""))
        for field in (
            "url",
            "full_size_url",
            "preview_url",
            "source_url",
            "original_url",
            "path",
        )
        if normalize_text(str(asset.get(field) or ""))
    }


def _extract_ams_table_assets(html_text: str, source_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(_normalize_ams_asset_html(html_text), choose_parser())
    assets: list[dict[str, str]] = []
    seen: set[str] = set()
    for node in soup.select(".tableWrap"):
        if not isinstance(node, Tag):
            continue
        image = _ams_inline_image(node)
        full_size_url = _ams_gallery_href(node) or _ams_full_image_src(node)
        preview_url = ""
        if isinstance(image, Tag):
            preview_url = normalize_text(
                str(
                    image.get("data-src")
                    or image.get("data-image-src")
                    or image.get("src")
                    or ""
                )
            )
            full_size_url = (
                normalize_text(str(image.get("data-full-size") or "")) or full_size_url
            )
        url = full_size_url or preview_url
        if not url:
            continue
        absolute = _absolute_url(source_url, url)
        if absolute in seen:
            continue
        seen.add(absolute)
        label = _table_label_text(node)
        caption = _table_caption_text(node, label)
        asset: dict[str, str] = {
            "kind": "table",
            "heading": label or "Table",
            "caption": caption,
            "url": absolute,
            "section": "body",
        }
        dom_id = normalize_text(str(node.get("id") or ""))
        if dom_id:
            asset["dom_id"] = dom_id
        if preview_url:
            asset["preview_url"] = _absolute_url(source_url, preview_url)
        if full_size_url:
            asset["full_size_url"] = _absolute_url(source_url, full_size_url)
        assets.append(asset)
    return assets


def scoped_asset_extractor(
    body_html_text: str,
    source_url: str,
    *,
    asset_profile,
    supplementary_html_text: str | None = None,
) -> list[dict[str, str]]:
    from .atypon_browser_workflow.asset_scopes import extract_scoped_html_assets

    normalized_body_html = _normalize_ams_asset_html(body_html_text)
    # The Atypon shared extractor owns figures, formulas, and supplementary assets.
    # AMS adds image-only tableWrap screenshots here because they are table surrogates.
    assets = extract_scoped_html_assets(
        normalized_body_html,
        source_url,
        asset_profile=asset_profile,
        supplementary_html_text=(
            _normalize_ams_asset_html(supplementary_html_text)
            if supplementary_html_text is not None
            else None
        ),
    )
    table_assets = _extract_ams_table_assets(normalized_body_html, source_url)
    table_urls = {url for asset in table_assets for url in _ams_asset_url_keys(asset)}
    if table_urls:
        assets = [
            asset for asset in assets if not (_ams_asset_url_keys(asset) & table_urls)
        ]
    assets.extend(table_assets)
    return assets


__all__ = [
    "scoped_asset_extractor",
]
