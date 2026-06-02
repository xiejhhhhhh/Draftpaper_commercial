from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from .project_scaffold import _write_json, utc_now


Runner = Callable[..., dict[str, Any]]
TARGET_CONTEXTS = {"data", "methods"}
MIN_CONTEXT_ITEMS = 5


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _vendored_source() -> Path | None:
    source = _repo_root() / "third_party" / "paper-fetch-skill" / "src"
    return source if source.exists() else None


def resolve_paper_fetch_command(command: list[str] | None = None) -> tuple[list[str] | None, dict[str, str], str]:
    env: dict[str, str] = {}
    if command:
        executable = command[0]
        if Path(executable).exists() or shutil.which(executable):
            return command, env, "explicit"
        return None, env, "explicit_missing"
    path_command = shutil.which("paper-fetch")
    if path_command:
        return [path_command], env, "path"
    source = _vendored_source()
    if source:
        env["PYTHONPATH"] = str(source)
        return [sys.executable, "-m", "paper_fetch.cli"], env, "vendored"
    return None, env, "missing"


def _default_runner(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def _target_text(item: dict[str, Any]) -> str:
    return str(item.get("doi") or item.get("url") or item.get("title") or "").strip()


def _has_readable_text(item: dict[str, Any]) -> bool:
    return bool(str(item.get("abstract") or item.get("pdf_text_excerpt") or "").strip())


def _context_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {context: 0 for context in TARGET_CONTEXTS}
    for item in items:
        context = str(item.get("search_context") or "").lower()
        if context in counts and _has_readable_text(item):
            counts[context] += 1
    return counts


def _select_targets(items: list[dict[str, Any]], *, min_per_context: int) -> list[tuple[int, dict[str, Any]]]:
    counts = _context_counts(items)
    targets = []
    for index, item in enumerate(items):
        context = str(item.get("search_context") or "").lower()
        if context not in TARGET_CONTEXTS or counts[context] >= min_per_context or _has_readable_text(item):
            continue
        if not _target_text(item):
            continue
        targets.append((index, item))
        counts[context] += 1
    return targets


def _safe_stem(text: str, fallback: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_").lower()
    return (stem[:72].strip("_") or fallback)


def _extract_metadata(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    article = payload.get("article") if isinstance(payload.get("article"), dict) else payload
    metadata = article.get("metadata") if isinstance(article.get("metadata"), dict) else {}
    return metadata if isinstance(metadata, dict) else {}


def _extract_markdown(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    markdown = payload.get("markdown")
    if isinstance(markdown, str):
        return markdown
    article = payload.get("article")
    if isinstance(article, dict):
        sections = article.get("sections")
        if isinstance(sections, list):
            parts = []
            for section in sections:
                if isinstance(section, dict):
                    parts.append(str(section.get("text") or section.get("content") or ""))
            return "\n\n".join(part for part in parts if part)
    return ""


def _apply_payload(item: dict[str, Any], payload_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return item
    metadata = _extract_metadata(payload)
    markdown = _extract_markdown(payload)
    abstract = str(metadata.get("abstract") or "").strip()
    enriched = dict(item)
    if metadata.get("title") and not enriched.get("title"):
        enriched["title"] = metadata.get("title")
    if metadata.get("doi") and not enriched.get("doi"):
        enriched["doi"] = metadata.get("doi")
    if metadata.get("year") and not enriched.get("year"):
        enriched["year"] = str(metadata.get("year"))
    if abstract:
        enriched["abstract"] = abstract
    elif markdown:
        enriched["abstract"] = re.sub(r"\s+", " ", markdown).strip()[:1200]
    if markdown:
        enriched["pdf_text_excerpt"] = re.sub(r"\s+", " ", markdown).strip()[:5000]
    enriched["paper_fetch_markdown_path"] = str(payload_path)
    enriched["paper_fetch_status"] = "enriched" if (abstract or markdown) else "metadata_only"
    return enriched


def enrich_with_paper_fetch(
    project: str | Path,
    items: list[dict[str, Any]],
    *,
    min_per_context: int = MIN_CONTEXT_ITEMS,
    command: list[str] | None = None,
    runner: Runner | None = None,
    timeout: int = 90,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    project_path = Path(project)
    references_dir = project_path / "references"
    fulltext_dir = references_dir / "fulltext"
    references_dir.mkdir(parents=True, exist_ok=True)
    fulltext_dir.mkdir(parents=True, exist_ok=True)

    targets = _select_targets(items, min_per_context=min_per_context)
    query_file = references_dir / "paper_fetch_queries.txt"
    query_file.write_text("\n".join(_target_text(item) for _, item in targets) + ("\n" if targets else ""), encoding="utf-8")

    if runner is not None and command is None:
        base_command, extra_env, runtime_source = ["paper-fetch"], {}, "injected"
    else:
        base_command, extra_env, runtime_source = resolve_paper_fetch_command(command)
    manifest: dict[str, Any] = {
        "status": "skipped",
        "runtime_source": runtime_source,
        "started_at": utc_now(),
        "query_file": str(query_file),
        "output_dir": str(fulltext_dir),
        "attempted_count": len(targets),
        "success_count": 0,
        "failures": [],
        "outputs": [],
    }
    if not targets:
        manifest["finished_at"] = utc_now()
        _write_json(references_dir / "paper_fetch_manifest.json", manifest)
        return items, manifest
    if not base_command:
        manifest["status"] = "unavailable"
        manifest["finished_at"] = utc_now()
        _write_json(references_dir / "paper_fetch_manifest.json", manifest)
        return items, manifest

    run = runner or _default_runner
    enriched = list(items)
    for target_index, item in targets:
        target = _target_text(item)
        output_path = fulltext_dir / f"{target_index + 1:02d}_{_safe_stem(str(item.get('title') or target), 'paper')}.json"
        fetch_command = [
            *base_command,
            "--query",
            target,
            "--format",
            "both",
            "--output",
            str(output_path),
            "--output-dir",
            str(fulltext_dir),
            "--asset-profile",
            "none",
            "--artifact-mode",
            "markdown-assets",
            "--no-download",
        ]
        try:
            result = run(fetch_command, cwd=project_path, env=extra_env, timeout=timeout)
        except Exception as exc:
            manifest["failures"].append({"query": target, "error": str(exc)})
            continue
        if int(result.get("returncode") or 0) != 0:
            manifest["failures"].append({
                "query": target,
                "returncode": result.get("returncode"),
                "stderr": result.get("stderr", ""),
            })
            continue
        if not output_path.exists():
            manifest["failures"].append({"query": target, "error": "paper-fetch produced no output file"})
            continue
        enriched[target_index] = _apply_payload(item, output_path)
        if _has_readable_text(enriched[target_index]):
            manifest["success_count"] += 1
            manifest["outputs"].append(str(output_path))
    manifest["status"] = "completed" if manifest["success_count"] else "failed"
    manifest["finished_at"] = utc_now()
    _write_json(references_dir / "paper_fetch_manifest.json", manifest)
    return enriched, manifest
