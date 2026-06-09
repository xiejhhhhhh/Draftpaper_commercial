from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ProjectAlreadyExistsError(FileExistsError):
    """Raised when a paper project already exists and overwrite is not allowed."""


@dataclass(frozen=True)
class ProjectScaffold:
    project_id: str
    project_slug: str
    path: Path
    metadata: dict[str, Any]


PROJECT_DIRECTORIES = [
    "idea",
    "research_plan",
    "references",
    "journal_profile",
    "introduction",
    "data/raw",
    "data/processed",
    "method_plan",
    "methods",
    "code",
    "code/src",
    "code/scripts",
    "code/tests",
    "result_validity",
    "results/figures",
    "results/tables",
    "discussion",
    "latex/sections",
    "latex/template",
    "integrity",
    "review",
    "quality_checks",
]

STAGE_ORDER = [
    "idea",
    "references",
    "journal_profile",
    "research_plan",
    "introduction",
    "data",
    "method_plan",
    "code",
    "methods",
    "result_validity",
    "results",
    "discussion",
    "latex",
    "quality_checks",
]


def slugify(value: str, max_length: int = 80) -> str:
    """Convert a research idea into a stable, filesystem-friendly slug."""
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return (normalized[:max_length].rstrip("-") or "untitled-paper")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_stage_metadata() -> dict[str, dict[str, Any]]:
    stages: dict[str, dict[str, Any]] = {}
    for stage in STAGE_ORDER:
        stages[stage] = {
            "status": "draft" if stage == "idea" else "pending",
            "stale": False,
            "depends_on": [],
            "manifest": f"{stage}/stage_manifest.json" if stage != "quality_checks" else "quality_checks/stage_manifest.json",
        }

    stages["references"]["depends_on"] = ["idea"]
    stages["journal_profile"]["depends_on"] = ["idea"]
    stages["research_plan"]["depends_on"] = ["references", "journal_profile"]
    stages["introduction"]["depends_on"] = ["research_plan", "references", "journal_profile"]
    stages["data"]["depends_on"] = ["research_plan"]
    stages["method_plan"]["depends_on"] = ["research_plan", "references", "data"]
    stages["code"]["depends_on"] = ["method_plan", "data", "references"]
    stages["methods"]["depends_on"] = ["method_plan", "data", "code"]
    stages["result_validity"]["depends_on"] = ["methods", "method_plan", "data"]
    stages["results"]["depends_on"] = ["result_validity"]
    stages["discussion"]["depends_on"] = ["introduction", "results", "references"]
    stages["latex"]["depends_on"] = ["introduction", "data", "method_plan", "methods", "result_validity", "results", "discussion", "references", "journal_profile"]
    stages["quality_checks"]["depends_on"] = ["latex"]
    return stages


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_simple_yaml(path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []

    def render(key: str, value: Any, indent: int = 0) -> None:
        prefix = " " * indent
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            for child_key, child_value in value.items():
                render(str(child_key), child_value, indent + 2)
        elif isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            if not value:
                lines.append(f"{prefix}  []")
            for item in value:
                lines.append(f"{prefix}  - {item}")
        elif isinstance(value, bool):
            lines.append(f"{prefix}{key}: {'true' if value else 'false'}")
        elif value is None:
            lines.append(f"{prefix}{key}: null")
        else:
            text = str(value).replace('"', '\\"')
            lines.append(f'{prefix}{key}: "{text}"')

    for root_key, root_value in payload.items():
        render(root_key, root_value)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_stage_manifests(project_path: Path, metadata: dict[str, Any]) -> None:
    for stage, stage_meta in metadata["stages"].items():
        stage_dir = project_path / ("quality_checks" if stage == "quality_checks" else stage)
        stage_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "project_id": metadata["project_id"],
            "stage": stage,
            "status": stage_meta["status"],
            "stale": stage_meta["stale"],
            "depends_on": stage_meta["depends_on"],
            "input_files": [],
            "output_files": [],
            "last_updated": metadata["created_at"] if stage == "idea" else None,
        }
        _write_json(stage_dir / "stage_manifest.json", manifest)


def _write_idea_note(project_path: Path, metadata: dict[str, Any]) -> None:
    content = (
        f"# Research Idea\n\n"
        f"**Idea:** {metadata['idea']}\n\n"
        f"**Field:** {metadata['field']}\n\n"
        f"**Target journal:** {metadata['target_journal']}\n\n"
        "## Notes\n\n"
        "Add user constraints, data availability, and writing preferences here before generating the research plan.\n"
    )
    (project_path / "idea" / "idea.md").write_text(content, encoding="utf-8")


def create_project(
    *,
    root: str | Path,
    idea: str,
    field: str,
    target_journal: str | None = None,
    overwrite: bool = False,
) -> ProjectScaffold:
    """Create a single-paper project directory for staged local manuscript work."""
    if not idea.strip():
        raise ValueError("idea is required")
    if not field.strip():
        raise ValueError("field is required")

    root_path = Path(root).expanduser().resolve()
    project_slug = slugify(idea)
    project_path = root_path / project_slug
    if project_path.exists() and not overwrite:
        raise ProjectAlreadyExistsError(f"Project already exists: {project_path}")

    project_path.mkdir(parents=True, exist_ok=True)
    for relative in PROJECT_DIRECTORIES:
        (project_path / relative).mkdir(parents=True, exist_ok=True)

    now = utc_now()
    metadata = {
        "schema_version": 1,
        "project_id": project_slug,
        "project_slug": project_slug,
        "title": idea.strip(),
        "idea": idea.strip(),
        "field": field.strip(),
        "target_journal": (target_journal or "General Academic Journal").strip(),
        "created_at": now,
        "updated_at": now,
        "current_stage": "idea",
        "source_mvp": {
            "path": "D:\\DraftAI_agent",
            "reuse_policy": "Check this MVP for reusable literature, export, validation, and generation utilities before adding new workflow code.",
        },
        "stages": _build_stage_metadata(),
    }

    _write_json(project_path / "project.json", metadata)
    _write_simple_yaml(project_path / "project.yaml", metadata)
    _write_stage_manifests(project_path, metadata)
    _write_idea_note(project_path, metadata)
    from .passport import initialize_project_passport

    initialize_project_passport(project_path)

    return ProjectScaffold(
        project_id=project_slug,
        project_slug=project_slug,
        path=project_path,
        metadata=metadata,
    )
