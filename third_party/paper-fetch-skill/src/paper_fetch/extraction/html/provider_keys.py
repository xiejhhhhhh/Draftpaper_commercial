"""Provider key normalization shared by extraction and quality helpers."""

from __future__ import annotations


def normalize_provider_key(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", "_").split())


__all__ = ["normalize_provider_key"]
