from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now
from .project_state import load_project, update_stage_status, validate_project


QUALITY_INPUTS = [
    "project.json",
    "latex/main.tex",
    "latex/library.bib",
    "latex/sections/introduction.tex",
    "latex/sections/data.tex",
    "latex/sections/methods.tex",
    "latex/sections/results.tex",
    "latex/sections/discussion.tex",
    "journal_profile/journal_profile.json",
    "journal_profile/journal_guidelines.md",
    "data/data_inventory.json",
    "data/data_quality_report.json",
    "data/data_feasibility_report.json",
    "methods/method_plan.md",
    "methods/method_requirements.json",
    "methods/run_manifest.yaml",
    "results/result_validity_report.json",
    "results/result_manifest.yaml",
    "results/results.tex",
    "references/citation_evidence.csv",
]

QUALITY_OUTPUTS = [
    "quality_checks/quality_report.json",
]

FINAL_INPUT_STAGES = ["references", "journal_profile", "introduction", "data", "method_plan", "methods", "result_validity", "results", "discussion", "latex"]
RESULT_CITATION_PATTERN = re.compile(r"\\(?:cite|citep|citet|parencite|autocite|textcite)\*?(?:\[[^\]]*\]){0,2}\{", re.IGNORECASE)
CITATION_PATTERN = re.compile(r"\\(?:cite|citep|citet|parencite|autocite|textcite)\*?(?:\[[^\]]*\]){0,2}\{([^{}]+)\}", re.IGNORECASE)


@dataclass
class QualityIssue:
    severity: str
    code: str
    message: str
    file: str | None = None


class QualityGateError(RuntimeError):
    """Raised when the quality gate cannot run because the project cannot be loaded."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _bibtex_keys(content: str) -> set[str]:
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)", content))


def _latex_citation_keys(content: str) -> set[str]:
    keys: set[str] = set()
    for match in CITATION_PATTERN.finditer(content):
        for key in match.group(1).split(","):
            clean = key.strip()
            if clean:
                keys.add(clean)
    return keys


def _read_citation_evidence(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _project_relative_path(project_path: Path, relative: str, issues: list[QualityIssue], *, code: str) -> Path | None:
    candidate = (project_path / relative).resolve()
    try:
        candidate.relative_to(project_path.resolve())
    except ValueError:
        issues.append(QualityIssue("error", code, f"Path escapes project directory: {relative}", relative))
        return None
    return candidate


def _check_required_files(project_path: Path, issues: list[QualityIssue]) -> dict[str, bool]:
    presence: dict[str, bool] = {}
    for relative in QUALITY_INPUTS:
        path = project_path / relative
        exists = path.exists()
        presence[relative] = exists
        if not exists:
            issues.append(QualityIssue("error", "required_artifact_missing", f"Required quality input is missing: {relative}", relative))
        elif path.is_file() and path.stat().st_size == 0:
            issues.append(QualityIssue("error", "required_artifact_empty", f"Required quality input is empty: {relative}", relative))
    return presence


def _check_project_validation(project: str | Path, issues: list[QualityIssue]) -> dict[str, Any]:
    report = validate_project(project)
    if report.get("status") != "passed":
        issues.append(QualityIssue("error", "project_validation_failed", "Project metadata or stage manifests failed validation.", "project.json"))
    return report


def _check_stage_readiness(state_meta: dict[str, Any], issues: list[QualityIssue]) -> dict[str, Any]:
    stages = state_meta.get("stages") or {}
    stale = []
    not_ready = []
    for stage in FINAL_INPUT_STAGES:
        stage_meta = stages.get(stage) or {}
        if stage_meta.get("stale"):
            stale.append(stage)
            issues.append(QualityIssue("error", "stale_stage_in_final_latex", f"Final LaTeX depends on stale stage: {stage}.", f"{stage}/stage_manifest.json"))
        if stage_meta.get("status") not in {"draft", "approved", "completed"}:
            not_ready.append(stage)
            issues.append(QualityIssue("error", "stage_not_ready_for_quality_gate", f"Stage is not ready for quality gate: {stage}={stage_meta.get('status')}.", f"{stage}/stage_manifest.json"))
    return {"stale_stages": stale, "not_ready_stages": not_ready}


def _check_methods(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    requirements = _read_json(project_path / "methods" / "method_requirements.json")
    if not requirements:
        issues.append(QualityIssue("error", "method_requirements_missing", "methods/method_requirements.json is required.", "methods/method_requirements.json"))
    manifest_path = project_path / "methods" / "run_manifest.yaml"
    manifest = _read_json(manifest_path)
    status = manifest.get("status")
    if status != "success":
        issues.append(QualityIssue("error", "methods_run_manifest_not_success", "methods/run_manifest.yaml must have status=success.", "methods/run_manifest.yaml"))
    missing_outputs = []
    for relative in manifest.get("output_files") or []:
        path = _project_relative_path(project_path, str(relative), issues, code="method_output_path_escape")
        if path and not path.exists():
            missing_outputs.append(str(relative))
            issues.append(QualityIssue("error", "method_output_missing", f"Declared method output is missing: {relative}", str(relative)))
    return {
        "method_data_fit": requirements.get("method_data_fit"),
        "primary_metric": requirements.get("primary_metric"),
        "minimum_primary_metric": requirements.get("minimum_primary_metric"),
        "run_manifest_status": status,
        "declared_output_count": len(manifest.get("output_files") or []),
        "missing_outputs": missing_outputs,
    }


def _check_result_validity(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    report = _read_json(project_path / "results" / "result_validity_report.json")
    decision = report.get("decision")
    if decision not in {"pass", "conditional_pass"}:
        issues.append(QualityIssue(
            "error",
            "result_validity_not_passed",
            f"Result validity must be pass or conditional_pass before final quality check. Current decision: {decision}.",
            "results/result_validity_report.json",
        ))
    if decision == "conditional_pass":
        issues.append(QualityIssue(
            "warning",
            "result_validity_conditional",
            "Results support only a reduced or threshold-unspecified claim level.",
            "results/result_validity_report.json",
        ))
    return {
        "decision": decision,
        "primary_metric": report.get("primary_metric"),
        "observed_value": report.get("observed_value"),
        "minimum_value": report.get("minimum_value"),
        "failure_causes": report.get("failure_causes") or [],
    }


def _check_data_feasibility(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    report = _read_json(project_path / "data" / "data_feasibility_report.json")
    decision = report.get("decision")
    if decision not in {"pass", "conditional_pass"}:
        issues.append(QualityIssue(
            "error",
            "data_feasibility_not_passed",
            f"Data feasibility must be pass or conditional_pass before final quality check. Current decision: {decision}.",
            "data/data_feasibility_report.json",
        ))
    if decision == "conditional_pass":
        issues.append(QualityIssue(
            "warning",
            "data_feasibility_conditional",
            "Data supports only a reduced or exploratory claim level.",
            "data/data_feasibility_report.json",
        ))
    return {
        "decision": decision,
        "scientific_goal_supported": report.get("scientific_goal_supported"),
        "supported_claim_level": report.get("supported_claim_level"),
        "blocking_issue_count": len(report.get("blocking_issues") or []),
    }


def _check_results(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    results_tex = _read_text(project_path / "results" / "results.tex")
    citation_count = len(RESULT_CITATION_PATTERN.findall(results_tex))
    if citation_count:
        issues.append(QualityIssue("error", "results_contains_citation", "Results section must not contain citation commands.", "results/results.tex"))

    manifest = _read_json(project_path / "results" / "result_manifest.yaml")
    entries = []
    for item in manifest.get("figures") or []:
        entries.append(("figure", item))
    for item in manifest.get("tables") or []:
        entries.append(("table", item))
    if not entries:
        issues.append(QualityIssue("error", "result_manifest_empty", "results/result_manifest.yaml must declare at least one figure or table.", "results/result_manifest.yaml"))

    missing = []
    escaping = []
    for kind, entry in entries:
        relative = str(entry.get("path") or "")
        if not relative:
            issues.append(QualityIssue("error", "result_artifact_path_missing", f"A {kind} result entry has no path.", "results/result_manifest.yaml"))
            continue
        path = _project_relative_path(project_path, relative, issues, code="result_artifact_path_escape")
        if path and not path.exists():
            missing.append(relative)
            issues.append(QualityIssue("error", "result_artifact_missing", f"Declared result artifact is missing: {relative}", relative))
        text = " ".join(str(entry.get(key) or "") for key in ("caption_draft", "result_claim"))
        if RESULT_CITATION_PATTERN.search(text):
            issues.append(QualityIssue("error", "result_manifest_contains_citation", "Results manifest contains a citation command.", "results/result_manifest.yaml"))
    return {
        "artifact_count": len(entries),
        "missing_artifacts": missing,
        "citation_command_count": citation_count,
        "path_escape_count": len(escaping),
    }


def _check_bibliography(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    main_tex = _read_text(project_path / "latex" / "main.tex")
    bibtex = _read_text(project_path / "latex" / "library.bib")
    introduction_tex = _read_text(project_path / "introduction" / "introduction.tex") + "\n" + _read_text(project_path / "latex" / "sections" / "introduction.tex")
    data_tex = _read_text(project_path / "data" / "data.tex") + "\n" + _read_text(project_path / "latex" / "sections" / "data.tex")
    methods_tex = _read_text(project_path / "methods" / "methods.tex") + "\n" + _read_text(project_path / "latex" / "sections" / "methods.tex")
    discussion_tex = _read_text(project_path / "discussion" / "discussion.tex") + "\n" + _read_text(project_path / "latex" / "sections" / "discussion.tex")
    bib_keys = _bibtex_keys(bibtex)
    main_citations = _latex_citation_keys(main_tex)
    intro_discussion_citations = _latex_citation_keys(introduction_tex + "\n" + discussion_tex)
    evidence_rows = _read_citation_evidence(project_path / "references" / "citation_evidence.csv")
    evidence_keys = {row.get("citation_key", "") for row in evidence_rows if row.get("citation_key")}
    evidence_by_section: dict[str, set[str]] = {}
    for row in evidence_rows:
        section = (row.get("section") or "").strip().lower()
        key = (row.get("citation_key") or "").strip()
        if section and key:
            evidence_by_section.setdefault(section, set()).add(key)

    if not bib_keys:
        issues.append(QualityIssue("error", "bib_no_entries", "latex/library.bib contains no BibTeX entries.", "latex/library.bib"))
    missing = sorted(main_citations - bib_keys)
    if missing:
        issues.append(QualityIssue("error", "citation_key_missing", "LaTeX cites keys that are absent from BibTeX: " + ", ".join(missing[:12]), "latex/main.tex"))
    untraced = sorted(intro_discussion_citations - evidence_keys)
    if untraced:
        issues.append(QualityIssue("error", "citation_not_in_evidence_table", "Introduction/Discussion cite keys absent from citation_evidence.csv: " + ", ".join(untraced[:12]), "references/citation_evidence.csv"))
    if "\\bibliography{" not in main_tex:
        issues.append(QualityIssue("error", "bibliography_command_missing", "latex/main.tex has no bibliography command.", "latex/main.tex"))
    if "natbib" not in main_tex and main_citations:
        issues.append(QualityIssue("warning", "natbib_missing", "latex/main.tex cites literature but does not load natbib.", "latex/main.tex"))
    section_citation_report = {}
    for section, tex, file_name in [
        ("data", data_tex, "data/data.tex"),
        ("methods", methods_tex, "methods/methods.tex"),
    ]:
        expected_keys = evidence_by_section.get(section, set())
        cited_keys = _latex_citation_keys(tex)
        matched_keys = sorted(expected_keys & cited_keys)
        section_citation_report[section] = {
            "evidence_key_count": len(expected_keys),
            "matched_citation_count": len(matched_keys),
            "matched_citation_keys": matched_keys,
        }
        if expected_keys and not matched_keys:
            issues.append(QualityIssue(
                "warning",
                f"{section}_context_references_not_cited",
                f"citation_evidence.csv contains {section}-context references, but the {section.capitalize()} section cites none of them.",
                file_name,
            ))
    unused_bib_keys = sorted(bib_keys - intro_discussion_citations)
    if unused_bib_keys:
        issues.append(QualityIssue("warning", "bib_entries_not_used_in_intro_or_discussion", "BibTeX entries not cited in Introduction or Discussion: " + ", ".join(unused_bib_keys[:12]), "latex/library.bib"))
    return {
        "bibtex_entry_count": len(bib_keys),
        "latex_citation_count": len(main_citations),
        "intro_discussion_citation_count": len(intro_discussion_citations),
        "missing_citation_keys": missing,
        "citations_without_evidence": untraced,
        "unused_bibtex_keys": unused_bib_keys,
        "section_context_citations": section_citation_report,
    }


def _check_latex_hygiene(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    main_tex = _read_text(project_path / "latex" / "main.tex")
    profile = _read_json(project_path / "journal_profile" / "journal_profile.json")
    documentclass = str(profile.get("documentclass") or "")
    target_journal = str(profile.get("target_journal") or "")
    begin_doc = main_tex.count("\\begin{document}")
    end_doc = main_tex.count("\\end{document}")
    if begin_doc != 1 or end_doc != 1:
        issues.append(QualityIssue("error", "latex_document_environment_invalid", f"Expected one document environment, found begin={begin_doc}, end={end_doc}.", "latex/main.tex"))
    if "\\input{sections/results}" not in main_tex:
        issues.append(QualityIssue("error", "latex_results_input_missing", "latex/main.tex does not input sections/results.", "latex/main.tex"))
    if documentclass and f"{{{documentclass}}}" not in main_tex:
        issues.append(QualityIssue("error", "journal_documentclass_not_used", f"latex/main.tex does not use journal documentclass: {documentclass}.", "latex/main.tex"))
    if "aastex" in documentclass.lower():
        if "\\submitjournal{" not in main_tex:
            issues.append(QualityIssue("error", "aas_submitjournal_missing", "AAS templates require a submitjournal command.", "latex/main.tex"))
        if "\\keywords{" not in main_tex:
            issues.append(QualityIssue("warning", "aas_keywords_missing", "AAS templates expect UAT keywords.", "latex/main.tex"))
        if "\\bibliographystyle{aasjournal}" not in main_tex and "\\bibliographystyle{aasjournalv7}" not in main_tex:
            issues.append(QualityIssue("error", "aas_bibliography_style_missing", "AAS templates should use an AAS journal bibliography style.", "latex/main.tex"))
    inline_dollars = re.sub(r"\\\$", "", main_tex).count("$")
    if inline_dollars % 2 != 0:
        issues.append(QualityIssue("error", "unbalanced_inline_math", "latex/main.tex has an odd number of inline math delimiters.", "latex/main.tex"))
    return {
        "document_begin_count": begin_doc,
        "document_end_count": end_doc,
        "inline_dollar_count": inline_dollars,
        "journal_documentclass": documentclass,
        "target_journal": target_journal,
    }


def _check_pdf(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    manifest_path = project_path / "latex" / "pdf_compile_manifest.json"
    pdf_path = project_path / "latex" / "main.pdf"
    if not manifest_path.exists():
        return {"status": "not_run", "pdf_exists": pdf_path.exists()}
    manifest = _read_json(manifest_path)
    status = manifest.get("status")
    if status == "failed":
        issues.append(QualityIssue("error", "pdf_compile_failed", str(manifest.get("message") or "PDF compilation failed."), "latex/pdf_compile_manifest.json"))
    elif status == "skipped":
        issues.append(QualityIssue("warning", "pdf_compile_skipped", str(manifest.get("message") or "PDF compilation skipped."), "latex/pdf_compile_manifest.json"))
    elif status == "success" and not pdf_path.exists():
        issues.append(QualityIssue("error", "pdf_missing_after_success", "PDF manifest says success but latex/main.pdf is missing.", "latex/main.pdf"))
    return {"status": status, "pdf_exists": pdf_path.exists(), "manifest": str(manifest_path)}


def _set_quality_manifest(project_path: Path) -> None:
    manifest_path = project_path / "quality_checks" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = QUALITY_INPUTS
    manifest["output_files"] = QUALITY_OUTPUTS
    _write_json(manifest_path, manifest)


def run_quality_check(project: str | Path) -> dict[str, Any]:
    """Run final staged manuscript quality checks and write quality_checks/quality_report.json."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise QualityGateError(str(exc)) from exc

    issues: list[QualityIssue] = []
    validation = _check_project_validation(state.path, issues)
    required_files = _check_required_files(state.path, issues)
    stage_report = _check_stage_readiness(state.metadata, issues)
    data_report = _check_data_feasibility(state.path, issues)
    methods_report = _check_methods(state.path, issues)
    result_validity_report = _check_result_validity(state.path, issues)
    results_report = _check_results(state.path, issues)
    bibliography_report = _check_bibliography(state.path, issues)
    latex_report = _check_latex_hygiene(state.path, issues)
    pdf_report = _check_pdf(state.path, issues)

    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    status = "passed" if error_count == 0 else "failed"
    report = {
        "status": status,
        "generated_at": utc_now(),
        "project_path": str(state.path),
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": [asdict(issue) for issue in issues],
        "project": {
            "project_id": state.metadata.get("project_id"),
            "validation_status": validation.get("status"),
            "required_files_present": required_files,
        },
        "stages": stage_report,
        "data": data_report,
        "methods": methods_report,
        "result_validity": result_validity_report,
        "results": results_report,
        "bibliography": bibliography_report,
        "latex": latex_report,
        "pdf": pdf_report,
    }

    quality_dir = state.path / "quality_checks"
    quality_dir.mkdir(parents=True, exist_ok=True)
    _write_json(quality_dir / "quality_report.json", report)
    update_stage_status(state.path, "quality_checks", "draft" if status == "passed" else "failed")
    _set_quality_manifest(state.path)
    return report
