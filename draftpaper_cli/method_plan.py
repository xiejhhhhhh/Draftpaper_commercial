from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status


METHOD_PLAN_INPUTS = [
    "research_plan/research_plan.md",
    "references/literature_items.json",
    "data/data_feasibility_report.json",
]

METHOD_PLAN_OUTPUTS = [
    "methods/method_plan.md",
    "methods/method_requirements.json",
]


class MethodPlanError(RuntimeError):
    """Raised when method planning cannot be completed from project inputs."""


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return fallback


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _extract_literature_methods(items: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    extracted: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda entry: entry.get("citation_weight", 0), reverse=True):
        summary = item.get("deep_summary") or {}
        method_text = str(summary.get("methods") or item.get("abstract") or "").strip()
        if not method_text:
            continue
        extracted.append({
            "citation_key": item.get("bibtex_key", ""),
            "title": item.get("title", ""),
            "publication": item.get("publication", ""),
            "citation_weight": item.get("citation_weight", 0),
            "method_summary": method_text[:800],
        })
        if len(extracted) >= limit:
            break
    return extracted


def _infer_method_families(text: str) -> list[str]:
    lowered = text.lower()
    families = []
    candidates = [
        ("time_series_deep_learning", ["light curve", "time series", "temporal", "tcn", "lstm", "transformer"]),
        ("multimodal_learning", ["multimodal", "spectral", "multi-wavelength", "multiwavelength", "hardness"]),
        ("classical_machine_learning", ["random forest", "svm", "xgboost", "gradient boosting"]),
        ("representation_learning", ["contrastive", "self-supervised", "representation"]),
        ("external_validation", ["external validation", "generalization", "validation set"]),
    ]
    for label, terms in candidates:
        if any(term in lowered for term in terms):
            families.append(label)
    return families or ["method_family_requires_user_confirmation"]


def _infer_required_features(text: str) -> list[str]:
    lowered = text.lower()
    features = []
    candidates = [
        ("label", ["classification", "supervised", "class label", "target"]),
        ("light_curve", ["light curve", "time series", "variability"]),
        ("spectral_features", ["spectral", "spectrum", "hardness", "energy"]),
        ("multiwavelength_features", ["multi-wavelength", "multiwavelength", "photometric", "optical", "radio"]),
        ("external_validation_split", ["external validation", "generalization"]),
    ]
    for label, terms in candidates:
        if any(term in lowered for term in terms):
            features.append(label)
    return features


def _render_method_plan_md(
    *,
    idea: str,
    user_method: str,
    method_families: list[str],
    required_features: list[str],
    literature_methods: list[dict[str, Any]],
    feasibility: dict[str, Any],
    primary_metric: str,
    minimum_primary_metric: float | None,
) -> str:
    lines = [
        "# Method Plan",
        "",
        f"Research idea: {idea}",
        "",
        "## User-Provided Method Direction",
        "",
        user_method.strip() or "No explicit user method note was provided. The method plan is inferred from the research plan and literature methods.",
        "",
        "## Literature-Informed Method Synthesis",
        "",
    ]
    if literature_methods:
        for item in literature_methods:
            lines.extend([
                f"### {item.get('citation_key') or 'uncited_method'}",
                "",
                f"Title: {item.get('title')}",
                "",
                f"Venue: {item.get('publication') or 'n/a'}; citation weight: {item.get('citation_weight')}",
                "",
                item.get("method_summary") or "No method summary available.",
                "",
            ])
    else:
        lines.extend([
            "No method summaries were available from the current literature metadata. Add literature items with abstracts or deep summaries before treating this plan as stable.",
            "",
        ])
    lines.extend([
        "## Proposed Method Families",
        "",
        ", ".join(method_families),
        "",
        "## Data Requirements Implied by Method",
        "",
        ", ".join(required_features) if required_features else "No concrete feature requirements were inferred; user confirmation is required.",
        "",
        "## Result Validity Expectations",
        "",
        f"Primary metric: {primary_metric}",
        "",
        f"Minimum acceptable value: {minimum_primary_metric if minimum_primary_metric is not None else 'not specified; result validity will be conditional without a threshold'}",
        "",
        "## Data-Method Fit",
        "",
        f"Current data feasibility decision: {feasibility.get('decision', 'missing')}",
        "",
        "The method can proceed only if data feasibility is pass or conditional_pass, method verification succeeds, and result validity later confirms that observed outputs support the expected claim strength.",
        "",
    ])
    return "\n".join(lines)


def _set_method_plan_manifest(project_path: Path) -> None:
    manifest_path = project_path / "method_plan" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = METHOD_PLAN_INPUTS
    manifest["output_files"] = METHOD_PLAN_OUTPUTS
    _write_json(manifest_path, manifest)


def collect_method_plan(
    project: str | Path,
    *,
    user_method: str = "",
    primary_metric: str = "f1",
    minimum_primary_metric: float | None = None,
) -> dict[str, Any]:
    """Collect user method intent and synthesize method requirements from literature."""
    state = load_project(project)
    plan_text = _read_text(state.path / "research_plan" / "research_plan.md")
    literature_items = _read_json(state.path / "references" / "literature_items.json", [])
    if not isinstance(literature_items, list):
        raise MethodPlanError("references/literature_items.json must contain a list.")
    feasibility = _read_json(state.path / "data" / "data_feasibility_report.json", {})
    combined_text = " ".join([
        state.metadata.get("idea", ""),
        plan_text,
        user_method,
        " ".join(str((item.get("deep_summary") or {}).get("methods") or item.get("abstract") or "") for item in literature_items),
    ])
    method_families = _infer_method_families(combined_text)
    required_features = _infer_required_features(combined_text)
    literature_methods = _extract_literature_methods(literature_items)
    requirements = {
        "project_id": state.metadata.get("project_id"),
        "user_method": user_method,
        "method_families": method_families,
        "required_data_features": required_features,
        "primary_metric": re.sub(r"[^A-Za-z0-9_:-]+", "_", primary_metric.strip().lower()) or "f1",
        "minimum_primary_metric": minimum_primary_metric,
        "literature_method_count": len(literature_methods),
        "literature_methods": literature_methods,
        "data_feasibility_decision": feasibility.get("decision"),
        "method_data_fit": "proceed" if feasibility.get("decision") in {"pass", "conditional_pass"} else "needs_data_or_goal_revision",
        "stale_if_changed": ["methods", "result_validity", "results", "discussion", "latex", "quality_checks"],
    }
    methods_dir = state.path / "methods"
    methods_dir.mkdir(parents=True, exist_ok=True)
    _write_json(methods_dir / "method_requirements.json", requirements)
    (methods_dir / "method_plan.md").write_text(
        _render_method_plan_md(
            idea=state.metadata.get("idea", ""),
            user_method=user_method,
            method_families=method_families,
            required_features=required_features,
            literature_methods=literature_methods,
            feasibility=feasibility,
            primary_metric=requirements["primary_metric"],
            minimum_primary_metric=minimum_primary_metric,
        ),
        encoding="utf-8",
    )
    update_stage_status(state.path, "method_plan", "draft")
    _set_method_plan_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "method_plan": str(methods_dir / "method_plan.md"),
        "method_requirements": str(methods_dir / "method_requirements.json"),
        "method_data_fit": requirements["method_data_fit"],
        "literature_method_count": len(literature_methods),
        "outputs": METHOD_PLAN_OUTPUTS,
    }


def validate_method_plan_for_methods(project_path: Path) -> dict[str, Any]:
    """Return method requirements if Methods may proceed; otherwise raise MethodPlanError."""
    state = load_project(project_path)
    stage = (state.metadata.get("stages") or {}).get("method_plan") or {}
    if stage.get("stale") or stage.get("status") not in {"draft", "approved", "completed"}:
        raise MethodPlanError("Methods require a non-stale method_plan stage before code verification or writing.")
    requirements = _read_json(project_path / "methods" / "method_requirements.json", {})
    if not requirements:
        raise MethodPlanError("methods/method_requirements.json is required before Methods.")
    if requirements.get("method_data_fit") == "needs_data_or_goal_revision":
        raise MethodPlanError("Method plan says current data or research goal must be revised before Methods.")
    return requirements
