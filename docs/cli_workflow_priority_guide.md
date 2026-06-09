# DraftPaper CLI Workflow Priority Guide

This guide is the planning reference for turning the existing `D:\DraftAI_agent` MVP into a callable, local-first paper-writing workflow. The MVP already contains reusable literature search, Zotero, BibTeX, LaTeX, PDF, prompt, and quality-gate utilities. Before adding new logic in this CLI project, check whether `D:\DraftAI_agent` already has a reusable implementation.

## Product Direction

Build a portable local research-paper production system first. Codex skills, a web UI, or a future commercial SaaS should call the same core Python package and CLI rather than embedding the workflow directly in Codex.

Recommended architecture:

```text
Core Python package + CLI
Codex skills wrapper
Local Web UI wrapper
Future SaaS/API wrapper
```

## Priority A/B Foundation: Orchestrator and DraftPaper Passport

The workflow now has a thin orchestrator layer above the individual stage commands. The orchestrator does not write paper content; it inspects project state, passport state, stage manifests, and append-only ledgers, then reports the next safe CLI action.

Implemented orchestrator commands:

```powershell
python -m draftpaper_cli.cli status --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli run-pipeline --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli checkpoint --project C:\DraftPaper_CLI\projects\my_project --stage research_plan --note "User approved the research plan"
python -m draftpaper_cli.cli resume --project C:\DraftPaper_CLI\projects\my_project --checkpoint-hash abc123def456
```

Each project also carries a DraftPaper Passport:

```text
project_passport.yaml
artifact_ledger.jsonl
checkpoint_ledger.jsonl
integrity_ledger.jsonl
```

`project_passport.yaml` is JSON-compatible YAML so the core package does not need a YAML runtime dependency. It stores the current project snapshot, artifact hashes, current pipeline state, and the latest unconsumed checkpoint. The ledgers are append-only JSONL files. They must be changed only through CLI commands, not by hand.

This foundation is the portable state layer for Codex skills, Web UI, desktop UI, and future API/SaaS wrappers. Wrapper layers should call `status` or `run-pipeline` first, then call the stage command suggested by the orchestrator.

## Priority C: Hash-Based Stale and Backtracking

The workflow should not rely only on manually maintained `stale` flags. DraftPaper now compares current artifact hashes against the last `project_passport.yaml` snapshot before planning the next stage.

Implemented Priority C CLI commands:

```powershell
python -m draftpaper_cli.cli detect-artifact-drift --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli sync-artifact-stale --project C:\DraftPaper_CLI\projects\my_project
```

`detect-artifact-drift` is read-only. It reports changed, missing, or newly tracked artifacts and maps each path back to a source stage. `sync-artifact-stale` is mutating. It marks downstream dependent stages stale, appends an `artifact_drift` event to `integrity_ledger.jsonl`, and refreshes the passport hash baseline. `status` and `run-pipeline` surface `pipeline_state=drift_detected` before continuing, so Codex/Web/Desktop wrappers should run `sync-artifact-stale` first whenever drift is reported.

## Priority D: Integrity Gate Before Final Quality

The workflow now has an independent integrity gate between LaTeX assembly and the final quality gate. This gate is narrower than `quality-check`: it focuses on traceability, citation existence, and result-claim binding so problems can be routed back to references or results before the final manuscript audit.

Implemented Priority D CLI command:

```powershell
python -m draftpaper_cli.cli run-integrity-gate --project C:\DraftPaper_CLI\projects\my_project
```

Outputs:

```text
integrity/integrity_report.json
integrity/integrity_report.md
integrity_ledger.jsonl
```

Required checks:

```text
All Introduction/Data/Methods/Discussion citation keys exist in references/library.bib or latex/library.bib
All Introduction/Data/Methods/Discussion citations have rows in references/citation_evidence.csv
Section citations are matched to section-specific citation evidence where available
Results contains no citation commands
results/result_manifest.yaml declares at least one figure or table
Every result manifest entry points to an existing local artifact
Every result manifest entry has a result_claim
```

The command returns exit code `0` only when the integrity report passes. It still writes the JSON and Markdown reports on failure. Each run appends an `integrity_gate` event to `integrity_ledger.jsonl`, which lets Codex, Web UI, or later batch workflows audit when a manuscript draft last passed or failed traceability checks.

`status` and `run-pipeline` are now connected to this gate. When the next pending stage is `quality_checks`, the orchestrator recommends `run-integrity-gate` until `integrity/integrity_report.json` exists with `status=passed`. After that, the normal next action becomes `quality-check`.

## Priority 1: Single-Paper Project Directory Model

Each research idea becomes an independent project directory:

```text
research_paper_agent/data/projects/
  project_slug/
    project.json
    project.yaml
    project_passport.yaml
    artifact_ledger.jsonl
    checkpoint_ledger.jsonl
    integrity_ledger.jsonl
    idea/
    research_plan/
    references/
    journal_profile/
    introduction/
    data/
      raw/
      processed/
    method_plan/
    methods/
    code/
      src/
      scripts/
      tests/
    result_validity/
    results/
      figures/
      tables/
    discussion/
    latex/
      sections/
      template/
    integrity/
    review/
    quality_checks/
```

`project.json` is the machine-readable source of truth. `project.yaml` is the human-readable companion used for review and migration.

## Priority 2: Stage State Machine

The workflow should expose these callable stages:

```text
create_project
status_project
checkpoint_project
resume_project
run_pipeline
search_literature
resolve_journal_template
generate_research_plan
write_introduction
prepare_data_section
collect_method_plan
generate_analysis_code
verify_methods
write_methods
assess_result_validity
inventory_results
write_results
write_discussion
assemble_latex
run_integrity_gate
run_quality_gate
```

Every stage writes a `stage_manifest.json` with:

```json
{
  "stage": "results",
  "status": "draft",
  "depends_on": ["result_validity"],
  "input_files": [],
  "output_files": [],
  "stale": false,
  "last_updated": null
}
```

If an earlier stage changes, later dependent stages should be marked stale instead of deleted.

Implemented Priority 2 CLI commands:

```powershell
python -m draftpaper_cli.cli load-project --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli validate-project --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli update-stage-status --project C:\DraftPaper_CLI\projects\my_project --stage research_plan --status approved
python -m draftpaper_cli.cli mark-stage-stale --project C:\DraftPaper_CLI\projects\my_project --stage research_plan
```

Supported stage statuses:

```text
pending
draft
approved
stale
failed
completed
```

When `mark-stage-stale` is called for an upstream stage, all direct and transitive dependent stages are marked stale in both `project.json` and their own `stage_manifest.json` files. This keeps later stages rerunnable without deleting user-edited drafts or outputs.

## Priority 3: Literature and References

Formal research planning should come after literature retrieval. Before searching, the workflow may create a lightweight search brief from the user's idea, field, and data notes, but this brief is only used to guide query construction. It is not the formal research plan.

```text
idea/search_brief.md
```

Use free/open literature sources as first-class providers:

```text
Semantic Scholar
arXiv
Crossref
SerpApi optional
Zotero optional
Consensus optional later
```

Normalize all sources into:

```text
title
authors
year
doi
url
abstract
venue
citation_count
source
pdf_url
pdf_path
bibtex_key
evidence_notes
search_context
search_query
relevance_score
authority_score
citation_authority_score
journal_score
citation_weight
```

Expected outputs:

```text
references/library.bib
references/literature_items.json
references/search_queries.json
references/citation_evidence.csv
references/literature_review_notes.md
references/literature_summaries/index.html
references/literature_summaries/*.html
```

Implemented Priority 3 CLI command:

```powershell
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\my_project --query "active galactic nuclei machine learning variability"
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\my_project --from-json C:\path\literature_items.json
```

The `--from-json` option is intended for offline runs, manual curation, Zotero exports, or future Codex-assisted literature selection. It accepts UTF-8 and UTF-8 BOM JSON files, which matters for Windows PowerShell-created files.

Live search currently uses Semantic Scholar, arXiv, Crossref, and optional SerpApi when `SERPAPI_API_KEY` is configured. Zotero and Consensus remain later optional providers; the CLI output contract should not change when they are added.

The reference stage now builds three separate query contexts before ranking: `idea`, `data`, and `methods`. The idea query comes from the user query or project idea. The data context builds three to five precise queries from project data signals in `idea/idea.md`, `data/data_inventory.json`, and `data/data_feasibility_report.json`. The methods context builds three to five precise queries from the user's method phrases in `methods/method_plan.md`, plus `methods/method_requirements.json` and `research_plan/research_plan.md` when available. Every data and methods query is crossed with the discipline/field name from `project.json`, rather than always forcing the full research direction or target journal into the query. This keeps broad terms such as `Transformer` or `dataset` inside the intended discipline without over-constraining retrieval. The resolved context queries are written to `references/search_queries.json` so that later review can see exactly how each literature subset was found.

Ranking is performed separately inside each context. For data and methods, the live search calls each precise query with a small per-query limit, normally one to two top records, instead of using one broad aggregated query. The final retained set still contains up to 30 papers by default, but the selector first reserves about five ranked papers for `data` and about five ranked papers for `methods` when enough candidates exist, then fills the remaining slots from idea and residual context candidates. Each candidate is ranked by context-query relevance, citation authority, and journal authority. Journal authority uses a conservative local heuristic now, and can later be replaced or augmented by EasyScholar, Zotero metadata, Consensus, or a paid journal ranking source without changing the project artifacts. Higher `citation_weight` papers are retained first and should be preferred by writing stages.

Metadata filtering is intentionally strict. A candidate is retained only when it has enough machine-readable metadata including an abstract, or when it includes a `pdf_url` or `pdf_path` that can be quick-read for missing abstract evidence. DOI, URL, year, and venue alone are not enough. If data/methods candidates with readable evidence are fewer than five, DraftPaper calls the project-level `paper_fetch_adapter` before final selection. The adapter uses the vendored `third_party/paper-fetch-skill` runtime or a `paper-fetch` command on `PATH`, writes `references/paper_fetch_queries.txt`, stores fetched JSON/Markdown under `references/fulltext/`, and records status in `references/paper_fetch_manifest.json`. If paper-fetch still cannot recover readable evidence, the workflow keeps however many usable data/methods references exist and fills the remaining reference budget with idea-context papers. When enough candidates exist, the selector prefers literature from the last five years and targets at least 60% recent papers. It also avoids papers older than 2011 when the candidate pool is large enough to keep 30 references without them. If fewer than 30 usable papers exist, the workflow relaxes the age preference rather than inventing references.

For human inspection, the stage also writes HTML literature summaries. `references/literature_summaries/index.html` is the overview page, while each retained paper gets a separate HTML note containing metadata, search context, search query, recommended manuscript section, citation weight, relevance, journal authority, abstract-based data/method/result/limitation notes, and relevance to the study. These summaries follow the MVP behavior from `D:\DraftAI_agent`: keep the best public literature candidates, make the ranking visible, and preserve an auditable reading trail before formal research planning.

`citation_evidence.csv` is the critical traceability file. It should record what claim each paper can support:

```csv
citation_key,section,claim,evidence_summary,source,doi,url
Smith2024Model,introduction,current gap,"Existing models lack external validation",semantic_scholar,10.xxxx/example,https://example.org/paper
```

This is what makes Introduction and Discussion traceable rather than AI-invented.

The `section` column is also used as a later writing and quality-audit hint. `idea` context references map to `introduction`, `data` context references map to `data`, and `methods` context references map to `methods`. Quality checks should report when a section has context-specific citation evidence but does not cite any matching evidence keys, because this usually means the section is no longer using the literature subset that justified it.

## Priority 4: Journal Profile and Template Constraints

Before formal writing, the workflow must resolve the target journal format. Different disciplines and journals use different manuscript structures, LaTeX classes, figure/table conventions, keyword systems, abstract limits, and bibliography styles. A single generic paper template is not sufficient for a cross-disciplinary system.

Expected outputs:

```text
journal_profile/journal_profile.json
journal_profile/journal_guidelines.md
journal_profile/template_source.html
journal_profile/template_main.tex
latex/template/main.tex
```

Implemented Priority 4 CLI commands:

```powershell
python -m draftpaper_cli.cli resolve-journal-template --project C:\DraftPaper_CLI\projects\my_project --target-journal APJS
python -m draftpaper_cli.cli resolve-journal-template --project C:\DraftPaper_CLI\projects\my_project --overleaf-url "https://www.overleaf.com/latex/templates/..."
python -m draftpaper_cli.cli resolve-journal-template --project C:\DraftPaper_CLI\projects\my_project --guideline-url "https://journal.example/author-guidelines"
```

The resolver first tries known Overleaf template mappings and Overleaf search. For APJS and other AAS journals it resolves to the AASTeX template family and writes an `aastex701` template with `\submitjournal{ApJS}`, `aasjournal` bibliography style, AAS keywords, and AAS-specific formatting rules. If the target journal has no Overleaf template, the user should provide a journal author-guidelines URL; the workflow stores the guideline page and converts its rules into `journal_profile.json` and `journal_guidelines.md`.

All later writing and LaTeX assembly stages should treat the journal profile as a hard formatting contract. If `journal_profile` changes, research plan, section writers, LaTeX assembly, and quality checks should be rerun.

## Priority 5: Literature-Informed Research Plan

The formal research plan must be generated after references exist. It should be based on:

```text
idea/idea.md
idea/search_brief.md
references/literature_items.json
references/citation_evidence.csv
references/literature_review_notes.md
journal_profile/journal_profile.json
journal_profile/journal_guidelines.md
```

Expected outputs:

```text
research_plan/research_plan.md
research_plan/research_questions.md
research_plan/target_journal_anchor_papers.json
research_plan/novelty_overlap_report.json
research_plan/novelty_overlap_report.md
research_plan/stage_manifest.json
```

The research plan should include background, research questions, hypotheses, data requirements, method route, expected figures, expected contribution, risks, user-confirmation questions, and target-journal anchor literature. The AI may synthesize and structure the plan, but it should not bypass the references stage or invent unsupported research gaps.

Implemented Priority 4 CLI command:

```powershell
python -m draftpaper_cli.cli generate-plan --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli generate-plan --project C:\DraftPaper_CLI\projects\my_project --allow-high-similarity
```

Current behavior is deterministic and offline: it reads `references/literature_items.json`, `references/citation_evidence.csv`, `references/literature_review_notes.md`, and the journal profile, then writes a traceable first version of `research_plan.md` and `research_questions.md`. This keeps the workflow usable without an AI API. A later AI-enhanced writer should use the same inputs and preserve the citation-evidence constraints.

Before writing the plan, the stage ranks target-journal anchor papers. These are papers from or close to the target journal that are highly relevant to the current idea, data, or method context. Their structure is a planning reference for the manuscript, but the workflow must not copy their wording, figures, claims, or unsupported assumptions.

The same step also performs a novelty-overlap check. If a retrieved paper is highly similar to the current idea plus available data and method context, `generate-plan` stops with `blocked_high_similarity` and writes `research_plan/novelty_overlap_report.md`. The user must decide whether to continue, revise the research question, change the data/method route, or abandon/reposition the paper. `--allow-high-similarity` is only for cases where the user explicitly chooses to continue after seeing the report.

If references outputs are missing, `generate-plan` fails instead of creating an unsupported research plan.

If journal profile outputs are missing, `generate-plan` also fails. The target journal is part of the research planning context, not only a final LaTeX formatting detail.

## Priority 6: Introduction Writer

Inputs:

```text
research_plan/research_plan.md
references/literature_review_notes.md
references/citation_evidence.csv
references/library.bib
```

Output:

```text
introduction/introduction.tex
```

Rules: natural academic prose, no arbitrary bullet lists, no casual bolding, and every citation key must exist in `library.bib` and have evidence in `citation_evidence.csv`.

Implemented Priority 5 CLI command:

```powershell
python -m draftpaper_cli.cli write-introduction --project C:\DraftPaper_CLI\projects\my_project
```

Current behavior is deterministic and offline. It reads the formal research plan plus `library.bib` and `citation_evidence.csv`, then writes `introduction/introduction.tex` as natural paragraph-style LaTeX. Citation commands are generated only from keys that appear in both the BibTeX library and the citation-evidence table. If the required inputs are missing, or if evidence keys are absent from `library.bib`, the command fails instead of writing an unsupported Introduction.

The current Introduction writer is intentionally conservative. A later AI-enhanced writer can improve style and domain specificity, but it must preserve these hard constraints: no unsupported citations, no arbitrary bullet lists, no casual bolding, and no claims that cannot be traced to the research plan or citation evidence.

## Priority 7: Methods Hard Gate

Methods writing requires a user/literature-informed method plan and code verification first. The method plan is collected after data feasibility, because method choice depends on the available data, but it also summarizes method patterns from the ranked literature.

Expected files:

```text
method_plan/stage_manifest.json
methods/method_plan.md
methods/method_requirements.json
methods/analysis_code_manifest.json
methods/run_manifest.yaml
methods/methods.tex
code/stage_manifest.json
code/scripts/run_analysis.py
code/src/generated_pipeline.py
code/tests/test_generated_pipeline.py
results/tables/metrics.csv
results/tables/analysis_summary.csv
results/figures/data_analysis_flow.svg
results/figures/data_processing_flow.svg
results/figures/method_analysis_flow.svg
results/figures/data_to_method_outputs.svg
```

`methods/method_plan.md` records the user's method input from UI/CLI, literature-derived method patterns, inferred method families, data requirements implied by the method, and the expected result validity metric. `methods/method_requirements.json` is the machine-readable contract used by later gates.

`run_manifest.yaml` must record command, input data, output files, metrics, figures generated, tables generated, timestamps, and `status: success`.

If `method_requirements.json` is missing, `method_plan` is stale, or `run_manifest.yaml` is missing/not successful, the workflow must not write final `methods.tex`.

Implemented Priority 6 CLI commands:

```powershell
python -m draftpaper_cli.cli collect-method-plan --project C:\DraftPaper_CLI\projects\my_project --method-note "Use a multimodal classifier" --primary-metric f1 --minimum-primary-metric 0.75
python -m draftpaper_cli.cli generate-analysis-code --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli verify-methods --project C:\DraftPaper_CLI\projects\my_project --command "python code/scripts/run_analysis.py" --output results/tables/metrics.csv --output results/tables/analysis_summary.csv --output results/figures/data_analysis_flow.svg --output results/figures/data_processing_flow.svg --output results/figures/method_analysis_flow.svg --output results/figures/data_to_method_outputs.svg
python -m draftpaper_cli.cli write-methods --project C:\DraftPaper_CLI\projects\my_project
```

`collect-method-plan` reads the research plan, data feasibility report, and ranked literature notes. It does not replace user expertise; it creates a structured method contract that combines user-provided method intent with literature method synthesis.

`generate-analysis-code` reads `references/literature_items.json`, `methods/method_plan.md`, `methods/method_requirements.json`, and `data/data_inventory.json`. It writes deterministic project-local baseline code under `code/`, records the generated command, selected input data, literature method sources, method families, and declared outputs in `methods/analysis_code_manifest.json`, and marks the `code` stage as draft so Methods and downstream stages become stale. The default generated run produces two tables plus four SVG figures: data analysis workflow, data processing workflow, method analysis workflow, and data-to-method output workflow. This is a reviewable scaffold for local analysis, not permission to skip code review or result validity checks.

`verify-methods` runs the provided command from the project directory and writes `methods/run_manifest.yaml` as JSON-compatible YAML. The manifest records command, return code, input data, declared output files, parsed CSV metrics, generated tables/figures, timestamps, stdout/stderr snippets, and missing outputs.

`write-methods` is blocked unless the method plan is current, data feasibility is `pass` or `conditional_pass`, `methods/run_manifest.yaml` has `status: success`, and every declared output file exists inside the project directory.

## Priority 8: Results Manifest and Writer

Results writing must be based on actual local outputs and a result validity gate. Data quality alone is not enough: even clean data can produce weak results, and weak results must trigger backtracking before formal Results and Discussion writing.

Expected files:

```text
results/result_validity_report.json
results/result_validity_report.md
results/result_manifest.yaml
```

Rules: Results must not contain citations, every result subsection must bind to a real figure or table, figure insertion belongs at the end of the corresponding subsection, and the text must not claim more than the result files support. `inventory-results` reads verified figures/tables plus `methods/analysis_code_manifest.json` and `methods/run_manifest.yaml` so the result manifest describes what each method-generated artifact supports before `write-results` turns it into paragraphs.

Implemented Priority 7 CLI commands:

```powershell
python -m draftpaper_cli.cli assess-result-validity --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli inventory-results --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli write-results --project C:\DraftPaper_CLI\projects\my_project
```

`assess-result-validity` reads `methods/method_requirements.json`, `methods/run_manifest.yaml`, and `data/data_feasibility_report.json`. It checks whether observed metrics satisfy the configured expectation. If results fail, it writes a diagnosis that points back to data, method, or research plan revision. This gate is where the workflow decides whether the current result can support the expected conclusion.

`inventory-results` scans `results/figures/` and `results/tables/`, then writes `results/result_manifest.yaml` as JSON-compatible YAML. Each entry contains `id`, `path`, `caption_draft`, and `result_claim`.

`write-results` is blocked unless result validity is `pass` or `conditional_pass`, `results/result_manifest.yaml` contains at least one real figure or table, and every declared artifact exists inside the project directory. It also rejects any citation command in result claims or captions. The generated `results/results.tex` is checked again so that `\cite`, `\citep`, `\citet`, `\parencite`, and related citation commands cannot enter the Results section.

## Priority 9: Discussion Writer

Inputs:

```text
research_plan/research_plan.md
introduction/introduction.tex
results/results.tex
references/citation_evidence.csv
references/library.bib
```

Output:

```text
discussion/discussion.tex
```

Discussion may cite literature, but citations must come from `library.bib` and should compare the current findings with existing work.

Implemented Priority 8 CLI command:

```powershell
python -m draftpaper_cli.cli write-discussion --project C:\DraftPaper_CLI\projects\my_project
```

`write-discussion` is blocked unless the formal research plan, Introduction, Results, `citation_evidence.csv`, and `library.bib` all exist. It verifies that every citation-evidence key is present in the BibTeX library before writing `discussion/discussion.tex`. The generated Discussion is paragraph-style LaTeX, may use literature citations, and is structured around research significance, comparison with existing literature, limitations, and future work. Because it depends on both Results and references, it should be rerun whenever result artifacts, method verification, or citation evidence changes.

The current writer is deterministic and offline. A later AI-enhanced Discussion writer can improve domain-specific interpretation, but it must preserve these hard constraints: cited keys must exist in `library.bib`, literature comparison must be traceable to `citation_evidence.csv`, and new claims must remain bounded by `results/results.tex` plus the project research plan.

## Priority 10: LaTeX Assembly

Inputs:

```text
latex/template/
introduction/introduction.tex
data/data.tex
methods/methods.tex
results/results.tex
discussion/discussion.tex
references/library.bib
```

Outputs:

```text
latex/main.tex
latex/sections/*.tex
latex/library.bib
latex/main.pdf optional review PDF
latex/main.compile.log optional compile log
latex/pdf_compile_manifest.json optional PDF compile status
```

Target-journal templates are resolved by `resolve-journal-template` and stored under `journal_profile/` plus `latex/template/`. Automatic Overleaf resolution is supported for known mappings such as APJS/AAS journals, and explicit Overleaf or author-guideline URLs are supported for other journals.

Implemented Priority 9 CLI command:

```powershell
python -m draftpaper_cli.cli assemble-latex --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli assemble-latex --project C:\DraftPaper_CLI\projects\my_project --compile-pdf
python -m draftpaper_cli.cli compile-latex-pdf --project C:\DraftPaper_CLI\projects\my_project
```

`assemble-latex` is blocked unless all required section files, `references/library.bib`, and `journal_profile/journal_profile.json` exist. It also blocks assembly when any input stage is stale or not ready, so stale upstream drafts are not silently included in `latex/main.tex`. The command copies staged sections into `latex/sections/`, copies `references/library.bib` into `latex/library.bib`, and writes `latex/main.tex` using the journal template contract.

The default `main.tex` uses a portable article scaffold with `graphicx`, `natbib`, `hyperref`, `xurl`, and `\graphicspath{{../}}` so project-relative result figure paths such as `results/figures/example.png` still resolve when compiling from the `latex/` directory. If `latex/template/main.tex` exists, the assembler uses it and replaces these optional placeholders:

```text
%%DRAFTPAPER_TITLE%%
%%DRAFTPAPER_SECTIONS%%
%%DRAFTPAPER_BIBLIOGRAPHY%%
```

If a supplied template does not contain section or bibliography placeholders, the assembler appends missing section inputs and bibliography commands conservatively. Citation keys are validated across the assembled section content before writing: any `\cite`, `\citep`, `\citet`, `\parencite`, `\autocite`, or `\textcite` key that is absent from `library.bib` causes the command to fail.

For human review, `assemble-latex --compile-pdf` runs local LaTeX compilation after `main.tex` is assembled. The same PDF step can be rerun independently with `compile-latex-pdf` after manual edits to files under `latex/`. The compiler lookup follows the existing `D:\DraftAI_agent` approach: prefer `xelatex`, fall back to `pdflatex`, run BibTeX when available, then rerun LaTeX enough times for citations and references. The PDF step writes `latex/main.pdf` when successful, always writes `latex/main.compile.log`, and records machine-readable status in `latex/pdf_compile_manifest.json`. If MiKTeX or TeX Live is not installed, the command returns `status: skipped` and keeps the assembled LaTeX files intact.

## Priority 11: Quality Gate Upgrades

Required checks:

```text
project.json exists
stage manifests are complete
stale stages are not assembled into final LaTeX
journal profile exists and documentclass is used
Results contains no citation commands
Results figures and tables exist
Method plan and method requirements exist
Methods has successful run manifest
Result validity is pass or conditional_pass
LaTeX citation keys all exist in BibTeX
BibTeX entries can be traced to Introduction or Discussion usage
```

Implemented Priority 10 CLI command:

```powershell
python -m draftpaper_cli.cli quality-check --project C:\DraftPaper_CLI\projects\my_project
```

Output:

```text
quality_checks/quality_report.json
```

`quality-check` is the final hard gate before treating the local draft as ready for manual review or downstream Overleaf editing. It validates project metadata and stage manifests, checks that final LaTeX was not assembled from stale stages, verifies that the journal profile exists and the journal document class is used, verifies that method requirements exist, verifies that Methods has a successful run manifest, confirms that result validity passed or conditionally passed, confirms that Results contains no citation commands, verifies result artifacts declared in `results/result_manifest.yaml`, checks that all LaTeX citation keys exist in `latex/library.bib`, and confirms that Introduction/Discussion citations are traceable to `references/citation_evidence.csv`.

CLI exit behavior is intentional: passed reports return exit code `0`, failed reports return exit code `1`. This makes the command usable in future batch workflows and Codex skills. The command still writes `quality_checks/quality_report.json` on failure so the user can inspect exact issues and rerun only the affected upstream stages.

PDF status is included in the report. A failed PDF compile is an error because it means the review artifact could not be created after compilation was attempted. A skipped PDF compile is recorded as a warning when no local LaTeX engine is available, because the assembled `.tex` and `.bib` files can still be reviewed or moved to Overleaf.

## Priority 12: Codex Skill Wrapper

The Codex skill is only a calling layer. It must not contain paper-writing business logic, must not directly edit `project.json` or stage manifests, and must not bypass the core Python package.

Implemented skill source:

```text
codex_skills/draftpaper-workflow/SKILL.md
codex_skills/draftpaper-workflow/references/commands.md
codex_skills/draftpaper-workflow/agents/openai.yaml
```

Local install target:

```text
C:\Users\97549\.codex\skills\draftpaper-workflow
```

The skill instructs Codex to call the existing CLI:

```powershell
python -m draftpaper_cli.cli <command>
```

It documents stage order, rerun rules, hard gates, and reporting expectations. If references change, Codex should rerun plan, Introduction, Discussion, LaTeX assembly, and quality checks. If methods or results change, Codex should rerun the relevant manifest/writer stages before assembly. If only the LaTeX template changes, Codex should rerun assembly and quality checks.

This keeps the architecture stable:

```text
Core Python package + CLI + local project structure
Codex skill wrapper
Future Web UI / desktop app / API service
```

## Priority E: Review, Revision Routing, and Re-review Loop

After the hard gates exist, the workflow needs a review-revise-re-review loop. This loop has two layers that share one unified revision issue schema. The first layer converts failed gates into actionable backtracking instructions. The second layer adds a reviewer-style manuscript pass and feeds those issues into the same revision plan.

Implemented Priority E CLI commands:

```powershell
python -m draftpaper_cli.cli diagnose-gate-failures --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli review-draft --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli generate-revision-plan --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli apply-revision --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli re-review --project C:\DraftPaper_CLI\projects\my_project
```

Outputs:

```text
review/gate_failure_diagnosis.json
review/gate_failure_diagnosis.md
review/review_report.md
review/reviewer_issues.json
review/revision_plan.json
review/revision_plan.md
review/commitment_ledger.csv
review/apply_revision_report.json
review/apply_revision_report.md
review/re_review_report.json
review/re_review_report.md
```

Every issue uses the same schema:

```json
{
  "issue_id": "V-12345678",
  "source": "result_validity",
  "code": "revise_required",
  "severity": "blocking",
  "target_stage": "methods",
  "title": "Results do not support the planned claim strength",
  "reason": "Observed f1 is below the planned threshold.",
  "files_to_add_or_edit": ["methods/run_manifest.yaml", "methods/method_requirements.json"],
  "recommended_commands": ["generate-analysis-code", "verify-methods", "assess-result-validity"],
  "required_user_input": "Decide whether to revise the method/data route or lower the manuscript claim strength.",
  "status": "pending"
}
```

`diagnose-gate-failures` reads the data feasibility report, method run manifest, result validity report, integrity report, and quality report. It does not merely say a gate failed; it maps each failure to a target stage, files to inspect, required user decision, and the CLI commands that should be rerun.

`review-draft` is a deterministic reviewer-style pass. It checks whether the assembled manuscript exists, whether Methods are reproducible from a successful run manifest, whether result claim strength matches the result validity decision, and whether Discussion exists after Results. This is intentionally conservative and does not replace human review.

`generate-revision-plan` merges gate diagnosis and reviewer issues into `review/revision_plan.json` and `review/commitment_ledger.csv`. The commitment ledger records issue id, source, target stage, decision, status, and the user's revision commitment so later re-review can audit what was supposed to change.

`apply-revision` currently applies only the safe part of revision: it marks affected target stages and their downstream dependents stale. It does not rewrite scientific content automatically. This is deliberate: adding data, changing methods, or lowering conclusions requires user confirmation and a normal rerun of the staged CLI commands.

`re-review` reruns gate diagnosis, reviewer pass, and revision planning after revisions. It writes a compact report showing remaining gate issues, reviewer issues, and total revision issues.

## Priority 13: Data Feasibility Gate

Data feasibility is a core scientific hard gate before method planning and Methods. The system must not continue into formal Methods writing when the available data cannot support the stated research goal. Literature-derived data expectations are treated as evidence for assessment, not as a universal hard standard; the decisive question is whether the current study's data can support the current research plan and method plan.

Implemented Priority 12 CLI commands:

```powershell
python -m draftpaper_cli.cli inventory-data --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli assess-data-quality --project C:\DraftPaper_CLI\projects\my_project --required-column id --required-column target
python -m draftpaper_cli.cli assess-data-feasibility --project C:\DraftPaper_CLI\projects\my_project --min-rows 30
```

Outputs:

```text
data/data_inventory.json
data/data_quality_report.json
data/data_feasibility_report.json
data/data_feasibility_report.md
```

Decision levels:

```text
pass
conditional_pass
revise_required
blocked
```

`pass` means the current data gate supports the planned claim level. `conditional_pass` means the workflow may continue, but manuscript claims must be lowered to exploratory or pilot strength. `revise_required` means the research question, data, or method route must be revised before Methods. `blocked` means the current data cannot support the stated scientific goal.

`collect-method-plan`, `verify-methods`, and `write-methods` are blocked in practice unless `data/data_feasibility_report.json` has decision `pass` or `conditional_pass`. This prevents the system from producing a formal Methods section after data quality or data sufficiency has already invalidated the scientific objective.

## Priority 14: Skill Reuse and Method-Code Skill Capture

Codex skills are a calling and reuse layer, not the core workflow. The core remains the Python package, CLI, and local project structure.

When building new data analysis code or methodology code, Codex should first inspect existing project code and then search for reusable skills before creating new ones. If a suitable skill exists, install and reuse it instead of writing a duplicate workflow. If no suitable skill exists and the user approves reusing the pattern later, summarize the new reusable workflow as a skill candidate after implementation. The skill summary should capture:

```text
problem type
input files and assumptions
commands or code entry points
outputs
validation checks
failure modes
reuse examples
```

For literature PDF download or full-text fetching, prefer an existing skill before writing custom download logic. A known candidate is:

```text
https://github.com/Dictation354/paper-fetch-skill
```

Only install this when the workflow actually needs PDF/full-text fetching. Use the Codex `skill-installer` workflow to install from GitHub, then restart Codex to pick up the new skill. The paper-writing core should still store fetched PDFs or extracted notes inside the project directory rather than inside the skill.

If the user revises the scientific goal after a feasibility failure, mark these stages stale and rerun them:

```text
research_plan
introduction
data
method_plan
code
methods
result_validity
results
discussion
latex
quality_checks
```

## Target CLI Shape

```powershell
python -m draftpaper_cli.cli create-project --root C:\DraftPaper_CLI\projects --idea "..." --field "..."
python -m draftpaper_cli.cli status --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli run-pipeline --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli detect-artifact-drift --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli sync-artifact-stale --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli resolve-journal-template --project C:\DraftPaper_CLI\projects\my_project --target-journal APJS
python -m draftpaper_cli.cli generate-plan --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli write-introduction --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli inventory-data --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli assess-data-quality --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli assess-data-feasibility --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli collect-method-plan --project C:\DraftPaper_CLI\projects\my_project --method-note "..." --primary-metric f1 --minimum-primary-metric 0.75
python -m draftpaper_cli.cli generate-analysis-code --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli verify-methods --project C:\DraftPaper_CLI\projects\my_project --command "python code/scripts/run_analysis.py" --output results/tables/metrics.csv --output results/tables/analysis_summary.csv --output results/figures/data_analysis_flow.svg --output results/figures/data_processing_flow.svg --output results/figures/method_analysis_flow.svg --output results/figures/data_to_method_outputs.svg
python -m draftpaper_cli.cli assess-result-validity --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli inventory-results --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli write-results --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli write-discussion --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli assemble-latex --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli run-integrity-gate --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli quality-check --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli diagnose-gate-failures --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli review-draft --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli generate-revision-plan --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli apply-revision --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli re-review --project C:\DraftPaper_CLI\projects\my_project
```

## Implementation Rule

Build one stage at a time. For each stage, write tests first, run them to confirm failure, implement the smallest working slice, then run the full local test suite. Keep the core workflow independent from Codex so it can move across computers and later support Codex skills, web UI, or commercial deployment.
