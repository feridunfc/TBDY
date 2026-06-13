import pytest

from tbdy_engine.checks.result import CheckResult


def test_check_result_canonical_fields():
    result = CheckResult(
        check_id="beam_geometry_min_width",
        component="B1",
        component_type="beam",
        story="+14.5",
        section="B30x60",
        status="OK",
        value=300,
        limit=250,
        ratio=1.2,
        ratio_type="actual_over_minimum",
        pass_rule="actual_over_minimum",
        unit="mm",
        evidence=[],
        messages=[],
        code_ref="contract",
    )
    payload = result.as_dict()
    assert payload["check_id"] == "beam_geometry_min_width"
    assert payload["status"] == "OK"
    assert "id" not in payload
    assert "check_type" not in payload


def test_check_result_rejects_legacy_id_check_type():
    with pytest.raises(ValueError):
        CheckResult(check_id="x", component="c", component_type="beam", status="NO_DATA", id="legacy")
    with pytest.raises(ValueError):
        CheckResult(check_id="x", component="c", component_type="beam", status="NO_DATA", check_type="legacy")


def test_check_result_unknown_ratio_type_rejected():
    with pytest.raises(ValueError):
        CheckResult(check_id="x", component="c", component_type="beam", status="OK", ratio_type="mystery")
