# DraftPaper Commercial

[![AI Research Workflow](https://img.shields.io/badge/AI-Research%20Workflow-5C4D7D?style=flat-square)](#)
[![Literature Analysis](https://img.shields.io/badge/Literature-Analysis-1D7874?style=flat-square)](#)
[![Citation Evidence](https://img.shields.io/badge/Citation-Evidence-4C956C?style=flat-square)](#)
[![BibTeX](https://img.shields.io/badge/BibTeX-Reference%20Library-3A506B?style=flat-square)](#)
[![Local First](https://img.shields.io/badge/Local-First-E07A5F?style=flat-square)](#)
[![Python CLI](https://img.shields.io/badge/Python-CLI-3776AB?style=flat-square&logo=python&logoColor=white)](./pyproject.toml)
[![Open Core](https://img.shields.io/badge/Open--core-Public%20Literature%20Layer-8A5A44?style=flat-square)](#)

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
- Independent integrity gate for BibTeX existence, citation evidence, and result artifact binding.
- Review-revise-re-review loop with gate-failure routing and commitment ledger.
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

### Use Through Codex

The intended product workflow is to let Codex read this repository and call the DraftPaper CLI for you. After cloning the repository locally, open or point Codex to the repository directory and ask in natural language, for example:

```text
Use the DraftPaper CLI in C:\Draftpaper_commercial to create a paper project for this idea, search literature, write the research plan, and tell me which stages are blocked.
```

Codex should then run the appropriate CLI commands, inspect the generated local project files, and report the next stage. The raw `draftpaper` commands below are the underlying interface for debugging, automation, and non-Codex use; they are not meant to replace normal conversation with Codex.

For staged work, Codex should first call the orchestrator layer:

```powershell
python -m draftpaper_cli.cli status --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli detect-artifact-drift --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli sync-artifact-stale --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-integrity-gate --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli diagnose-gate-failures --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli generate-revision-plan --project C:\DraftPaper_CLI\projects\your_project
```

### One-Command Local Setup

Run this from the directory where you want to place the repository. The command clones the private repository, creates a local virtual environment, installs DraftPaper CLI, and prints the CLI help. The paper-fetch runtime is vendored in `third_party/paper-fetch-skill`; install it separately only when full-text fetching is needed.

```powershell
powershell -ExecutionPolicy Bypass -Command "git clone https://github.com/xiejhhhhhh/Draftpaper_commercial.git; cd Draftpaper_commercial; py -3 -m venv .venv; .\.venv\Scripts\python -m pip install -U pip; .\.venv\Scripts\python -m pip install -e .; .\.venv\Scripts\draftpaper --help"
```

Optional full-text fetch runtime:

```powershell
.\.venv\Scripts\python -m pip install -e third_party\paper-fetch-skill
```

After setup, the installed `draftpaper` command can be used from the repository root:

```powershell
.\.venv\Scripts\draftpaper create-project --root .\projects --idea "Your research idea" --field "machine learning astronomy" --target-journal APJS
.\.venv\Scripts\draftpaper status --project .\projects\your_project
.\.venv\Scripts\draftpaper run-pipeline --project .\projects\your_project
.\.venv\Scripts\draftpaper search-literature --project .\projects\your_project --query "topic keywords"
.\.venv\Scripts\draftpaper validate-project --project .\projects\your_project
```

For a quick local smoke test without live literature search, create and validate a project:

```powershell
.\.venv\Scripts\draftpaper create-project --root .\projects --idea "X-ray flaring source classification" --field "machine learning astronomy" --target-journal APJS
.\.venv\Scripts\draftpaper validate-project --project .\projects\x-ray-flaring-source-classification
```

### Editable Install

```powershell
python -m pip install -e .
python -m draftpaper_cli.cli create-project --root C:\DraftPaper_CLI\projects --idea "Your research idea" --field "machine learning astronomy" --target-journal APJS
python -m draftpaper_cli.cli status --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\your_project --query "topic keywords"
python -m draftpaper_cli.cli generate-analysis-code --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-integrity-gate --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli validate-project --project C:\DraftPaper_CLI\projects\your_project
```

Run tests:

```powershell
python -m unittest discover -s tests
```

## Implementation Status

The CLI already includes an orchestrator layer (`status`, `checkpoint`, `resume`, `run-pipeline`) plus hash-based stale synchronization (`detect-artifact-drift`, `sync-artifact-stale`) and staged commands for project state, literature search, journal profile resolution, research plan generation, Introduction, data inventory and feasibility checks, method-plan collection, literature-informed baseline analysis-code generation, method execution verification, Methods writing, result validity checks, result inventory, Results writing, Discussion, LaTeX assembly, PDF compilation, independent integrity checks, review/revision routing, and final quality checks.

Every project now carries a DraftPaper Passport at `project_passport.yaml` plus append-only `artifact_ledger.jsonl`, `checkpoint_ledger.jsonl`, and `integrity_ledger.jsonl`. These files record project artifacts, hashes, explicit user checkpoints, and integrity events so the project can be moved across machines and later audited without relying on Codex conversation memory.

When a tracked artifact hash changes, `status` reports `pipeline_state=drift_detected` and recommends `sync-artifact-stale`. That command maps changed artifact paths back to their source stages, marks downstream dependent stages stale, records the drift in `integrity_ledger.jsonl`, and refreshes the passport hash baseline.

`generate-analysis-code` reads retrieved literature, `methods/method_requirements.json`, `methods/method_plan.md`, and `data/data_inventory.json`, then writes reviewable project-local Python code under `code/` plus `methods/analysis_code_manifest.json`. The generated baseline now produces two tables and four required SVG figures by default: data analysis workflow, data processing workflow, method analysis workflow, and data-to-method output workflow. It is intentionally a reproducible scaffold rather than a final scientific model; `verify-methods` must still run the generated command, record `methods/run_manifest.yaml`, and block Methods writing until every declared output exists. `inventory-results` then converts the verified figures and tables into `results/result_manifest.yaml`, and `write-results` writes citation-free result paragraphs from that manifest.

`run-integrity-gate` writes `integrity/integrity_report.json` and `integrity/integrity_report.md`, then appends an `integrity_gate` event to `integrity_ledger.jsonl`. It checks that manuscript citations exist in BibTeX, that Introduction/Data/Methods/Discussion citations are traceable to `references/citation_evidence.csv`, that Results contains no citation commands, and that every result claim in `results/result_manifest.yaml` is bound to an existing local figure or table. When the project reaches `quality_checks`, `status` and `run-pipeline` recommend `run-integrity-gate` before final `quality-check` until the integrity report has passed.

`diagnose-gate-failures`, `review-draft`, `generate-revision-plan`, `apply-revision`, and `re-review` implement the review-revise-re-review loop. Gate failures are converted into unified revision issues with target stages, files to inspect, required user decisions, and recommended CLI reruns. The reviewer layer adds a conservative manuscript-level pass, while `apply-revision` only marks affected stages stale; it does not rewrite scientific content without user confirmation.

## Paper Fetch Integration

This repository vendors [`Dictation354/paper-fetch-skill`](https://github.com/Dictation354/paper-fetch-skill) under `third_party/paper-fetch-skill`. The adapter prefers a `paper-fetch` command on `PATH`; if unavailable, it can use the vendored runtime source. For a clean environment:

```powershell
python -m pip install -e third_party\paper-fetch-skill
```

The third-party runtime is MIT licensed. Keep its license notice when redistributing.

## License

DraftPaper CLI is released under the MIT License. Third-party components keep their own licenses.
