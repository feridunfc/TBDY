from __future__ import annotations
import csv
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
from tbdy_engine.features.live_etabs_geometry_probe import LiveEtabsLengthUnitEvidence
from tbdy_engine.product.live_beam_column_minimum_compliance import (
    _evaluate_absolute_beam_depth,
    _evaluate_depth_vs_slab,
    _evaluate_web_detailing_trigger,
    _summary,
    run_live_beam_column_minimum_compliance,
)
from tbdy_engine.reports.minimum_compliance_tabular_report import table_columns
ROOT = Path(__file__).resolve().parents[2]
def _evidence(value: float, unit: str, table: str, column: str) -> dict[str, object]:
    return {
        "evidence_status": "FULL", "source_table": table, "actual_table_name": table,
        "source_column": column, "source_row": {column: value}, "raw_value": value,
        "normalized_value": value, "unit": unit, "resolver": "fixture",
    }
def _snapshot(
    component_type: str, component_id: str, section: str, *,
    width: float = 400.0, depth: float = 600.0, fck: float = 35.0,
    story: str = "+1.00", material: str = "C35",
) -> dict[str, object]:
    prefix = "beam" if component_type == "beam" else "column"
    features = {
        f"{prefix}_width_mm": {
            "feature_name": f"{prefix}_width_mm", "value": width, "unit": "mm",
            "semantic_role": "GEOMETRY", "status": "RESOLVED",
            "evidence": [_evidence(width, "mm", "Concrete Rectangular", "t2")],
        },
        f"{prefix}_depth_mm": {
            "feature_name": f"{prefix}_depth_mm", "value": depth, "unit": "mm",
            "semantic_role": "GEOMETRY", "status": "RESOLVED",
            "evidence": [_evidence(depth, "mm", "Concrete Rectangular", "t3")],
        },
        "concrete_fck_mpa": {
            "feature_name": "concrete_fck_mpa", "value": fck, "unit": "MPa",
            "semantic_role": "DESIGN_BASIS", "status": "RESOLVED",
            "evidence": [_evidence(fck, "MPa", "Concrete Data", "Fc")],
        },
    }
    return {
        "component_type": component_type, "component_id": component_id,
        "identity": {"story": story, "section": section, "section_name": section, "assigned_material_name": material},
        "features": features, "evidence_by_feature": {}, "diagnostics": [],
    }
def _units(unit: str = "m") -> LiveEtabsLengthUnitEvidence:
    return LiveEtabsLengthUnitEvidence(
        present_force_unit="kN", present_length_unit=unit, present_temperature_unit="C",
        database_force_unit="kN", database_length_unit=unit, database_temperature_unit="C",
        present_units_raw=(4, 6, 2, 0), database_units_raw=(4, 6, 2, 0),
    )
def _source(
    snapshots: list[dict[str, object]] | None = None, *,
    extra_components: list[dict[str, object]] | None = None,
    assignment_overrides: list[dict[str, object]] | None = None,
    section_rows: list[dict[str, object]] | None = None,
    material_rows: list[dict[str, object]] | None = None,
    connectivity: list[dict[str, object]] | None = None,
    offsets: list[dict[str, object]] | None = None,
    diagnostics: list[dict[str, object]] | None = None,
    unit: str = "m",
) -> dict[str, object]:
    if snapshots is None:
        snapshots = [_snapshot("beam", "B1", "BSEC"), _snapshot("column", "C1", "CSEC")]
    components = [
        {"UniqueName": row["component_id"], "Type": "Beam" if row["component_type"] == "beam" else "Column"}
        for row in snapshots
    ] + list(extra_components or [])
    assignments = [
        {
            "UniqueName": row["component_id"], "Story": row["identity"]["story"],
            "Label": row["component_id"], "SectProp": row["identity"]["section"],
            "Shape": "Concrete Rectangular",
        }
        for row in snapshots
    ]
    if assignment_overrides is not None:
        assignments = assignment_overrides
    if section_rows is None:
        unique_sections = {(row["identity"]["section"], row["identity"]["assigned_material_name"]) for row in snapshots}
        section_rows = [{"Name": sec, "Material": mat, "t2": "0.4", "t3": "0.6"} for sec, mat in sorted(unique_sections)]
    if material_rows is None:
        materials = {row["identity"]["assigned_material_name"] for row in snapshots}
        material_rows = [{"Material": value, "Fc": "35000"} for value in sorted(materials)]
    return {
        "component_rows": components, "assignment_rows": assignments,
        "section_rows": section_rows, "material_rows": material_rows,
        "connectivity_rows": list(connectivity or []), "offset_rows": list(offsets or []),
        "snapshots": snapshots, "source_diagnostics": list(diagnostics or []),
        "unit_evidence": _units(unit),
    }
def _run(tmp_path: Path, source: dict[str, object], **selectors):
    return run_live_beam_column_minimum_compliance(
        output_dir=tmp_path,
        attach_runner=lambda: SimpleNamespace(status="ATTACHED", sap_model=object()),
        source_loader=lambda _attach, _work: source,
        **selectors,
    )
def _results(tmp_path: Path) -> list[dict[str, object]]:
    return json.loads((tmp_path / "artifacts/check_results.json").read_text(encoding="utf-8"))
def _result(tmp_path: Path, check_id: str, component: str = "B1") -> dict[str, object]:
    return next(row for row in _results(tmp_path) if row["check_id"] == check_id and row["component"] == component)
# Negative contracts first.
def test_cli_refuses_without_live_etabs_and_creates_no_output(tmp_path: Path):
    out = tmp_path / "refused"
    completed = subprocess.run(
        [sys.executable, "tools/run_live_beam_column_minimum_compliance.py", "--out", str(out)],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    assert completed.returncode != 0
    assert "--live-etabs" in completed.stderr
    assert not out.exists()
def test_attach_failure_writes_structured_failure(tmp_path: Path):
    result = run_live_beam_column_minimum_compliance(
        output_dir=tmp_path, attach_runner=lambda: (_ for _ in ()).throw(RuntimeError("attach failed"))
    )
    assert result["product_status"] == "FAIL"
    assert result["engineering_fail"] is False
    assert json.loads((tmp_path / "artifacts/product_summary.json").read_text())["failure_stage"] == "COM_ATTACH_OR_SOURCE"
def test_full_model_has_no_default_truncation(tmp_path: Path):
    snapshots = [_snapshot("beam", f"B{index}", "BSEC") for index in range(25)]
    result = _run(tmp_path, _source(snapshots))
    assert result["beam_assignment_count"] == 25
    assert result["supported_concrete_beam_count"] == 25
    assert len(json.loads((tmp_path / "artifacts/enriched_feature_snapshots.json").read_text())["snapshots"]) == 25
def test_brace_and_null_are_out_of_scope_not_engineering_fail(tmp_path: Path):
    source = _source(
        [_snapshot("beam", "B1", "BSEC")],
        extra_components=[{"UniqueName": "D1", "Type": "Brace"}, {"UniqueName": "L1", "Type": "Null"}],
    )
    result = _run(tmp_path, source)
    assert result["out_of_scope_object_count"] == 2
    assert result["engineering_fail"] is False
    assert result["coverage_status"] == "PARTIAL"
    statuses = {(row["component"], row["status"]) for row in _results(tmp_path)}
    assert ("D1", "OUT_OF_SCOPE") in statuses
    assert ("L1", "OUT_OF_SCOPE") in statuses
def test_steel_section_is_reported_out_of_scope_and_not_geometry_fail(tmp_path: Path):
    beam = _snapshot("beam", "B1", "BSEC")
    source = _source(
        [beam], extra_components=[{"UniqueName": "S1", "Type": "Beam"}],
        assignment_overrides=[
            {"UniqueName": "B1", "Story": "+1.00", "Label": "B1", "SectProp": "BSEC", "Shape": "Concrete Rectangular"},
            {"UniqueName": "S1", "Story": "+4.50", "Label": "B9", "SectProp": "HE160A", "Shape": "Steel I/Wide Flange"},
        ],
    )
    result = _run(tmp_path, source)
    rows = list(csv.DictReader((tmp_path / "report/unsupported_beam_sections.csv").open(encoding="utf-8")))
    assert any(row["section"] == "HE160A" and "Steel I/Wide Flange" in row["section_family"] for row in rows)
    assert result["geometry_fail_count"] == 0
    assert result["coverage_status"] == "PARTIAL"
def test_exact_unique_name_join_does_not_fall_back_to_label(tmp_path: Path):
    source = _source(
        [], extra_components=[{"UniqueName": "100", "Type": "Beam"}],
        assignment_overrides=[{"UniqueName": "999", "Story": "+1", "Label": "100", "SectProp": "BSEC", "Shape": "Concrete Rectangular"}],
        section_rows=[{"Name": "BSEC", "Material": "C35"}], material_rows=[{"Material": "C35", "Fc": "35000"}],
    )
    result = _run(tmp_path, source)
    assert result["supported_concrete_beam_count"] == 0
    assert result["engineering_fail"] is False
    assert _result(tmp_path, "minimum_compliance_scope", "100")["status"] == "NO_DATA"
def test_section_name_is_not_parsed_for_geometry(tmp_path: Path):
    source = _source(
        [], extra_components=[{"UniqueName": "1", "Type": "Beam"}],
        assignment_overrides=[{"UniqueName": "1", "Story": "+1", "Label": "B1", "SectProp": "B40x70", "Shape": "Concrete Rectangular"}],
        section_rows=[], material_rows=[],
    )
    result = _run(tmp_path, source)
    assert result["supported_concrete_beam_count"] == 0
    assert result["engineering_fail"] is False
def test_material_name_is_not_parsed_for_strength(tmp_path: Path):
    beam = _snapshot("beam", "B1", "BSEC", material="C35/45")
    source = _source([beam], material_rows=[])
    source["snapshots"] = []
    result = _run(tmp_path, source)
    assert result["supported_concrete_beam_count"] == 0
    assert result["engineering_fail"] is False
def test_missing_duplicate_and_unsupported_sources_have_honest_coverage(tmp_path: Path):
    base_component = [{"UniqueName": "B1", "Type": "Beam"}]
    missing_assignment = _source([], extra_components=base_component, assignment_overrides=[], section_rows=[], material_rows=[])
    assert _run(tmp_path / "missing_assignment", missing_assignment)["coverage_status"] == "PARTIAL"
    duplicate_assignment = _source([], extra_components=base_component, assignment_overrides=[
        {"UniqueName": "B1", "Story": "+1", "Label": "B1", "SectProp": "S", "Shape": "Concrete Rectangular"},
        {"UniqueName": "B1", "Story": "+1", "Label": "B1", "SectProp": "S", "Shape": "Concrete Rectangular"},
    ], section_rows=[{"Name": "S", "Material": "C"}], material_rows=[{"Material": "C", "Fc": "35000"}])
    _run(tmp_path / "duplicate_assignment", duplicate_assignment)
    assert _result(tmp_path / "duplicate_assignment", "minimum_compliance_scope")["status"] == "BLOCKED"
    duplicate_section = _source([], extra_components=base_component, assignment_overrides=[
        {"UniqueName": "B1", "Story": "+1", "Label": "B1", "SectProp": "S", "Shape": "Concrete Rectangular"}
    ], section_rows=[{"Name": "S", "Material": "C"}, {"Name": "S", "Material": "C"}], material_rows=[{"Material": "C", "Fc": "35000"}])
    _run(tmp_path / "duplicate_section", duplicate_section)
    assert _result(tmp_path / "duplicate_section", "minimum_compliance_scope")["status"] == "BLOCKED"
    duplicate_material = _source([], extra_components=base_component, assignment_overrides=[
        {"UniqueName": "B1", "Story": "+1", "Label": "B1", "SectProp": "S", "Shape": "Concrete Rectangular"}
    ], section_rows=[{"Name": "S", "Material": "C"}], material_rows=[{"Material": "C", "Fc": "35000"}, {"Material": "C", "Fc": "35000"}])
    _run(tmp_path / "duplicate_material", duplicate_material)
    assert _result(tmp_path / "duplicate_material", "minimum_compliance_scope")["status"] == "BLOCKED"
    missing_fc = _source([], extra_components=base_component, assignment_overrides=[
        {"UniqueName": "B1", "Story": "+1", "Label": "B1", "SectProp": "S", "Shape": "Concrete Rectangular"}
    ], section_rows=[{"Name": "S", "Material": "C"}], material_rows=[{"Material": "C", "Fc": None}])
    _run(tmp_path / "missing_fc", missing_fc)
    assert _result(tmp_path / "missing_fc", "minimum_compliance_scope")["status"] == "NO_DATA"
    unsupported_units = _source([], extra_components=base_component, assignment_overrides=[
        {"UniqueName": "B1", "Story": "+1", "Label": "B1", "SectProp": "S", "Shape": "Concrete Rectangular"}
    ], section_rows=[{"Name": "S", "Material": "C"}], material_rows=[{"Material": "C", "Fc": "35000"}], diagnostics=[
        {"status": "BLOCKED", "code": "MATERIAL_STRESS_UNIT_UNSUPPORTED", "component_id": "B1", "component_type": "beam", "message": "unsupported units"}
    ])
    _run(tmp_path / "unsupported_units", unsupported_units)
    assert _result(tmp_path / "unsupported_units", "minimum_compliance_scope")["status"] == "BLOCKED"
def test_absolute_depth_and_ratio_checks_pass_and_fail_independently(tmp_path: Path):
    passing = _source([_snapshot("beam", "B1", "S1", width=300, depth=600)])
    _run(tmp_path / "pass", passing)
    assert _result(tmp_path / "pass", "beam_geometry_min_depth_absolute")["status"] == "OK"
    assert _result(tmp_path / "pass", "beam_depth_width_ratio")["status"] == "OK"
    failing = _source([_snapshot("beam", "B1", "S1", width=200, depth=250)])
    _run(tmp_path / "fail", failing)
    assert _result(tmp_path / "fail", "beam_geometry_min_width")["status"] == "FAIL"
    assert _result(tmp_path / "fail", "beam_geometry_min_depth_absolute")["status"] == "FAIL"
    assert _run(tmp_path / "fail2", _source([_snapshot("beam", "B1", "S1", width=250, depth=1000)]))["engineering_fail"] is True
    assert _result(tmp_path / "fail2", "beam_depth_width_ratio")["status"] == "FAIL"
def test_depth_above_300_does_not_wait_for_slab_resolver(tmp_path: Path):
    result = _run(tmp_path, _source([_snapshot("beam", "B1", "S", depth=600)]))
    assert _result(tmp_path, "beam_geometry_min_depth_absolute")["status"] == "OK"
    slab = _result(tmp_path, "beam_geometry_depth_ge_three_times_slab_thickness")
    assert slab["status"] == "BLOCKED"
    assert result["engineering_fail"] is False
    assert result["coverage_status"] == "PARTIAL"
def test_depth_vs_slab_supported_association_missing_row_is_no_data():
    assert _evaluate_depth_vs_slab(600.0, None, relationship_supported=True) == "NO_DATA"
    assert _evaluate_depth_vs_slab(600.0, 180.0, relationship_supported=True) == "OK"
    assert _evaluate_depth_vs_slab(500.0, 180.0, relationship_supported=True) == "FAIL"
def test_absolute_depth_missing_and_invalid_semantics():
    assert _evaluate_absolute_beam_depth(None) == "NO_DATA"
    assert _evaluate_absolute_beam_depth("600", unit_supported=False) == "BLOCKED"
    assert _evaluate_absolute_beam_depth(299.0) == "FAIL"
    assert _evaluate_absolute_beam_depth(300.0) == "OK"
def test_clear_span_candidate_exists_but_trigger_is_blocked_not_no_data(tmp_path: Path):
    source = _source(
        [_snapshot("beam", "B1", "S")],
        connectivity=[{"UniqueName": "B1", "Length": "5.0"}],
        offsets=[{"UniqueName": "B1", "OffsetI": "0.2", "OffsetJ": "0.3"}],
    )
    result = _run(tmp_path, source)
    trigger = _result(tmp_path, "beam_web_reinforcement_detailing_trigger")
    assert trigger["result_status"] == "BLOCKED"
    assert trigger["candidate_clear_span"]["candidate_clear_span_mm"] == 4500.0
    assert result["no_data_check_count"] == 0
    assert any(row["code"] == "BEAM_CLEAR_SPAN_SEMANTICS_NOT_LOCKED" for row in json.loads((tmp_path / "artifacts/adapter_diagnostics.json").read_text()))
def test_genuinely_absent_clear_span_is_no_data(tmp_path: Path):
    _run(tmp_path, _source([_snapshot("beam", "B1", "S")]))
    trigger = _result(tmp_path, "beam_web_reinforcement_detailing_trigger")
    assert trigger["result_status"] == "NO_DATA"
    assert trigger["status"] == "NO_DATA"
def test_trigger_true_is_required_and_false_is_not_required():
    assert _evaluate_web_detailing_trigger(600.0, 2000.0, semantics_locked=True) == "REQUIRED"
    assert _evaluate_web_detailing_trigger(400.0, 2000.0, semantics_locked=True) == "NOT_REQUIRED"
    assert _evaluate_web_detailing_trigger(600.0, 2000.0, semantics_locked=False) == "BLOCKED"
def test_blocked_and_required_do_not_increase_engineering_fail_count():
    tables = {"executive_summary": []}
    records = [
        {"status": "BLOCKED", "result_status": "BLOCKED", "component_type": "beam", "check_id": "blocked"},
        {"status": "WARNING", "result_status": "REQUIRED", "component_type": "beam", "check_id": "trigger"},
    ]
    summary = _summary(tables, [], [], records)
    assert summary["engineering_fail"] is False
    assert summary["total_fail_count"] == 0
    assert summary["detailing_required_count"] == 1
    assert summary["coverage_status"] == "PARTIAL"
def test_column_dimension_area_and_aspect_pass_fail(tmp_path: Path):
    _run(tmp_path / "pass", _source([_snapshot("column", "C1", "C", width=400, depth=400)]))
    for check_id in ("column_geometry_min_dimension", "column_geometry_min_area", "column_geometry_aspect_ratio"):
        assert _result(tmp_path / "pass", check_id, "C1")["status"] == "OK"
    _run(tmp_path / "area_fail", _source([_snapshot("column", "C1", "C", width=200, depth=300)]))
    assert _result(tmp_path / "area_fail", "column_geometry_min_dimension", "C1")["status"] == "FAIL"
    assert _result(tmp_path / "area_fail", "column_geometry_min_area", "C1")["status"] == "FAIL"
    _run(tmp_path / "aspect_fail", _source([_snapshot("column", "C1", "C", width=300, depth=1000)]))
    assert _result(tmp_path / "aspect_fail", "column_geometry_aspect_ratio", "C1")["status"] == "FAIL"
def test_material_minimum_candidates_remain_blocked_without_clause(tmp_path: Path):
    result = _run(tmp_path, _source())
    assert _result(tmp_path, "beam_material_min_concrete_strength")["status"] == "BLOCKED"
    assert _result(tmp_path, "column_material_min_concrete_strength", "C1")["status"] == "BLOCKED"
    assert result["material_fail_count"] == 0
def test_section_aggregation_and_report_columns_are_deterministic(tmp_path: Path):
    snapshots = [
        _snapshot("beam", "B2", "S", story="+2.00"),
        _snapshot("beam", "B1", "S", story="+1.00"),
    ]
    _run(tmp_path, _source(snapshots))
    row = next(csv.DictReader((tmp_path / "report/beam_section_checks.csv").open(encoding="utf-8")))
    assert row["assigned_beam_count"] == "2"
    assert row["stories"] == "+1.00; +2.00"
    required_columns = {
        "absolute_depth_value_mm", "absolute_depth_limit_mm", "absolute_depth_status",
        "slab_thickness_mm", "three_times_slab_thickness_mm", "depth_vs_slab_status",
        "clear_span_mm", "web_detailing_trigger_status", "web_detailing_trigger_reason",
    }
    assert required_columns.issubset(set(table_columns()["beam_section_checks"]))
def test_output_is_deterministic_and_unrelated_root_file_is_preserved(tmp_path: Path):
    note = tmp_path / "user_note.txt"
    note.write_text("keep\n", encoding="utf-8")
    source = _source()
    first = _run(tmp_path, source)
    first_payloads = {path.relative_to(tmp_path).as_posix(): path.read_text(encoding="utf-8") for path in sorted((tmp_path / "artifacts").rglob("*")) if path.is_file()}
    second = _run(tmp_path, source)
    second_payloads = {path.relative_to(tmp_path).as_posix(): path.read_text(encoding="utf-8") for path in sorted((tmp_path / "artifacts").rglob("*")) if path.is_file()}
    assert first["product_status"] == second["product_status"]
    assert first_payloads == second_payloads
    assert note.read_text(encoding="utf-8") == "keep\n"
