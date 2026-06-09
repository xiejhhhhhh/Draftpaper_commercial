from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analysis_code import AnalysisCodeGenerationError, generate_analysis_code
from .data_feasibility import DataGateError, assess_data_feasibility, assess_data_quality, inventory_data
from .discussion import DiscussionCitationIntegrityError, MissingDiscussionInputsError, write_discussion
from .introduction import CitationIntegrityError, MissingIntroductionInputsError, write_introduction
from .integrity_gate import IntegrityGateError, run_integrity_gate
from .journal_profile import JournalProfileError, resolve_journal_template
from .latex_assembly import LatexAssemblyError, assemble_latex, compile_latex_pdf
from .literature_search import search_literature_for_project
from .method_plan import MethodPlanError, collect_method_plan
from .methods import MethodsGateError, verify_methods, write_methods
from .orchestrator import OrchestratorError, checkpoint_project, resume_project, run_pipeline, status_project
from .passport import PassportError
from .project_scaffold import ProjectAlreadyExistsError, create_project
from .project_state import (
    InvalidStageStatusError,
    ProjectStateError,
    UnknownStageError,
    load_project,
    mark_stage_stale,
    update_stage_status,
    validate_project,
)
from .quality_gate import QualityGateError, run_quality_check
from .research_plan import MissingReferencesError, NoveltyOverlapError, generate_research_plan
from .review_revision import (
    ReviewRevisionError,
    apply_revision,
    diagnose_gate_failures,
    generate_revision_plan,
    re_review,
    review_draft,
)
from .result_validity import ResultValidityError, assess_result_validity
from .results import ResultsGateError, inventory_results, write_results
from .stale_sync import ArtifactDriftError, detect_artifact_drift, sync_artifact_stale


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="draftpaper",
        description="Local-first staged workflow for research paper projects.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-project", help="Create a single-paper project directory model.")
    create.add_argument("--root", required=True, help="Directory that will contain paper projects.")
    create.add_argument("--idea", required=True, help="Research idea or working title.")
    create.add_argument("--field", required=True, help="Research field or aim.")
    create.add_argument("--target-journal", default="General Academic Journal", help="Target journal or template family.")
    create.add_argument("--overwrite", action="store_true", help="Allow regenerating an existing project scaffold.")

    load = subparsers.add_parser("load-project", help="Load project metadata as JSON.")
    load.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    validate = subparsers.add_parser("validate-project", help="Validate project metadata and stage manifests.")
    validate.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    status = subparsers.add_parser("status", help="Report orchestrated pipeline status and next action.")
    status.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    checkpoint = subparsers.add_parser("checkpoint", help="Create an explicit user-confirmation checkpoint.")
    checkpoint.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    checkpoint.add_argument("--stage", required=True, help="Stage being checkpointed.")
    checkpoint.add_argument("--note", default="", help="Human-readable checkpoint note.")

    resume = subparsers.add_parser("resume", help="Resume from a checkpoint hash.")
    resume.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    resume.add_argument("--checkpoint-hash", required=True, help="Checkpoint hash to consume.")
    resume.add_argument("--note", default="", help="Human-readable resume note.")

    run = subparsers.add_parser("run-pipeline", help="Plan the next orchestrated pipeline action.")
    run.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    drift = subparsers.add_parser("detect-artifact-drift", help="Detect artifact hash drift from project_passport.yaml.")
    drift.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    sync_stale = subparsers.add_parser("sync-artifact-stale", help="Mark dependent stages stale from artifact hash drift.")
    sync_stale.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    update = subparsers.add_parser("update-stage-status", help="Update one stage status.")
    update.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    update.add_argument("--stage", required=True, help="Stage name to update.")
    update.add_argument("--status", required=True, help="New stage status.")

    stale = subparsers.add_parser("mark-stage-stale", help="Mark downstream dependent stages as stale.")
    stale.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    stale.add_argument("--stage", required=True, help="Stage whose dependents should be marked stale.")
    stale.add_argument("--include-self", action="store_true", help="Also mark the named stage stale.")

    search = subparsers.add_parser("search-literature", help="Search or import literature and write references artifacts.")
    search.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    search.add_argument("--query", default=None, help="Optional explicit scholarly search query.")
    search.add_argument("--limit", type=int, default=30, help="Maximum number of ranked references to keep.")
    search.add_argument("--from-json", default=None, help="Use a local JSON list of literature items instead of live search.")

    journal = subparsers.add_parser("resolve-journal-template", help="Resolve target journal Overleaf/template formatting constraints.")
    journal.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    journal.add_argument("--target-journal", default=None, help="Target journal name or abbreviation, for example APJS.")
    journal.add_argument("--overleaf-url", default=None, help="Explicit Overleaf template URL.")
    journal.add_argument("--guideline-url", default=None, help="Journal author-guidelines URL when no Overleaf template exists.")
    journal.add_argument("--from-html", default=None, help="Use a local HTML file as the template/guideline source.")

    plan = subparsers.add_parser("generate-plan", help="Generate a literature-informed formal research plan.")
    plan.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    plan.add_argument("--allow-high-similarity", action="store_true", help="Continue even when a highly similar prior paper is detected.")

    intro = subparsers.add_parser("write-introduction", help="Write a traceable LaTeX Introduction section.")
    intro.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    data_inventory = subparsers.add_parser("inventory-data", help="Inventory local data files.")
    data_inventory.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    data_quality = subparsers.add_parser("assess-data-quality", help="Assess basic local data quality.")
    data_quality.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    data_quality.add_argument("--required-column", action="append", default=[], help="Column required for the current research plan.")
    data_quality.add_argument("--max-missing-ratio", type=float, default=0.2, help="Maximum acceptable missing-cell ratio.")

    data_feasibility = subparsers.add_parser("assess-data-feasibility", help="Assess whether data can support the research plan.")
    data_feasibility.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    data_feasibility.add_argument("--min-rows", type=int, default=30, help="Minimum tabular row count expected for the planned study.")

    method_plan = subparsers.add_parser("collect-method-plan", help="Collect user method intent and synthesize literature-informed method requirements.")
    method_plan.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    method_plan.add_argument("--method-note", action="append", default=[], help="User-provided method note. Can be repeated.")
    method_plan.add_argument("--primary-metric", default="f1", help="Primary metric expected for result validity.")
    method_plan.add_argument("--minimum-primary-metric", type=float, default=None, help="Minimum acceptable primary metric value.")

    codegen = subparsers.add_parser("generate-analysis-code", help="Generate project-local analysis code from literature and method requirements.")
    codegen.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    codegen.add_argument("--output", action="append", default=[], help="Project-relative output file expected from generated code.")

    verify = subparsers.add_parser("verify-methods", help="Run method code and write methods/run_manifest.yaml.")
    verify.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    verify.add_argument("--command", required=True, dest="method_command", help="Command that verifies method code and outputs.")
    verify.add_argument("--output", action="append", default=[], help="Project-relative output file that must exist after the command.")
    verify.add_argument("--input", action="append", default=[], help="Project-relative input data file used by the method command.")

    methods = subparsers.add_parser("write-methods", help="Write methods.tex after successful method verification.")
    methods.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    inventory = subparsers.add_parser("inventory-results", help="Inventory local result figures and tables.")
    inventory.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    result_validity = subparsers.add_parser("assess-result-validity", help="Assess whether method outputs support expected result claims.")
    result_validity.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    result_validity.add_argument("--primary-metric", default=None, help="Override primary metric from methods/method_requirements.json.")
    result_validity.add_argument("--minimum-value", type=float, default=None, help="Override minimum acceptable primary metric value.")

    results = subparsers.add_parser("write-results", help="Write results.tex from result_manifest.yaml.")
    results.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    discussion = subparsers.add_parser("write-discussion", help="Write a traceable LaTeX Discussion section.")
    discussion.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    latex = subparsers.add_parser("assemble-latex", help="Assemble staged sections into latex/main.tex.")
    latex.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    latex.add_argument("--compile-pdf", action="store_true", help="Compile latex/main.tex into latex/main.pdf for review.")

    pdf = subparsers.add_parser("compile-latex-pdf", help="Compile latex/main.tex into latex/main.pdf for review.")
    pdf.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    quality = subparsers.add_parser("quality-check", help="Run final staged manuscript quality checks.")
    quality.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    integrity = subparsers.add_parser("run-integrity-gate", help="Run citation evidence and result artifact integrity checks.")
    integrity.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    diagnose = subparsers.add_parser("diagnose-gate-failures", help="Convert failed gates into actionable revision issues.")
    diagnose.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    review = subparsers.add_parser("review-draft", help="Run a reviewer-style manuscript pass and write review artifacts.")
    review.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    revision_plan = subparsers.add_parser("generate-revision-plan", help="Merge gate diagnosis and reviewer issues into a revision plan.")
    revision_plan.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    apply = subparsers.add_parser("apply-revision", help="Safely apply a revision plan by marking affected stages stale.")
    apply.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    apply.add_argument("--issue-id", action="append", default=[], help="Only apply selected revision issue ids. Can be repeated.")
    apply.add_argument("--dry-run", action="store_true", help="Report affected stages without marking them stale.")

    rereview = subparsers.add_parser("re-review", help="Rerun gate diagnosis, reviewer pass, and revision planning.")
    rereview.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "create-project":
        try:
            project = create_project(
                root=Path(args.root),
                idea=args.idea,
                field=args.field,
                target_journal=args.target_journal,
                overwrite=args.overwrite,
            )
        except ProjectAlreadyExistsError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 2
        except ValueError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1

        print(json.dumps({
            "status": "created",
            "project_id": project.project_id,
            "project_slug": project.project_slug,
            "project_path": str(project.path),
            "project_json": str(project.path / "project.json"),
            "project_yaml": str(project.path / "project.yaml"),
        }, ensure_ascii=False))
        return 0

    if args.command == "load-project":
        try:
            state = load_project(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "loaded",
            "project_path": str(state.path),
            "metadata": state.metadata,
        }, ensure_ascii=False))
        return 0

    if args.command == "validate-project":
        report = validate_project(args.project)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get("status") == "passed" else 1

    if args.command == "status":
        try:
            result = status_project(args.project)
        except (OrchestratorError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "checkpoint":
        try:
            result = checkpoint_project(args.project, stage=args.stage, note=args.note)
        except (OrchestratorError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "resume":
        try:
            result = resume_project(args.project, checkpoint_hash=args.checkpoint_hash, note=args.note)
        except (OrchestratorError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "run-pipeline":
        try:
            result = run_pipeline(args.project)
        except (OrchestratorError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") in {"planned", "awaiting_confirmation", "drift_detected"} else 1

    if args.command == "detect-artifact-drift":
        try:
            result = detect_artifact_drift(args.project)
        except (ArtifactDriftError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "sync-artifact-stale":
        try:
            result = sync_artifact_stale(args.project)
        except (ArtifactDriftError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "update-stage-status":
        try:
            state = update_stage_status(args.project, args.stage, args.status)
        except (ProjectStateError, UnknownStageError, InvalidStageStatusError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "updated",
            "project_path": str(state.path),
            "stage": args.stage,
            "stage_status": state.metadata["stages"][args.stage]["status"],
            "stale": state.metadata["stages"][args.stage]["stale"],
        }, ensure_ascii=False))
        return 0

    if args.command == "mark-stage-stale":
        try:
            changed = mark_stage_stale(args.project, args.stage, include_self=args.include_self)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "updated",
            "stage": args.stage,
            "stale_stages": changed,
        }, ensure_ascii=False))
        return 0

    if args.command == "search-literature":
        try:
            result = search_literature_for_project(
                args.project,
                query=args.query,
                limit=args.limit,
                from_json=args.from_json,
            )
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "resolve-journal-template":
        try:
            result = resolve_journal_template(
                args.project,
                target_journal=args.target_journal,
                overleaf_url=args.overleaf_url,
                guideline_url=args.guideline_url,
                from_html=args.from_html,
            )
        except (JournalProfileError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "generate-plan":
        try:
            result = generate_research_plan(args.project, allow_high_similarity=args.allow_high_similarity)
        except MissingReferencesError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except NoveltyOverlapError as exc:
            print(json.dumps({
                "status": "blocked_high_similarity",
                "message": str(exc),
                "novelty_overlap_report": str(exc.report_path),
            }, ensure_ascii=False), file=sys.stderr)
            return 3
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "write-introduction":
        try:
            result = write_introduction(args.project)
        except (MissingIntroductionInputsError, CitationIntegrityError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "inventory-data":
        try:
            result = inventory_data(args.project)
        except DataGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assess-data-quality":
        try:
            result = assess_data_quality(
                args.project,
                required_columns=args.required_column,
                max_missing_ratio=args.max_missing_ratio,
            )
        except DataGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assess-data-feasibility":
        try:
            result = assess_data_feasibility(args.project, min_rows=args.min_rows)
        except DataGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") in {"pass", "conditional_pass"} else 1

    if args.command == "verify-methods":
        try:
            result = verify_methods(args.project, command=args.method_command, output_files=args.output, input_data=args.input)
        except MethodsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "generate-analysis-code":
        try:
            result = generate_analysis_code(args.project, output_files=args.output)
        except (AnalysisCodeGenerationError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "collect-method-plan":
        try:
            result = collect_method_plan(
                args.project,
                user_method="\n".join(args.method_note or []),
                primary_metric=args.primary_metric,
                minimum_primary_metric=args.minimum_primary_metric,
            )
        except (MethodPlanError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "write-methods":
        try:
            result = write_methods(args.project)
        except MethodsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "inventory-results":
        try:
            result = inventory_results(args.project)
        except ResultsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assess-result-validity":
        try:
            result = assess_result_validity(
                args.project,
                primary_metric=args.primary_metric,
                minimum_value=args.minimum_value,
            )
        except (ResultValidityError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "write-results":
        try:
            result = write_results(args.project)
        except ResultsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "write-discussion":
        try:
            result = write_discussion(args.project)
        except (MissingDiscussionInputsError, DiscussionCitationIntegrityError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assemble-latex":
        try:
            result = assemble_latex(args.project, compile_pdf=args.compile_pdf)
        except LatexAssemblyError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "compile-latex-pdf":
        try:
            result = compile_latex_pdf(args.project)
        except LatexAssemblyError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "quality-check":
        try:
            result = run_quality_check(args.project)
        except QualityGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1

    if args.command == "run-integrity-gate":
        try:
            result = run_integrity_gate(args.project)
        except IntegrityGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1

    if args.command == "diagnose-gate-failures":
        try:
            result = diagnose_gate_failures(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "review-draft":
        try:
            result = review_draft(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "generate-revision-plan":
        try:
            result = generate_revision_plan(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "apply-revision":
        try:
            result = apply_revision(args.project, issue_ids=args.issue_id, dry_run=args.dry_run)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "re-review":
        try:
            result = re_review(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
