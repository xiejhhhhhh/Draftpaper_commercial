# DraftPaper CLI Commands

Run commands from `C:\DraftPaper_CLI` unless the package is installed into the active Python environment.

## Project

```powershell
python -m draftpaper_cli.cli create-project --root C:\DraftPaper_CLI\projects --idea "..." --field "..." --target-journal "General Academic Journal"
python -m draftpaper_cli.cli load-project --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli validate-project --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli status --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli run-pipeline --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli detect-artifact-drift --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli sync-artifact-stale --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli checkpoint --project C:\DraftPaper_CLI\projects\my_project --stage research_plan --note "User approved the research plan"
python -m draftpaper_cli.cli resume --project C:\DraftPaper_CLI\projects\my_project --checkpoint-hash abc123def456
python -m draftpaper_cli.cli mark-stage-stale --project C:\DraftPaper_CLI\projects\my_project --stage references
python -m draftpaper_cli.cli update-stage-status --project C:\DraftPaper_CLI\projects\my_project --stage data --status draft
```

`status` and `run-pipeline` are the orchestrator layer. They inspect `project.json`, stage manifests, `project_passport.yaml`, and append-only ledgers to report the next safe action. If `status` returns `pipeline_state=drift_detected`, run `sync-artifact-stale` before any downstream stage. `detect-artifact-drift` is read-only; `sync-artifact-stale` maps hash drift to downstream stale stages, writes an integrity ledger event, and refreshes the passport baseline. `checkpoint` records an explicit human confirmation boundary in `checkpoint_ledger.jsonl`; `resume` consumes it by appending a resume event, never by deleting or rewriting the checkpoint.

## Literature and Plan

```powershell
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\my_project --query "topic keywords"
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\my_project --from-json C:\path\literature_items.json
python -m draftpaper_cli.cli resolve-journal-template --project C:\DraftPaper_CLI\projects\my_project --target-journal APJS
python -m draftpaper_cli.cli resolve-journal-template --project C:\DraftPaper_CLI\projects\my_project --overleaf-url "https://www.overleaf.com/latex/templates/..."
python -m draftpaper_cli.cli resolve-journal-template --project C:\DraftPaper_CLI\projects\my_project --guideline-url "https://journal.example/author-guidelines"
python -m draftpaper_cli.cli generate-plan --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli generate-plan --project C:\DraftPaper_CLI\projects\my_project --allow-high-similarity
```

`search-literature` builds separate `idea`, `data`, and `methods` search queries, writes them to `references/search_queries.json`, and tags each retained paper with `search_context` and `search_query`. Data and methods use three to five precise queries crossed with the discipline/field name, not necessarily the full research direction or target journal. Methods queries should preserve user-provided method phrases such as `1D CNN / ResNet`, `Transformer`, `Temporal Convolutional Network`, multimodal networks, and contrastive/self-supervised learning instead of collapsing them into one broad keyword string. Each data/methods query fetches only one to two top records, then the context is ranked separately by query relevance, citation authority, and journal authority before the final set is assembled.

The command writes `references/literature_summaries/index.html` plus one HTML summary per retained paper. Each summary records the search context, search query, recommended manuscript section, ranking scores, metadata, and structured reading notes. The ranking fields in `references/literature_items.json` are `relevance_score`, `authority_score`, `citation_authority_score`, `journal_score`, and `citation_weight`; high `citation_weight` papers should be preferred by the matching writing stage.

`citation_evidence.csv` maps context to manuscript section: idea -> introduction, data -> data, methods -> methods. If later Data or Methods drafts do not cite any evidence keys from their matching context, `quality-check` reports a context-reference warning. Literature candidates without abstracts are first sent through DraftPaper's project-level `paper_fetch_adapter` when data/methods usable evidence is below five. The adapter writes `references/paper_fetch_queries.txt`, `references/paper_fetch_manifest.json`, and fetched files under `references/fulltext/`. If paper-fetch cannot recover readable evidence, keep the usable data/methods references that exist and let idea-context papers fill the remaining reference budget.

`generate-plan` also writes target-journal anchor papers and a novelty-overlap report. If it returns `blocked_high_similarity`, stop and ask the user whether to continue, revise, or abandon the current framing before rerunning with `--allow-high-similarity`.

## Writing Stages

```powershell
python -m draftpaper_cli.cli write-introduction --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli inventory-data --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli assess-data-quality --project C:\DraftPaper_CLI\projects\my_project --required-column id --required-column target
python -m draftpaper_cli.cli assess-data-feasibility --project C:\DraftPaper_CLI\projects\my_project --min-rows 30
python -m draftpaper_cli.cli collect-method-plan --project C:\DraftPaper_CLI\projects\my_project --method-note "Use a multimodal classifier" --primary-metric f1 --minimum-primary-metric 0.75
python -m draftpaper_cli.cli generate-analysis-code --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli verify-methods --project C:\DraftPaper_CLI\projects\my_project --command "python code/scripts/run_analysis.py" --output results/tables/metrics.csv --output results/tables/analysis_summary.csv --output results/figures/data_analysis_flow.svg --output results/figures/data_processing_flow.svg --output results/figures/method_analysis_flow.svg --output results/figures/data_to_method_outputs.svg
python -m draftpaper_cli.cli write-methods --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli assess-result-validity --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli inventory-results --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli write-results --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli write-discussion --project C:\DraftPaper_CLI\projects\my_project
```

## Assembly and Review

```powershell
python -m draftpaper_cli.cli assemble-latex --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli assemble-latex --project C:\DraftPaper_CLI\projects\my_project --compile-pdf
python -m draftpaper_cli.cli compile-latex-pdf --project C:\DraftPaper_CLI\projects\my_project
python -m draftpaper_cli.cli quality-check --project C:\DraftPaper_CLI\projects\my_project
```

`quality-check` returns exit code `0` for passed and `1` for failed. It still writes `quality_checks/quality_report.json` on failure.
