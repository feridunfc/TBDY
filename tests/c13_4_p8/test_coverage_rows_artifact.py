from __future__ import annotations

import json
from pathlib import Path

import pytest

from tbdy_engine.checks.coverage_artifact import coverage_rows_payload
from tbdy_engine.coverage.models import CoverageRow, CoverageStatus
from tbdy_engine.checks.geometry_vertical_slice import run_geometry_vertical_slice_from_file
from tbdy_engine.product.bundle_validator import validate_geometry_product_bundle
from tbdy_engine.product.geometry_product_smoke import run_geometry_product_smoke

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "c13_4_p4" / "geometry_feature_snapshots.json"


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "bundle"
    run_geometry_product_smoke(feature_snapshot_path=FIXTURE, output_dir=root)
    return root


def test_artifact_is_exact_authoritative_rows_in_canonical_order(tmp_path: Path):
    out = tmp_path / "out"
    result = run_geometry_vertical_slice_from_file(feature_snapshot_path=FIXTURE, output_dir=out)
    artifact = _read(out / "coverage_rows.json")
    assert isinstance(artifact, list)
    assert all(isinstance(row, CoverageRow) for row in result.coverage_rows)
    assert artifact == [row.as_dict() for row in result.coverage_rows]
    keys = [(r["component_type"], r["component_id"], r["check_id"]) for r in artifact]
    assert keys == sorted(keys)
    assert result.run_summary["coverage_row_count"] == len(artifact) == 6
    assert result.run_summary["coverage_status_counts"] == {"RUNNABLE": 6}
    assert result.manifest["coverage_authority"] == "CoverageBuilder"
    assert result.manifest["coverage_artifact_source"] == "authoritative_runtime_objects"
    assert result.manifest["coverage_reconstructed_from_check_results"] is False
    assert result.manifest["synthetic_coverage_path_used"] is False


def test_runnable_partial_and_blocked_rows_preserve_coverage_only_schema():
    rows = (
        CoverageRow(
            check_id="check_runnable",
            component_type="beam",
            component_id="B1",
            coverage_status=CoverageStatus.RUNNABLE,
        ),
        CoverageRow(
            check_id="check_partial",
            component_type="beam",
            component_id="B1",
            coverage_status=CoverageStatus.PARTIAL,
            reason="coverage evidence is partial",
            expected_evidence_requirements={"beam_width_mm": ("raw_value",)},
        ),
        CoverageRow(
            check_id="check_blocked",
            component_type="beam",
            component_id="B1",
            coverage_status=CoverageStatus.BLOCKED,
            reason="required coverage input is missing",
            expected_evidence_requirements={"beam_width_mm": ("raw_value",)},
        ),
    )
    payload = coverage_rows_payload(rows)
    assert {item["coverage_status"] for item in payload} == {"RUNNABLE", "PARTIAL", "BLOCKED"}
    forbidden = {
        "check_result", "result_status", "ratio", "value", "limit", "formula",
        "pass_rule", "utilization", "governing_combo", "engineering_verdict",
    }
    assert all(not (forbidden & set(item)) for item in payload)


def test_blocked_rows_remain_even_when_no_check_result_is_emitted(tmp_path: Path):
    payload = _read(FIXTURE)["snapshots"][0]
    payload["features"].pop("beam_depth_mm")
    source = tmp_path / "blocked.json"
    _write(source, payload)
    out = tmp_path / "out"
    result = run_geometry_vertical_slice_from_file(feature_snapshot_path=source, output_dir=out)
    artifact = _read(out / "coverage_rows.json")
    assert len(artifact) == 3
    assert len(result.check_results) == 1
    assert any(item["coverage_status"] == "BLOCKED" for item in artifact)
    assert len(artifact) > len(result.check_results)


def test_duplicate_authoritative_keys_fail_closed(tmp_path: Path):
    payload = _read(FIXTURE)
    payload["snapshots"].append(payload["snapshots"][0])
    source = tmp_path / "duplicate.json"
    _write(source, payload)
    with pytest.raises(ValueError, match="Duplicate authoritative CoverageRow canonical key"):
        run_geometry_vertical_slice_from_file(feature_snapshot_path=source, output_dir=tmp_path / "out")


def test_bundle_validator_accepts_valid_coverage_artifact(tmp_path: Path):
    bundle = _bundle(tmp_path)
    result = validate_geometry_product_bundle(bundle_dir=bundle)
    assert result.status == "OK"
    assert (bundle / "artifacts" / "coverage_rows.json").is_file()


@pytest.mark.parametrize("mutation, message", [
    ("duplicate", "Duplicate CoverageRow canonical key"),
    ("order", "canonical component_type/component_id/check_id order"),
    ("count", "coverage_row_count"),
    ("statuses", "coverage_status_counts"),
    ("forbidden", "Forbidden engineering-result field"),
    ("forbidden_nested", "Forbidden engineering-result field"),
])
def test_bundle_validator_rejects_invalid_coverage_contract(tmp_path: Path, mutation: str, message: str):
    bundle = _bundle(tmp_path)
    rows_path = bundle / "artifacts" / "coverage_rows.json"
    rows = _read(rows_path)
    summary_path = bundle / "artifacts" / "run_summary.json"
    summary = _read(summary_path)
    if mutation == "duplicate": rows.append(dict(rows[0]))
    elif mutation == "order": rows[0], rows[-1] = rows[-1], rows[0]
    elif mutation == "count": summary["coverage_row_count"] += 1
    elif mutation == "statuses": summary["coverage_status_counts"] = {"BLOCKED": len(rows)}
    elif mutation == "forbidden": rows[0]["ratio"] = 0.5
    elif mutation == "forbidden_nested":
        rows[0]["diagnostics"] = [{"details": {"engineering_verdict": "not_allowed"}}]
    _write(rows_path, rows)
    _write(summary_path, summary)
    result = validate_geometry_product_bundle(
        bundle_dir=bundle,
        validation_output_path=bundle / "validation.json",
    )
    assert result.status == "FAIL"
    assert any(message in item for item in _read(bundle / "validation.json")["errors"])


def test_bundle_validator_rejects_missing_coverage_artifact(tmp_path: Path):
    bundle = _bundle(tmp_path)
    (bundle / "artifacts" / "coverage_rows.json").unlink()
    result = validate_geometry_product_bundle(
        bundle_dir=bundle,
        validation_output_path=bundle / "validation.json",
    )
    assert result.status == "FAIL"
    assert any("Missing required file: artifacts/coverage_rows.json" in item for item in _read(bundle / "validation.json")["errors"])
