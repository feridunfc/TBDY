from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from openpyxl import load_workbook

from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.design.beams.beam_module import BeamDesignModule
from tbdy_engine.etabs.normalizers.beam_design import build_beam_context_from_tables, to_context_namespace
from tbdy_engine.etabs.table_access import EtabsTableAccessStatus, read_etabs_table_on_demand
from tbdy_engine.reports.facade import ReportingFacade


ROOT = Path(__file__).resolve().parents[1]
INCLUDED_BEAM_CHECKS = {"beam_geometry", "beam_flexure", "beam_shear", "beam_ductility"}
EXCLUDED_BEAM_CHECKS = {"beam_capacity_hierarchy", "beam_design_full"}
BEAM_TABLE_CANDIDATES = {
    "story_definitions": ["Story Definitions"],
    "beam_design_summary": [
        "Concrete Beam Design Summary - TS 500-2000(R2018)",
        "Concrete Beam Design Summary",
    ],
    "beam_flexure_envelope": [
        "Concrete Beam Flexure Envelope - TS 500-2000(R2018)",
        "Concrete Beam Flexure Envelope -  TS 500-2000(R2018)",
    ],
    "beam_shear_envelope": [
        "Concrete Beam Shear Envelope - TS 500-2000(R2018)",
        "Concrete Beam Shear Envelope -  TS 500-2000(R2018)",
    ],
}


def _skip_unless_live_enabled() -> None:
    if os.environ.get("TBDY_RUN_ETABS_LIVE_SMOKE") != "1":
        pytest.skip("Live ETABS beam vertical slice disabled; set TBDY_RUN_ETABS_LIVE_SMOKE=1")


def _read_first_ok(logical_name: str):
    diagnostics = []
    for table_name in BEAM_TABLE_CANDIDATES[logical_name]:
        result = read_etabs_table_on_demand(table_name)
        diagnostics.append(result.to_dict())
        if result.status is EtabsTableAccessStatus.OK and result.df is not None:
            return result, diagnostics
    return None, diagnostics


def _live_tables_or_skip() -> tuple[dict[str, object], dict[str, list[dict[str, object]]]]:
    tables: dict[str, object] = {}
    diagnostics: dict[str, list[dict[str, object]]] = {}

    for logical_name in ("story_definitions", "beam_design_summary", "beam_flexure_envelope", "beam_shear_envelope"):
        result, attempts = _read_first_ok(logical_name)
        diagnostics[logical_name] = attempts
        if result is None:
            pytest.skip(f"Required live ETABS beam table unavailable: {logical_name}; attempts={attempts}")
        tables[logical_name] = result.df
        tables[f"{logical_name}_source_table"] = result.table_name

    return tables, diagnostics


def _catalog():
    return EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()


def _evidence_by_label(context: dict[str, object]) -> dict[str, dict[str, object]]:
    evidence: dict[str, dict[str, object]] = {}
    for row in context["design_metadata"].get("beam_design_summary_rows", []):
        label = str(row.get("label") or "")
        if label:
            evidence.setdefault(label, {})["design_summary"] = _source_evidence(row)
    for label, force in context["envelopes"].get("beam_forces_map", {}).items():
        if isinstance(force, dict) and isinstance(force.get("evidence"), dict):
            evidence.setdefault(str(label), {}).update(force["evidence"])
    return evidence


def _source_evidence(row: dict[str, object]) -> dict[str, object]:
    return {
        "source_table": row.get("source_table"),
        "source_row": row.get("source_row"),
        "source_columns": row.get("source_columns"),
        "evidence_type": "live_etabs_table",
        "unit_conversion_status": "not_normalized",
        "combo_family_status": "not_inferred",
    }


def _attach_beam_provenance(evaluation_result: dict[str, Any], context: dict[str, object]) -> dict[str, Any]:
    evidence_map = _evidence_by_label(context)
    for output in evaluation_result.get("outputs", []) or []:
        label = str(output.get("label") or "")
        per_label = evidence_map.get(label, {})
        checks = output.get("checks", {}) or {}
        for check_name, check in checks.items():
            if not isinstance(check, dict):
                continue
            if check_name == "geometry":
                evidence = per_label.get("design_summary")
            elif check_name == "ductility":
                evidence = per_label.get("design_summary")
            elif check_name == "flexure":
                evidence = per_label.get("flexure") or per_label.get("design_summary")
            elif check_name == "shear":
                evidence = per_label.get("shear") or per_label.get("design_summary")
            else:
                evidence = None
            if evidence:
                check["source"] = "live_etabs_table"
                check["evidence"] = evidence
    return evaluation_result


def _run_live_beam_slice(tmp_path: Path):
    tables, diagnostics = _live_tables_or_skip()
    context = build_beam_context_from_tables(tables)
    ctx = to_context_namespace(context)
    raw_result = BeamDesignModule(ctx).run()
    evaluation_result = _attach_beam_provenance(raw_result, context)
    eval_results = {
        "results": {"BEAM_DESIGN": evaluation_result},
        "errors": {},
        "skipped": {},
        "execution_order": ["BEAM_DESIGN"],
        "cache_stats": {},
    }
    catalog = _catalog()
    checks = CheckAdapter(catalog).adapt_all(eval_results)
    ReportingFacade(tmp_path).generate(checks, eval_results, runtime_catalog=catalog)
    return {
        "tables": tables,
        "diagnostics": diagnostics,
        "context": context,
        "evaluation_result": evaluation_result,
        "eval_results": eval_results,
        "checks": checks,
        "report_dir": tmp_path,
    }


def _json_report(report_dir: Path) -> dict[str, object]:
    return json.loads((report_dir / "engine_report.json").read_text(encoding="utf-8"))


def _excel_details_rows(report_dir: Path) -> tuple[list[str], list[list[object]]]:
    workbook = load_workbook(report_dir / "engine_report.xlsx")
    rows = list(workbook["Details"].iter_rows(values_only=True))
    return list(rows[0]), [list(row) for row in rows[1:]]


@pytest.mark.etabs_smoke
def test_live_etabs_beam_vertical_slice_reports_json_and_excel(tmp_path):
    _skip_unless_live_enabled()

    run = _run_live_beam_slice(tmp_path)
    json_payload = _json_report(tmp_path)
    header, excel_rows = _excel_details_rows(tmp_path)
    json_check_ids = {row["check_id"] for row in json_payload["checks"]}
    excel_check_id_index = header.index("check_id")
    excel_check_ids = {row[excel_check_id_index] for row in excel_rows}

    assert INCLUDED_BEAM_CHECKS.issubset(json_check_ids)
    assert INCLUDED_BEAM_CHECKS.issubset(excel_check_ids)
    assert not (EXCLUDED_BEAM_CHECKS & json_check_ids)
    assert not (EXCLUDED_BEAM_CHECKS & excel_check_ids)
    assert run["context"]["diagnostics"]["beam_design_summary_row_count"] > 0
    assert run["context"]["diagnostics"]["beam_flexure_row_count"] > 0
    assert run["context"]["diagnostics"]["beam_shear_row_count"] > 0


@pytest.mark.etabs_smoke
def test_live_etabs_beam_report_evidence_contains_source_provenance(tmp_path):
    _skip_unless_live_enabled()

    _run_live_beam_slice(tmp_path)
    json_payload = _json_report(tmp_path)
    beam_rows = [row for row in json_payload["checks"] if row["check_id"] in INCLUDED_BEAM_CHECKS]

    assert beam_rows
    for row in beam_rows:
        evidence = row.get("evidence")
        assert isinstance(evidence, dict), row["check_id"]
        assert evidence.get("source_table"), row["check_id"]
        assert isinstance(evidence.get("source_columns"), list), row["check_id"]
        assert evidence.get("evidence_type") == "live_etabs_table"
        assert evidence.get("unit_conversion_status") == "not_normalized"
        assert evidence.get("combo_family_status") == "not_inferred"

    header, excel_rows = _excel_details_rows(tmp_path)
    check_id_index = header.index("check_id")
    evidence_index = header.index("evidence")
    for row in excel_rows:
        if row[check_id_index] not in INCLUDED_BEAM_CHECKS:
            continue
        evidence = json.loads(row[evidence_index])
        assert evidence["source_table"]
        assert evidence["source_columns"]
        assert evidence["evidence_type"] == "live_etabs_table"


@pytest.mark.etabs_smoke
def test_live_etabs_beam_table_attempts_are_narrow_and_structured(tmp_path):
    _skip_unless_live_enabled()

    run = _run_live_beam_slice(tmp_path)
    diagnostics = run["diagnostics"]

    assert set(diagnostics) == {"story_definitions", "beam_design_summary", "beam_flexure_envelope", "beam_shear_envelope"}
    for logical_name, attempts in diagnostics.items():
        attempted_names = [attempt["table_name"] for attempt in attempts]
        assert attempted_names
        assert attempted_names == BEAM_TABLE_CANDIDATES[logical_name][: len(attempted_names)]
        for attempt in attempts:
            assert attempt["status"] in {
                "OK",
                "ETABS_UNAVAILABLE",
                "NO_OPEN_MODEL",
                "TABLE_UNAVAILABLE",
                "TABLE_EMPTY",
                "READ_ERROR",
            }


def test_live_beam_smoke_source_is_opt_in_and_has_no_fake_evaluator():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden_raw_com_import = "win32com" + "." + "client"
    forbidden_raw_com_call = "Get" + "Active" + "Object"

    assert "TBDY_RUN_ETABS_LIVE_SMOKE" in source
    assert "read_etabs_table_on_demand" in source
    assert "BeamDesignModule" in source
    assert "CheckAdapter" in source
    assert "ReportingFacade" in source
    assert "fake_evaluator" not in source
    assert forbidden_raw_com_import not in source
    assert forbidden_raw_com_call not in source
    assert "WALL" not in source
    assert "COLUMN" not in source
    assert "Concrete Joint" not in source
