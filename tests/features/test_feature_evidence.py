import pytest

from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus


def test_full_feature_evidence_requires_source_fields():
    evidence = FeatureEvidence(
        evidence_status="FULL",
        source_table="frame_section_properties",
        actual_table_name="Frame Section Property Definitions - Concrete Rectangular",
        source_column="Width",
        source_row={"SectionName": "B40x70"},
        raw_value=400,
        normalized_value=400,
        unit="mm",
        resolver="generic_table_resolver",
    )
    assert evidence.evidence_status == FeatureEvidenceStatus.FULL
    assert evidence.as_dict()["source_column"] == "Width"


def test_partial_or_missing_feature_evidence_requires_reason():
    with pytest.raises(ValueError):
        FeatureEvidence(evidence_status="PARTIAL")
    missing = FeatureEvidence(evidence_status="MISSING", reason="table missing")
    assert missing.evidence_status == FeatureEvidenceStatus.MISSING
