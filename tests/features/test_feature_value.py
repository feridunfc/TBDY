import pytest

from tbdy_engine.features.evidence import FeatureEvidence
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus


def full_evidence():
    return FeatureEvidence(
        evidence_status="FULL",
        source_table="story_definitions",
        actual_table_name="Story Definitions",
        source_column="Height",
        source_row={"Story": "S1"},
        raw_value=3000,
        normalized_value=3000,
        unit="mm",
    )


@pytest.mark.parametrize("bad_name", ["beam_ratio", "beam_status", "beam_pass", "beam_fail", "beam_ok"])
def test_feature_value_cannot_use_ratio_status_pass_fail_feature_names(bad_name):
    with pytest.raises(ValueError):
        FeatureValue(feature_name=bad_name, value=1, unit="", semantic_role="DATA", evidence=[full_evidence()])


def test_resolved_feature_requires_evidence():
    with pytest.raises(ValueError):
        FeatureValue(feature_name="beam_width_mm", value=400, unit="mm", semantic_role="GEOMETRY")


def test_missing_evidence_makes_feature_partial_or_missing():
    partial = FeatureValue(feature_name="beam_width_mm", value=None, unit="mm", semantic_role="GEOMETRY", status="PARTIAL")
    assert partial.status == FeatureValueStatus.PARTIAL
    assert partial.diagnostics
