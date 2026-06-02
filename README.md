# DraftPaper Commercial

`Private Commercial Edition` `AI Research Workflow` `Local-first` `Python CLI` `LaTeX Drafting` `Data Analysis` `Results Analysis`

This repository contains the private commercial implementation of DraftPaper. Do not publish this repository or mirror its implementation details into the public open-source repository.

The commercial edition keeps the full staged workflow, including local data analysis processing, methods hard gates, result validity checks, results writing, LaTeX assembly, Codex skill orchestration, and quality gate logic. The public repository should expose only the literature analysis and validation layer used for product demonstration and lead generation.

[中文](README.zh-CN.md) | English

DraftPaper CLI is a local-first research paper workflow engine. It turns a research idea, local data, verified method code, result artifacts, and traceable literature evidence into a staged LaTeX manuscript draft. The core is a Python package plus CLI; Codex skills, desktop UI, Web UI, and future API/SaaS layers should call the same core workflow rather than reimplementing it.

## What It Does

DraftPaper CLI organizes one paper as one local project directory and advances it through explicit stages: project creation, literature search, journal template profiling, research planning, Introduction, Data, Methods, Results, Discussion, LaTeX assembly, PDF review, and quality gates.

The reference workflow uses free literature providers first, including Semantic Scholar, arXiv, Crossref, and optional SerpApi. It writes BibTeX, citation evidence, literature notes, HTML paper summaries, and context-aware evidence for Introduction, Data, and Methods. When data or method references lack readable abstract evidence, DraftPaper can call the vendored `paper-fetch-skill` runtime through `paper_fetch_adapter.py` to fetch full-text Markdown/JSON evidence.

## Key Features

- Single-paper local project model with staged manifests.
- State machine commands for rerun, stale-stage tracking, and validation.
- Context-aware literature retrieval for `idea`, `data`, and `methods`.
- Traceable `citation_evidence.csv` for auditable manuscript claims.
- Journal profile stage for target-journal LaTeX constraints.
- Methods hard gate requiring successful local code execution.
- Result validity gate before Results writing.
- Results no-citation enforcement.
- LaTeX assembly with optional local PDF compilation.
- Quality gate for citations, result artifacts, stale stages, and journal template checks.
- Codex skill wrapper that remains only a calling layer.

## Public Scope

This public repository is an implementation-oriented CLI foundation. It intentionally keeps product strategy, prompt recipes, commercial orchestration details, and discipline-specific writing heuristics out of the README. Those should live in private deployment notes or a commercial wrapper repository.

## Project Layout

```text
draftpaper_cli/                 # Core Python package and CLI stages
codex_skills/draftpaper-workflow # Optional Codex skill wrapper
docs/                           # Workflow design and priority guide
tests/                          # Unit tests
third_party/paper-fetch-skill/   # Vendored MIT paper-fetch runtime
github_submit/                  # GitHub submission package and notes
```

Generated paper projects are stored under `projects/` locally and are intentionally ignored by git to avoid uploading research data, generated drafts, full-text paper caches, and result artifacts.

## Quick Start

```powershell
python -m pip install -e .
python -m draftpaper_cli.cli create-project --root C:\DraftPaper_CLI\projects --idea "Your research idea" --field "machine learning astronomy" --target-journal APJS
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\your_project --query "topic keywords"
python -m draftpaper_cli.cli validate-project --project C:\DraftPaper_CLI\projects\your_project
```

Run tests:

```powershell
python -m unittest discover -s tests
```

## Paper Fetch Integration

This repository vendors [`Dictation354/paper-fetch-skill`](https://github.com/Dictation354/paper-fetch-skill) under `third_party/paper-fetch-skill`. The adapter prefers a `paper-fetch` command on `PATH`; if unavailable, it can use the vendored runtime source. For a clean environment:

```powershell
python -m pip install -e third_party\paper-fetch-skill
```

The third-party runtime is MIT licensed. Keep its license notice when redistributing.

## License

DraftPaper CLI is released under the MIT License. Third-party components keep their own licenses.
