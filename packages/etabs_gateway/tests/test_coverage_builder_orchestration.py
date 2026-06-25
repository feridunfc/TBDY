from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

from tbdy_engine.checks.geometry_coverage_orchestration import (
    assemble_geometry_check_inputs,
    load_geometry_contract_bundle,
)
from tbdy_engine.checks.geometry_vertical_slice import (
    run_geometry_vertical_slice_from_file,
)
from tbdy_engine.checks.input_adapter import (
    normalize_geometry_feature_snapshot_input,
)
from tbdy_engine.coverage.models import CoverageStatus

ROOT = Path(__file__).resolve().parents[3]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"
FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "c13_4_p4"
    / "geometry_feature_snapshots.json"
)


def _payloads():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return tuple(payload["snapshots"])


def test_geometry_bundle_includes_column_overlay_checks() -> None:
    checks = load_geometry_contract_bundle(
        CATALOG_DIR
    ).catalog("check_catalog.yaml")["checks"]

    assert "column_geometry_min_width" in checks
    assert "column_geometry_min_depth" in checks


def test_beam_assembly_preserves_three_coverage_rows() -> None:
    bundle = load_geometry_contract_bundle(CATALOG_DIR)
    snapshot = normalize_geometry_feature_snapshot_input(
        copy.deepcopy(_payloads()[0])
    )
    assembly = assemble_geometry_check_inputs(
        snapshot=snapshot,
        contract_bundle=bundle,
    )

    assert len(assembly.coverage_rows) == 3
    assert len(assembly.build_result.check_inputs) == 3
    assert assembly.build_result.diagnostics == ()
    for check_input, row in zip(
        assembly.build_result.check_inputs,
        assembly.coverage_rows,
        strict=True,
    ):
        assert check_input.coverage is row
        assert row.coverage_status is CoverageStatus.RUNNABLE


def test_column_assembly_uses_overlay_order() -> None:
    bundle = load_geometry_contract_bundle(CATALOG_DIR)
    snapshot = normalize_geometry_feature_snapshot_input(
        copy.deepcopy(_payloads()[1])
    )
    assembly = assemble_geometry_check_inputs(
        snapshot=snapshot,
        contract_bundle=bundle,
    )

    assert tuple(
        row.check_id for row in assembly.coverage_rows
    ) == (
        "column_geometry_min_dimension",
        "column_geometry_min_width",
        "column_geometry_min_depth",
    )
    assert len(assembly.build_result.check_inputs) == 3


def test_missing_feature_is_blocked_by_coverage() -> None:
    payload = copy.deepcopy(_payloads()[0])
    payload["features"].pop("beam_depth_mm")
    snapshot = normalize_geometry_feature_snapshot_input(payload)
    assembly = assemble_geometry_check_inputs(
        snapshot=snapshot,
        contract_bundle=load_geometry_contract_bundle(CATALOG_DIR),
    )
    rows = {row.check_id: row for row in assembly.coverage_rows}

    assert rows["beam_geometry_min_width"].coverage_status is (
        CoverageStatus.RUNNABLE
    )
    assert rows["beam_geometry_min_depth"].coverage_status is (
        CoverageStatus.BLOCKED
    )
    assert rows["beam_depth_width_ratio"].coverage_status is (
        CoverageStatus.BLOCKED
    )
    assert tuple(
        item.check_id
        for item in assembly.build_result.check_inputs
    ) == ("beam_geometry_min_width",)


def test_wrong_unit_remains_blocked_without_conversion() -> None:
    payload = copy.deepcopy(_payloads()[0])
    payload["features"]["beam_width_mm"]["unit"] = "cm"
    snapshot = normalize_geometry_feature_snapshot_input(payload)
    assembly = assemble_geometry_check_inputs(
        snapshot=snapshot,
        contract_bundle=load_geometry_contract_bundle(CATALOG_DIR),
    )

    assert tuple(
        item.check_id
        for item in assembly.build_result.check_inputs
    ) == ("beam_geometry_min_depth",)
    assert {
        item.check_id
        for item in assembly.build_result.diagnostics
    } == {
        "beam_geometry_min_width",
        "beam_depth_width_ratio",
    }
    assert all(
        "cm" in item.reason
        for item in assembly.build_result.diagnostics
    )


def test_unsupported_component_remains_out_of_scope() -> None:
    snapshot = normalize_geometry_feature_snapshot_input(
        {
            "component_id": "W1",
            "component_type": "wall",
            "features": {},
            "identity": {},
        }
    )
    assembly = assemble_geometry_check_inputs(
        snapshot=snapshot,
        contract_bundle=load_geometry_contract_bundle(CATALOG_DIR),
    )

    assert assembly.coverage_rows == ()
    assert assembly.build_result.check_inputs == ()
    assert (
        assembly.build_result.diagnostics[0].status
        == "OUT_OF_SCOPE"
    )


def test_vertical_slice_no_longer_calls_legacy_adapter() -> None:
    path = ROOT / "tbdy_engine/checks/geometry_vertical_slice.py"
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
    }

    assert "assemble_geometry_check_inputs" in imported_names
    assert "assemble_geometry_check_inputs" in called_names
    assert (
        "build_geometry_check_inputs_from_feature_snapshot"
        not in imported_names
    )
    assert (
        "build_geometry_check_inputs_from_feature_snapshot"
        not in called_names
    )


def test_vertical_slice_manifest_declares_coverage_authority(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "out"
    run_geometry_vertical_slice_from_file(
        feature_snapshot_path=FIXTURE,
        output_dir=out_dir,
    )
    manifest = json.loads(
        (out_dir / "run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    summary = json.loads(
        (out_dir / "run_summary.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["coverage_authority"] == "CoverageBuilder"
    assert manifest["synthetic_coverage_path_used"] is False
    assert summary["coverage_row_count"] == 6


def test_orchestration_module_does_not_import_engine() -> None:
    path = (
        ROOT
        / "tbdy_engine/checks/"
        "geometry_coverage_orchestration.py"
    )
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert "tbdy_engine.checks.engine" not in modules
    assert "tbdy_engine.checks.result" not in modules


def test_repeated_authoritative_runs_are_deterministic(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "out"
    run_geometry_vertical_slice_from_file(
        feature_snapshot_path=FIXTURE,
        output_dir=out_dir,
    )
    first = {
        path.name: path.read_text(encoding="utf-8")
        for path in out_dir.iterdir()
    }
    run_geometry_vertical_slice_from_file(
        feature_snapshot_path=FIXTURE,
        output_dir=out_dir,
    )
    second = {
        path.name: path.read_text(encoding="utf-8")
        for path in out_dir.iterdir()
    }

    assert first == second
