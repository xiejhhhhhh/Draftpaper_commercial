from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status


DATA_INVENTORY_OUTPUT = "data/data_inventory.json"
DATA_QUALITY_OUTPUT = "data/data_quality_report.json"
DATA_FEASIBILITY_JSON = "data/data_feasibility_report.json"
DATA_FEASIBILITY_MD = "data/data_feasibility_report.md"

DATA_OUTPUTS = [
    DATA_INVENTORY_OUTPUT,
    DATA_QUALITY_OUTPUT,
    DATA_FEASIBILITY_JSON,
    DATA_FEASIBILITY_MD,
]

TABULAR_EXTENSIONS = {".csv", ".tsv"}
DATA_EXTENSIONS = TABULAR_EXTENSIONS | {".json", ".xlsx", ".xls", ".parquet", ".txt", ".fits", ".fit", ".h5", ".hdf5", ".npy", ".npz"}


class DataGateError(RuntimeError):
    """Raised when data inventory, quality, or feasibility cannot be assessed."""


def _project_relative(project_path: Path, path: Path) -> str:
    return path.relative_to(project_path).as_posix()


def _read_tabular_profile(path: Path) -> dict[str, Any]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            columns = list(reader.fieldnames or [])
            row_count = 0
            missing_cells = 0
            total_cells = 0
            for row in reader:
                row_count += 1
                for column in columns:
                    total_cells += 1
                    value = row.get(column)
                    if value is None or str(value).strip() == "":
                        missing_cells += 1
    except UnicodeDecodeError:
        return {"readable": False, "columns": [], "row_count": None, "column_count": None, "missing_cells": None, "total_cells": None}
    return {
        "readable": True,
        "columns": columns,
        "row_count": row_count,
        "column_count": len(columns),
        "missing_cells": missing_cells,
        "total_cells": total_cells,
        "missing_cell_ratio": (missing_cells / total_cells) if total_cells else 0.0,
    }


def inventory_data(project: str | Path) -> dict[str, Any]:
    """Inventory local data files under data/raw and data/processed."""
    state = load_project(project)
    files = []
    for base in [state.path / "data" / "raw", state.path / "data" / "processed"]:
        base.mkdir(parents=True, exist_ok=True)
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.name.startswith(".") or path.name.endswith(".tex"):
                continue
            if path.suffix.lower() not in DATA_EXTENSIONS:
                continue
            profile = _read_tabular_profile(path) if path.suffix.lower() in TABULAR_EXTENSIONS else {
                "readable": None,
                "columns": [],
                "row_count": None,
                "column_count": None,
                "missing_cells": None,
                "total_cells": None,
                "missing_cell_ratio": None,
            }
            files.append({
                "path": _project_relative(state.path, path),
                "kind": "raw" if "data/raw" in _project_relative(state.path, path) else "processed",
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                **profile,
            })
    payload = {
        "project_id": state.metadata.get("project_id"),
        "file_count": len(files),
        "files": files,
        "total_rows": sum(int(item.get("row_count") or 0) for item in files),
        "tabular_file_count": sum(1 for item in files if item.get("suffix") in TABULAR_EXTENSIONS),
    }
    _write_json(state.path / DATA_INVENTORY_OUTPUT, payload)
    _set_data_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "data_inventory": str(state.path / DATA_INVENTORY_OUTPUT),
        "file_count": len(files),
        "total_rows": payload["total_rows"],
    }


def _load_json(project_path: Path, relative: str) -> dict[str, Any]:
    path = project_path / relative
    if not path.exists():
        raise DataGateError(f"{relative} is required.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise DataGateError(f"{relative} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise DataGateError(f"{relative} must contain an object.")
    return payload


def assess_data_quality(project: str | Path, *, required_columns: list[str] | None = None, max_missing_ratio: float = 0.2) -> dict[str, Any]:
    """Assess basic local data quality from data_inventory.json."""
    state = load_project(project)
    inventory = _load_json(state.path, DATA_INVENTORY_OUTPUT)
    required = [column for column in (required_columns or []) if column]
    all_columns = set()
    total_missing = 0
    total_cells = 0
    unreadable_files = []
    for item in inventory.get("files") or []:
        all_columns.update(item.get("columns") or [])
        total_missing += int(item.get("missing_cells") or 0)
        total_cells += int(item.get("total_cells") or 0)
        if item.get("readable") is False:
            unreadable_files.append(item.get("path"))
    missing_required = sorted(set(required) - all_columns)
    missing_ratio = (total_missing / total_cells) if total_cells else 0.0
    issues = []
    if not inventory.get("file_count"):
        issues.append("No local data files were found under data/raw or data/processed.")
    if missing_required:
        issues.append("Missing required columns: " + ", ".join(missing_required))
    if missing_ratio > max_missing_ratio:
        issues.append(f"Overall missing-cell ratio {missing_ratio:.3f} exceeds threshold {max_missing_ratio:.3f}.")
    if unreadable_files:
        issues.append("Some tabular files could not be read: " + ", ".join(str(item) for item in unreadable_files))
    overall = "pass" if not issues else "warning"
    payload = {
        "project_id": state.metadata.get("project_id"),
        "overall_status": overall,
        "required_columns": required,
        "missing_required_columns": missing_required,
        "overall_missing_cell_ratio": missing_ratio,
        "max_missing_ratio": max_missing_ratio,
        "unreadable_files": unreadable_files,
        "issues": issues,
        "total_rows": inventory.get("total_rows", 0),
        "file_count": inventory.get("file_count", 0),
    }
    _write_json(state.path / DATA_QUALITY_OUTPUT, payload)
    _set_data_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "data_quality_report": str(state.path / DATA_QUALITY_OUTPUT),
        "overall_status": overall,
        "issue_count": len(issues),
    }


def _plan_requires_external_validation(plan_text: str) -> bool:
    lowered = plan_text.lower()
    return "external validation" in lowered or "generalizable" in lowered or "generalization" in lowered


def _plan_is_exploratory(plan_text: str) -> bool:
    lowered = plan_text.lower()
    return "exploratory" in lowered or "pilot" in lowered or "preliminary" in lowered


def _render_feasibility_md(report: dict[str, Any]) -> str:
    lines = [
        "# Data Feasibility Report",
        "",
        f"Decision: {report['decision']}",
        "",
        f"Scientific goal supported: {str(report['scientific_goal_supported']).lower()}",
        "",
        f"Supported claim level: {report['supported_claim_level']}",
        "",
        "## Blocking Issues",
        "",
    ]
    for issue in report.get("blocking_issues") or ["None."]:
        lines.append(f"- {issue}")
    lines.extend(["", "## Recommended Actions", ""])
    for action in report.get("recommended_actions") or ["Proceed with the current staged workflow."]:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def assess_data_feasibility(project: str | Path, *, min_rows: int = 30) -> dict[str, Any]:
    """Assess whether current local data can support the research plan."""
    state = load_project(project)
    quality = _load_json(state.path, DATA_QUALITY_OUTPUT)
    plan_path = state.path / "research_plan" / "research_plan.md"
    plan_text = plan_path.read_text(encoding="utf-8") if plan_path.exists() else ""
    total_rows = int(quality.get("total_rows") or 0)
    missing_required = list(quality.get("missing_required_columns") or [])
    issues: list[str] = []
    actions: list[str] = []

    if total_rows < min_rows:
        issues.append(f"Total tabular row count {total_rows} is below the minimum threshold {min_rows}.")
        actions.append("Add more observations or reduce the scope to a small exploratory analysis.")
    if missing_required:
        issues.append("Required variables are missing: " + ", ".join(missing_required))
        actions.append("Provide data containing the missing variables or revise the research question.")
    if _plan_requires_external_validation(plan_text) and "external_validation_id" in missing_required:
        issues.append("The research plan requires external validation, but no external validation identifier or split is available.")
        actions.append("Collect or define an external validation dataset before making generalizable prediction claims.")
    if quality.get("overall_missing_cell_ratio", 0) > quality.get("max_missing_ratio", 0.2):
        issues.append("Missingness exceeds the configured quality threshold.")
        actions.append("Impute, filter, or recollect data before model verification.")

    if not issues and _plan_is_exploratory(plan_text):
        decision = "conditional_pass"
        scientific_goal_supported = True
        claim_level = "exploratory or pilot claims only"
        actions.append("Keep conclusion strength aligned with the exploratory or pilot study framing.")
    elif not issues:
        decision = "pass"
        scientific_goal_supported = True
        claim_level = "planned confirmatory or predictive claims are supportable by the current data gate"
    elif total_rows >= min_rows and not missing_required:
        decision = "conditional_pass"
        scientific_goal_supported = False
        claim_level = "exploratory or pilot claims only"
        actions.append("Lower conclusion strength and explicitly describe limitations in Results and Discussion.")
    elif total_rows >= max(3, min_rows // 2):
        decision = "revise_required"
        scientific_goal_supported = False
        claim_level = "insufficient for the stated scientific goal without revision"
    else:
        decision = "blocked"
        scientific_goal_supported = False
        claim_level = "insufficient for the stated scientific goal"

    if not actions:
        actions.append("Proceed to Methods with the current data assumptions.")

    report = {
        "project_id": state.metadata.get("project_id"),
        "decision": decision,
        "scientific_goal_supported": scientific_goal_supported,
        "supported_claim_level": claim_level,
        "min_rows": min_rows,
        "observed_rows": total_rows,
        "blocking_issues": issues,
        "recommended_actions": actions,
        "stale_if_goal_changes": ["research_plan", "introduction", "method_plan", "methods", "result_validity", "results", "discussion", "latex", "quality_checks"],
    }
    _write_json(state.path / DATA_FEASIBILITY_JSON, report)
    (state.path / DATA_FEASIBILITY_MD).write_text(_render_feasibility_md(report), encoding="utf-8")
    update_stage_status(state.path, "data", "draft" if decision in {"pass", "conditional_pass"} else "failed")
    _set_data_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "decision": decision,
        "data_feasibility_report": str(state.path / DATA_FEASIBILITY_JSON),
        "scientific_goal_supported": scientific_goal_supported,
    }


def _set_data_manifest(project_path: Path) -> None:
    manifest_path = project_path / "data" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = ["research_plan/research_plan.md", "data/raw", "data/processed"]
    manifest["output_files"] = DATA_OUTPUTS
    _write_json(manifest_path, manifest)


def validate_data_feasibility_for_methods(project_path: Path) -> dict[str, Any]:
    """Return feasibility report if Methods may proceed; otherwise raise DataGateError."""
    report = _load_json(project_path, DATA_FEASIBILITY_JSON)
    decision = report.get("decision")
    if decision not in {"pass", "conditional_pass"}:
        raise DataGateError(
            "Methods writing requires data feasibility decision pass or conditional_pass. Current decision: "
            + str(decision)
        )
    return report
