"""Copernicus adapters around the shared NLM/JATS XML renderer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import xml.etree.ElementTree as ET

from ._article_markdown_jats import (
    JatsExtraction,
    build_jats_markdown_document,
    extract_jats_authors,
    extract_jats_metadata,
    extract_jats_references,
    parse_jats_xml,
)

CopernicusExtraction = JatsExtraction
extract_copernicus_authors = extract_jats_authors
extract_copernicus_metadata = extract_jats_metadata
extract_copernicus_references = extract_jats_references


def parse_copernicus_xml(
    xml_body: bytes,
    *,
    source_url: str,
    base_metadata: Mapping[str, Any] | None = None,
    xml_root: ET.Element | None = None,
) -> CopernicusExtraction | None:
    return parse_jats_xml(
        xml_body,
        source_url=source_url,
        base_metadata=base_metadata,
        xml_root=xml_root,
    )


def build_copernicus_markdown_document(
    extraction: CopernicusExtraction,
    *,
    xml_path: Path | None = None,
) -> str:
    return build_jats_markdown_document(
        extraction,
        xml_path=xml_path,
        provider_label="copernicus",
    )


__all__ = [
    "CopernicusExtraction",
    "build_copernicus_markdown_document",
    "extract_copernicus_authors",
    "extract_copernicus_metadata",
    "extract_copernicus_references",
    "parse_copernicus_xml",
]
