import pytest

from tbdy_engine.features.evidence import FeatureEvidence
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue


def evidence():
    return FeatureEvidence(
        evidence_status="FULL",
        source_table="frame_section_properties",
        actual_table_name="Frame Section Property Definitions - Concrete Rectangular",
        source_column="Width",
        source_row={"SectionName": "B40x70"},
        raw_value=400,
        normalized_value=400,
        unit="mm",
    )


def test_feature_snapshot_contains_features_and_evidence():
    feature = FeatureValue(feature_name="beam_width_mm", value=400, unit="mm", semantic_role="GEOMETRY", evidence=[evidence()])
    snapshot = FeatureSnapshot(
        component_type="beam",
        component_id="B1",
        identity={"story": "S1", "section": "B40x70"},
        features={"beam_width_mm": feature},
    )
    assert snapshot.features["beam_width_mm"].value == 400
    assert snapshot.evidence_by_feature["beam_width_mm"]
    assert "CheckResult" not in repr(snapshot.as_dict())


def test_feature_snapshot_cannot_contain_checkresult_semantics():
    with pytest.raises(ValueError):
        FeatureSnapshot(component_type="beam", component_id="B1", identity={"CheckResult": "legacy"})
