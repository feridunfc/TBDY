import pytest

from tbdy_engine.checks.result import CheckResult
from tbdy_engine.features.snapshot import FeatureSnapshot


def _snapshot(identity):
    return FeatureSnapshot(
        component_type="beam",
        component_id="B1",
        identity=identity,
        features={},
    )


def test_identity_value_story_smoke_is_accepted():
    snapshot = _snapshot({"story": "STORY_SMOKE", "component": "STORY_SMOKE"})
    assert snapshot.identity["story"] == "STORY_SMOKE"


def test_identity_value_okul_is_accepted():
    snapshot = _snapshot({"story": "OKUL", "label": "B1"})
    assert snapshot.identity["story"] == "OKUL"


@pytest.mark.parametrize("key", ["check_result", "pass_rule"])
def test_identity_forbidden_key_rejected_with_path_key_token(key):
    with pytest.raises(ValueError) as exc:
        _snapshot({"story": "S1", key: "legacy"})
    message = str(exc.value)
    assert "path=" in message
    assert "key=" in message
    assert "token=" in message
    assert key in message


def test_nested_identity_forbidden_key_rejected_with_offending_path():
    with pytest.raises(ValueError) as exc:
        _snapshot({"nested": {"status_counts": {"OK": 1}}})
    assert "identity.nested.status_counts" in str(exc.value)


def test_feature_snapshot_still_rejects_checkresult_object_in_features():
    result = CheckResult(
        check_id="beam_geometry_min_width",
        component="B1",
        component_type="beam",
        story="S1",
        section="B40x70",
        status="OK",
    )
    with pytest.raises(TypeError):
        FeatureSnapshot(
            component_type="beam",
            component_id="B1",
            identity={"story": "STORY_SMOKE"},
            features={"beam_width_mm": result},
        )
