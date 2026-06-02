from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status


RESULT_VALIDITY_INPUTS = [
    "methods/run_manifest.yaml",
    "methods/method_requirements.json",
    "data/data_feasibility_report.json",
]

RESULT_VALIDITY_OUTPUTS = [
    "results/result_validity_report.json",
    "results/result_validity_report.md",
]


class ResultValidityError(RuntimeError):
    """Raised when result validity cannot be assessed or has not passed."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _project_relative_path(project_path: Path, relative: str) -> Path:
    candidate = (project_path / relative).resolve()
    try:
        candidate.relative_to(project_path.resolve())
    except ValueError as exc:
        raise ResultValidityError(f"Result path escapes project directory: {relative}") from exc
    return candidate


def _missing_outputs(project_path: Path, run_manifest: dict[str, Any]) -> list[str]:
    missing = []
    for relative in run_manifest.get("output_files") or []:
        if not _project_relative_path(project_path, str(relative)).exists():
            missing.append(str(relative))
    return missing


def _diagnose_failure(
    *,
    data_feasibility: dict[str, Any],
    run_manifest: dict[str, Any],
    metric_value: float | None,
    minimum_value: float | None,
    missing_outputs: list[str],
) -> tuple[list[str], list[str]]:
    causes: list[str] = []
    actions: list[str] = []
    data_decision = data_feasibility.get("decision")
    if data_decision not in {"pass", "conditional_pass"}:
        causes.append("data")
        actions.append("Return to data feasibility: add data, revise variables, or lower the research objective.")
    if data_decision == "conditional_pass":
        causes.append("data")
        actions.append("Treat conclusions as exploratory unless stronger data or external validation is added.")
    if run_manifest.get("status") != "success" or missing_outputs:
        causes.append("method")
        actions.append("Return to method verification: fix code execution and regenerate declared outputs.")
    if minimum_value is not None and metric_value is not None and metric_value < minimum_value:
        if "data" not in causes and data_decision == "pass":
            causes.append("method")
        actions.append("Inspect model design, feature construction, validation split, and class imbalance before writing Results.")
    if metric_value is None:
        causes.append("method")
        actions.append("Add a metric,value CSV output or set explicit validity criteria for non-tabular results.")
    if not causes:
        causes.append("research_plan")
        actions.append("Revise the expected claim strength or define a concrete result validity threshold.")
    return sorted(set(causes)), actions


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Result Validity Report",
        "",
        f"Decision: {report['decision']}",
        "",
        f"Primary metric: {report.get('primary_metric')}",
        "",
        f"Observed value: {report.get('observed_value')}",
        "",
        f"Minimum acceptable value: {report.get('minimum_value')}",
        "",
        "## Diagnosis",
        "",
    ]
    for cause in report.get("failure_causes") or ["None."]:
        lines.append(f"- {cause}")
    lines.extend(["", "## Recommended Backtracking", ""])
    for action in report.get("recommended_actions") or ["Proceed to Results writing."]:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def _set_result_validity_manifest(project_path: Path) -> None:
    manifest_path = project_path / "result_validity" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = RESULT_VALIDITY_INPUTS
    manifest["output_files"] = RESULT_VALIDITY_OUTPUTS
    _write_json(manifest_path, manifest)


def assess_result_validity(
    project: str | Path,
    *,
    primary_metric: str | None = None,
    minimum_value: float | None = None,
) -> dict[str, Any]:
    """Assess whether observed method outputs support the expected result claim."""
    state = load_project(project)
    run_manifest = _read_json(state.path / "methods" / "run_manifest.yaml")
    requirements = _read_json(state.path / "methods" / "method_requirements.json")
    data_feasibility = _read_json(state.path / "data" / "data_feasibility_report.json")
    metric = (primary_metric or requirements.get("primary_metric") or "f1").strip().lower()
    threshold = minimum_value if minimum_value is not None else requirements.get("minimum_primary_metric")
    threshold_float = _to_float(threshold)
    metrics = run_manifest.get("metrics") or {}
    observed = _to_float(metrics.get(metric))
    missing_outputs = _missing_outputs(state.path, run_manifest)
    issues = []
    if run_manifest.get("status") != "success":
        issues.append("Method run manifest is not successful.")
    if missing_outputs:
        issues.append("Declared method outputs are missing: " + ", ".join(missing_outputs))
    if threshold_float is not None and observed is None:
        issues.append(f"Primary metric {metric} is missing from parsed method metrics.")
    if threshold_float is not None and observed is not None and observed < threshold_float:
        issues.append(f"Primary metric {metric}={observed:.3f} is below threshold {threshold_float:.3f}.")

    if not issues and threshold_float is not None:
        decision = "pass"
    elif not issues:
        decision = "conditional_pass"
        issues.append("No explicit minimum result threshold was configured; result validity is conditional.")
    else:
        decision = "revise_required"

    causes, actions = _diagnose_failure(
        data_feasibility=data_feasibility,
        run_manifest=run_manifest,
        metric_value=observed,
        minimum_value=threshold_float,
        missing_outputs=missing_outputs,
    ) if decision == "revise_required" else ([], ["Proceed to Results writing while keeping claim strength aligned with the validity decision."])

    report = {
        "project_id": state.metadata.get("project_id"),
        "decision": decision,
        "primary_metric": metric,
        "observed_value": observed,
        "minimum_value": threshold_float,
        "issues": issues,
        "failure_causes": causes,
        "recommended_actions": actions,
        "missing_outputs": missing_outputs,
        "data_feasibility_decision": data_feasibility.get("decision"),
        "stale_if_changed": ["results", "discussion", "latex", "quality_checks"],
    }
    results_dir = state.path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    _write_json(results_dir / "result_validity_report.json", report)
    (results_dir / "result_validity_report.md").write_text(_render_md(report), encoding="utf-8")
    update_stage_status(state.path, "result_validity", "draft" if decision in {"pass", "conditional_pass"} else "failed")
    _set_result_validity_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "decision": decision,
        "failure_causes": causes,
        "result_validity_report": str(results_dir / "result_validity_report.json"),
        "outputs": RESULT_VALIDITY_OUTPUTS,
    }


def validate_result_validity_for_results(project_path: Path) -> dict[str, Any]:
    """Return validity report if Results may proceed; otherwise raise ResultValidityError."""
    report = _read_json(project_path / "results" / "result_validity_report.json")
    decision = report.get("decision")
    if decision not in {"pass", "conditional_pass"}:
        raise ResultValidityError(
            "Results writing requires result validity decision pass or conditional_pass. Current decision: "
            + str(decision)
        )
    return report
