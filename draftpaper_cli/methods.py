from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .data_feasibility import DataGateError, validate_data_feasibility_for_methods
from .method_plan import MethodPlanError, validate_method_plan_for_methods
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, update_stage_status


METHOD_INPUTS = [
    "methods/method_plan.md",
    "methods/method_requirements.json",
    "methods/run_manifest.yaml",
]

METHOD_OUTPUTS = [
    "methods/methods.tex",
]


class MethodsGateError(RuntimeError):
    """Raised when Methods writing is attempted before successful code verification."""


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise MethodsGateError(f"methods/run_manifest.yaml is not valid JSON-compatible YAML: {exc}") from exc


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    _write_json(path, payload)


def _ensure_method_plan(project_path: Path) -> Path:
    path = project_path / "methods" / "method_plan.md"
    if not path.exists():
        state = load_project(project_path)
        content = (
            "# Method Plan\n\n"
            f"Research idea: {state.metadata.get('idea')}\n\n"
            "This file is a planning placeholder. Formal `methods.tex` can only be generated after "
            "`methods/run_manifest.yaml` records a successful method/code run and all declared output files exist.\n"
        )
        path.write_text(content, encoding="utf-8")
    return path


def _project_relative_path(project_path: Path, relative: str) -> Path:
    candidate = (project_path / relative).resolve()
    try:
        candidate.relative_to(project_path.resolve())
    except ValueError as exc:
        raise MethodsGateError(f"Output path escapes project directory: {relative}") from exc
    return candidate


def _missing_declared_outputs(project_path: Path, manifest: dict[str, Any]) -> list[str]:
    missing = []
    for relative in manifest.get("output_files") or []:
        if not _project_relative_path(project_path, str(relative)).exists():
            missing.append(str(relative))
    return missing


def verify_methods(
    project: str | Path,
    *,
    command: str,
    output_files: list[str] | None = None,
    input_data: list[str] | None = None,
) -> dict[str, Any]:
    """Run a method verification command and write methods/run_manifest.yaml."""
    state = load_project(project)
    try:
        validate_method_plan_for_methods(state.path)
    except MethodPlanError as exc:
        raise MethodsGateError(str(exc)) from exc
    methods_dir = state.path / "methods"
    methods_dir.mkdir(parents=True, exist_ok=True)
    _ensure_method_plan(state.path)

    started_at = utc_now()
    completed = subprocess.run(command, cwd=state.path, shell=True, capture_output=True, text=True)
    finished_at = utc_now()
    declared_outputs = output_files or []
    missing_outputs = _missing_declared_outputs(state.path, {"output_files": declared_outputs})
    status = "success" if completed.returncode == 0 and not missing_outputs else "failed"
    manifest = {
        "status": status,
        "command": command,
        "returncode": completed.returncode,
        "input_data": input_data or [],
        "output_files": declared_outputs,
        "metrics": _read_metrics_from_outputs(state.path, declared_outputs),
        "figures_generated": [item for item in declared_outputs if item.lower().endswith((".png", ".jpg", ".jpeg", ".pdf", ".svg"))],
        "tables_generated": [item for item in declared_outputs if item.lower().endswith((".csv", ".tsv", ".xlsx", ".json"))],
        "started_at": started_at,
        "finished_at": finished_at,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "missing_outputs": missing_outputs,
    }
    _write_manifest(methods_dir / "run_manifest.yaml", manifest)
    update_stage_status(state.path, "methods", "approved" if status == "success" else "failed")
    return {
        "status": status,
        "project_path": str(state.path),
        "run_manifest": str(methods_dir / "run_manifest.yaml"),
        "returncode": completed.returncode,
        "missing_outputs": missing_outputs,
    }


def _read_metrics_from_outputs(project_path: Path, output_files: list[str]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for relative in output_files:
        path = _project_relative_path(project_path, relative)
        if not path.exists() or path.suffix.lower() != ".csv":
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeDecodeError:
            continue
        if len(lines) < 2:
            continue
        header = [part.strip().lower() for part in lines[0].split(",")]
        if header[:2] != ["metric", "value"]:
            continue
        for line in lines[1:]:
            parts = [part.strip() for part in line.split(",", 1)]
            if len(parts) == 2 and parts[0]:
                metrics[parts[0]] = parts[1]
    return metrics


def _safe_latex_text(text: Any) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in str(text or ""))


def _validate_successful_manifest(project_path: Path) -> dict[str, Any]:
    _ensure_method_plan(project_path)
    try:
        validate_method_plan_for_methods(project_path)
    except MethodPlanError as exc:
        raise MethodsGateError(str(exc)) from exc
    try:
        validate_data_feasibility_for_methods(project_path)
    except DataGateError as exc:
        raise MethodsGateError(str(exc)) from exc
    manifest_path = project_path / "methods" / "run_manifest.yaml"
    if not manifest_path.exists():
        raise MethodsGateError("methods/run_manifest.yaml is required before writing methods.tex.")
    manifest = _read_manifest(manifest_path)
    if manifest.get("status") != "success":
        raise MethodsGateError("methods/run_manifest.yaml must have status=success before writing methods.tex.")
    missing = _missing_declared_outputs(project_path, manifest)
    if missing:
        raise MethodsGateError("Declared method output files are missing: " + ", ".join(missing))
    return manifest


def _render_methods_tex(project_meta: dict[str, Any], manifest: dict[str, Any]) -> str:
    metrics = manifest.get("metrics") or {}
    outputs = manifest.get("output_files") or []
    output_text = ", ".join(_safe_latex_text(output) for output in outputs) if outputs else "no explicit output files were declared"
    metric_text = ", ".join(f"{_safe_latex_text(key)}={_safe_latex_text(value)}" for key, value in metrics.items()) if metrics else "no scalar metrics were parsed"
    command = _safe_latex_text(manifest.get("command") or "manual verification")
    idea = _safe_latex_text(project_meta.get("idea"))
    return (
        "\\section{Methods}\n"
        f"The method workflow for {idea} was written only after the local verification command completed successfully. "
        f"The recorded command was \\texttt{{{command}}}, and the verification manifest declares the following reproducible outputs: {output_text}. "
        "This gate ensures that the method description is tied to executable code and observed artifacts rather than to an unsupported methodological narrative.\n\n"
        f"The verified workflow reports {metric_text}. These values should be treated as implementation evidence for drafting the Methods section and should be updated whenever the code, input data, or validation design changes. "
        "The final manuscript should describe data preprocessing, model construction, validation protocol, and uncertainty handling in the same order as the verified pipeline.\n"
    )


def _set_methods_manifest(project_path: Path) -> None:
    manifest_path = project_path / "methods" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = METHOD_INPUTS
    manifest["output_files"] = METHOD_OUTPUTS
    _write_json(manifest_path, manifest)


def write_methods(project: str | Path) -> dict[str, Any]:
    """Write methods.tex only if methods/run_manifest.yaml proves a successful run."""
    state = load_project(project)
    manifest = _validate_successful_manifest(state.path)
    methods_dir = state.path / "methods"
    output_path = methods_dir / "methods.tex"
    output_path.write_text(_render_methods_tex(state.metadata, manifest), encoding="utf-8")
    update_stage_status(state.path, "methods", "draft")
    _set_methods_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "methods": str(output_path),
        "run_manifest": str(methods_dir / "run_manifest.yaml"),
        "outputs": METHOD_OUTPUTS,
    }
