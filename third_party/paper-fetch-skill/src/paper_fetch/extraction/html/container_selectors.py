"""Shared article container selectors used by HTML scoring and extraction."""

from __future__ import annotations

ARTICLE_BODY_SELECTORS = (
    "#bodymatter",
    "[data-extent='bodymatter']",
    "[property='articleBody']",
    "[itemprop='articleBody']",
    ".article__body",
    ".article-body",
    ".article__content",
    ".article-section__content",
    ".article__fulltext",
    ".epub-section",
)


__all__ = ["ARTICLE_BODY_SELECTORS"]
