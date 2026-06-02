"""List rendering helpers."""

from __future__ import annotations

from ...utils import normalize_text
from ._ir import MarkdownList


def render_list(lst: MarkdownList) -> list[str]:
    lines: list[str] = []
    index = 1
    for item in lst.items:
        text = normalize_text(item)
        if not text:
            continue
        marker = f"{index}." if lst.ordered else "-"
        lines.append(f"{marker} {text}")
        index += 1
    if lines:
        lines.append("")
    return lines
