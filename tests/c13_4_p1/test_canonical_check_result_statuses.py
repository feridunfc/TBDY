from __future__ import annotations

import pytest

from tbdy_engine.checks.diagnostics import CheckDiagnostic, CheckDiagnosticCode, CheckDiagnosticSeverity
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel


def test_check_status_has_required_values():
    assert {"OK", "FAIL", "WARNING", "NO_DATA", "BLOCKED", "OUT_OF_SCOPE"}.issubset(set(CheckStatus.__members__))


def test_blocked_result_serializes_and_forces_no_data_level():
    result = CheckResult(
        check_id="beam_geometry_min_width",
        component="B1",
        component_type="beam",
        status=CheckStatus.BLOCKED,
        evaluation_level=EvaluationLevel.SCREENING,
        diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.CHECK_NOT_ALLOWED, "policy pending"),),
    )
    payload = result.as_dict()
    assert payload["status"] == "BLOCKED"
    assert payload["evaluation_level"] == "NO_DATA"
    assert payload["diagnostics"][0]["code"] == "CHECK_NOT_ALLOWED"


def test_out_of_scope_result_serializes_and_forces_no_data_level():
    result = CheckResult(
        check_id="beam_geometry_min_width",
        component="C1",
        component_type="column",
        status=CheckStatus.OUT_OF_SCOPE,
        evaluation_level=EvaluationLevel.SCREENING,
    )
    payload = result.as_dict()
    assert payload["status"] == "OUT_OF_SCOPE"
    assert payload["evaluation_level"] == "NO_DATA"
    assert payload["diagnostics"] == []


def test_no_data_result_forces_no_data_level():
    result = CheckResult(
        check_id="beam_geometry_min_width",
        component="B1",
        component_type="beam",
        status=CheckStatus.NO_DATA,
        evaluation_level=EvaluationLevel.SCREENING,
    )
    assert result.evaluation_level == EvaluationLevel.NO_DATA


def test_legacy_result_fields_are_rejected():
    with pytest.raises(ValueError):
        CheckResult(check_id="x", component="B1", component_type="beam", status=CheckStatus.NO_DATA, id="legacy")
    with pytest.raises(ValueError):
        CheckResult(check_id="x", component="B1", component_type="beam", status=CheckStatus.NO_DATA, check_type="legacy")
