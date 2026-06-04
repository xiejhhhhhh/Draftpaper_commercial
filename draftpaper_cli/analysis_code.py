from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from .method_plan import MethodPlanError, validate_method_plan_for_methods
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, update_stage_status


ANALYSIS_CODE_INPUTS = [
    "references/literature_items.json",
    "methods/method_plan.md",
    "methods/method_requirements.json",
    "data/data_inventory.json",
]

ANALYSIS_CODE_OUTPUTS = [
    "code/scripts/run_analysis.py",
    "code/src/generated_pipeline.py",
    "code/tests/test_generated_pipeline.py",
    "methods/analysis_code_manifest.json",
]

DEFAULT_DECLARED_OUTPUTS = [
    "results/tables/metrics.csv",
    "results/tables/analysis_summary.csv",
    "results/figures/data_analysis_flow.svg",
    "results/figures/data_processing_flow.svg",
    "results/figures/method_analysis_flow.svg",
    "results/figures/data_to_method_outputs.svg",
]

TABULAR_SUFFIXES = {".csv", ".tsv"}


class AnalysisCodeGenerationError(RuntimeError):
    """Raised when project-local analysis code cannot be generated safely."""


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise AnalysisCodeGenerationError(f"{path.name} is not valid JSON: {exc}") from exc


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _project_relative_path(project_path: Path, relative: str) -> Path:
    candidate = (project_path / relative).resolve()
    try:
        candidate.relative_to(project_path.resolve())
    except ValueError as exc:
        raise AnalysisCodeGenerationError(f"Generated output path escapes project directory: {relative}") from exc
    return candidate


def _select_tabular_input(inventory: dict[str, Any]) -> dict[str, Any]:
    files = [
        item for item in inventory.get("files") or []
        if str(item.get("suffix") or "").lower() in TABULAR_SUFFIXES and item.get("readable") is not False
    ]
    if not files:
        raise AnalysisCodeGenerationError("data/data_inventory.json contains no readable CSV/TSV data file.")
    files.sort(key=lambda item: (int(item.get("row_count") or 0), int(item.get("column_count") or 0)), reverse=True)
    return files[0]


def _literature_sources(items: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    sources = []
    for item in sorted(items, key=lambda entry: entry.get("citation_weight", 0), reverse=True):
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        sources.append({
            "citation_key": item.get("bibtex_key") or item.get("citation_key") or "",
            "title": title,
            "publication": item.get("publication") or item.get("venue") or "",
            "year": item.get("year") or "",
            "method_summary": str((item.get("deep_summary") or {}).get("methods") or item.get("abstract") or "")[:700],
            "citation_weight": item.get("citation_weight", 0),
        })
        if len(sources) >= limit:
            break
    return sources


def _quote_command(path: str) -> str:
    return f'"{path}"' if " " in path else path


def _sanitize_outputs(project_path: Path, output_files: list[str] | None) -> list[str]:
    outputs = output_files or DEFAULT_DECLARED_OUTPUTS
    cleaned = []
    for relative in outputs:
        normalized = str(relative).replace("\\", "/").strip()
        if not normalized:
            continue
        _project_relative_path(project_path, normalized)
        cleaned.append(normalized)
    return cleaned or list(DEFAULT_DECLARED_OUTPUTS)


def _render_generated_pipeline(manifest: dict[str, Any]) -> str:
    manifest_literal = json.dumps(manifest, ensure_ascii=True, sort_keys=True)
    return f'''from __future__ import annotations

import csv
import json
from html import escape
from collections import Counter
from pathlib import Path
from typing import Any


PIPELINE_MANIFEST: dict[str, Any] = json.loads({manifest_literal!r})


def _delimiter_for(path: Path) -> str:
    return "\\t" if path.suffix.lower() == ".tsv" else ","


def read_table(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=_delimiter_for(path)))


def write_key_value_csv(path: Path, rows: list[tuple[str, Any]], header: tuple[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for key, value in rows:
            writer.writerow([key, value])


def infer_label_column(rows: list[dict[str, str]]) -> str | None:
    if not rows:
        return None
    columns = list(rows[0].keys())
    preferred = ["target", "label", "class", "source_class", "y"]
    for column in preferred:
        if column in columns:
            return column
    return None


def compute_baseline_metrics(rows: list[dict[str, str]], label_column: str | None) -> dict[str, float]:
    row_count = len(rows)
    column_count = len(rows[0]) if rows else 0
    metrics: dict[str, float] = {{
        "row_count": float(row_count),
        "feature_column_count": float(max(column_count - (1 if label_column else 0), 0)),
    }}
    if not rows or not label_column:
        metrics.update({{"class_count": 0.0, "baseline_accuracy": 0.0, "f1": 0.0}})
        return metrics
    counts = Counter(str(row.get(label_column, "")).strip() for row in rows if str(row.get(label_column, "")).strip())
    majority = max(counts.values()) if counts else 0
    baseline = majority / row_count if row_count else 0.0
    metrics.update({{
        "class_count": float(len(counts)),
        "baseline_accuracy": round(baseline, 6),
        "f1": round(baseline, 6),
    }})
    return metrics


def write_flow_svg(path: Path, title: str, steps: list[str], accent: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width = 1120
    height = 210
    box_width = 210
    box_height = 72
    gap = 48
    start_x = 38
    box_y = 88
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{{width}}" height="{{height}}" viewBox="0 0 {{width}} {{height}}">',
        '<rect width="1120" height="210" fill="#ffffff"/>',
        f'<text x="38" y="42" font-family="Arial, sans-serif" font-size="24" fill="#1f2937">{{escape(title)}}</text>',
    ]
    for index, step in enumerate(steps):
        x = start_x + index * (box_width + gap)
        parts.append(f'<rect x="{{x}}" y="{{box_y}}" width="{{box_width}}" height="{{box_height}}" rx="6" fill="#f8fafc" stroke="{{accent}}" stroke-width="2"/>')
        parts.append(f'<text x="{{x + 18}}" y="{{box_y + 32}}" font-family="Arial, sans-serif" font-size="15" fill="#111827">{{escape(step[:32])}}</text>')
        if len(step) > 32:
            parts.append(f'<text x="{{x + 18}}" y="{{box_y + 54}}" font-family="Arial, sans-serif" font-size="13" fill="#4b5563">{{escape(step[32:64])}}</text>')
        if index < len(steps) - 1:
            arrow_x = x + box_width + 10
            parts.append(f'<line x1="{{arrow_x}}" y1="{{box_y + 36}}" x2="{{arrow_x + gap - 20}}" y2="{{box_y + 36}}" stroke="#6b7280" stroke-width="2"/>')
            parts.append(f'<polygon points="{{arrow_x + gap - 20}},{{box_y + 36}} {{arrow_x + gap - 30}},{{box_y + 29}} {{arrow_x + gap - 30}},{{box_y + 43}}" fill="#6b7280"/>')
    parts.append("</svg>")
    path.write_text("\\n".join(parts), encoding="utf-8")


def run_pipeline(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[2]
    input_path = root / PIPELINE_MANIFEST["selected_input_data"]
    rows = read_table(input_path)
    label_column = infer_label_column(rows)
    metrics = compute_baseline_metrics(rows, label_column)
    metrics_path = root / "results" / "tables" / "metrics.csv"
    summary_path = root / "results" / "tables" / "analysis_summary.csv"
    write_key_value_csv(metrics_path, list(metrics.items()), ("metric", "value"))
    write_key_value_csv(
        summary_path,
        [
            ("selected_input_data", PIPELINE_MANIFEST["selected_input_data"]),
            ("label_column", label_column or ""),
            ("method_families", ";".join(PIPELINE_MANIFEST.get("method_families") or [])),
            ("literature_method_count", PIPELINE_MANIFEST.get("literature_method_count", 0)),
            ("generated_stage", "analysis_code"),
        ],
        ("key", "value"),
    )
    figures_dir = root / "results" / "figures"
    families = PIPELINE_MANIFEST.get("method_families") or ["model workflow"]
    write_flow_svg(
        figures_dir / "data_analysis_flow.svg",
        "Data analysis workflow",
        ["Local data inventory", "Quality and feasibility gate", "Feature table profiling", "Metric-ready outputs"],
        "#2563eb",
    )
    write_flow_svg(
        figures_dir / "data_processing_flow.svg",
        "Data processing workflow",
        ["Read tabular source data", "Infer label column", "Summarize feature space", "Write analysis tables"],
        "#059669",
    )
    write_flow_svg(
        figures_dir / "method_analysis_flow.svg",
        "Method analysis workflow",
        ["Literature method synthesis", families[0].replace("_", " "), "Baseline metric check", "Run manifest gate"],
        "#7c3aed",
    )
    write_flow_svg(
        figures_dir / "data_to_method_outputs.svg",
        "Data-to-method output workflow",
        ["Selected input data", "Generated pipeline", "Metrics and summaries", "Result figures"],
        "#dc2626",
    )
    return {{
        "metrics": metrics,
        "outputs": [
            str(metrics_path),
            str(summary_path),
            str(figures_dir / "data_analysis_flow.svg"),
            str(figures_dir / "data_processing_flow.svg"),
            str(figures_dir / "method_analysis_flow.svg"),
            str(figures_dir / "data_to_method_outputs.svg"),
        ],
    }}
'''


def _render_run_script() -> str:
    return '''from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "code" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from generated_pipeline import run_pipeline


if __name__ == "__main__":
    run_pipeline(PROJECT_ROOT)
'''


def _render_generated_test() -> str:
    return '''from __future__ import annotations

import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from generated_pipeline import compute_baseline_metrics, infer_label_column


def test_compute_baseline_metrics_from_labels() -> None:
    rows = [
        {"target": "a", "x": "1"},
        {"target": "a", "x": "2"},
        {"target": "b", "x": "3"},
    ]
    label_column = infer_label_column(rows)
    metrics = compute_baseline_metrics(rows, label_column)
    assert label_column == "target"
    assert metrics["row_count"] == 3.0
    assert metrics["class_count"] == 2.0
    assert metrics["f1"] > 0.0
'''


def _set_analysis_manifest(project_path: Path, payload: dict[str, Any]) -> None:
    _write_json(project_path / "methods" / "analysis_code_manifest.json", payload)


def _set_code_stage_manifest(project_path: Path) -> None:
    manifest_path = project_path / "code" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = ANALYSIS_CODE_INPUTS
    manifest["output_files"] = ANALYSIS_CODE_OUTPUTS
    _write_json(manifest_path, manifest)


def generate_analysis_code(
    project: str | Path,
    *,
    output_files: list[str] | None = None,
) -> dict[str, Any]:
    """Generate project-local baseline analysis code from literature and method requirements."""
    state = load_project(project)
    try:
        requirements = validate_method_plan_for_methods(state.path)
    except MethodPlanError as exc:
        raise AnalysisCodeGenerationError(str(exc)) from exc

    inventory = _read_json(state.path / "data" / "data_inventory.json", {})
    if not isinstance(inventory, dict) or not inventory:
        raise AnalysisCodeGenerationError("data/data_inventory.json is required before analysis code generation.")
    selected_input = _select_tabular_input(inventory)

    literature_items = _read_json(state.path / "references" / "literature_items.json", [])
    if not isinstance(literature_items, list):
        raise AnalysisCodeGenerationError("references/literature_items.json must contain a list.")
    method_plan_text = _read_text(state.path / "methods" / "method_plan.md")
    declared_outputs = _sanitize_outputs(state.path, output_files)
    literature_sources = _literature_sources(literature_items)
    method_families = list(requirements.get("method_families") or [])
    if not method_families:
        method_families = ["method_family_requires_user_confirmation"]

    manifest = {
        "status": "written",
        "project_id": state.metadata.get("project_id"),
        "generated_at": utc_now(),
        "generator": "draftpaper_cli.analysis_code.generate_analysis_code",
        "selected_input_data": selected_input.get("path"),
        "selected_input_profile": selected_input,
        "method_families": method_families,
        "required_data_features": requirements.get("required_data_features") or [],
        "primary_metric": requirements.get("primary_metric") or "f1",
        "minimum_primary_metric": requirements.get("minimum_primary_metric"),
        "literature_method_count": len(literature_sources),
        "literature_sources": literature_sources,
        "method_plan_excerpt": re.sub(r"\s+", " ", method_plan_text).strip()[:1000],
        "declared_outputs": declared_outputs,
        "generated_files": ANALYSIS_CODE_OUTPUTS,
        "notes": [
            "Generated code is a deterministic baseline scaffold. Review and extend it before treating results as final science.",
            "Run verify-methods with verify_command before writing Methods or Results.",
        ],
    }

    scripts_dir = state.path / "code" / "scripts"
    src_dir = state.path / "code" / "src"
    tests_dir = state.path / "code" / "tests"
    for directory in [scripts_dir, src_dir, tests_dir, state.path / "methods", state.path / "results" / "tables"]:
        directory.mkdir(parents=True, exist_ok=True)

    (src_dir / "generated_pipeline.py").write_text(_render_generated_pipeline(manifest), encoding="utf-8")
    (scripts_dir / "run_analysis.py").write_text(_render_run_script(), encoding="utf-8")
    (tests_dir / "test_generated_pipeline.py").write_text(_render_generated_test(), encoding="utf-8")
    _set_analysis_manifest(state.path, manifest)
    _set_code_stage_manifest(state.path)
    update_stage_status(state.path, "code", "draft")

    verify_command = f"{_quote_command(sys.executable)} code/scripts/run_analysis.py"
    return {
        "status": "written",
        "project_path": str(state.path),
        "analysis_code_manifest": str(state.path / "methods" / "analysis_code_manifest.json"),
        "generated_files": [str(state.path / relative) for relative in ANALYSIS_CODE_OUTPUTS[:-1]],
        "selected_input_data": selected_input.get("path"),
        "declared_outputs": declared_outputs,
        "verify_command": verify_command,
        "next_command": (
            f'{_quote_command(sys.executable)} -m draftpaper_cli.cli verify-methods '
            f'--project "{state.path}" --command "{verify_command}" '
            + " ".join(f"--output {output}" for output in declared_outputs)
        ),
    }
