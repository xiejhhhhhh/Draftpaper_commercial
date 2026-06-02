# Routing Rules

This file is a historical design note for routing heuristics. It is not loaded by the runtime and is not the source of truth for current provider routing.

Canonical routing behavior lives in:

- [`docs/providers.md`](../docs/providers.md), for provider capabilities, routing semantics, and provider-owned waterfalls.
- `paper_fetch.provider_catalog.PROVIDER_CATALOG`, for supported provider identities, domains, DOI prefixes, publisher aliases, default asset policy, status ordering, and client factory paths.
- `src/paper_fetch/publisher_identity.py` and `src/paper_fetch/workflow/routing.py`, for runtime selection logic derived from the catalog.

## Stable Historical Invariants

Runtime routing is intentionally conservative and signal-based:

1. Landing-page / URL domain signal.
2. Crossref publisher-name signal.
3. DOI-prefix fallback signal.

Earlier signals win. DOI-prefix inference is a fallback, not an override. Crossref may always contribute metadata and route signals, but it is not a generic full-text downloader.

If no supported official provider is selected, Crossref remains metadata-only. If an official provider is selected and later cannot provide full text, full-text retrieval stays inside that provider's own waterfall and then degrades through provider-managed `abstract_only` or generic `metadata_only` fallback as documented in [`docs/providers.md`](../docs/providers.md#抓取瀑布与回退语义).

## Historical Scope

This note deliberately does not duplicate current provider waterfalls, supported-provider tables, or planned provider designs. In particular:

- IEEE is implemented and documented in [`docs/providers.md`](../docs/providers.md#ieee).
- Copernicus is implemented and documented in [`docs/providers.md`](../docs/providers.md#copernicus).
- MDPI is a planned design documented only in [`docs/providers.md`](../docs/providers.md#待接入设计mdpi).
- A publisher is not treated as full-text supported until it exists in the provider catalog, router-derived surfaces, registry, status surface, and tests.
