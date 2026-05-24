from __future__ import annotations

from pathlib import Path

from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.contracts.models import model_to_dict
from tbdy_engine.reports.report_plan import ReportPlanner


ROOT = Path(__file__).resolve().parents[1]


def _plan():
    catalog = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()
    return catalog, ReportPlanner(catalog.reports).plan()


def test_report_planner_sees_full_engine_report():
    _, plan = _plan()

    assert "full_engine_report" in plan.report_ids()


def test_full_engine_report_declares_json_and_excel_formats():
    _, plan = _plan()

    assert plan.get("full_engine_report").formats == ("json", "excel")


def test_action_summary_exposes_status_and_severity_filters():
    _, plan = _plan()
    action_summary = plan.get("action_summary")

    assert action_summary.filters["status"] == ["FAIL", "WARNING"]
    assert action_summary.filters["severity"] == ["HIGH", "MEDIUM"]


def test_coverage_report_exposes_metrics():
    _, plan = _plan()

    assert plan.get("coverage_report").metrics == (
        "total_checks_possible",
        "checks_executed",
        "checks_no_data",
        "checks_not_evaluated",
        "coverage_pct",
    )


def test_report_planner_does_not_mutate_runtime_catalog():
    catalog = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()
    before = model_to_dict(catalog)

    ReportPlanner(catalog.reports).plan()

    assert model_to_dict(catalog) == before


def test_report_planner_works_from_contract_first_loader_default():
    catalog = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()
    plan = ReportPlanner(catalog.reports).plan()

    assert set(plan.report_ids()) == {"full_engine_report", "action_summary", "coverage_report"}
    assert catalog.warnings == []
