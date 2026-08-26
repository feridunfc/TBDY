"""Generic immutable delivery artifact contract for report exports.

The artifact contract records delivery metadata and exact content identity only.
It owns no engineering, regulatory, closure, coverage, or compliance semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256 as _sha256
import json
import re


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _exact_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a nonblank exact string")
    return value


def _optional_exact_text(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    return _exact_text(value, label)


def _sha256_text(value: str, label: str) -> str:
    value = _exact_text(value, label)
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")
    return value


def _safe_filename(value: str) -> str:
    value = _exact_text(value, "filename")
    if value in {".", ".."} or "/" in value or "\\" in value or "\x00" in value:
        raise ValueError("filename must be a filesystem-safe basename")
    return value


@dataclass(frozen=True, slots=True)
class ReportArtifact:
    """One deterministic content-addressed report delivery artifact."""

    logical_role: str
    format: str
    media_type: str
    filename: str
    view: str
    content: bytes = field(repr=False)
    source_report_id: str | None
    source_project_id: str | None
    source_projection_sha256: str
    presentation_selection_sha256: str
    source_render_sha256: str
    options_sha256: str
    renderer_toolchain_fingerprint: str
    byte_length: int = field(init=False)
    sha256: str = field(init=False)
    artifact_id: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "logical_role", _exact_text(self.logical_role, "logical_role"))
        object.__setattr__(self, "format", _exact_text(self.format, "format"))
        object.__setattr__(self, "media_type", _exact_text(self.media_type, "media_type"))
        object.__setattr__(self, "filename", _safe_filename(self.filename))
        object.__setattr__(self, "view", _exact_text(self.view, "view"))
        object.__setattr__(
            self,
            "source_report_id",
            _optional_exact_text(self.source_report_id, "source_report_id"),
        )
        object.__setattr__(
            self,
            "source_project_id",
            _optional_exact_text(self.source_project_id, "source_project_id"),
        )
        object.__setattr__(
            self,
            "source_projection_sha256",
            _sha256_text(self.source_projection_sha256, "source_projection_sha256"),
        )
        object.__setattr__(
            self,
            "presentation_selection_sha256",
            _sha256_text(
                self.presentation_selection_sha256,
                "presentation_selection_sha256",
            ),
        )
        object.__setattr__(
            self,
            "source_render_sha256",
            _sha256_text(self.source_render_sha256, "source_render_sha256"),
        )
        object.__setattr__(
            self,
            "options_sha256",
            _sha256_text(self.options_sha256, "options_sha256"),
        )
        object.__setattr__(
            self,
            "renderer_toolchain_fingerprint",
            _exact_text(
                self.renderer_toolchain_fingerprint,
                "renderer_toolchain_fingerprint",
            ),
        )
        if not isinstance(self.content, bytes) or not self.content:
            raise ValueError("content must be non-empty immutable bytes")

        content_sha256 = _sha256(self.content).hexdigest()
        object.__setattr__(self, "byte_length", len(self.content))
        object.__setattr__(self, "sha256", content_sha256)

        identity_payload = {
            "logical_role": self.logical_role,
            "format": self.format,
            "media_type": self.media_type,
            "filename": self.filename,
            "view": self.view,
            "byte_length": len(self.content),
            "sha256": content_sha256,
            "source_report_id": self.source_report_id,
            "source_project_id": self.source_project_id,
            "source_projection_sha256": self.source_projection_sha256,
            "presentation_selection_sha256": self.presentation_selection_sha256,
            "source_render_sha256": self.source_render_sha256,
            "options_sha256": self.options_sha256,
            "renderer_toolchain_fingerprint": self.renderer_toolchain_fingerprint,
        }
        identity_bytes = json.dumps(
            identity_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        object.__setattr__(
            self,
            "artifact_id",
            "REPORT_ARTIFACT:sha256:" + _sha256(identity_bytes).hexdigest(),
        )

    def as_dict(self) -> dict[str, object]:
        """Return deterministic JSON-safe delivery metadata without duplicating content."""

        return {
            "artifact_id": self.artifact_id,
            "logical_role": self.logical_role,
            "format": self.format,
            "media_type": self.media_type,
            "filename": self.filename,
            "view": self.view,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
            "source_report_id": self.source_report_id,
            "source_project_id": self.source_project_id,
            "source_projection_sha256": self.source_projection_sha256,
            "presentation_selection_sha256": self.presentation_selection_sha256,
            "source_render_sha256": self.source_render_sha256,
            "options_sha256": self.options_sha256,
            "renderer_toolchain_fingerprint": self.renderer_toolchain_fingerprint,
        }


__all__ = ["ReportArtifact"]
