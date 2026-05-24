from __future__ import annotations

from types import SimpleNamespace

from tbdy_engine.reports.facade import ReportingFacade, ReportingResult


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

    result = ReportingFacade(tmp_path).generate(
        [SimpleNamespace(check_id="c1")],
        {"errors": {}, "skipped": {}, "execution_order": [], "cache_stats": {}},
        runtime_catalog="catalog",
    )

    assert isinstance(result, ReportingResult)
    assert result.json_report == str(tmp_path / "engine_report.json")
    assert result.excel_report == str(tmp_path / "engine_report.xlsx")
    assert result.json_snapshot == "json-snapshot"
    assert result.excel_snapshot == "excel-snapshot"
    assert result.action_summary == [{"check_id": "c1"}]
    assert ("json_init", True) in calls
    assert ("excel_init", True) in calls
    assert ("json_generate", str(tmp_path / "engine_report.json"), "catalog") in calls
    assert ("excel_generate", str(tmp_path / "engine_report.xlsx")) in calls
    assert ("action_summary", 1) in calls


def test_reporting_facade_does_not_call_diagnostic_tools():
    import tbdy_engine.reports.facade as facade_module

    module_names = set(facade_module.__dict__)

    assert "run_final_engine_report_v1" not in module_names
    assert "run_genesis_final_v1" not in module_names
    assert "enrich_engine_report_v1_2" not in module_names
