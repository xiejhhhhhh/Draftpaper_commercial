from __future__ import annotations

from pathlib import Path
from typing import Any

from .passport import (
    PASSPORT_FILES,
    PassportError,
    append_integrity_event,
    collect_artifacts,
    load_project_passport,
    project_root,
    refresh_project_passport,
    utc_now,
)
from .project_scaffold import STAGE_ORDER
from .project_state import ProjectStateError, load_project, mark_stage_stale


class ArtifactDriftError(RuntimeError):
    """Raised when artifact drift cannot be mapped to stage backtracking."""


def _stage_for_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized in {"project.json", "project.yaml"}:
        return "idea"
    first = normalized.split("/", 1)[0]
    if first in {"artifact_ledger.jsonl", "checkpoint_ledger.jsonl", "integrity_ledger.jsonl", "project_passport.yaml"}:
        return "passport"
    return first


def _known_stage(stage: str) -> str:
    if stage == "quality_checks":
        return stage
    if stage in STAGE_ORDER:
        return stage
    if stage == "code":
        return "code"
    return "idea"


def _stage_sort_key(stage: str) -> int:
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return len(STAGE_ORDER)


def _artifact_maps(project: str | Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    project_path = project_root(project)
    passport = load_project_passport(project_path)
    baseline = {
        str(item.get("path")): item
        for item in (passport.get("artifacts") or [])
        if isinstance(item, dict) and item.get("path")
    }
    current = {
        str(item.get("path")): item
        for item in collect_artifacts(project_path)
        if isinstance(item, dict) and item.get("path")
    }
    return baseline, current


def detect_artifact_drift(project: str | Path) -> dict[str, Any]:
    """Compare current artifact hashes against project_passport.yaml without mutating state."""
    project_path = project_root(project)
    baseline, current = _artifact_maps(project_path)
    changed = []
    missing = []
    added = []
    for path, old in sorted(baseline.items()):
        if path not in current:
            missing.append({"path": path, "stage": _known_stage(_stage_for_path(path)), "previous_sha256": old.get("sha256")})
            continue
        new = current[path]
        if old.get("sha256") != new.get("sha256"):
            changed.append({
                "path": path,
                "stage": _known_stage(_stage_for_path(path)),
                "previous_sha256": old.get("sha256"),
                "current_sha256": new.get("sha256"),
            })
    for path, new in sorted(current.items()):
        if path not in baseline:
            added.append({"path": path, "stage": _known_stage(_stage_for_path(path)), "current_sha256": new.get("sha256")})

    source_stages = sorted(
        {
            item["stage"]
            for item in [*changed, *missing, *added]
            if item.get("stage") not in {"passport"}
        },
        key=_stage_sort_key,
    )
    drift_count = len(changed) + len(missing) + len(added)
    return {
        "status": "drift_detected" if drift_count else "clean",
        "project_path": str(project_path),
        "drift_count": drift_count,
        "changed_artifacts": changed,
        "missing_artifacts": missing,
        "added_artifacts": added,
        "source_stages": source_stages,
        "recommended_command": (
            f"python -m draftpaper_cli.cli sync-artifact-stale --project \"{project_path}\""
            if drift_count else None
        ),
    }


def sync_artifact_stale(project: str | Path) -> dict[str, Any]:
    """Mark dependent stages stale from artifact hash drift and refresh passport baseline."""
    project_path = project_root(project)
    state = load_project(project_path)
    drift = detect_artifact_drift(project_path)
    if drift["status"] == "clean":
        passport = refresh_project_passport(project_path, event="artifact_drift_clean")
        return {
            "status": "clean",
            "project_path": str(project_path),
            "stale_stages": [],
            "drift": drift,
            "passport": str(project_path / PASSPORT_FILES["passport"]),
            "artifact_count": passport.get("artifact_count", 0),
        }

    stale_stages: list[str] = []
    for source_stage in drift.get("source_stages") or []:
        if source_stage not in (state.metadata.get("stages") or {}):
            continue
        for stage in mark_stage_stale(project_path, source_stage, include_self=False):
            if stage not in stale_stages:
                stale_stages.append(stage)
        state = load_project(project_path)

    event = {
        "kind": "artifact_drift",
        "recorded_at": utc_now(),
        "source_stages": drift.get("source_stages") or [],
        "stale_stages": stale_stages,
        "changed_artifacts": drift.get("changed_artifacts") or [],
        "missing_artifacts": drift.get("missing_artifacts") or [],
        "added_artifacts": drift.get("added_artifacts") or [],
    }
    append_integrity_event(project_path, event)
    passport = refresh_project_passport(project_path, event="artifact_drift_synced")
    return {
        "status": "synced",
        "project_path": str(project_path),
        "stale_stages": sorted(stale_stages, key=_stage_sort_key),
        "drift": drift,
        "passport": str(project_path / PASSPORT_FILES["passport"]),
        "artifact_count": passport.get("artifact_count", 0),
    }


def handle_stale_sync_error(exc: Exception) -> dict[str, str]:
    if isinstance(exc, (ArtifactDriftError, PassportError, ProjectStateError)):
        return {"status": "error", "message": str(exc)}
    return {"status": "error", "message": str(exc)}
