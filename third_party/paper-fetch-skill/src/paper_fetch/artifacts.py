"""Artifact writing and download diagnostics policies."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Literal, Mapping

from .extraction.html.assets.dom import preview_dimensions_are_acceptable
from .models import AssetProfile
from .provider_catalog import provider_persists_provider_html
from .reason_codes import PDF_FALLBACK
from .tracing import download_marker
from .utils import (
    build_output_path,
    extension_from_content_type,
    extend_unique,
    normalize_text,
    provider_display_name,
    safe_text,
    sanitize_filename,
)


ArtifactMode = Literal["markdown-assets", "all", "none"]
DEFAULT_ARTIFACT_MODE: ArtifactMode = "all"


@dataclass(frozen=True)
class DownloadPolicy:
    """Controls whether provider artifacts are materialized locally."""

    download_dir: Path | None = None
    artifact_mode: ArtifactMode = DEFAULT_ARTIFACT_MODE

    def __post_init__(self) -> None:
        if self.artifact_mode not in {"markdown-assets", "all", "none"}:
            raise ValueError(
                "artifact_mode must be one of: markdown-assets, all, none."
            )

    @property
    def asset_download_dir(self) -> Path | None:
        if self.artifact_mode in {"markdown-assets", "all"}:
            return self.download_dir
        return None

    @property
    def allows_auxiliary_artifacts(self) -> bool:
        return self.artifact_mode == "all" and self.download_dir is not None

    @property
    def allows_http_disk_cache(self) -> bool:
        return self.artifact_mode == "all"

    @property
    def allows_structured_sidecars(self) -> bool:
        return self.artifact_mode == "all"

    @property
    def allows_provider_html(self) -> bool:
        return self.artifact_mode == "all" and self.download_dir is not None

    def allows_provider_payload(self, content: Any) -> bool:
        if self.download_dir is None or self.artifact_mode == "none":
            return False
        if self.artifact_mode == "all":
            return True
        return _is_pdf_fallback_content(content)


@dataclass
class ArtifactStore:
    """Centralizes provider payload saves and artifact diagnostics."""

    policy: DownloadPolicy = field(default_factory=DownloadPolicy)

    @classmethod
    def from_download_dir(
        cls,
        download_dir: Path | None,
        *,
        artifact_mode: ArtifactMode = DEFAULT_ARTIFACT_MODE,
    ) -> "ArtifactStore":
        return cls(DownloadPolicy(download_dir=download_dir, artifact_mode=artifact_mode))

    @property
    def download_dir(self) -> Path | None:
        return self.policy.download_dir

    @property
    def artifact_mode(self) -> ArtifactMode:
        return self.policy.artifact_mode

    @property
    def asset_download_dir(self) -> Path | None:
        return self.policy.asset_download_dir

    @property
    def allows_auxiliary_artifacts(self) -> bool:
        return self.policy.allows_auxiliary_artifacts

    @property
    def allows_http_disk_cache(self) -> bool:
        return self.policy.allows_http_disk_cache

    @property
    def allows_structured_sidecars(self) -> bool:
        return self.policy.allows_structured_sidecars

    def write_text_file(self, path: Path, text: str, *, encoding: str = "utf-8") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".part")
        try:
            tmp_path.write_text(text, encoding=encoding)
            tmp_path.replace(path)
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return path

    def write_bytes_file(self, path: Path, body: bytes) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".part")
        try:
            tmp_path.write_bytes(body)
            tmp_path.replace(path)
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return path

    def write_json_file(self, path: Path, payload: Mapping[str, Any]) -> Path:
        return self.write_text_file(
            path,
            json.dumps(dict(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_provider_payload(
        self,
        provider_name: str,
        *,
        content: Any,
        doi: str | None,
        metadata: Mapping[str, Any],
    ) -> tuple[list[str], list[str]]:
        if content is None or not content.needs_local_copy:
            return [], []
        provider_slug = safe_text(provider_name or "provider").lower().replace(" ", "_") or "provider"
        provider_label = provider_display_name(provider_slug)
        if self.download_dir is None:
            return [f"{provider_label} official PDF/binary was not written to disk because --no-download was set."], [
                download_marker(provider_slug, "skipped")
            ]
        if not self.policy.allows_provider_payload(content):
            return [], []
        output_path = build_output_path(
            self.download_dir,
            doi,
            safe_text(metadata.get("title")),
            content.content_type,
            content.source_url,
        )
        if output_path is not None:
            saved_path = self.write_bytes_file(output_path, content.body)
            return [f"{provider_label} official full text was downloaded as PDF/binary to {saved_path}."], [
                download_marker(provider_slug, "saved")
            ]
        return [f"{provider_label} official full text was available only as PDF/binary and could not be written to disk."], [
            download_marker(f"{provider_slug}_save_failed")
        ]

    def provider_html_output_path(
        self,
        provider_name: str,
        *,
        content: Any,
        doi: str | None,
        metadata: Mapping[str, Any],
    ) -> Path | None:
        if content is None or not self.policy.allows_provider_html:
            return None
        if not provider_persists_provider_html(provider_name):
            return None
        if normalize_text(content.route_kind).lower() != "html":
            return None

        extension = extension_from_content_type(content.content_type, content.source_url).lower()
        if extension not in {".html", ".htm"}:
            return None

        article_slug = sanitize_filename(doi or safe_text(metadata.get("title")) or "article")
        if self.download_dir.name == article_slug:
            return self.download_dir / f"original{extension}"
        return self.download_dir / f"{article_slug}_original{extension}"

    def save_provider_html_payload(
        self,
        provider_name: str,
        *,
        content: Any,
        doi: str | None,
        metadata: Mapping[str, Any],
    ) -> tuple[list[str], list[str]]:
        output_path = self.provider_html_output_path(
            provider_name,
            content=content,
            doi=doi,
            metadata=metadata,
        )
        if output_path is None or content is None:
            return [], []
        self.write_bytes_file(output_path, content.body)
        return [], [download_marker(f"{normalize_text(provider_name).lower()}_html", "saved")]

    def apply_provider_artifacts(
        self,
        *,
        provider_name: str,
        artifacts: Any,
        asset_profile: AssetProfile,
        warnings: list[str],
        source_trail: list[str],
    ) -> None:
        if self.asset_download_dir is None:
            return
        if asset_profile == "none":
            extend_unique(source_trail, [download_marker(f"{provider_name}_assets_skipped_profile_none")])
            return
        if artifacts.skip_warning:
            extend_unique(warnings, [artifacts.skip_warning])
            extend_unique(source_trail, [event.marker() for event in artifacts.skip_trace if event.marker()])
            return
        if artifacts.assets:
            extend_unique(source_trail, [download_marker(f"{provider_name}_assets_saved_profile_{asset_profile}")])
            preview_assets = [
                asset
                for asset in artifacts.assets
                if normalize_text(asset.get("download_tier")).lower() == "preview"
            ]
            preview_accepted_count = sum(1 for asset in preview_assets if _preview_asset_accepted(asset))
            preview_fallback_count = len(preview_assets) - preview_accepted_count
            if preview_accepted_count:
                extend_unique(source_trail, [download_marker(f"{provider_name}_assets_preview", "accepted")])
            if preview_fallback_count:
                extend_unique(
                    warnings,
                    [
                        (
                            f"{provider_display_name(provider_name)} figure downloads fell back to preview images for "
                            f"{preview_fallback_count} asset(s) because full-size/original downloads were unavailable."
                        )
                    ],
                )
                extend_unique(source_trail, [download_marker(f"{provider_name}_assets_preview_fallback")])
        if artifacts.asset_failures:
            extend_unique(
                warnings,
                [
                    (
                        f"{provider_display_name(provider_name)} related assets were only partially downloaded "
                        f"({len(artifacts.asset_failures)} failed)."
                    )
                ],
            )
            extend_unique(source_trail, [download_marker(f"{provider_name}_asset_failures")])


def _preview_asset_accepted(asset: Mapping[str, Any]) -> bool:
    if bool(asset.get("preview_accepted")):
        return True
    try:
        width = int(asset.get("width") or 0)
        height = int(asset.get("height") or 0)
    except (TypeError, ValueError):
        return False
    return preview_dimensions_are_acceptable(width, height)


def _is_pdf_fallback_content(content: Any) -> bool:
    return normalize_text(getattr(content, "route_kind", "")).lower() == PDF_FALLBACK


__all__ = [
    "ArtifactMode",
    "DEFAULT_ARTIFACT_MODE",
    "DownloadPolicy",
    "ArtifactStore",
]
