---
name: draftpaper-workflow
description: Use when a user wants Codex to operate DraftPaper CLI projects, staged research-paper workflows, LaTeX drafts, citation evidence, results manifests, quality gates, or local review PDFs.
---

# DraftPaper Workflow

Use this skill as a thin Codex calling layer for `C:\DraftPaper_CLI`. The core capability is the Python package, CLI, and local project directory model. Codex must translate user intent into CLI calls and explain results; it must not reimplement workflow logic.

## Boundary

Do not directly edit project.json. Do not directly edit stage_manifest files. Do not generate paper sections by bypassing the CLI. Do not patch references, status, or LaTeX assembly metadata by hand unless the user explicitly asks for manual repair after a failed command.

Use:

```powershell
python -m draftpaper_cli.cli <command>
```

Read `references/commands.md` when exact command syntax is needed.

## Stage Order

Run stages in this order unless the user asks for a focused rerun:

1. `create-project`
2. `search-literature`
3. `resolve-journal-template`
4. `generate-plan`
5. `write-introduction`
6. `inventory-data`
7. `assess-data-quality`
8. `assess-data-feasibility`
9. `collect-method-plan`
10. `verify-methods`
11. `write-methods`
12. `assess-result-validity`
13. `inventory-results`
14. `write-results`
15. `write-discussion`
16. `assemble-latex`
17. `quality-check`

Use `assemble-latex --compile-pdf` when the user wants a local review PDF. Use `compile-latex-pdf` after manual edits under `latex/`.

## Rerun Rules

If references change, rerun `generate-plan`, `write-introduction`, `write-discussion`, `assemble-latex`, and `quality-check`.

If journal profile or target template changes, rerun `generate-plan`, all writing stages, `assemble-latex`, and `quality-check`.

If research plan changes, rerun `write-introduction`, `inventory-data`, `assess-data-quality`, `assess-data-feasibility`, `collect-method-plan`, affected method work, `write-methods`, `assess-result-validity`, `write-results`, `write-discussion`, `assemble-latex`, and `quality-check`.

If data changes, rerun `inventory-data`, `assess-data-quality`, `assess-data-feasibility`, `collect-method-plan`, `verify-methods`, `write-methods`, `assess-result-validity`, `inventory-results`, `write-results`, `write-discussion`, `assemble-latex`, and `quality-check`.

If method plan or methods code changes, rerun `collect-method-plan` when needed, `verify-methods`, `write-methods`, `assess-result-validity`, `inventory-results`, `write-results`, `write-discussion`, `assemble-latex`, and `quality-check`.

If results change, rerun `assess-result-validity`, `inventory-results`, `write-results`, `write-discussion`, `assemble-latex`, and `quality-check`.

If only LaTeX template files change, rerun `assemble-latex` and `quality-check`.

## Gates

Never generate the research plan or writing stages before `resolve-journal-template` has produced a current journal profile. If `generate-plan` returns `blocked_high_similarity`, stop and report the similar paper warning; rerun with `--allow-high-similarity` only after the user explicitly chooses to continue. Never verify or write Methods before `assess-data-feasibility` returns `pass` or `conditional_pass` and `collect-method-plan` has produced method requirements. If data feasibility returns `revise_required` or `blocked`, stop and report whether the user should add data, lower claim strength, revise the research question, or abandon the current paper plan. Never write Results before `assess-result-validity` returns `pass` or `conditional_pass`. If result validity fails, report whether the likely backtracking target is data, method, or research plan. Results must contain no citation commands. Discussion may cite literature, but citation keys must come from BibTeX and citation evidence. Data and Methods citation evidence is context-specific: if `citation_evidence.csv` contains `section=data` or `section=methods`, the matching manuscript section should cite at least one corresponding key or `quality-check` will report a context-reference warning. Always run `quality-check` before telling the user a draft package is ready.

## Skill Reuse

Before building new data-analysis or method-code workflows, search for existing reusable skills or GitHub skill repositories. Reuse or install a suitable skill before creating a new one. If a new reusable workflow is created during implementation, summarize it as a future skill candidate with inputs, commands, outputs, validation checks, and failure modes. For PDF or full-text literature fetching, prefer the GitHub skill `Dictation354/paper-fetch-skill` when that need arises; install it with the system `skill-installer` flow and tell the user to restart Codex.

## Reporting

Report command status, important output paths, and the next actionable stage. If a command fails, summarize the error JSON and suggest the smallest upstream rerun instead of editing state files manually.
