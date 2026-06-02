from __future__ import annotations

from dataclasses import dataclass, field
import json
import sys
from typing import Any


@dataclass
class ToolError(Exception):
    code: str
    message: str
    retryable: bool
    provider: str | None = None
    manifest: str | None = None
    task_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)


def error_payload(
    code: str,
    message: str,
    *,
    provider: str | None = None,
    manifest: str | None = None,
    task_id: str | None = None,
    retryable: bool,
    details: dict[str, Any] | None = None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "message": message,
        "provider": provider,
        "manifest": manifest,
        "task_id": task_id,
        "retryable": retryable,
        "details": details or {},
    }
    if extras:
        payload.update(extras)
    return payload


def payload_from_error(error: ToolError, **overrides: Any) -> dict[str, Any]:
    provider = overrides.pop("provider", None) or error.provider
    manifest = overrides.pop("manifest", None) or error.manifest
    task_id = overrides.pop("task_id", None) or error.task_id
    details = dict(error.details)
    details.update(overrides.pop("details", {}) or {})
    extras = dict(error.extras)
    extras.update(overrides)
    return error_payload(
        error.code,
        error.message,
        provider=provider,
        manifest=manifest,
        task_id=task_id,
        retryable=error.retryable,
        details=details,
        extras=extras,
    )


def emit_error(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
