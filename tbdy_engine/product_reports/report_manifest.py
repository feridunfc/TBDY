"""Deterministic UR-1E report-package manifest.

The manifest cryptographically accounts for the seven non-manifest delivery
artifacts only. It deliberately does not contain a hash of its own final bytes;
its own content identity is represented externally by the common ReportArtifact.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Sequence

from tbdy_engine.product_reports.report_artifact import ReportArtifact


DEFAULT_PAYLOAD_FILENAMES = (
    "audit.html",
    "audit.pdf",
    "audit.xlsx",
    "building_report_model.json",
    "engineering.html",
    "engineering.pdf",
    "engineering.xlsx",
)
MANIFEST_FILENAME = "manifest.json"


class ReportManifestIntegrityError(ValueError):
    """Raised when bounded UR-1E payload accounting is incomplete or ambiguous."""


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _entry(artifact: ReportArtifact) -> dict[str, object]:
    metadata = artifact.as_dict()
    return {
        "filename": artifact.filename,
        "logical_role": artifact.logical_role,
        "format": artifact.format,
        "media_type": artifact.media_type,
        "view": artifact.view,
        "byte_length": artifact.byte_length,
        "sha256": artifact.sha256,
        "artifact_id": artifact.artifact_id,
        "source_report_id": metadata["source_report_id"],
        "source_project_id": metadata["source_project_id"],
        "source_model_sha256": metadata["source_model_sha256"],
        "source_projection_sha256": metadata["source_projection_sha256"],
        "presentation_selection_sha256": metadata["presentation_selection_sha256"],
        "source_render_sha256": metadata["source_render_sha256"],
        "options_sha256": metadata["options_sha256"],
        "renderer_toolchain_fingerprint": metadata["renderer_toolchain_fingerprint"],
    }


def _validate_payloads(
    payload_artifacts: Sequence[ReportArtifact],
) -> tuple[ReportArtifact, ...]:
    artifacts = tuple(payload_artifacts)
    if any(not isinstance(item, ReportArtifact) for item in artifacts):
        raise TypeError("payload_artifacts must contain ReportArtifact")
    filenames = tuple(item.filename for item in artifacts)
    if len(filenames) != len(set(filenames)):
        raise ReportManifestIntegrityError("payload filenames must be unique")
    if tuple(sorted(filenames)) != DEFAULT_PAYLOAD_FILENAMES:
        raise ReportManifestIntegrityError(
            "UR-1E default manifest must account for exactly the seven frozen non-manifest payloads"
        )
    return tuple(sorted(artifacts, key=lambda item: item.filename))


def build_report_manifest(
    payload_artifacts: Sequence[ReportArtifact],
) -> ReportArtifact:
    """Build deterministic package-integrity metadata for seven payload artifacts."""

    artifacts = _validate_payloads(payload_artifacts)
    report_ids = {item.source_report_id for item in artifacts}
    project_ids = {item.source_project_id for item in artifacts}
    if len(report_ids) != 1 or None in report_ids:
        raise ReportManifestIntegrityError(
            "all payload artifacts must carry one exact source_report_id"
        )
    if len(project_ids) != 1 or None in project_ids:
        raise ReportManifestIntegrityError(
            "all payload artifacts must carry one exact source_project_id"
        )

    canonical_model = next(
        item for item in artifacts if item.filename == "building_report_model.json"
    )
    if canonical_model.source_model_sha256 is None:
        raise ReportManifestIntegrityError(
            "canonical model artifact must carry source_model_sha256"
        )

    payload = {
        "schema_version": "report_manifest.ur_1e.v1",
        "artifact_type": "REPORT_PACKAGE_MANIFEST",
        "integrity_scope": "DELIVERY_ONLY",
        "global_compliance_verdict_emitted": False,
        "payload_inventory_policy": "SEVEN_NON_MANIFEST_ARTIFACTS",
        "manifest_self_reference_policy": (
            "MANIFEST_SHA256_AND_ARTIFACT_ID_ARE_EXTERNAL_REPORT_ARTIFACT_METADATA"
        ),
        "manifest_self_hash_in_payload_inventory": False,
        "payload_count": 7,
        "payloads": [_entry(item) for item in artifacts],
    }
    content = _canonical_json_bytes(payload)

    return ReportArtifact(
        logical_role="REPORT_PACKAGE_MANIFEST",
        format="JSON",
        media_type="application/json",
        filename=MANIFEST_FILENAME,
        content=content,
        view=None,
        source_report_id=next(iter(report_ids)),
        source_project_id=next(iter(project_ids)),
        source_model_sha256=canonical_model.source_model_sha256,
    )


def verify_manifest_payloads(
    manifest_artifact: ReportArtifact,
    payload_artifacts: Sequence[ReportArtifact],
) -> None:
    """Fail closed unless manifest bytes exactly account for supplied payloads."""

    if not isinstance(manifest_artifact, ReportArtifact):
        raise TypeError("manifest_artifact must be ReportArtifact")
    if manifest_artifact.filename != MANIFEST_FILENAME:
        raise ReportManifestIntegrityError("manifest artifact filename is invalid")
    artifacts = _validate_payloads(payload_artifacts)
    try:
        payload = json.loads(manifest_artifact.content.decode("utf-8"))
    except Exception as exc:
        raise ReportManifestIntegrityError("manifest JSON is invalid") from exc
    if payload.get("manifest_self_hash_in_payload_inventory") is not False:
        raise ReportManifestIntegrityError("manifest self-hash policy is invalid")
    entries = payload.get("payloads")
    if not isinstance(entries, list) or len(entries) != 7:
        raise ReportManifestIntegrityError("manifest must contain exactly seven payload entries")
    expected = [_entry(item) for item in artifacts]
    if entries != expected:
        raise ReportManifestIntegrityError(
            "manifest payload inventory does not match supplied ReportArtifact metadata"
        )
    if sha256(manifest_artifact.content).hexdigest() != manifest_artifact.sha256:
        raise ReportManifestIntegrityError("manifest ReportArtifact SHA-256 is inconsistent")


__all__ = [
    "DEFAULT_PAYLOAD_FILENAMES",
    "MANIFEST_FILENAME",
    "ReportManifestIntegrityError",
    "build_report_manifest",
    "verify_manifest_payloads",
]
