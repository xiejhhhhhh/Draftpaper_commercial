"""Caption rendering helpers."""

from __future__ import annotations

from ...utils import normalize_text
from ._ir import MarkdownCaption


def render_caption(caption: MarkdownCaption) -> str:
    label = normalize_text(caption.label)
    text = normalize_text(caption.text)
    if label and text:
        return f"**{label}** {text}"
    if label:
        return f"**{label}**"
    return text
