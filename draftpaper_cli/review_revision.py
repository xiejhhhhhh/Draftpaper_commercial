from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now
from .project_state import load_project, mark_stage_stale


REVIEW_DIR = "review"
GATE_DIAGNOSIS_JSON = "review/gate_failure_diagnosis.json"
GATE_DIAGNOSIS_MD = "review/gate_failure_diagnosis.md"
REVIEW_REPORT_MD = "review/review_report.md"
REVIEWER_ISSUES_JSON = "review/reviewer_issues.json"
REVISION_PLAN_JSON = "review/revision_plan.json"
REVISION_PLAN_MD = "review/revision_plan.md"
COMMITMENT_LEDGER_CSV = "review/commitment_ledger.csv"
APPLY_REVISION_JSON = "review/apply_revision_report.json"
APPLY_REVISION_MD = "review/apply_revision_report.md"
RE_REVIEW_REPORT_MD = "review/re_review_report.md"
RE_REVIEW_REPORT_JSON = "review/re_review_report.json"


@dataclass
class RevisionIssue:
    issue_id: str
    source: str
    code: str
    severity: str
    target_stage: str
    title: str
    reason: str
    files_to_add_or_edit: list[str]
    recommended_commands: list[str]
    required_user_input: str
    status: str = "pending"


class ReviewRevisionError(RuntimeError):
    """Raised when the review/revision loop cannot load or write project artifacts."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""


def _review_dir(project_path: Path) -> Path:
    path = project_path / REVIEW_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _issue_id(source: str, code: str, target_stage: str, reason: str) -> str:
    digest = hashlib.sha256(f"{source}|{code}|{target_stage}|{reason}".encode("utf-8")).hexdigest()[:8]
    prefix = {
        "reviewer": "R",
        "data_feasibility": "D",
        "methods": "M",
        "result_validity": "V",
        "integrity": "I",
        "quality": "Q",
    }.get(source, "X")
    return f"{prefix}-{digest}"


def _commands_from_stage(target_stage: str) -> list[str]:
    mapping = {
        "references": ["search-literature", "generate-plan", "write-introduction", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "research_plan": ["generate-plan", "write-introduction", "collect-method-plan", "generate-analysis-code", "verify-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "data": ["inventory-data", "assess-data-quality", "assess-data-feasibility", "collect-method-plan", "generate-analysis-code", "verify-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "method_plan": ["collect-method-plan", "generate-analysis-code", "verify-methods", "write-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "code": ["generate-analysis-code", "verify-methods", "write-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "methods": ["generate-analysis-code", "verify-methods", "write-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "result_validity": ["assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "results": ["inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "discussion": ["write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "latex": ["assemble-latex", "run-integrity-gate", "quality-check"],
        "quality_checks": ["run-integrity-gate", "quality-check"],
    }
    return mapping.get(target_stage, ["status", "run-pipeline"])


def _issue(
    *,
    source: str,
    code: str,
    severity: str,
    target_stage: str,
    title: str,
    reason: str,
    files: list[str],
    user_input: str,
) -> RevisionIssue:
    return RevisionIssue(
        issue_id=_issue_id(source, code, target_stage, reason),
        source=source,
        code=code,
        severity=severity,
        target_stage=target_stage,
        title=title,
        reason=reason,
        files_to_add_or_edit=files,
        recommended_commands=_commands_from_stage(target_stage),
        required_user_input=user_input,
    )


def _dedupe_issues(issues: list[RevisionIssue]) -> list[RevisionIssue]:
    seen: set[str] = set()
    result: list[RevisionIssue] = []
    for issue in issues:
        if issue.issue_id in seen:
            continue
        seen.add(issue.issue_id)
        result.append(issue)
    return result


def _stage_for_integrity_issue(issue: dict[str, Any]) -> str:
    code = str(issue.get("code") or "")
    section = str(issue.get("section") or "")
    file_name = str(issue.get("file") or "")
    if "citation" in code or "bib" in code:
        if section in {"introduction", "data", "methods", "discussion"} and "section" in code:
            return section
        return "references"
    if "result" in code or file_name.startswith("results/"):
        return "results"
    return "quality_checks"


def _stage_for_quality_issue(issue: dict[str, Any]) -> str:
    file_name = str(issue.get("file") or "")
    if file_name.startswith("data/"):
        return "data"
    if file_name.startswith("methods/"):
        return "methods"
    if file_name.startswith("results/"):
        return "results"
    if file_name.startswith("references/") or "citation" in str(issue.get("code") or ""):
        return "references"
    if file_name.startswith("latex/"):
        return "latex"
    return "quality_checks"


def _render_issue_md(title: str, issues: list[RevisionIssue]) -> str:
    lines = [f"# {title}", "", f"Generated at: {utc_now()}", "", f"Issue count: {len(issues)}", ""]
    if not issues:
        lines.append("No revision issues were found.")
    for issue in issues:
        lines.extend([
            f"## {issue.issue_id}: {issue.title}",
            "",
            f"- Source: {issue.source}",
            f"- Severity: {issue.severity}",
            f"- Target stage: {issue.target_stage}",
            f"- Reason: {issue.reason}",
            f"- Files: {', '.join(issue.files_to_add_or_edit) or 'none'}",
            f"- Recommended commands: {', '.join(issue.recommended_commands)}",
            f"- User input: {issue.required_user_input}",
            "",
        ])
    return "\n".join(lines)


def diagnose_gate_failures(project: str | Path) -> dict[str, Any]:
    """Convert failed gate reports into actionable revision issues."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise ReviewRevisionError(str(exc)) from exc
    project_path = state.path
    issues: list[RevisionIssue] = []

    data_report = _read_json(project_path / "data" / "data_feasibility_report.json")
    if data_report and data_report.get("decision") not in {"pass", "conditional_pass"}:
        reason = "; ".join(str(item) for item in data_report.get("blocking_issues") or []) or f"Data feasibility decision is {data_report.get('decision')}."
        issues.append(_issue(
            source="data_feasibility",
            code=str(data_report.get("decision") or "data_gate_failed"),
            severity="blocking",
            target_stage="data",
            title="Data cannot support the current scientific goal",
            reason=reason,
            files=["data/raw", "data/processed", "data/data_feasibility_report.json", "research_plan/research_plan.md"],
            user_input="Decide whether to add data, revise variables, reduce claim strength, or change the research question.",
        ))

    run_manifest = _read_json(project_path / "methods" / "run_manifest.yaml")
    if run_manifest and run_manifest.get("status") != "success":
        missing = ", ".join(str(item) for item in run_manifest.get("missing_outputs") or [])
        reason = f"Method verification status is {run_manifest.get('status')}."
        if missing:
            reason += f" Missing outputs: {missing}."
        issues.append(_issue(
            source="methods",
            code="method_run_failed",
            severity="blocking",
            target_stage="methods",
            title="Method verification did not complete successfully",
            reason=reason,
            files=["code/scripts/run_analysis.py", "methods/run_manifest.yaml", "methods/method_requirements.json"],
            user_input="Confirm whether to fix generated code, change method requirements, or provide missing input data.",
        ))

    validity_report = _read_json(project_path / "results" / "result_validity_report.json")
    if validity_report and validity_report.get("decision") not in {"pass", "conditional_pass"}:
        causes = set(str(item) for item in validity_report.get("failure_causes") or [])
        target = "data" if "data" in causes else "methods" if "method" in causes else "research_plan"
        reason = "; ".join(str(item) for item in validity_report.get("issues") or validity_report.get("recommended_actions") or [])
        if not reason:
            reason = f"Result validity decision is {validity_report.get('decision')}."
        issues.append(_issue(
            source="result_validity",
            code=str(validity_report.get("decision") or "result_validity_failed"),
            severity="blocking",
            target_stage=target,
            title="Results do not support the planned claim strength",
            reason=reason,
            files=["results/result_validity_report.json", "methods/run_manifest.yaml", "methods/method_requirements.json"],
            user_input="Decide whether to revise the method/data route or lower the manuscript claim strength.",
        ))

    integrity_report = _read_json(project_path / "integrity" / "integrity_report.json")
    if integrity_report and integrity_report.get("status") != "passed":
        for raw in integrity_report.get("issues") or []:
            if str(raw.get("severity") or "") not in {"error", "blocking"}:
                continue
            target = _stage_for_integrity_issue(raw)
            issues.append(_issue(
                source="integrity",
                code=str(raw.get("code") or "integrity_failed"),
                severity="blocking",
                target_stage=target,
                title="Traceability or result-artifact integrity failed",
                reason=str(raw.get("message") or "Integrity gate failed."),
                files=[str(raw.get("file") or "integrity/integrity_report.json")],
                user_input="Fix the traceability table, section citations, result manifest, or missing local artifacts.",
            ))

    quality_report = _read_json(project_path / "quality_checks" / "quality_report.json")
    if quality_report and quality_report.get("status") != "passed":
        for raw in quality_report.get("issues") or []:
            if str(raw.get("severity") or "") != "error":
                continue
            target = _stage_for_quality_issue(raw)
            issues.append(_issue(
                source="quality",
                code=str(raw.get("code") or "quality_failed"),
                severity="major",
                target_stage=target,
                title="Final quality gate failed",
                reason=str(raw.get("message") or "Quality gate failed."),
                files=[str(raw.get("file") or "quality_checks/quality_report.json")],
                user_input="Repair the affected upstream stage, rerun assembly, then rerun integrity and quality checks.",
            ))

    issues = _dedupe_issues(issues)
    review_dir = _review_dir(project_path)
    report = {
        "status": "issues_found" if issues else "passed",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "issue_count": len(issues),
        "issues": [asdict(issue) for issue in issues],
    }
    _write_json(review_dir / "gate_failure_diagnosis.json", report)
    (review_dir / "gate_failure_diagnosis.md").write_text(_render_issue_md("Gate Failure Diagnosis", issues), encoding="utf-8")
    return report


def review_draft(project: str | Path) -> dict[str, Any]:
    """Run a deterministic reviewer-style pass and emit review issues."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise ReviewRevisionError(str(exc)) from exc
    project_path = state.path
    issues: list[RevisionIssue] = []
    main_tex = _read_text(project_path / "latex" / "main.tex")
    results_tex = _read_text(project_path / "results" / "results.tex")
    discussion_tex = _read_text(project_path / "discussion" / "discussion.tex")
    methods_manifest = _read_json(project_path / "methods" / "run_manifest.yaml")
    validity = _read_json(project_path / "results" / "result_validity_report.json")

    if not main_tex.strip():
        issues.append(_issue(
            source="reviewer",
            code="missing_assembled_latex",
            severity="major",
            target_stage="latex",
            title="No assembled manuscript was found for review",
            reason="latex/main.tex is missing or empty, so the reviewer pass cannot inspect the full draft.",
            files=["latex/main.tex"],
            user_input="Run LaTeX assembly after upstream sections are current.",
        ))
    if methods_manifest.get("status") != "success":
        issues.append(_issue(
            source="reviewer",
            code="methods_not_reproducible",
            severity="blocking",
            target_stage="methods",
            title="Methods are not yet reproducible from a successful run manifest",
            reason="A reviewer would not accept a Methods section whose local verification manifest is missing or failed.",
            files=["methods/run_manifest.yaml", "code/scripts/run_analysis.py"],
            user_input="Fix or rerun method verification before relying on the method narrative.",
        ))
    if validity.get("decision") == "conditional_pass":
        issues.append(_issue(
            source="reviewer",
            code="claim_strength_conditional",
            severity="major",
            target_stage="results",
            title="Result claims should be framed as exploratory or conditional",
            reason="The result validity gate is conditional, so Results and Discussion should avoid confirmatory language.",
            files=["results/result_validity_report.json", "results/results.tex", "discussion/discussion.tex"],
            user_input="Confirm whether to lower the claim strength or improve data/method evidence.",
        ))
    elif validity and validity.get("decision") not in {"pass", "conditional_pass"}:
        issues.append(_issue(
            source="reviewer",
            code="unsupported_result_claim",
            severity="blocking",
            target_stage="results",
            title="Results do not yet support the manuscript claims",
            reason="The reviewer layer sees a failed result-validity decision, so the draft should not proceed as a completed manuscript.",
            files=["results/result_validity_report.json", "results/results.tex"],
            user_input="Revise method/data or lower the research claim before final review.",
        ))
    if results_tex.strip() and not discussion_tex.strip():
        issues.append(_issue(
            source="reviewer",
            code="missing_discussion",
            severity="major",
            target_stage="discussion",
            title="Discussion is missing after Results exist",
            reason="A reviewer expects the Discussion to compare findings, limitations, and implications after Results are drafted.",
            files=["discussion/discussion.tex", "results/results.tex"],
            user_input="Run or revise Discussion writing after Results are current.",
        ))

    issues = _dedupe_issues(issues)
    review_dir = _review_dir(project_path)
    payload = {
        "status": "reviewed",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "issue_count": len(issues),
        "issues": [asdict(issue) for issue in issues],
    }
    _write_json(review_dir / "reviewer_issues.json", payload)
    (review_dir / "review_report.md").write_text(_render_issue_md("Reviewer Draft Report", issues), encoding="utf-8")
    return payload


def _load_issue_payload(path: Path) -> list[RevisionIssue]:
    payload = _read_json(path)
    issues: list[RevisionIssue] = []
    for raw in payload.get("issues") or []:
        try:
            issues.append(RevisionIssue(**{field: raw.get(field) for field in RevisionIssue.__dataclass_fields__}))
        except TypeError:
            continue
    return issues


def _write_commitment_ledger(path: Path, issues: list[RevisionIssue]) -> None:
    fieldnames = ["issue_id", "source", "target_stage", "decision", "status", "commitment", "updated_at"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for issue in issues:
            writer.writerow({
                "issue_id": issue.issue_id,
                "source": issue.source,
                "target_stage": issue.target_stage,
                "decision": "revise",
                "status": issue.status,
                "commitment": issue.required_user_input,
                "updated_at": utc_now(),
            })


def generate_revision_plan(project: str | Path) -> dict[str, Any]:
    """Merge gate diagnosis and reviewer issues into a staged revision plan."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise ReviewRevisionError(str(exc)) from exc
    project_path = state.path
    review_dir = _review_dir(project_path)
    if not (review_dir / "gate_failure_diagnosis.json").exists():
        diagnose_gate_failures(project_path)

    issues = []
    issues.extend(_load_issue_payload(review_dir / "gate_failure_diagnosis.json"))
    issues.extend(_load_issue_payload(review_dir / "reviewer_issues.json"))
    issues = _dedupe_issues(issues)
    by_stage: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        by_stage.setdefault(issue.target_stage, []).append(asdict(issue))
    plan = {
        "status": "revision_required" if issues else "no_revision_needed",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "issue_count": len(issues),
        "issues": [asdict(issue) for issue in issues],
        "by_stage": by_stage,
        "recommended_stage_order": _recommended_stage_order(issues),
    }
    _write_json(review_dir / "revision_plan.json", plan)
    (review_dir / "revision_plan.md").write_text(_render_issue_md("Revision Plan", issues), encoding="utf-8")
    _write_commitment_ledger(review_dir / "commitment_ledger.csv", issues)
    return plan


def _recommended_stage_order(issues: list[RevisionIssue]) -> list[str]:
    order = ["references", "research_plan", "data", "method_plan", "code", "methods", "result_validity", "results", "discussion", "latex", "quality_checks"]
    present = {issue.target_stage for issue in issues}
    return [stage for stage in order if stage in present]


def apply_revision(project: str | Path, *, issue_ids: list[str] | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Apply the safe part of a revision plan by marking affected stages stale."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise ReviewRevisionError(str(exc)) from exc
    project_path = state.path
    plan_path = project_path / "review" / "revision_plan.json"
    if not plan_path.exists():
        generate_revision_plan(project_path)
    plan = _read_json(plan_path)
    selected = set(issue_ids or [])
    issues = [issue for issue in plan.get("issues") or [] if not selected or issue.get("issue_id") in selected]
    target_stages = sorted({str(issue.get("target_stage")) for issue in issues if issue.get("target_stage")})
    stale_changes: dict[str, list[str]] = {}
    if not dry_run:
        for stage in target_stages:
            stale_changes[stage] = mark_stage_stale(project_path, stage, include_self=True)
    report = {
        "status": "dry_run" if dry_run else "applied",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "issue_count": len(issues),
        "target_stages": target_stages,
        "stale_changes": stale_changes,
        "message": "Scientific content was not edited automatically; affected stages were marked stale for explicit rerun.",
    }
    review_dir = _review_dir(project_path)
    _write_json(review_dir / "apply_revision_report.json", report)
    (review_dir / "apply_revision_report.md").write_text(_render_apply_md(report), encoding="utf-8")
    return report


def _render_apply_md(report: dict[str, Any]) -> str:
    lines = [
        "# Apply Revision Report",
        "",
        f"Status: {report['status']}",
        f"Generated at: {report['generated_at']}",
        "",
        "Scientific content was not edited automatically. The CLI marked affected stages stale so the normal staged workflow can rerun them.",
        "",
        "## Target Stages",
        "",
    ]
    for stage in report.get("target_stages") or ["none"]:
        lines.append(f"- {stage}")
    lines.append("")
    return "\n".join(lines)


def re_review(project: str | Path) -> dict[str, Any]:
    """Rerun gate diagnosis, reviewer pass, and revision planning after revisions."""
    diagnosis = diagnose_gate_failures(project)
    review = review_draft(project)
    plan = generate_revision_plan(project)
    project_path = Path(plan["project_path"])
    report = {
        "status": "passed" if plan.get("issue_count") == 0 else "revision_required",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "gate_issue_count": diagnosis.get("issue_count", 0),
        "reviewer_issue_count": review.get("issue_count", 0),
        "revision_issue_count": plan.get("issue_count", 0),
        "revision_plan": REVISION_PLAN_JSON,
    }
    review_dir = _review_dir(project_path)
    _write_json(review_dir / "re_review_report.json", report)
    (review_dir / "re_review_report.md").write_text(_render_re_review_md(report), encoding="utf-8")
    return report


def _render_re_review_md(report: dict[str, Any]) -> str:
    return (
        "# Re-review Report\n\n"
        f"Status: {report['status']}\n\n"
        f"Gate issues: {report['gate_issue_count']}\n\n"
        f"Reviewer issues: {report['reviewer_issue_count']}\n\n"
        f"Revision issues: {report['revision_issue_count']}\n\n"
        f"Revision plan: {report['revision_plan']}\n"
    )
