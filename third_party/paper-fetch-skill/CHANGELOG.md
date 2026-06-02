# Changelog

All notable public changes to `paper-fetch-skill` are documented in this file.

## Unreleased

<!-- SCAFFOLD: changelog-unreleased -->

## 2.0.0 - 2026-05-28

### Changed

- Derive MCP provider guidance from the runtime provider catalog so accepted provider hints, browser-runtime providers, and public source names stay aligned with registered providers.
- Refresh public provider and extraction documentation for the current provider catalog, including Annual Reviews, Royal Society Publishing, PLOS, Oxford Academic, ACS, IOP, AIP, MDPI, AMS, Science, and PNAS route details.
- Mark browser-workflow providers through provider specs instead of maintaining separate hard-coded browser-runtime provider lists.
- Update Codex skill installation, offline installer, deployment, and onboarding documentation around the supported installation surface.

### Removed

- Remove the Gemini skill installer and legacy Codex MCP runner scripts from the shipped script surface.

### Fixed

- Keep CloakBrowser workflow labels, provider docs drift checks, offline install checks, and skill template tests synchronized with catalog-derived provider facts.

## 1.9.0 - 2026-05-27

### Added

- Add AIP Publishing (`aip`) provider routing for `10.1063/` and `pubs.aip.org`, with CloakBrowser article HTML, seeded-browser PDF fallback, `aip_html` / `aip_pdf` sources, body figure/table/formula/supplementary extraction, and provider-managed abstract-only degradation.
- Add two-step provider onboarding human gates with `prepare-human-preflight` and `finalize-review-artifact` so users review waterfall/access once, then batch-confirm final Markdown quality instead of editing every fixture review by hand.
- Add IOP Publishing (`iop`) provider routing for `10.1088/` and `iopscience.iop.org`, with CloakBrowser article HTML, seeded-browser PDF fallback, `iop_html` / `iop_pdf` sources, and Radware/hCaptcha challenge rejection.
- Add real IOP fixture coverage for table, formula, and PDF fallback purposes with `10.1088/2058-9565/ac3460` and `10.1088/1748-9326/aa9f73`.
- Add ACS (`acs`) provider routing for `10.1021/`, `www.acs.org` / `pubs.acs.org`, shared CloakBrowser HTML plus seeded publisher PDF/ePDF workflow, replay-backed table / formula / Supporting Information coverage, and direct public `/doi/pdf` fallback capture with seeded browser-navigation headers.

### Changed

- Tighten provider fixture discovery so Crossref candidate searches can be DOI-prefix filtered, off-provider DOI candidates are dropped before probing, and challenge/access/empty-shell probes cannot rank as high-confidence fulltext fixtures.

### Fixed

- Re-approve the IOP replay fixture coverage so the real `10.1088/1748-9326/ab7d02` capture now covers the supplementary purpose through the article-scoped `stacks.iop.org` media link.
- Require ACS body figure assets in the onboarding contract and preserve ACS figure image links through browser-workflow cleanup so downloaded body figures rewrite Markdown to local asset paths.

## 1.8.0 - 2026-05-26

### Added

- Add PLOS (`plos`) provider routing for `10.1371/` DOI and `journals.plos.org`, using public JATS XML first, direct HTTP PDF fallback, provider-managed metadata fallback, and `plos_xml` / `plos_pdf` sources.
- Add Oxford Academic (`oxfordacademic`) provider onboarding for public HTTP article HTML, validated article-PDF fallback, `oxfordacademic_html` / `oxfordacademic_pdf` sources, provider manifest, access review, cleaning proposal, and benchmark samples.
- Add PLOS and Oxford Academic golden corpus coverage with real replay fixtures, expected Markdown summaries, markdown-quality reports, and representative fixtures.

### Changed

- Extend onboarding automation, fixture capture, manifest sync-back, and cleaning-chain proposal tooling for the PLOS and Oxford Academic provider workflows.
- Refresh provider documentation, extraction-rule evidence, onboarding runbooks, and known-provider manifests for the new providers.
- Update Royal Society Publishing PDF fallback expected payloads and markdown-quality fixtures after shared PDF rendering cleanup.

### Fixed

- Follow PLOS signed figure-image redirects during asset downloads and rewrite refreshed PLOS figure golden replay Markdown to local `body_assets`.
- Render PLOS graphic-only JATS formulas as inline formula image assets instead of `Formula unavailable` placeholders.
- Preserve Oxford Academic Silverchair formula paragraphs and render references from visible reference-list text instead of raw `citation_reference` meta keys.
- Keep Oxford Academic golden corpus count guards in sync with the new provider fixtures and representative sample.

## 1.7.0 - 2026-05-24

### Added

- Add Annual Reviews (`annualreviews`) provider for `10.1146/` DOI routing, CloakBrowser-rendered HTML full text, seeded-browser PDF fallback, provider-managed abstract-only degradation, fixture replay, golden corpus coverage, and HTML body figure extraction.

- Add Royal Society Publishing direct HTTP HTML provider with strict PDF fallback.

### Fixed

- Wait for Annual Reviews dynamic full-text DOM containers during fast browser fixture capture, and stop treating institutional "access provided by" labels as paywall blockers while keeping them as Markdown cleanup noise.
- Classify browser PDF fixture downloads that return non-PDF payloads as `NON_PDF_FALLBACK_CONTENT` instead of a network transient, and require replacing the failed PDF sample before onboarding resumes.
- Refetch browser PDF fallback responses through the browser request context when Chromium exposes a PDF viewer shell instead of the underlying PDF bytes.
- Allow manifest-driven fixture capture to reuse an already registered DOI fixture when multiple onboarding purposes share the same article.
- Avoid classifying publisher access UI as an access gate during fixture capture when the captured page has a populated full-text container.
- Preserved Royal Society Publishing Silverchair figure captions and stripped Royal Society PDF fallback watermark/page placeholder noise from Markdown.
- Derived DOI values for known MDPI numeric article URLs before generic landing-page fetches, and derived MDPI article landing URLs from known MDPI DOI suffixes before falling back to `doi.org`.
- Synced the bundled formula Node workspace to `katex` 0.17.0 so root and formula package lockfiles stay aligned.
- Replaced invalid UTF-8 bytes from external formula converter subprocess output instead of letting Windows reader threads raise `UnicodeDecodeError`.
- Replaced invalid UTF-8 bytes from PyMuPDF's Windows Tesseract-probe subprocess output during PDF fallback Markdown conversion.

## 1.6 - 2026-05-22

### Added

- Added experimental macOS offline release tarballs for CPython 3.11, 3.12, 3.13, and 3.14, with CI installation checks, headful layout validation, and CloakBrowser smoke coverage.
- Added the MDPI CloakBrowser HTML provider with browser PDF fallback, recorded replay fixtures, Markdown cleanup coverage, and `mdpi_html` / `mdpi_pdf` sources.
- Added operator access-review and provider Markdown-review artifacts for AI provider onboarding, with schema-backed gates before discovery and acceptance.
- Added a local `scripts/dev-preflight.sh` gate plus low-strength contract-layer `mypy` checking, formula Node package sync tests, and golden corpus provider adapters for easier provider onboarding.

### Changed

- Changed manifest-driven fixture capture to support `--all` batch capture and changed provider scaffold replay to return merge-plan JSON when generated files already exist.
- Tightened live review to compare provider sources against manifest `route_sources` and reuse manifest Markdown contracts for automatic issue classification.
- Enabled the normal Chrome browser User-Agent in offline installer-managed `offline.env` blocks by default so CloakBrowser-backed AGU/Wiley fetches are less likely to stop at Cloudflare challenge pages.
- Derived MCP status, live review support, and golden corpus representative coverage from provider facts instead of hard-coded provider lists where possible.

## 1.5.6 - 2026-05-18

### Fixed

- Fixed Windows offline installer smoke checks by running bundled Python probes from temporary `.py` files instead of passing multi-line scripts through `python.exe -c`, avoiding PowerShell native-command quote stripping around CloakBrowser checks.

## 1.5.5 - 2026-05-17

### Fixed

- Restored the Wiley full-text waterfall after Cloudflare/challenge HTML failures so browser PDF/ePDF fallback and then the optional Wiley TDM API PDF lane are still attempted before provider-managed metadata-only fallback.
- Kept the AGU/Wiley Cloudflare workaround centered on `PAPER_FETCH_BROWSER_USER_AGENT` with headless CloakBrowser as the usual runtime path.

## 1.5.4 - 2026-05-17

### Changed

- Changed Linux offline release assets from `.tar.gz` bundles to single self-extracting `.sh` installers with `--install-dir <path>` support and the default install root `~/.local/share/paper-fetch-skill`.
- Changed Linux and Windows offline upgrades to clear the old runtime payload before installing the new runtime-only payload while preserving user-authored `offline.env` content and refreshing managed environment, PATH, skill, and MCP registration blocks.
- Changed Linux offline uninstall semantics so `--uninstall` removes only user-level shell/skill/MCP integration and `--purge` explicitly deletes the fixed install directory.

### Fixed

- Prevented the Windows offline installer from aborting after runtime files are installed when optional post-install integration or smoke checks fail on a user machine; warnings are now logged to `install-helper.log`.
- Fixed Linux offline installer CloakBrowser checks and Claude MCP registration arguments for current host CLIs.
- Fixed browser PDF fallback so CloakBrowser/Playwright sync work is handed to a worker thread when the caller is already inside an asyncio loop.

## 1.5.3 - 2026-05-17

### Changed

- Changed the Windows offline installer to package only the embedded runtime, installed packages, command wrappers, static skill, formula tools, and installer metadata, removing the repository source snapshot and build wheelhouse from the installed payload.

## 1.5.2 - 2026-05-17

### Changed

- Changed Linux offline tarballs into preinstalled runtime packages with `bin/` launchers and `runtime/site-packages/`, without the repository source snapshot or target-machine wheelhouse; installation no longer runs pip.

### Fixed

- Prevented Atypon browser HTML routes for Wiley, Science, PNAS, and AMS from treating residual Cloudflare/challenge text as an HTML-route failure once a stable full-text DOM is already present.

## 1.5.1 - 2026-05-17

### Fixed

- Updated browser workflow User-Agent handling so CloakBrowser/Playwright contexts no longer inherit the default `paper-fetch-skill/<version>` HTTP UA unless users explicitly configure a browser UA.
- Added `PAPER_FETCH_BROWSER_USER_AGENT` for browser-only UA overrides while keeping explicit `PAPER_FETCH_SKILL_USER_AGENT` as a compatibility fallback for browser contexts.
- Documented the AGU/Wiley Cloudflare challenge workaround using a normal Chrome browser UA with headless CloakBrowser.

## 1.5 - 2026-05-16

### Added

- Added the CloakBrowser-backed browser runtime abstraction and provider status diagnostics, replacing the FlareSolverr runtime path.
- Added browser image payload and runtime smoke coverage for the migrated browser workflow.

### Changed

- Migrated Science, PNAS, Wiley, AMS, IEEE browser/PDF flows, MCP diagnostics, live runners, installers, offline packages, and CI from FlareSolverr-specific paths to the shared CloakBrowser/browser runtime path.
- Removed bundled FlareSolverr source, setup scripts, vendor patches, docs, and release-package runtime assets; offline packages now ship the `cloakbrowser` Python package and document that the browser binary is not redistributed.
- arXiv HTML asset handling now recovers figure assets from the arXiv e-print source package when official HTML exposes only missing-image placeholders; source PDF figures are rendered to PNG assets and inserted back near their figure captions while full-text extraction remains official-HTML first.
- Browser workflow concurrent asset downloads now use thread-private browser/context/page instances instead of sharing the `RuntimeContext` browser across worker threads.
- Optimized browser workflow fetching, CLI output-directory handling, provider request options, MCP cache payload handling, and fixture/scaffold docs around the new runtime contract.

### Fixed

- Fixed the Windows offline package builder so the MCP command wrapper PowerShell here-string closes correctly before writing `README.offline.md`.
- Suppressed CloakBrowser's first-launch promotional stderr banner during browser-backed fetches.

## 1.4.1 - 2026-05-15

### Added

- Added native CLI batch fetching with `--query-file`, per-item output files, JSONL batch summaries, bounded `--batch-concurrency`, and per-item failure reporting without aborting the whole batch.
- Added dedicated CLI documentation for output routing, artifact modes, asset profiles, `--save-markdown`, and batch-mode behavior.

### Changed

- Release 1.4.1: native batch CLI and provider/MCP refinements.
- Refined CLI output/artifact semantics so batch and single-query runs consistently separate primary output files from saved Markdown and provider artifacts.
- Updated MCP fetch/cache payload behavior for inline image budgets, cache resource visibility, and schema coverage.
- Hardened Elsevier Markdown and Springer HTML extraction around tables, figures, asset rewriting, and provider-specific cleanup.
- Fixed offline installer smoke checks to use the current MCP provider-status entrypoint during Linux and PowerShell installs.
- Refreshed README, provider, deployment, bundled skill, and tool-contract documentation to match the new CLI and MCP/provider behavior.

## 1.4 - 2026-05-12

### Added

- Added the `arxiv` provider for `arxiv.org` and DOI prefix `10.48550/`, publishing `arxiv_html` on official HTML success with text-only PDF fallback as `arxiv_pdf`.
- Added 10 real arXiv replay fixtures: 8 official HTML success samples and 2 official HTML 404 -> real PDF fallback samples, each with arXiv API metadata replay.

### Changed

- Reworked Phase 1 routing/extraction internals: Copernicus URL identity now uses catalog `domain_suffixes`, early metadata probes are driven by `ProviderSpec.probe_capability`, reference-anchor detection is centralized in HTML semantics, Wiley supplementary data attributes are handled by the Wiley extractor, and Science/PNAS figure teaser filtering now receives the actual publisher.
- Centralized provider source ownership, including Springer HTML/PDF source ownership, API-like hosts, Wiley TDM URL template, Springer/Nature domain matching, workflow HTML-managed fallback markers, and body-text thresholds in `ProviderSpec` / `SOURCE_PROVIDER_MAP`.
- Tightened Phase 4 generic extraction boundaries: Springer/Nature citation cleanup patterns now live in the provider layer, provider formula tokens require explicit `ProviderHtmlRules` profile injection, and Research Briefing authorless signatures live with quality signals.
- Completed Phase 4 duplicate-source cleanup: `FRONT_MATTER_PUBLICATION_KEYWORDS` now has one generic source with Science/PNAS publication tokens scoped to provider rules, `SourceKind` is checked against catalog sources at import time, Cloudflare cookie filters share the FlareSolverr constants, and Science reuses the shared AAAS datalayer pattern.
- Centralized Phase 3 HTML availability overrides and access-gate signals through provider rules and shared signal patterns, including Science perspective, Elsevier canonical abstract, and Springer preview-wall body-run handling.
- Hardened Phase 6 provider-specific contracts: IEEE article-number URL parsing now only accepts `/document/{article_number}/` landing paths, Springer/Nature Creative Commons cleanup no longer removes article roots, and HTML asset helpers avoid importing the public models package during package initialization.
- Completed Phase 7 cleanup: generic browser HTML failures are now `HtmlExtractionFailure`, FlareSolverr status probes use a non-DOI sentinel, landing-page redirect resolution has one request-URL-based semantic, and old FlareSolverr rate-limit env cleanup code was removed.
- Moved Atypon browser HTML/PDF candidate templates into `ProviderSpec` and removed the `paper_fetch.providers.science_html`, `paper_fetch.providers.pnas_html`, and `paper_fetch.providers.wiley_html` compatibility facades.
- Completed Phase 5 Atypon/Wiley cleanup: Wiley owns abbreviations and supplementary filename contracts, datalayer signal parsing uses schema field maps, and Atypon browser workflow scope is documented as Science/PNAS/Wiley catalog entries only.
- Golden criteria live review now includes `copernicus` in the supported provider rotation and provider-status diagnostics.
- Documented Phase 8 CI/test policy updates: regular unit/integration jobs and full golden regression continue to use pytest-xdist defaults, while live FlareSolverr/MCP paths document their required serial execution.
- Clarified CLI output semantics: explicit `--format` with `--output-dir` and stdout output now also writes a same-format document copy under `--output-dir`, while `--output` remains the explicit formatted-output file path.
- Golden criteria live review now treats `arxiv` as a supported provider, records arXiv provider status, preserves derived-URL fallback when arXiv API metadata has transient failures, and classifies arXiv asset partial-download diagnostics as `asset_download_failure`.
- arXiv metadata enrichment now uses a small internal Atom API client for ID lookup and no longer depends on the PyPI `arxiv` / `feedparser` dependency chain.
- arXiv HTML asset downloads now use a provider-specific lower concurrency cap and retry network-exception failures once sequentially while preserving non-retryable failures in `quality.asset_failures`.
- arXiv fulltext routing is now fixed to official HTML first with direct text-only PDF fallback; retired local source-conversion fallback code and related asset handling are no longer part of the supported route.
- arXiv official HTML Markdown cleanup now folds ordinary prose hard line breaks, sanitizes nested `$...$` delimiters inside LaTeXML TeX annotations, and lifts full-width table title rows out of GFM pipe table headers.
- Completed Phase 2 callback cleanup: Atypon DOM postprocess and scoped asset extraction are now provider-registered callbacks, and provider display names resolve through the catalog-backed `provider_display_name()` helper.
- Completed Phase 3 catalog field cleanup: Springer/Nature PDF candidates, arXiv metadata probe short-circuiting, provider HTML artifact persistence, XML source inference, provider-managed abstract-only handling, and PDF URL token semantics are now catalog/callback driven instead of provider-name hardcoded.
- Completed Phase 5 Atypon browser workflow rename: the old Science/PNAS package/profile/postprocess names were moved to `atypon_browser_workflow`, the legacy profiles facade was removed, Atypon profile dispatch now dynamically imports provider HTML modules from `ATYPON_BROWSER_WORKFLOW_PROVIDER_NAMES`, shared figure-link and abstract-redirect helpers live in neutral modules, and Science citation-italic repair now belongs to `_science_html.py`.
- Elsevier XML body asset downloads now retry only failed transient network items once sequentially and remove the original asset failure when the retry succeeds.
- Wiley formula image discovery now includes `data-altimg` fallback spans and display formula containers, so image-only formulas can enter the `kind="formula"` asset download path instead of requiring an `<img>` tag.

## 1.3 - 2026-05-09

### Added

- Added the `copernicus` XML-first provider for Copernicus Publications DOI prefix `10.5194/`, publishing `copernicus_xml` on NLM/JATS XML success with text-only PDF fallback as `copernicus_pdf`.
- Added 8 Copernicus XML golden fixtures across ACP, HESS, GMD, TC, ESSD, NHESS, AMT, and BG, plus 4 older Copernicus PDF-fallback golden fixtures whose XML is abstract-level only; live smoke sample coverage remains behind `PAPER_FETCH_RUN_LIVE=1`.
- Hardened Copernicus fallback handling for older articles whose XML only exposes abstract-level content: those XML failures now continue directly to text-only PDF fallback, and PDF discovery includes DOI-derived `.pdf` candidates when the landing page omits PDF metadata.

### Refactor

- Split `paper_fetch.http` from a single module into a package facade plus internal transport, cache, retry, body, and error modules while preserving the existing public import path.
- Move dev-only `geography_live`, `geography_issue_artifacts`, and `golden_criteria_live*` modules from `paper_fetch.*` to source-tree-only `paper_fetch_devtools.*`; wheels no longer ship those modules, while the existing repo-local script CLIs keep the same behavior.

### Changed

- Copernicus XML extraction now reuses the parsed XML root through validation and article assembly, validates usable body paragraphs with a named threshold, and continues with DOI-derived XML/PDF URLs when landing HTML cannot be fetched.
- Copernicus XML assets now use `original_url` as the canonical remote URL while shared asset download mirrors the compatibility URL fields after download; table assets are emitted directly as `kind="table"` with `table_render_kind`.
- Installer completion summaries now explicitly prompt users to request and configure `ELSEVIER_API_KEY` from <https://dev.elsevier.com/> before Elsevier full-text fetching, and point to the relevant `.env` file.
- Windows offline release artifacts now use `paper-fetch-skill-windows-x86_64-setup.exe` and bundle CPython 3.13 x64, Python dependencies, Playwright Chromium, formula tools, the FlareSolverr runtime, Codex / Claude Code skills, and MCP registration helpers.
- GitHub Actions now creates a GitHub Release on `v*` tag pushes or explicit manual releases after regular validation, the full Linux offline package matrix, and the Windows x86_64 setup exe succeed, uploading 4 Linux tarballs plus 1 Windows installer release asset.
- Expanded body-image payload recognition and persistence formats: in addition to PNG/JPEG/GIF/WebP/AVIF/TIFF, SVG text, BMP, ICO, APNG, and HEIC/HEIF MIME/extension mappings are supported; body images are verified for image magic bytes or top-level SVG document signatures before being saved, avoiding challenge HTML being persisted as images.
- Added Science `10.1126/science.adz3492` to the golden fixtures with real SVG body-image assets to guard against Science/PNAS SVG image persistence regressions.
- Added a fast initial FlareSolverr HTML pass for Wiley / Science / PNAS full-text fetching: primary HTML requests use `waitInSeconds=0` and `disableMedia=true`, then automatically fall back to the original conservative wait strategy on challenges, access blocks, abstract redirects, or insufficient body extraction.
- Image recovery, body/supplementary asset downloads, and figure-page HTML discovery continue to use media-enabled paths so `disableMedia` does not block full-size image discovery or downloads.
- Consolidated duplicate implementations for HTML availability/container handling, section hints, browser-workflow Markdown profiles, author fallback, Crossref resolve forwarding, and HTML heading/table helpers; canonical owners are now `quality.html_availability`, `extraction.section_hints` / `extraction.html.semantics`, `ProviderBrowserProfile` / `_html_authors.py`, and `metadata.crossref`.
- Clarified that the shared Science / PNAS / Wiley browser extraction is an Atypon-only profile, and consolidated asset scope, Wiley abbreviations, Wiley author noise, supplementary URL/filename rules, and AAAS/PNAS/Wiley datalayer detection into provider-owned callbacks/schemas.
- Moved the HTML asset canonical owner to the `paper_fetch.extraction.html.assets` package, removed the `paper_fetch.extraction.html._assets` and `paper_fetch.providers.html_assets` compatibility facades, and made download hooks patch from the extraction asset package or `paper_fetch.extraction.html.assets.download`.
- Materialized `paper_fetch.models` as a package split by schema, markdown, tokens, quality, render, sections, and builders while keeping `from paper_fetch.models import ...` compatible.
- Materialized the Science/PNAS browser-workflow HTML implementation as the `paper_fetch.providers.science_pnas` package, removed the `paper_fetch.providers._science_pnas_html` compatibility facade, and extracted the provider HTML asset policy engine plus Playwright document fetcher base class.

## 1.0.0 - 2026-04-26

### Changed

- Released the package as `1.0.0` and updated the default `paper-fetch-skill/1.0` User-Agent.
- Hardened Wiley / Science / PNAS seeded Playwright image fetching so Cloudflare challenge pages and non-image responses fail quickly instead of stalling a live review.
- Reordered the Wiley full-text waterfall so browser PDF/ePDF fallback now runs before the optional TDM API PDF lane whenever the local browser runtime is ready, keeping `wiley_browser` as the default successful route.
- Added `code_availability` as a first-class section kind. Elsevier, Springer / Nature, Wiley, Science, and PNAS now share data/code/software availability classification, retain those sections in final Markdown/ArticleModel output, and exclude them from body sufficiency metrics.

### Docs

- Documented the short-timeout behavior for seeded Playwright image fetches in the FlareSolverr workflow notes.
- Documented the unified data/code availability retention and quality-metric exclusion rules.

### Validation

- `PYTHONPATH=src python3 -m pytest tests/unit/test_provider_request_options.py`
- `PYTHONPATH=src python3 -m pytest tests/unit/test_science_pnas_provider.py -k 'download_related_assets or image'`
- Live smoke: Wiley `10.1111/gcb.16414`, Science `10.1126/science.ady3136`, and PNAS `10.1073/pnas.2406303121` produced full-text Markdown with full-size body images using the WSLg FlareSolverr preset.

## 2026-04-25

### Changed

- Promoted the Wiley / Science / PNAS browser workflow runtime to [`src/paper_fetch/providers/browser_workflow.py`](src/paper_fetch/providers/browser_workflow.py). Science, PNAS, and Wiley now declare `ProviderBrowserProfile` objects for URL candidates, Markdown extraction, author fallback, public source, labels, and browser asset behavior; `_science_pnas.py` remains a compatibility alias.
- Promoted the Wiley / Science / PNAS HTML asset downloader to a shared Playwright primary path. Figure, table, and formula image candidates now reuse one seeded browser context per download attempt instead of trying direct HTTP first.
- Kept full-size/original candidates ahead of preview candidates, but now fetches both tiers through the same shared browser context. Target-provider downloads report `download_tier="full_size"` or `download_tier="preview"` rather than `playwright_canvas_fallback`.
- Tightened the browser-workflow image recovery path: repeated figure-page / image-candidate URLs are cached per attempt, body-image payload downloads now use fixed limited parallelism with stable output ordering, and FlareSolverr recovery no longer falls back to screenshot cropping when `solution.imagePayload` is missing or invalid.
- Preserved the FlareSolverr seed refresh retry for partial asset failures, while keeping the generic HTTP-first asset downloader unchanged for non-target providers such as Springer.
- Expanded HTML formula handling so Wiley, Science / PNAS shared HTML, and Springer / Nature paths preserve MathML when possible and retain formula image fallbacks as `![Formula](...)` assets when MathML is absent or unusable.
- Normalized final Markdown after asset-link rewrites so downloaded figure / table / formula links replace remote URLs before section parsing, block images are separated from adjacent headings/text/math fences, and empty body parent headings remain visible.
- Hardened structured metadata and references: front matter unescapes HTML entities, Elsevier XML references no longer skip sparse bibliography entries, and Wiley / Springer-style HTML references remove link chrome while preferring visible citation text over DOI-only snippets.
- Tightened Springer / Nature HTML cleanup by pruning more article chrome and license sections, preserving scientific back matter outside the main body, extracting formula image assets, and emitting explicit table-body-unavailable placeholders when table-page parsing fails.
- Adjusted golden-criteria live issue classification so formula-only preview fallback is not treated as an asset-download failure, while non-formula preview fallback still remains an asset issue unless explicitly accepted.

### Docs

- Updated README, provider, FlareSolverr, extraction-rule, deployment, architecture, and schema notes to describe the shared Playwright primary asset path, formula image preservation, Markdown asset-link rewrites, reference fallback behavior, and target-provider `download_tier` semantics.

### Validation

- `pytest tests/unit/test_science_pnas_provider.py tests/unit/test_provider_waterfalls.py tests/unit/test_provider_request_options.py tests/unit/test_html_shared_helpers.py -q`
- `pytest tests/unit/test_elsevier_markdown.py tests/unit/test_golden_criteria_live.py tests/unit/test_models_render.py tests/unit/test_science_pnas_markdown.py tests/unit/test_springer_html_regressions.py -q`
- Live smoke: Wiley `10.1111/gcb.16455` downloaded 5/5 full-size body figures, Science `10.1126/science.ady3136` downloaded 6/6 full-size body figures, and PNAS `10.1073/pnas.2406303121` downloaded 4/4 full-size body figures; all local files had image magic bytes, dimensions, and Markdown links rewritten to local paths.

## 2026-04-19

### Changed

- Moved shared HTML full-text diagnostics into [`src/paper_fetch/providers/_html_availability.py`](src/paper_fetch/providers/_html_availability.py) and switched `html_generic`, `elsevier`, `springer`, FlareSolverr, and PDF fallback helpers to import the shared availability/access-signal layers directly instead of reaching through `_science_pnas_html.py`.
- Added internal `PublisherProfile` plumbing in [`src/paper_fetch/providers/_science_pnas_profiles.py`](src/paper_fetch/providers/_science_pnas_profiles.py) so browser-workflow candidate builders, noise-profile selection, and provider-specific postprocess hooks live outside `_science_pnas_html.py`.
- Removed the `_article_markdown_document.py` compatibility wrapper; direct Elsevier document assembly now lives only in [`src/paper_fetch/providers/_article_markdown_elsevier_document.py`](src/paper_fetch/providers/_article_markdown_elsevier_document.py), while [`src/paper_fetch/providers/_article_markdown.py`](src/paper_fetch/providers/_article_markdown.py) remains the intentional aggregate entrypoint.
- Split the oversized `tests/unit/test_science_pnas_html.py` coverage into focused candidate, availability, markdown, and postprocess test files, while keeping `detect_html_block()` coverage in `tests/unit/test_html_access_signals.py`.
- Promoted the geography report/export/group scripts plus their supporting modules and tests into tracked repo-local internal tooling without adding new CLI install surfaces or MCP tools.

### Docs

- Updated README, provider docs, and backlog notes to describe geography report/export/group as live-only internal tooling behind `PAPER_FETCH_RUN_LIVE=1`.

### Validation

- `pytest tests/unit/test_science_pnas_candidates.py tests/unit/test_html_availability.py tests/unit/test_science_pnas_markdown.py tests/unit/test_science_pnas_postprocess.py tests/unit/test_html_access_signals.py tests/unit/test_elsevier_markdown.py -q`
- `pytest tests/unit/test_geography_live.py tests/unit/test_geography_issue_artifacts.py -q`
- `python3 scripts/run_geography_live_report.py --help`
- `python3 scripts/export_geography_issue_artifacts.py --help`
- `python3 scripts/group_geography_issue_artifacts.py --help`

## 2026-04-16

### Added

- Added a public `provider_status()` MCP tool that reports stable local diagnostics for `crossref`, `elsevier`, `springer`, `wiley`, `science`, and `pnas` without probing remote publisher APIs.
- Added provider-level status probing with stable `ready` / `partial` / `not_configured` / `rate_limited` / `error` semantics plus per-provider `checks=[...]` details.
- Added MCP `resources/list_changed` support for cache resources when `fetch_paper()`, `list_cached()`, or `get_cached()` changes the visible cache-resource URI set for the current session.

### Changed

- Changed all 8 public MCP tools to expose `ToolAnnotations`; read-only tools now advertise `readOnlyHint=true`, while `fetch_paper` stays writable because it may refresh local cache files.
- Changed Science / PNAS local diagnostics so MCP can inspect FlareSolverr runtime readiness and local rate-limit windows without mutating the rate-limit tracking file.
- Changed `batch_resolve()` and `batch_check()` to reject requests with more than `50` queries instead of attempting oversized batch runs.
- Changed MCP initialization so the server now advertises `capabilities.resources.listChanged=true` across supported transports.

### Docs

- Updated README, deployment docs, provider docs, and the bundled skill guide to document `provider_status()` and the new MCP tool-annotation hints.
- Updated README, deployment docs, and the bundled skill guide to document the `50`-query batch limit and the new cache-resource list-change notifications.

## 2026-04-15

### Added

- Added a dedicated `has_fulltext(query)` MCP probe tool with cheap Crossref, provider-metadata, and landing-page HTML-meta signals.
- Added JSON output schemas for all 7 public MCP tools so schema-aware clients can validate tool results and surface stronger autocomplete.
- Added `fetch_paper(..., prefer_cache=true)` cache-first short-circuiting backed by an MCP-local cached FetchEnvelope sidecar.
- Added `missing_env=[...]` on MCP error payloads when missing credentials or required environment variables can be identified.
- Added two MCP prompt templates, `summarize_paper(query, focus)` and `verify_citation_list(citations, mode)`, for cache-first paper summaries and batch-first citation-list triage.
- Added `token_estimate_breakdown={abstract,body,refs}` to `fetch_paper` results, `article.quality`, and `batch_check(mode="article")` item payloads.

### Changed

- Changed `batch_check(mode="metadata")` to reuse the cheap probe path instead of running the full fetch waterfall.
- Changed the bundled skill layout to a thin `SKILL.md` entrypoint plus `references/` docs for environment variables, CLI fallback, and failure handling.
- Changed `batch_resolve` and `batch_check` to accept optional `concurrency`, allowing cross-host overlap while the shared HTTP transport still serializes same-host requests.
- Changed long-running MCP `fetch_paper` and `batch_*` tool calls to observe cancellation cooperatively so cancelled requests stop issuing follow-up network work.
- Changed MCP cache resources so explicit non-default `download_dir` values also register scoped cache-index and cached-entry resources for the current server session.
- Changed MCP `fetch_paper.strategy` to accept optional `inline_image_budget` controls for inline `ImageContent` limits without changing service-layer fetch behavior or cache eligibility.
- Changed `token_estimate` semantics to remain backward compatible as `abstract + body`, while the new `refs` budget now lives only in `token_estimate_breakdown`.
- Changed MCP cached FetchEnvelope sidecar loading to backfill missing token-breakdown fields when reading older cache entries that predate the new contract.

### Docs

- Updated README, deployment docs, the skill guide, and the probe-semantics note to document the shipped `has_fulltext` v1 behavior and the new `batch_check(mode="metadata")` semantics.
- Updated the static skill installer and architecture docs to treat `skills/paper-fetch-skill/` as a runtime-agnostic bundle that can include on-demand `references/` files.
- Updated MCP-facing docs to describe the new `concurrency` parameter and the "cross-host concurrent, same-host serial" behavior of `batch_*`.
- Updated the MCP-facing docs and skill notes to describe cooperative cancellation for `fetch_paper` and `batch_*`.
- Updated README, deployment docs, and MCP instruction text to document scoped cache resources for explicit isolated download directories.
- Updated README, deployment docs, skill notes, and MCP instruction text to document `strategy.inline_image_budget` and its default `3 / 2 MiB / 8 MiB` inline-image caps.
- Updated README, deployment docs, and the bundled skill guide to document the two published MCP prompts and the new `token_estimate_breakdown` budgeting hint.

## 2026-04-14

### Added

- Added public `science` and `pnas` provider routes, including direct `provider_hint`, `preferred_providers`, and final `source` support.
- Added repo-local Science / PNAS provider implementations in [`src/paper_fetch/providers/science.py`](src/paper_fetch/providers/science.py) and [`src/paper_fetch/providers/pnas.py`](src/paper_fetch/providers/pnas.py), backed by shared FlareSolverr, HTML cleanup, and Playwright PDF-fallback helpers.
- Added repo-local `vendor/flaresolverr/` workflow assets, thin wrapper scripts under [`scripts/`](scripts), and a dedicated operator guide in [`docs/flaresolverr.md`](docs/flaresolverr.md).
- Added offline Science / PNAS fixtures plus unit coverage for routing, FlareSolverr error handling, provider fallbacks, and public result provenance.
- Added opt-in live smoke coverage for one Science HTML DOI and one PNAS PDF-fallback DOI behind the existing `PAPER_FETCH_RUN_LIVE=1` gate.

### Changed

- Extended `SourceKind` and the service provider registry so `science` and `pnas` are first-class public provenance values instead of envelope-only aliases.
- Made Science / PNAS use a provider-managed `HTML first -> PDF fallback -> metadata-only fallback` chain, while explicitly skipping the generic `html_generic` fallback after those providers are selected.
- Moved Science / PNAS HTML extraction onto provider-specific cleanup rules, then fed the cleaned HTML back through the existing HTML-to-Markdown pipeline for final rendering.
- Added explicit repo-local runtime checks for `vendor/flaresolverr`, `FLARESOLVERR_ENV_FILE`, local FlareSolverr health, and required local rate-limit settings before Science / PNAS full-text retrieval proceeds.
- Added local Science / PNAS rate-limit accounting in the user data directory and kept `asset_profile=body|all` on those routes as text-only downgrades with warnings instead of hard failures.
- Expanded `install-formula-tools.sh` so repo-local development can bootstrap FlareSolverr source setup, Playwright Chromium, and headless `Xvfb` prerequisites from one entrypoint.

### Docs

- Updated README, deployment guidance, provider docs, MCP instruction snippets, and FlareSolverr workflow docs to describe the new Science / PNAS route, repo-local-only support boundary, required environment variables, and operator-owned ToS risk.

### Validation

- `python3 -m compileall src/paper_fetch`
- `ruff check src/paper_fetch tests/unit`
- `PYTHONPATH=src python3 -m unittest -q tests.unit.test_publisher_identity tests.unit.test_resolve_query tests.unit.test_science_pnas_html tests.unit.test_science_pnas_flaresolverr tests.unit.test_science_pnas_provider tests.unit.test_service`

## 2026-04-13

### Added

- Added MCP cache indexing with `list_cached()` / `get_cached()` plus `resource://paper-fetch/cache-index` and `resource://paper-fetch/cached/{entry_id}` resources for the default shared download directory.
- Added `batch_resolve(queries)` and `batch_check(queries, mode)` MCP tools so citation-list workflows can stay serial, transport-reusing, and context-light.
- Added canonical MCP/skill-facing instruction helpers in [`src/paper_fetch/mcp/_instructions.py`](src/paper_fetch/mcp/_instructions.py) to keep defaults, environment notes, and error-contract wording aligned.
- Added inline `ImageContent` support for a few local body figures when `strategy.asset_profile` is `body` or `all`.
- Added structured MCP progress updates and structured log notifications for `fetch_paper`, `batch_check`, and `batch_resolve`.
- Added live MCP end-to-end smoke coverage for representative Elsevier and HTML-fallback flows.
- Added a probe-semantics design note in [`docs/architecture/probe-semantics.md`](docs/architecture/probe-semantics.md) to define the future `has_fulltext(query)` direction.

### Changed

- Moved public change history and shipped-surface notes out of ad hoc backlog docs into this changelog.
- Exposed `download_dir` on the MCP `fetch_paper` surface so task-local directories can override `PAPER_FETCH_DOWNLOAD_DIR` and XDG defaults.
- Expanded MCP `resolve_paper` to accept either a raw `query` or structured `title` plus optional `authors` / `year`.
- Updated the static skill to document the real defaults, the environment variables that affect behavior, the error contract, cache-first call discipline, and the batch-first bibliography workflow.
- Clarified that `include_refs=null` behaves like `all` for `max_tokens="full_text"` and like `top10` for numeric token budgets.
- Reworked the skill frontmatter into a shorter trigger-style description and moved call-discipline guidance ahead of the main workflow.
- Shifted provider routing toward Crossref/domain-first hints with DOI-prefix fallback only when needed, and added route diagnostics to `source_trail`.
- Unified text-normalization, DOI extraction, metadata merge helpers, and HTML lookup heuristics around shared utilities to reduce duplicate logic.
- Split large renderer and HTML modules into thinner facades backed by focused helpers while preserving public compatibility entrypoints.
- Refined CLI exit codes, Markdown asset-link handling, render budgeting, and token-estimation internals without changing the public fetch contract.

### Fixed

- Protected in-process HTTP GET caching with `threading.RLock`.
- Switched the HTTP transport to `urllib3.PoolManager` for connection reuse without changing the public request contract.
- Added response-size guards, gzip pre-decompression size checks, cache-budget eviction, and safer retry behavior for timeout/transient errors.
- Converted payload and asset writes to atomic `.part -> replace` flows so failed writes do not corrupt final files.
- Tightened exception handling so programming errors are no longer silently downgraded into partial-download or fallback paths.
- Prevented `batch_check()` from writing payloads to disk by forcing `download_dir=None`.
- Preserved top-level fetch provenance fields even when `article`, `markdown`, or `metadata` are unrequested and therefore returned as `null`.

### Docs

- Kept architecture rationale in [`docs/architecture/overview.md`](docs/architecture/overview.md) and moved shipped changes to this file.
- Updated deployment, provider, MCP, and skill-facing documentation to match the landed MCP surface and environment behavior.

### Validation

- `ruff check .`
- `PYTHONPATH=src python3 -m pytest tests/unit tests/integration -q`
- `PYTHONPATH=src python3 -m pytest -n 0 tests/live/test_live_mcp.py -q` skips cleanly when live env is not enabled; `-n 0` is required because live MCP shares external publisher/API state and secrets.

### Follow-up

- The dedicated MCP probe tool `has_fulltext(query)` is intentionally not shipped yet; only its semantics note is landed in [`docs/architecture/probe-semantics.md`](docs/architecture/probe-semantics.md).
