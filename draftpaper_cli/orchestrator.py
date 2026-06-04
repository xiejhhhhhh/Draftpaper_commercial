from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .passport import (
    PASSPORT_FILES,
    PassportError,
    append_checkpoint_event,
    load_project_passport,
    project_root,
    read_jsonl,
    refresh_project_passport,
    utc_now,
)
from .project_scaffold import STAGE_ORDER
from .project_state import ProjectStateError, load_project
from .stale_sync import detect_artifact_drift


COMPLETE_STATUSES = {"draft", "approved", "completed"}

STAGE_COMMANDS = {
    "references": "search-literature",
    "journal_profile": "resolve-journal-template",
    "research_plan": "generate-plan",
    "introduction": "write-introduction",
    "data": "inventory-data",
    "method_plan": "collect-method-plan",
    "code": "generate-analysis-code",
    "methods": "verify-methods",
    "result_validity": "assess-result-validity",
    "results": "inventory-results",
    "discussion": "write-discussion",
    "latex": "assemble-latex",
    "quality_checks": "quality-check",
}


class OrchestratorError(RuntimeError):
    """Raised when the pipeline orchestrator cannot resolve a legal next action."""


def _stage_is_current(stage_meta: dict[str, Any]) -> bool:
    return stage_meta.get("status") in COMPLETE_STATUSES and not stage_meta.get("stale")


def _quote(path: Path) -> str:
    text = str(path)
    return f'"{text}"' if " " in text else text


def _cli_for(project_path: Path, command: str) -> str:
    return f"python -m draftpaper_cli.cli {command} --project {_quote(project_path)}"


def _next_stage(metadata: dict[str, Any]) -> str | None:
    stages = metadata.get("stages") or {}
    for stage in STAGE_ORDER:
        if stage == "idea":
            continue
        stage_meta = stages.get(stage) or {}
        if not _stage_is_current(stage_meta):
            return stage
    return None


def _next_action(project_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    stage = _next_stage(metadata)
    if stage is None:
        return {
            "stage": None,
            "command": None,
            "cli": None,
            "reason": "All declared stages are current.",
        }
    command = STAGE_COMMANDS.get(stage)
    if not command:
        raise OrchestratorError(f"No orchestrator command mapping exists for stage: {stage}")
    return {
        "stage": stage,
        "command": command,
        "cli": _cli_for(project_path, command),
        "reason": f"Stage {stage} is pending, stale, or not yet completed.",
    }


def status_project(project: str | Path) -> dict[str, Any]:
    """Return pipeline status, passport state, and the next CLI action."""
    state = load_project(project)
    drift = detect_artifact_drift(state.path)
    if drift.get("status") == "drift_detected":
        return {
            "status": "reported",
            "project_path": str(state.path),
            "pipeline_state": "drift_detected",
            "current_stage": state.metadata.get("current_stage"),
            "awaiting_checkpoint": None,
            "passport": str(state.path / PASSPORT_FILES["passport"]),
            "drift": drift,
            "next_action": {
                "stage": None,
                "command": "sync-artifact-stale",
                "cli": f"python -m draftpaper_cli.cli sync-artifact-stale --project {_quote(state.path)}",
                "reason": "Artifact hashes changed since the last passport snapshot.",
            },
        }
    passport = refresh_project_passport(state.path, event="status")
    awaiting = passport.get("awaiting_checkpoint")
    if awaiting:
        return {
            "status": "reported",
            "project_path": str(state.path),
            "pipeline_state": "awaiting_confirmation",
            "current_stage": state.metadata.get("current_stage"),
            "awaiting_checkpoint": awaiting,
            "passport": str(state.path / PASSPORT_FILES["passport"]),
            "next_action": {
                "stage": awaiting.get("stage"),
                "command": "resume",
                "cli": f"python -m draftpaper_cli.cli resume --project {_quote(state.path)} --checkpoint-hash {awaiting.get('hash')}",
                "reason": "A checkpoint is waiting for explicit resume confirmation.",
            },
        }
    return {
        "status": "reported",
        "project_path": str(state.path),
        "pipeline_state": "ready",
        "current_stage": state.metadata.get("current_stage"),
        "awaiting_checkpoint": None,
        "passport": str(state.path / PASSPORT_FILES["passport"]),
        "next_action": _next_action(state.path, state.metadata),
    }


def _checkpoint_hash(entry: dict[str, Any]) -> str:
    payload = dict(entry)
    payload["hash"] = "000000000000"
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def checkpoint_project(project: str | Path, *, stage: str, note: str = "") -> dict[str, Any]:
    """Append a checkpoint ledger entry and wait for explicit resume."""
    state = load_project(project)
    if stage not in (state.metadata.get("stages") or {}):
        raise OrchestratorError(f"Unknown checkpoint stage: {stage}")
    passport = load_project_passport(state.path)
    if passport.get("awaiting_checkpoint"):
        raise OrchestratorError("A checkpoint is already awaiting resume.")
    base = {
        "kind": "checkpoint",
        "stage": stage,
        "note": note,
        "created_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "next_action": _next_action(state.path, state.metadata),
    }
    base["hash"] = _checkpoint_hash(base)
    append_checkpoint_event(state.path, base)
    return {
        "status": "checkpoint_created",
        "project_path": str(state.path),
        "checkpoint_hash": base["hash"],
        "checkpoint_ledger": str(state.path / PASSPORT_FILES["checkpoint_ledger"]),
        "next_action": base["next_action"],
    }


def resume_project(project: str | Path, *, checkpoint_hash: str, note: str = "") -> dict[str, Any]:
    """Consume a checkpoint by appending a resume ledger entry."""
    state = load_project(project)
    events = read_jsonl(state.path / PASSPORT_FILES["checkpoint_ledger"])
    checkpoints = [event for event in events if event.get("kind") == "checkpoint" and event.get("hash") == checkpoint_hash]
    if not checkpoints:
        raise OrchestratorError(f"Checkpoint hash not found: {checkpoint_hash}")
    if any(event.get("kind") == "resume" and event.get("consumes_hash") == checkpoint_hash for event in events):
        raise OrchestratorError(f"Checkpoint hash has already been consumed: {checkpoint_hash}")
    resume_event = {
        "kind": "resume",
        "consumes_hash": checkpoint_hash,
        "stage": checkpoints[-1].get("stage"),
        "note": note,
        "created_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
    }
    append_checkpoint_event(state.path, resume_event)
    status = status_project(state.path)
    return {
        "status": "resumed",
        "project_path": str(state.path),
        "consumed_checkpoint_hash": checkpoint_hash,
        "next_action": status["next_action"],
    }


def run_pipeline(project: str | Path) -> dict[str, Any]:
    """Plan the next pipeline action from current project state."""
    status = status_project(project)
    if status["pipeline_state"] == "awaiting_confirmation":
        return {
            "status": "awaiting_confirmation",
            "project_path": status["project_path"],
            "awaiting_checkpoint": status["awaiting_checkpoint"],
            "next_action": status["next_action"],
        }
    if status["pipeline_state"] == "drift_detected":
        return {
            "status": "drift_detected",
            "project_path": status["project_path"],
            "drift": status["drift"],
            "next_action": status["next_action"],
        }
    return {
        "status": "planned",
        "project_path": status["project_path"],
        "pipeline_state": status["pipeline_state"],
        "next_action": status["next_action"],
    }


def handle_orchestrator_error(exc: Exception) -> dict[str, str]:
    if isinstance(exc, (OrchestratorError, PassportError, ProjectStateError)):
        return {"status": "error", "message": str(exc)}
    return {"status": "error", "message": str(exc)}
