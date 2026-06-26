from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import tbdy_engine.features.live_etabs_geometry_probe as live_probe_module
from tbdy_engine.features.live_etabs_geometry_probe import (
    AcceptedMappingGeometryRowProvider,
    calculate_live_probe_status,
    probe_geometry_feature_snapshots,
)
from tbdy_engine.product.live_geometry_product import run_live_geometry_product


REQUIRED_PRODUCT_FILES = (
    "artifacts/coverage_rows.json",
    "artifacts/check_results.json",
    "artifacts/adapter_diagnostics.json",
    "artifacts/run_summary.json",
    "artifacts/run_manifest.json",
    "reports/geometry_report.md",
    "product_smoke_summary.json",
    "product_smoke_manifest.json",
)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _source(
    component_id: str,
    component_type: str,
    section: str | None = None,
    *,
    include_identity: bool = True,
):
    row: dict[str, object] = {
        "UniqueName": component_id,
        "Type": component_type,
        "AnalysisSect": section,
        "DesignSect": section,
    }
    if include_identity:
        row.update({"Label": component_id, "Story": "+14.5"})
    return row


def _assignment(component_id: str, section: str, shape: str, *, label: str | None = None):
    return {
        "UniqueName": component_id,
        "Label": label or component_id,
        "Story": "+14.5",
        "SectProp": section,
        "Shape": shape,
    }


def _property(section: str, width: float = 400.0, depth: float = 700.0):
    return {"Name": section, "t2": width, "t3": depth, "unit": "mm"}


def _provider(*, source_rows, assignment_rows, property_rows):
    return AcceptedMappingGeometryRowProvider(
        assignment_rows=assignment_rows,
        property_rows=property_rows,
        component_type_rows=source_rows,
        component_type_source_table="Frame Assignments - Summary",
        component_type_source_column="Type",
        component_type_join_key_column="UniqueName",
    )


def _successful_product_runner(*, feature_snapshot_path: Path, output_dir: Path):
    root = Path(output_dir)
    for relative in REQUIRED_PRODUCT_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == "product_smoke_summary.json":
            path.write_text(
                '{"p4":{"adapter_diagnostic_count":0,"check_result_count":1,"coverage_row_count":1,"coverage_status_counts":{"RUNNABLE":1}},"status":"OK"}\n',
                encoding="utf-8",
            )
        else:
            path.write_text("{}\n" if path.suffix == ".json" else "# report\n", encoding="utf-8")
    return SimpleNamespace(
        status="OK",
        product_smoke_summary_path=root / "product_smoke_summary.json",
        p4_check_result_count=1,
        p4_adapter_diagnostic_count=0,
    )


def test_status_helper_contract():
    assert calculate_live_probe_status(
        snapshot_count=1,
        population_blocked_row_count=0,
        blocking_diagnostic_count=0,
    ) == "OK"
    assert calculate_live_probe_status(
        snapshot_count=1,
        population_blocked_row_count=1,
        blocking_diagnostic_count=0,
    ) == "PARTIAL"
    assert calculate_live_probe_status(
        snapshot_count=1,
        population_blocked_row_count=0,
        blocking_diagnostic_count=1,
    ) == "PARTIAL"
    assert calculate_live_probe_status(
        snapshot_count=0,
        population_blocked_row_count=0,
        blocking_diagnostic_count=0,
    ) == "FAIL"


def test_joined_assignment_shape_drives_concrete_steel_null_and_brace_scope(tmp_path: Path):
    source_rows = (
        _source("297", "Beam", "B40x70", include_identity=False),
        _source("301", "Column", "C50x60", include_identity=False),
        _source("NULL-1", "Null"),
        _source("BR-1", "Brace", "DN40"),
        _source("ST-1", "Beam", "HE160A"),
    )
    assert all("Shape" not in row for row in source_rows)
    provider = _provider(
        source_rows=source_rows,
        assignment_rows=(
            _assignment("297", "B40x70", "Rectangular", label="B1"),
            _assignment("301", "C50x60", "Concrete Rectangular", label="C1"),
            _assignment("ST-1", "HE160A", "Steel I/Wide Flange"),
        ),
        property_rows=(
            _property("B40x70"),
            _property("C50x60", 500.0, 600.0),
        ),
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    summary = _read_json(result.summary_path)
    diagnostics = _read_json(result.diagnostics_path)
    population = _read_json(result.population_audit_path)
    rows = {row["component_id"]: row for row in population["rows"]}

    assert result.status == "OK"
    assert result.snapshot_count == 2
    assert summary["population_source_row_count"] == 5
    assert summary["population_in_scope_row_count"] == 2
    assert summary["population_out_of_scope_row_count"] == 3
    assert summary["population_blocked_row_count"] == 0
    assert summary["blocking_diagnostic_count"] == 0
    assert rows["297"]["section_shape"] == "Rectangular"
    assert rows["297"]["label"] == "B1"
    assert rows["301"]["reason_code"] == "IN_SCOPE_CONCRETE_RECTANGULAR_COLUMN"
    assert rows["ST-1"]["reason_code"] == "OUT_OF_SCOPE_STEEL_SECTION"
    assert rows["ST-1"]["assigned_section"] == "HE160A"
    assert rows["NULL-1"]["reason_code"] == "OUT_OF_SCOPE_NULL_FRAME"
    assert rows["BR-1"]["reason_code"] == "OUT_OF_SCOPE_BRACE"
    codes = {item["code"] for item in diagnostics}
    assert "SECTION_PROPERTY_NOT_FOUND" not in codes
    assert "COMPONENT_TYPE_VALUE_UNSUPPORTED" not in codes


def test_blocked_concrete_population_row_plus_valid_snapshot_is_partial(tmp_path: Path):
    provider = _provider(
        source_rows=(
            _source("297", "Beam", "B40x70"),
            _source("BAD", "Beam", "MISSING"),
        ),
        assignment_rows=(
            _assignment("297", "B40x70", "Rectangular"),
            _assignment("BAD", "MISSING", "Concrete Rectangular"),
        ),
        property_rows=(_property("B40x70"),),
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    summary = _read_json(result.summary_path)

    assert result.status == "PARTIAL"
    assert result.snapshot_count == 1
    assert summary["population_blocked_row_count"] == 1
    assert summary["blocking_diagnostic_count"] == 0


def test_authoritative_998_row_population_is_complete_and_untruncated(tmp_path: Path):
    source_rows: list[dict[str, object]] = []
    assignment_rows: list[dict[str, object]] = []

    for index in range(918):
        component_id = f"RC-{index:04d}"
        component_type = "Beam" if index % 2 == 0 else "Column"
        source_rows.append(_source(component_id, component_type, "B40x70"))
        assignment_rows.append(_assignment(component_id, "B40x70", "Rectangular"))
    source_rows.extend(_source(f"NULL-{index:02d}", "Null") for index in range(68))
    source_rows.extend(_source(f"BR-{index:02d}", "Brace") for index in range(4))
    for index in range(8):
        component_id = f"ST-{index:02d}"
        source_rows.append(_source(component_id, "Beam", "HE160A"))
        assignment_rows.append(_assignment(component_id, "HE160A", "Steel I/Wide Flange"))

    assert len(source_rows) == 998
    assert all("Shape" not in row for row in source_rows)
    provider = _provider(
        source_rows=source_rows,
        assignment_rows=assignment_rows,
        property_rows=(_property("B40x70"),),
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path, max_rows=1)
    summary = _read_json(result.summary_path)
    diagnostics = _read_json(result.diagnostics_path)
    population = _read_json(result.population_audit_path)
    population_ids = [row["component_id"] for row in population["rows"]]

    assert result.status == "OK"
    assert result.snapshot_count == 1
    assert summary["population_source_row_count"] == 998
    assert summary["population_in_scope_row_count"] == 918
    assert summary["population_out_of_scope_row_count"] == 80
    assert summary["population_blocked_row_count"] == 0
    assert summary["warning_diagnostic_count"] == 1
    assert summary["blocking_diagnostic_count"] == 0
    assert population["source_row_count"] == 998
    assert population["in_scope_row_count"] == 918
    assert population["out_of_scope_row_count"] == 80
    assert population["blocked_row_count"] == 0
    assert len(population_ids) == 998
    assert len(set(population_ids)) == 998
    assert set(population_ids) == {row["UniqueName"] for row in source_rows}
    assert sum(
        row["reason_code"] == "OUT_OF_SCOPE_STEEL_SECTION"
        for row in population["rows"]
    ) == 8
    codes = {item["code"] for item in diagnostics}
    assert codes == {"ROW_LIMIT_TRUNCATED"}


def test_authoritative_accepted_mapping_path_never_uses_resolved_row_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def _forbidden_fallback(_rows):
        raise AssertionError("resolved-row population fallback must not be used")

    monkeypatch.setattr(
        live_probe_module,
        "_population_audit_from_resolved_rows",
        _forbidden_fallback,
    )
    provider = _provider(
        source_rows=(_source("297", "Beam", "B40x70"),),
        assignment_rows=(_assignment("297", "B40x70", "Rectangular"),),
        property_rows=(_property("B40x70"),),
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)

    assert result.status == "OK"
    assert _read_json(result.population_audit_path)["source_row_count"] == 1


def test_probe_and_live_product_manifests_include_population_audit(tmp_path: Path):
    provider = _provider(
        source_rows=(_source("297", "Beam", "B40x70"),),
        assignment_rows=(_assignment("297", "B40x70", "Rectangular"),),
        property_rows=(_property("B40x70"),),
    )

    result = run_live_geometry_product(
        output_dir=tmp_path,
        provider_factory=lambda: provider,
        product_runner=_successful_product_runner,
    )
    probe_manifest = _read_json(tmp_path / "live_probe" / "live_geometry_probe_manifest.json")
    product_manifest = _read_json(result.manifest_path)

    assert result.status == "OK"
    assert "probe_population_audit.json" in probe_manifest["output_files"]
    assert product_manifest["source_population_audit"] == "live_probe/probe_population_audit.json"
    assert "live_probe/probe_population_audit.json" in product_manifest["output_files"]
    assert not (tmp_path / "product" / "probe_population_audit.json").exists()
