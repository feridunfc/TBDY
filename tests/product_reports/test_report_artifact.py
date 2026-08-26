from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256

import pytest

from tbdy_engine.product_reports.report_artifact import ReportArtifact


def _digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def _pdf_artifact(content: bytes = b"%PDF-1.7\nexample") -> ReportArtifact:
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


def _generic_artifact(
    *,
    source_model_sha256: str | None = None,
    content: bytes = b'{"report":"canonical"}\n',
) -> ReportArtifact:
    return ReportArtifact(
        logical_role="CANONICAL_BUILDING_REPORT_MODEL",
        format="JSON",
        media_type="application/json",
        filename="building_report_model.json",
        content=content,
        view=None,
        source_report_id="REPORT:1",
        source_project_id="PROJECT:1",
        source_model_sha256=source_model_sha256,
    )


def test_artifact_content_metadata_is_exact_and_content_addressed() -> None:
    artifact = _pdf_artifact()

    assert artifact.byte_length == len(artifact.content)
    assert artifact.sha256 == sha256(artifact.content).hexdigest()
    assert artifact.artifact_id.startswith("REPORT_ARTIFACT:sha256:")
    assert artifact.as_dict()["sha256"] == artifact.sha256
    assert artifact.as_dict()["byte_length"] == artifact.byte_length
    assert "content" not in artifact.as_dict()


def test_generic_non_view_artifact_requires_no_fake_presentation_provenance() -> None:
    model_sha = _digest(b"canonical-model")
    artifact = _generic_artifact(source_model_sha256=model_sha)

    assert artifact.format == "JSON"
    assert artifact.view is None
    assert artifact.source_model_sha256 == model_sha
    assert artifact.source_projection_sha256 is None
    assert artifact.presentation_selection_sha256 is None
    assert artifact.source_render_sha256 is None
    assert artifact.options_sha256 is None
    assert artifact.renderer_toolchain_fingerprint is None
    assert artifact.as_dict()["view"] is None
    assert artifact.as_dict()["source_projection_sha256"] is None


def test_generic_artifact_may_omit_all_nonapplicable_provenance() -> None:
    artifact = _generic_artifact()

    assert artifact.source_model_sha256 is None
    assert artifact.source_projection_sha256 is None
    assert artifact.presentation_selection_sha256 is None
    assert artifact.source_render_sha256 is None
    assert artifact.options_sha256 is None
    assert artifact.renderer_toolchain_fingerprint is None


@pytest.mark.parametrize(
    "field_name",
    [
        "source_model_sha256",
        "source_projection_sha256",
        "presentation_selection_sha256",
        "source_render_sha256",
        "options_sha256",
    ],
)
def test_optional_sha_fields_validate_when_supplied(field_name: str) -> None:
    kwargs = {
        "logical_role": "ROLE",
        "format": "JSON",
        "media_type": "application/json",
        "filename": "report.json",
        "content": b"{}\n",
        field_name: "NOT-A-LOWERCASE-SHA256",
    }

    with pytest.raises(ValueError, match=field_name):
        ReportArtifact(**kwargs)


def test_optional_sha_fields_preserve_none_exactly() -> None:
    artifact = _generic_artifact()

    assert artifact.source_model_sha256 is None
    assert artifact.as_dict()["source_model_sha256"] is None


def test_artifact_id_is_deterministic_for_identical_pdf_inputs() -> None:
    first = _pdf_artifact()
    second = _pdf_artifact()

    assert first.artifact_id == second.artifact_id
    assert first.sha256 == second.sha256
    assert first.as_dict() == second.as_dict()


def test_generic_artifact_id_is_deterministic_for_identical_inputs() -> None:
    model_sha = _digest(b"canonical-model")
    first = _generic_artifact(source_model_sha256=model_sha)
    second = _generic_artifact(source_model_sha256=model_sha)

    assert first.artifact_id == second.artifact_id
    assert first.as_dict() == second.as_dict()


def test_generic_artifact_id_changes_with_source_model_sha256() -> None:
    first = _generic_artifact(source_model_sha256=_digest(b"model-a"))
    second = _generic_artifact(source_model_sha256=_digest(b"model-b"))

    assert first.content == second.content
    assert first.sha256 == second.sha256
    assert first.artifact_id != second.artifact_id


def test_artifact_id_changes_with_content() -> None:
    first = _pdf_artifact(b"%PDF-1.7\nfirst")
    second = _pdf_artifact(b"%PDF-1.7\nsecond")

    assert first.sha256 != second.sha256
    assert first.artifact_id != second.artifact_id


def test_artifact_is_immutable() -> None:
    artifact = _pdf_artifact()

    with pytest.raises(FrozenInstanceError):
        artifact.filename = "other.pdf"  # type: ignore[misc]


def test_artifact_rejects_unsafe_filename_paths() -> None:
    with pytest.raises(ValueError, match="filesystem-safe basename"):
        ReportArtifact(
            logical_role="ROLE",
            format="JSON",
            media_type="application/json",
            filename="../report.json",
            content=b"{}",
        )


def test_artifact_requires_immutable_nonempty_bytes() -> None:
    with pytest.raises(ValueError, match="immutable bytes"):
        ReportArtifact(
            logical_role="ROLE",
            format="JSON",
            media_type="application/json",
            filename="report.json",
            content=bytearray(b"x"),  # type: ignore[arg-type]
        )
