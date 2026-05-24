from __future__ import annotations

import pytest
from types import SimpleNamespace

from tbdy_engine.reports.facade import ReportingFacade, ReportingResult
from tbdy_engine.reports.report_plan import ReportPlan


def _runtime_catalog(reports=None):
    return SimpleNamespace(
        reports=reports
        if reports is not None
        else {
            "full_engine_report": SimpleNamespace(
                formats=["json", "excel"],
                include=[],
                sections=[],
                filters={},
                include_fields=[],
                metrics=[],
            ),
            "action_summary": SimpleNamespace(
                formats=["json", "excel"],
                include=[],
                sections=[],
                filters={"status": ["FAIL", "WARNING"], "severity": ["HIGH", "MEDIUM"]},
                include_fields=[],
                metrics=[],
            ),
        }
    )


def test_reporting_facade_returns_report_paths_and_action_summary(tmp_path, monkeypatch):
    calls = []

    class DummyJSONReporter:
        def __init__(self, write_history):
            self.last_snapshot_path = "json-snapshot"
            calls.append(("json_init", write_history))

        def generate(self, checks, eval_results, *, runtime_catalog, output_path):
            calls.append(("json_generate", output_path, runtime_catalog))
            return output_path

    class DummyExcelReporter:
        def __init__(self, write_history):
            self.last_snapshot_path = "excel-snapshot"
            calls.append(("excel_init", write_history))

        def generate(self, checks, eval_results, output_path):
            calls.append(("excel_generate", output_path))
            return output_path

    class DummyActionSummaryBuilder:
        def build(self, checks):
            calls.append(("action_summary", len(checks)))
            return [{"check_id": "c1"}]

    monkeypatch.setattr("tbdy_engine.reports.facade.JSONReporter", DummyJSONReporter)
    monkeypatch.setattr("tbdy_engine.reports.facade.ExcelReporter", DummyExcelReporter)
    monkeypatch.setattr("tbdy_engine.reports.facade.ActionSummaryBuilder", DummyActionSummaryBuilder)

    runtime_catalog = _runtime_catalog()
    result = ReportingFacade(tmp_path).generate(
        [SimpleNamespace(check_id="c1")],
        {"errors": {}, "skipped": {}, "execution_order": [], "cache_stats": {}},
        runtime_catalog=runtime_catalog,
    )

    assert isinstance(result, ReportingResult)
    assert result.json_report == str(tmp_path / "engine_report.json")
    assert result.excel_report == str(tmp_path / "engine_report.xlsx")
    assert result.json_snapshot == "json-snapshot"
    assert result.excel_snapshot == "excel-snapshot"
    assert result.action_summary == [{"check_id": "c1"}]
    assert ("json_init", True) in calls
    assert ("excel_init", True) in calls
    assert ("json_generate", str(tmp_path / "engine_report.json"), runtime_catalog) in calls
    assert ("excel_generate", str(tmp_path / "engine_report.xlsx")) in calls
    assert ("action_summary", 1) in calls


def test_reporting_facade_uses_report_plan_from_runtime_catalog(tmp_path, monkeypatch):
    seen = []

    class DummyReportPlanner:
        def __init__(self, reports):
            seen.append(reports)

        def plan(self):
            return ReportPlan(reports=_runtime_catalog().reports)

    monkeypatch.setattr("tbdy_engine.reports.facade.ReportPlanner", DummyReportPlanner)
    monkeypatch.setattr("tbdy_engine.reports.facade.JSONReporter", _NoopJSONReporter)
    monkeypatch.setattr("tbdy_engine.reports.facade.ExcelReporter", _NoopExcelReporter)
    monkeypatch.setattr("tbdy_engine.reports.facade.ActionSummaryBuilder", _NoopActionSummaryBuilder)

    runtime_catalog = _runtime_catalog()
    ReportingFacade(tmp_path).generate([], {}, runtime_catalog=runtime_catalog)

    assert seen == [runtime_catalog.reports]


def test_reporting_facade_missing_full_engine_report_raises_value_error(tmp_path):
    with pytest.raises(ValueError, match="full_engine_report"):
        ReportingFacade(tmp_path).generate([], {}, runtime_catalog=_runtime_catalog({"action_summary": _runtime_catalog().reports["action_summary"]}))


def test_reporting_facade_missing_json_format_raises_value_error(tmp_path):
    reports = _runtime_catalog().reports
    reports = dict(reports)
    reports["full_engine_report"] = SimpleNamespace(
        formats=["excel"], include=[], sections=[], filters={}, include_fields=[], metrics=[]
    )

    with pytest.raises(ValueError, match="json format"):
        ReportingFacade(tmp_path).generate([], {}, runtime_catalog=_runtime_catalog(reports))


def test_reporting_facade_missing_excel_format_raises_value_error(tmp_path):
    reports = _runtime_catalog().reports
    reports = dict(reports)
    reports["full_engine_report"] = SimpleNamespace(
        formats=["json"], include=[], sections=[], filters={}, include_fields=[], metrics=[]
    )

    with pytest.raises(ValueError, match="excel format"):
        ReportingFacade(tmp_path).generate([], {}, runtime_catalog=_runtime_catalog(reports))


def test_reporting_facade_missing_action_summary_raises_value_error(tmp_path):
    reports = dict(_runtime_catalog().reports)
    reports.pop("action_summary")

    with pytest.raises(ValueError, match="action_summary"):
        ReportingFacade(tmp_path).generate([], {}, runtime_catalog=_runtime_catalog(reports))


def test_reporting_facade_does_not_call_diagnostic_tools():
    import tbdy_engine.reports.facade as facade_module

    module_names = set(facade_module.__dict__)

    assert "run_final_engine_report_v1" not in module_names
    assert "run_genesis_final_v1" not in module_names
    assert "enrich_engine_report_v1_2" not in module_names


class _NoopJSONReporter:
    def __init__(self, write_history):
        self.last_snapshot_path = None

    def generate(self, checks, eval_results, *, runtime_catalog, output_path):
        return output_path


class _NoopExcelReporter:
    def __init__(self, write_history):
        self.last_snapshot_path = None

    def generate(self, checks, eval_results, output_path):
        return output_path


class _NoopActionSummaryBuilder:
    def build(self, checks):
        return []
