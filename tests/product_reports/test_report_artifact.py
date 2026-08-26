from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256

import pytest

from tbdy_engine.product_reports.report_artifact import ReportArtifact


def _digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def _artifact(content: bytes = b"%PDF-1.7\nexample") -> ReportArtifact:
    marker = _digest(b"marker")
    return ReportArtifact(
        logical_role="UNIFIED_ENGINEERING_REVIEW",
        format="PDF",
        media_type="application/pdf",
        filename="REPORT_1_engineering.pdf",
        view="ENGINEERING",
        content=content,
        source_report_id="REPORT:1",
        source_project_id="PROJECT:1",
        source_projection_sha256=marker,
        presentation_selection_sha256=marker,
        source_render_sha256=marker,
        options_sha256=marker,
        renderer_toolchain_fingerprint='{"profile":"toolchain.v1"}',
    )


def test_artifact_content_metadata_is_exact_and_content_addressed() -> None:
    artifact = _artifact()

    assert artifact.byte_length == len(artifact.content)
    assert artifact.sha256 == sha256(artifact.content).hexdigest()
    assert artifact.artifact_id.startswith("REPORT_ARTIFACT:sha256:")
    assert artifact.as_dict()["sha256"] == artifact.sha256
    assert artifact.as_dict()["byte_length"] == artifact.byte_length
    assert "content" not in artifact.as_dict()


def test_artifact_id_is_deterministic_for_identical_inputs() -> None:
    first = _artifact()
    second = _artifact()

    assert first.artifact_id == second.artifact_id
    assert first.sha256 == second.sha256
    assert first.as_dict() == second.as_dict()


def test_artifact_id_changes_with_content() -> None:
    first = _artifact(b"%PDF-1.7\nfirst")
    second = _artifact(b"%PDF-1.7\nsecond")

    assert first.sha256 != second.sha256
    assert first.artifact_id != second.artifact_id


def test_artifact_is_immutable() -> None:
    artifact = _artifact()

    with pytest.raises(FrozenInstanceError):
        artifact.filename = "other.pdf"  # type: ignore[misc]


def test_artifact_rejects_unsafe_filename_paths() -> None:
    marker = _digest(b"marker")
    with pytest.raises(ValueError, match="filesystem-safe basename"):
        ReportArtifact(
            logical_role="ROLE",
            format="PDF",
            media_type="application/pdf",
            filename="../report.pdf",
            view="ENGINEERING",
            content=b"x",
            source_report_id=None,
            source_project_id=None,
            source_projection_sha256=marker,
            presentation_selection_sha256=marker,
            source_render_sha256=marker,
            options_sha256=marker,
            renderer_toolchain_fingerprint="toolchain",
        )


def test_artifact_rejects_non_sha_fingerprints() -> None:
    marker = _digest(b"marker")
    with pytest.raises(ValueError, match="source_projection_sha256"):
        ReportArtifact(
            logical_role="ROLE",
            format="PDF",
            media_type="application/pdf",
            filename="report.pdf",
            view="ENGINEERING",
            content=b"x",
            source_report_id=None,
            source_project_id=None,
            source_projection_sha256="not-a-digest",
            presentation_selection_sha256=marker,
            source_render_sha256=marker,
            options_sha256=marker,
            renderer_toolchain_fingerprint="toolchain",
        )


def test_artifact_requires_immutable_nonempty_bytes() -> None:
    marker = _digest(b"marker")
    with pytest.raises(ValueError, match="immutable bytes"):
        ReportArtifact(
            logical_role="ROLE",
            format="PDF",
            media_type="application/pdf",
            filename="report.pdf",
            view="ENGINEERING",
            content=bytearray(b"x"),  # type: ignore[arg-type]
            source_report_id=None,
            source_project_id=None,
            source_projection_sha256=marker,
            presentation_selection_sha256=marker,
            source_render_sha256=marker,
            options_sha256=marker,
            renderer_toolchain_fingerprint="toolchain",
        )
