from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status
from .result_validity import ResultValidityError, validate_result_validity_for_results


RESULT_INPUTS = [
    "results/result_validity_report.json",
    "results/result_manifest.yaml",
]

RESULT_OUTPUTS = [
    "results/results.tex",
]

FIGURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".svg"}
TABLE_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".json"}
CITATION_PATTERN = re.compile(r"\\(?:cite|citep|citet|parencite|autocite|textcite)\*?\{", re.IGNORECASE)


class ResultsGateError(RuntimeError):
    """Raised when Results writing would use unsupported or missing artifacts."""


def _safe_latex_text(text: str) -> str:
    replacements = {
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


def _project_relative_path(project_path: Path, relative: str) -> Path:
    candidate = (project_path / relative).resolve()
    try:
        candidate.relative_to(project_path.resolve())
    except ValueError as exc:
        raise ResultsGateError(f"Result artifact path escapes project directory: {relative}") from exc
    return candidate


def _artifact_id(prefix: str, index: int, path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", path.stem).strip("_").lower() or str(index)
    return f"{prefix}_{index}_{stem}"


def _figure_entry(project_path: Path, path: Path, index: int) -> dict[str, str]:
    relative = path.relative_to(project_path).as_posix()
    return {
        "id": _artifact_id("fig", index, path),
        "path": relative,
        "caption_draft": f"Result figure {index}: {path.stem.replace('_', ' ')}.",
        "result_claim": f"The artifact {relative} provides visual evidence for one result that should be interpreted directly from the generated output.",
    }


def _table_entry(project_path: Path, path: Path, index: int) -> dict[str, str]:
    relative = path.relative_to(project_path).as_posix()
    return {
        "id": _artifact_id("table", index, path),
        "path": relative,
        "caption_draft": f"Result table {index}: {path.stem.replace('_', ' ')}.",
        "result_claim": f"The artifact {relative} provides tabular evidence for one result that should be interpreted directly from the generated output.",
    }


def inventory_results(project: str | Path) -> dict[str, Any]:
    """Create results/result_manifest.yaml from existing local figures and tables."""
    state = load_project(project)
    results_dir = state.path / "results"
    figures_dir = results_dir / "figures"
    tables_dir = results_dir / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    figure_paths = sorted(path for path in figures_dir.iterdir() if path.is_file() and path.suffix.lower() in FIGURE_EXTENSIONS)
    table_paths = sorted(path for path in tables_dir.iterdir() if path.is_file() and path.suffix.lower() in TABLE_EXTENSIONS)
    manifest = {
        "figures": [_figure_entry(state.path, path, index + 1) for index, path in enumerate(figure_paths)],
        "tables": [_table_entry(state.path, path, index + 1) for index, path in enumerate(table_paths)],
    }
    _write_json(results_dir / "result_manifest.yaml", manifest)
    return {
        "status": "written",
        "project_path": str(state.path),
        "result_manifest": str(results_dir / "result_manifest.yaml"),
        "figure_count": len(manifest["figures"]),
        "table_count": len(manifest["tables"]),
    }


def _read_manifest(project_path: Path) -> dict[str, Any]:
    path = project_path / "results" / "result_manifest.yaml"
    if not path.exists():
        raise ResultsGateError("results/result_manifest.yaml is required before writing results.tex.")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ResultsGateError(f"results/result_manifest.yaml is not valid JSON-compatible YAML: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ResultsGateError("results/result_manifest.yaml must contain an object.")
    return manifest


def _all_entries(manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    entries: list[tuple[str, dict[str, Any]]] = []
    for entry in manifest.get("figures") or []:
        entries.append(("figure", entry))
    for entry in manifest.get("tables") or []:
        entries.append(("table", entry))
    return entries


def _validate_manifest(project_path: Path, manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    entries = _all_entries(manifest)
    if not entries:
        raise ResultsGateError("result_manifest.yaml must contain at least one figure or table.")
    missing = []
    for kind, entry in entries:
        relative = str(entry.get("path") or "")
        if not relative:
            raise ResultsGateError(f"A {kind} entry is missing its path.")
        if not _project_relative_path(project_path, relative).exists():
            missing.append(relative)
        text = " ".join(str(entry.get(key) or "") for key in ("caption_draft", "result_claim"))
        if CITATION_PATTERN.search(text):
            raise ResultsGateError(f"Results manifest entry {entry.get('id') or relative} contains a citation command.")
    if missing:
        raise ResultsGateError("Declared result artifacts are missing: " + ", ".join(missing))
    return entries


def _render_figure(entry: dict[str, Any]) -> str:
    path = str(entry["path"]).replace("\\", "/")
    caption = _safe_latex_text(str(entry.get("caption_draft") or entry.get("id") or "Result figure"))
    return (
        "\\begin{figure}[htbp]\n"
        "\\centering\n"
        f"\\includegraphics[width=0.92\\linewidth]{{{path}}}\n"
        f"\\caption{{{caption}}}\n"
        f"\\label{{fig:{_safe_label(str(entry.get('id') or Path(path).stem))}}}\n"
        "\\end{figure}"
    )


def _render_table(entry: dict[str, Any]) -> str:
    path = str(entry["path"]).replace("\\", "/")
    caption = _safe_latex_text(str(entry.get("caption_draft") or entry.get("id") or "Result table"))
    return (
        "\\begin{table}[htbp]\n"
        "\\centering\n"
        f"\\caption{{{caption}}}\n"
        f"\\label{{tab:{_safe_label(str(entry.get('id') or Path(path).stem))}}}\n"
        f"\\small\\texttt{{{_safe_latex_text(path)}}}\n"
        "\\end{table}"
    )


def _safe_label(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9:-]+", "-", text).strip("-") or "result"


def render_results_tex(project_meta: dict[str, Any], entries: list[tuple[str, dict[str, Any]]]) -> str:
    lines = [
        "\\section{Results}",
        (
            "The results are reported only from local artifacts registered in the result manifest. "
            "No literature citations are used in this section, so each interpretation is tied directly to a figure or table generated by the project workflow."
        ),
        "",
    ]
    for index, (kind, entry) in enumerate(entries, start=1):
        title = _safe_latex_text(str(entry.get("caption_draft") or f"Result {index}"))
        claim = _safe_latex_text(str(entry.get("result_claim") or "This artifact supports one result from the verified workflow."))
        path = _safe_latex_text(str(entry.get("path")))
        lines.extend([
            f"\\subsection{{Result {index}: {title}}}",
            f"{claim} The interpretation is limited to the local artifact at \\texttt{{{path}}}, and the claim should be revised if that artifact changes.",
            "",
            _render_figure(entry) if kind == "figure" else _render_table(entry),
            "",
        ])
    tex = "\n".join(lines)
    if CITATION_PATTERN.search(tex):
        raise ResultsGateError("Generated results.tex contains a citation command, which is forbidden.")
    return tex


def _set_results_stage_manifest(project_path: Path) -> None:
    manifest_path = project_path / "results" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = RESULT_INPUTS
    manifest["output_files"] = RESULT_OUTPUTS
    _write_json(manifest_path, manifest)


def write_results(project: str | Path) -> dict[str, Any]:
    """Write results.tex only from existing artifacts declared in result_manifest.yaml."""
    state = load_project(project)
    try:
        validate_result_validity_for_results(state.path)
    except ResultValidityError as exc:
        raise ResultsGateError(str(exc)) from exc
    manifest = _read_manifest(state.path)
    entries = _validate_manifest(state.path, manifest)
    output_path = state.path / "results" / "results.tex"
    output_path.write_text(render_results_tex(state.metadata, entries), encoding="utf-8")
    update_stage_status(state.path, "results", "draft")
    _set_results_stage_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "results": str(output_path),
        "artifact_count": len(entries),
        "outputs": RESULT_OUTPUTS,
    }
