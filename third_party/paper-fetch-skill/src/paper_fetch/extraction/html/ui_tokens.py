"""Shared publisher UI labels that appear in multiple rule layers."""

from __future__ import annotations

DOWNLOAD_PDF_LABEL = "download pdf"
COMMON_NOISE_TOKENS = (
    "related",
    "recommend",
    "metric",
    "metrics",
    "share",
    "social",
    "toolbar",
    "breadcrumb",
    "cookie",
    "promo",
    "banner",
    "rightslink",
)
CITATION_TOOL_CHROME_TOKENS = ("export citation",)
RELATED_CONTENT_CHROME_TOKENS = ("related articles",)
FIGURE_FULL_SIZE_IMAGE_LABEL = "full size image"
FIGURE_POWERPOINT_SLIDE_LABEL = "PowerPoint slide"
SPRINGER_FULL_SIZE_IMAGE_LABEL = FIGURE_FULL_SIZE_IMAGE_LABEL
SPRINGER_NATURE_SOURCE_DATA_LABEL = "source data"
SPRINGER_POWERPOINT_SLIDE_LABEL = FIGURE_POWERPOINT_SLIDE_LABEL
SPRINGER_PREVIEW_PHRASE = "this is a preview of subscription content"


__all__ = [
    "DOWNLOAD_PDF_LABEL",
    "FIGURE_FULL_SIZE_IMAGE_LABEL",
    "FIGURE_POWERPOINT_SLIDE_LABEL",
    "COMMON_NOISE_TOKENS",
    "CITATION_TOOL_CHROME_TOKENS",
    "RELATED_CONTENT_CHROME_TOKENS",
    "SPRINGER_FULL_SIZE_IMAGE_LABEL",
    "SPRINGER_NATURE_SOURCE_DATA_LABEL",
    "SPRINGER_POWERPOINT_SLIDE_LABEL",
    "SPRINGER_PREVIEW_PHRASE",
]
