from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .project_scaffold import PROJECT_DIRECTORIES, _build_stage_metadata, _write_json, _write_simple_yaml, utc_now


VALID_STAGE_STATUSES = {"pending", "draft", "approved", "stale", "failed", "completed"}


class ProjectStateError(RuntimeError):
    """Raised when a project cannot be loaded or updated safely."""


class UnknownStageError(ProjectStateError):
    """Raised when a requested stage is not declared in project metadata."""


class InvalidStageStatusError(ProjectStateError):
    """Raised when a requested stage status is not supported."""


@dataclass(frozen=True)
class ProjectState:
    path: Path
    metadata: dict[str, Any]

    @property
    def stage_names(self) -> list[str]:
        return list((self.metadata.get("stages") or {}).keys())


def _project_json_path(project: str | Path) -> Path:
    path = Path(project).expanduser().resolve()
    if path.is_file() and path.name == "project.json":
        return path
    return path / "project.json"


def load_project(project: str | Path) -> ProjectState:
    """Load a staged paper project from a project directory or project.json path."""
    json_path = _project_json_path(project)
    if not json_path.exists():
        raise ProjectStateError(f"project.json not found: {json_path}")
    try:
        metadata = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectStateError(f"project.json is invalid JSON: {json_path}") from exc
    if not isinstance(metadata, dict):
        raise ProjectStateError(f"project.json must contain an object: {json_path}")
    if "stages" not in metadata or not isinstance(metadata["stages"], dict):
        raise ProjectStateError(f"project.json has no stages object: {json_path}")
    metadata = _migrate_metadata_schema(json_path, metadata)
    return ProjectState(path=json_path.parent, metadata=metadata)


def _stage_dir(project_path: Path, stage: str) -> Path:
    if stage == "quality_checks":
        return project_path / "quality_checks"
    return project_path / stage


def _manifest_path(project_path: Path, stage: str) -> Path:
    return _stage_dir(project_path, stage) / "stage_manifest.json"


def _migrate_metadata_schema(json_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Add newly introduced stages and dependency edges to older local projects."""
    project_path = json_path.parent
    defaults = _build_stage_metadata()
    changed = False
    for relative in PROJECT_DIRECTORIES:
        directory = project_path / relative
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            changed = True
    for stage, default_meta in defaults.items():
        if stage not in metadata["stages"]:
            metadata["stages"][stage] = default_meta
            changed = True
            continue
        if metadata["stages"][stage].get("depends_on") != default_meta.get("depends_on"):
            metadata["stages"][stage]["depends_on"] = list(default_meta.get("depends_on") or [])
            changed = True
    if changed:
        metadata["updated_at"] = utc_now()
        _write_json(project_path / "project.json", metadata)
        _write_simple_yaml(project_path / "project.yaml", metadata)
        state = ProjectState(path=project_path, metadata=metadata)
        for stage in defaults:
            if not _manifest_path(project_path, stage).exists():
                _write_stage_manifest(state, stage)
    return metadata


def _save_project(state: ProjectState) -> ProjectState:
    state.metadata["updated_at"] = utc_now()
    _write_json(state.path / "project.json", state.metadata)
    _write_simple_yaml(state.path / "project.yaml", state.metadata)
    return load_project(state.path)


def _write_stage_manifest(state: ProjectState, stage: str) -> None:
    stage_meta = state.metadata["stages"][stage]
    manifest_path = _manifest_path(state.path, stage)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    manifest = {
        "project_id": state.metadata.get("project_id"),
        "stage": stage,
        "status": stage_meta.get("status", "pending"),
        "stale": bool(stage_meta.get("stale", False)),
        "depends_on": list(stage_meta.get("depends_on", [])),
        "input_files": existing.get("input_files", []),
        "output_files": existing.get("output_files", []),
        "last_updated": stage_meta.get("last_updated") or existing.get("last_updated"),
    }
    _write_json(manifest_path, manifest)


def _require_stage(state: ProjectState, stage: str) -> None:
    if stage not in state.metadata["stages"]:
        raise UnknownStageError(f"Unknown stage '{stage}'. Known stages: {', '.join(state.stage_names)}")


def _require_status(status: str) -> None:
    if status not in VALID_STAGE_STATUSES:
        raise InvalidStageStatusError(
            f"Invalid stage status '{status}'. Use one of: {', '.join(sorted(VALID_STAGE_STATUSES))}"
        )


def _dependent_stages(state: ProjectState, changed_stage: str) -> list[str]:
    dependents: list[str] = []
    frontier = [changed_stage]
    seen = {changed_stage}
    while frontier:
        current = frontier.pop(0)
        for stage, stage_meta in state.metadata["stages"].items():
            if stage in seen:
                continue
            if current in (stage_meta.get("depends_on") or []):
                dependents.append(stage)
                seen.add(stage)
                frontier.append(stage)
    return dependents


def update_stage_status(project: str | Path, stage: str, status: str) -> ProjectState:
    """Update a stage status and keep project metadata plus stage manifest synchronized."""
    _require_status(status)
    state = load_project(project)
    _require_stage(state, stage)

    now = utc_now()
    state.metadata["current_stage"] = stage
    stage_meta = state.metadata["stages"][stage]
    stage_meta["status"] = status
    stage_meta["stale"] = status == "stale"
    stage_meta["last_updated"] = now
    _write_stage_manifest(state, stage)

    saved = _save_project(state)
    _write_stage_manifest(saved, stage)
    if status in {"draft", "failed"}:
        mark_stage_stale(saved.path, stage)
        return load_project(saved.path)
    return saved


def mark_stage_stale(project: str | Path, stage: str, *, include_self: bool = False) -> list[str]:
    """Mark all stages that depend on `stage` as stale, recursively."""
    state = load_project(project)
    _require_stage(state, stage)

    changed = [stage] if include_self else []
    changed.extend(_dependent_stages(state, stage))
    now = utc_now()
    for stale_stage in changed:
        stage_meta = state.metadata["stages"][stale_stage]
        stage_meta["status"] = "stale"
        stage_meta["stale"] = True
        stage_meta["last_updated"] = now
        _write_stage_manifest(state, stale_stage)

    saved = _save_project(state)
    for stale_stage in changed:
        _write_stage_manifest(saved, stale_stage)
    return changed


def validate_project(project: str | Path) -> dict[str, Any]:
    """Validate project metadata, required directories, and stage manifests."""
    issues: list[dict[str, str]] = []
    try:
        state = load_project(project)
    except ProjectStateError as exc:
        return {
            "status": "failed",
            "project_path": str(Path(project).expanduser().resolve()),
            "issues": [{"severity": "error", "code": "project_load_failed", "message": str(exc)}],
        }

    for relative in PROJECT_DIRECTORIES:
        if not (state.path / relative).is_dir():
            issues.append({
                "severity": "error",
                "code": "missing_project_directory",
                "message": f"Missing project directory: {relative}",
            })

    for stage, stage_meta in state.metadata["stages"].items():
        status = stage_meta.get("status")
        if status not in VALID_STAGE_STATUSES:
            issues.append({
                "severity": "error",
                "code": "invalid_stage_status",
                "message": f"Stage {stage} has invalid status: {status}",
            })
        manifest_path = _manifest_path(state.path, stage)
        if not manifest_path.exists():
            issues.append({
                "severity": "error",
                "code": "missing_stage_manifest",
                "message": f"Stage {stage} is missing stage_manifest.json",
            })
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            issues.append({
                "severity": "error",
                "code": "invalid_stage_manifest_json",
                "message": f"Stage {stage} manifest is invalid JSON",
            })
            continue
        if manifest.get("stage") != stage:
            issues.append({
                "severity": "error",
                "code": "stage_manifest_mismatch",
                "message": f"Stage {stage} manifest declares stage {manifest.get('stage')}",
            })
        if manifest.get("status") != stage_meta.get("status"):
            issues.append({
                "severity": "warning",
                "code": "stage_manifest_status_drift",
                "message": f"Stage {stage} manifest status differs from project.json",
            })
        if bool(manifest.get("stale", False)) != bool(stage_meta.get("stale", False)):
            issues.append({
                "severity": "warning",
                "code": "stage_manifest_stale_drift",
                "message": f"Stage {stage} manifest stale flag differs from project.json",
            })

    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    return {
        "status": "passed" if error_count == 0 else "failed",
        "project_path": str(state.path),
        "project_id": state.metadata.get("project_id"),
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": issues,
    }
