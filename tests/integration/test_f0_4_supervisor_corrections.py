from __future__ import annotations

import pytest

from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.integration.f0_evidence_adapter import (
    EvidenceBindingSource,
    F0EvidenceBinding,
    build_component_f0_authorities,
)
from tbdy_engine.regulatory.beam_min_width import EVIDENCE_TRACE_KEY
from tbdy_engine.regulatory.contracts import (
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS


def _epoch(*, provenance_refs: object = ("capture:fixture:B1",)) -> EvidenceEpoch:
    return EvidenceEpoch(
        epoch_id="E17",
        model_fingerprint="model:fixture:sha256:abc",
        origin=EvidenceEpochOrigin.FIXTURE_REPLAY,
        source_fingerprint="source:fixture:sha256:def",
        provenance_refs=provenance_refs,  # type: ignore[arg-type]
    )


def test_evidence_epoch_rejects_string_bytes_and_arbitrary_iterable_provenance_refs() -> None:
    with pytest.raises(TypeError, match="tuple of strings"):
        _epoch(provenance_refs="abc")
    with pytest.raises(TypeError, match="tuple of strings"):
        _epoch(provenance_refs=b"abc")
    with pytest.raises(TypeError, match="tuple of strings"):
        _epoch(provenance_refs=["abc"])
    with pytest.raises(TypeError, match="tuple of strings"):
        _epoch(provenance_refs=(item for item in ("abc",)))


def test_evidence_epoch_rejects_non_string_tuple_member() -> None:
    with pytest.raises(TypeError, match="strings only"):
        _epoch(provenance_refs=("capture:fixture:B1", 7))


def test_evidence_epoch_preserves_valid_string_tuple() -> None:
    refs = ("capture:fixture:B1", "source:fixture:row:1")
    epoch = _epoch(provenance_refs=refs)
    assert type(epoch.provenance_refs) is tuple
    assert epoch.provenance_refs == refs


def test_f0_4_evidence_trace_excludes_legacy_system_and_selection_adjacent_fields() -> None:
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table="frame_section_assignments",
        actual_table_name="Frame Section Assignments",
        source_column="Width",
        source_row={"Story": "STORY1", "Label": "B1", "Section": "B300x500"},
        output_case="LC_G",
        combo_family="LEGACY_COMBO_FAMILY",
        governing_combo="LEGACY_GOVERNING_COMBO",
        section_state="LEGACY_SECTION_STATE",
        ductility_class="LEGACY_DUCTILITY_CLASS",
        raw_value=249.0,
        normalized_value=249.0,
        unit="mm",
        resolver="fixture-explicit-beam-width",
    )
    feature = FeatureValue(
        feature_name="beam_width_mm",
        value=249.0,
        unit="mm",
        semantic_role="GEOMETRY",
        status=FeatureValueStatus.RESOLVED,
        evidence=(evidence,),
    )
    snapshot = FeatureSnapshot(
        component_type="beam",
        component_id="B1",
        identity={"story": "STORY1", "section": "B300x500"},
        features={"beam_width_mm": feature},
    )
    binding = F0EvidenceBinding(
        source_location=EvidenceBindingSource.EVIDENCE_TRACE,
        source_key="beam_width_mm",
        dependency_key=EVIDENCE_TRACE_KEY,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.COMPONENT,
        unit=UNIT_DIMENSIONLESS,
    )

    authority = build_component_f0_authorities(
        epoch=_epoch(),
        snapshot=snapshot,
        bindings=(binding,),
    )[0]
    row = authority.value[0]

    assert row["output_case"] == "LC_G"
    assert row["raw_value"] == 249.0
    assert row["normalized_value"] == 249.0
    for forbidden in (
        "combo_family",
        "governing_combo",
        "ductility_class",
        "section_state",
    ):
        assert forbidden not in row
