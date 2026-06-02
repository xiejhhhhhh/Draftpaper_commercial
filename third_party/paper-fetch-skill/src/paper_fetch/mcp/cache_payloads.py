"""Payload glue for MCP cache listing and lookup tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from mcp.types import CallToolResult

from ._deps import MCPDeps, default_mcp_deps
from .fetch_cache import FetchCache
from .results import _tool_result, error_payload_from_exception
from .schemas import ResolvePaperRequest

_MCP_DEFAULT_DOWNLOAD_DIR = object()


def _resolve_download_dir(
    runtime_env: Mapping[str, str],
    download_dir: Path | None | object,
    *,
    deps: MCPDeps = default_mcp_deps(),
) -> Path | None:
    if download_dir is _MCP_DEFAULT_DOWNLOAD_DIR:
        return deps.resolve_mcp_download_dir(runtime_env)
    return download_dir


def list_cached_payload(
    *,
    env: Mapping[str, str] | None = None,
    download_dir: Path | None | object = _MCP_DEFAULT_DOWNLOAD_DIR,
    deps: MCPDeps = default_mcp_deps(),
) -> dict[str, Any]:
    runtime_env = deps.build_runtime_env(env)
    effective_download_dir = _resolve_download_dir(runtime_env, download_dir, deps=deps)
    return FetchCache(
        effective_download_dir,
        list_cache_entries_fn=deps.list_cache_entries,
    ).list_payload()


def get_cached_payload(
    *,
    doi: str,
    env: Mapping[str, str] | None = None,
    download_dir: Path | None | object = _MCP_DEFAULT_DOWNLOAD_DIR,
    deps: MCPDeps = default_mcp_deps(),
) -> dict[str, Any]:
    request = ResolvePaperRequest(query=doi)
    runtime_env = deps.build_runtime_env(env)
    effective_download_dir = _resolve_download_dir(runtime_env, download_dir, deps=deps)
    return FetchCache(
        effective_download_dir,
        refresh_cache_index_for_doi_fn=deps.refresh_cache_index_for_doi,
        preferred_cached_entries_fn=deps.preferred_cached_entries,
    ).get_payload(request.composed_query())


def cached_entry_payload(
    *,
    entry_id: str,
    env: Mapping[str, str] | None = None,
    deps: MCPDeps = default_mcp_deps(),
) -> dict[str, Any] | None:
    runtime_env = deps.build_runtime_env(env)
    default_download_dir = deps.resolve_mcp_download_dir(runtime_env)
    return deps.find_cached_entry(default_download_dir, entry_id)


def list_cached_tool(
    *,
    env: Mapping[str, str] | None = None,
    download_dir: Path | None | object = _MCP_DEFAULT_DOWNLOAD_DIR,
    deps: MCPDeps = default_mcp_deps(),
) -> CallToolResult:
    try:
        return _tool_result(
            list_cached_payload(
                env=env,
                download_dir=download_dir,
                deps=deps,
            ),
            is_error=False,
        )
    except Exception as error:
        return _tool_result(error_payload_from_exception(error), is_error=True)


def get_cached_tool(
    *,
    doi: str,
    env: Mapping[str, str] | None = None,
    download_dir: Path | None | object = _MCP_DEFAULT_DOWNLOAD_DIR,
    deps: MCPDeps = default_mcp_deps(),
) -> CallToolResult:
    try:
        return _tool_result(
            get_cached_payload(
                doi=doi,
                env=env,
                download_dir=download_dir,
                deps=deps,
            ),
            is_error=False,
        )
    except Exception as error:
        return _tool_result(error_payload_from_exception(error), is_error=True)
