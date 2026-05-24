from __future__ import annotations

from types import SimpleNamespace

from tbdy_engine.reports.action_summary import ActionSummaryBuilder


def _check(check_id: str, status: str, severity=None):
    payload = {
        "check_id": check_id,
        "element_label": "C1",
        "story": "Story1",
        "status": status,
        "ratio": 1.25,
        "message": "message",
        "action": "action",
        "tbdy_ref": "TBDY",
        "evaluation_level": "DESIGN_LEVEL",
        "source": "contract-test",
        "category": "STRENGTH",
    }
    if severity is not None:
        payload["severity"] = severity
    return SimpleNamespace(**payload)


def _ids(items):
    return [item["check_id"] for item in items]


def test_action_summary_includes_fail_and_warning_for_high_medium_severity():
    checks = [
        _check("fail_high", "FAIL", "HIGH"),
        _check("warning_medium", "WARNING", "MEDIUM"),
    ]

    assert _ids(ActionSummaryBuilder().build(checks)) == ["fail_high", "warning_medium"]


def test_action_summary_excludes_error_and_partial_by_contract_default():
    checks = [
        _check("error_high", "ERROR", "HIGH"),
        _check("partial_medium", "PARTIAL", "MEDIUM"),
        _check("fail_high", "FAIL", "HIGH"),
    ]

    assert _ids(ActionSummaryBuilder().build(checks)) == ["fail_high"]


def test_action_summary_excludes_low_severity_when_severity_filter_exists():
    checks = [
        _check("fail_low", "FAIL", "LOW"),
        _check("warning_low", "WARNING", "LOW"),
        _check("warning_medium", "WARNING", "MEDIUM"),
    ]

    assert _ids(ActionSummaryBuilder().build(checks)) == ["warning_medium"]


def test_action_summary_rows_without_severity_remain_backward_compatible():
    checks = [
        _check("fail_without_severity", "FAIL"),
        _check("warning_without_severity", "WARNING"),
        _check("error_without_severity", "ERROR"),
    ]

    items = ActionSummaryBuilder().build(checks)

    assert _ids(items) == ["fail_without_severity", "warning_without_severity"]
    assert all(item["severity"] == "" for item in items)
