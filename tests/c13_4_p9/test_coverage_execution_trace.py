from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from tbdy_engine.checks.coverage_execution_trace import (
    CoverageExecutionTraceRow,
    canonicalize_coverage_execution_trace,
)
from tbdy_engine.checks.geometry_coverage_orchestration import (
    assemble_geometry_check_inputs,
    load_geometry_contract_bundle,
)
from tbdy_engine.checks.geometry_vertical_slice import (
    _execute_coverage_assembly,
    run_geometry_vertical_slice_from_file,
)
from tbdy_engine.checks.input_adapter import (
    CheckInputBuildDiagnostic,
    GeometryCheckInput,
    normalize_geometry_feature_snapshot_input,
)
from tbdy_engine.checks.result import CheckResult
from tbdy_engine.coverage.models import CoverageRow, CoverageStatus
from tbdy_engine.product.bundle_validator import validate_geometry_product_bundle
from tbdy_engine.product.geometry_product_smoke import run_geometry_product_smoke

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "c13_4_p4" / "geometry_feature_snapshots.json"
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"
BASELINE_SHA256 = {
    "check_results.json": "845ad0ea8f45e53d47bf8b0bb64d8140623814d5731a5c62aa858c1bb1c116d5",
    "adapter_diagnostics.json": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    "coverage_rows.json": "b27402b51bc929936ebae8c167f4f788972b24c77a295fa74b1c56ee7243b511",
}
FORBIDDEN_TRACE_FIELDS = {
    "value",
    "limit",
    "ratio",
    "demand",
    "capacity",
    "formula",
    "pass_rule",
    "utilization",
    "governing_combo",
    "engineering_verdict",
}


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _blocked_input(tmp_path: Path) -> Path:
    payload = _read(FIXTURE)["snapshots"][0]
    payload["features"].pop("beam_depth_mm")
    path = tmp_path / "blocked_feature_snapshot.json"
    _write(path, payload)
    return path


def _bundle(tmp_path: Path, *, blocked: bool = False) -> Path:
    root = tmp_path / "bundle"
    source = _blocked_input(tmp_path) if blocked else FIXTURE
    run_geometry_product_smoke(feature_snapshot_path=source, output_dir=root)
    return root


def _validate(bundle: Path):
    path = bundle / "validation.json"
    result = validate_geometry_product_bundle(
        bundle_dir=bundle,
        validation_output_path=path,
    )
    return result, _read(path)


def _trace_key(item: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(item["component_type"]),
        str(item["component_id"]),
        str(item["check_id"]),
    )


def _forbidden_paths(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in FORBIDDEN_TRACE_FIELDS:
                found.append(key)
            found.extend(_forbidden_paths(nested))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_forbidden_paths(nested))
    return found


class _MatchingEngine:
    def run_check(self, check_id, snapshot, coverage):
        return CheckResult(
            check_id=check_id,
            component=coverage.component_id,
            component_type=coverage.component_type,
            status="OK",
        )


def test_trace_artifact_is_exact_typed_runtime_rows_in_canonical_order(tmp_path: Path):
    out = tmp_path / "out"
    result = run_geometry_vertical_slice_from_file(
        feature_snapshot_path=FIXTURE,
        output_dir=out,
    )
    trace = _read(out / "coverage_execution_trace.json")
    coverage = _read(out / "coverage_rows.json")
    check_results = _read(out / "check_results.json")

    assert isinstance(trace, list)
    assert all(isinstance(row, CoverageExecutionTraceRow) for row in result.coverage_execution_trace)
    assert trace == [row.as_dict() for row in result.coverage_execution_trace]
    trace_keys = [_trace_key(item) for item in trace]
    coverage_keys = [_trace_key(item) for item in coverage]
    assert trace_keys == sorted(trace_keys) == coverage_keys
    assert len(trace) == len(coverage) == 6
    assert all(not _forbidden_paths(item) for item in trace)

    for item in trace:
        referenced = check_results[item["check_result_index"]]
        assert item["check_input_emitted"] is True
        assert item["adapter_status"] == "READY"
        assert item["adapter_reason"] is None
        assert item["adapter_diagnostic_index"] is None
        assert referenced["component_type"] == item["component_type"]
        assert referenced["component"] == item["component_id"]
        assert referenced["check_id"] == item["check_id"]
        assert referenced["status"] == item["check_result_status"]


def test_blocked_mixed_population_links_diagnostics_and_trace_exceeds_results(tmp_path: Path):
    out = tmp_path / "out"
    result = run_geometry_vertical_slice_from_file(
        feature_snapshot_path=_blocked_input(tmp_path),
        output_dir=out,
    )
    trace = _read(out / "coverage_execution_trace.json")
    diagnostics = _read(out / "adapter_diagnostics.json")

    assert len(trace) == len(result.coverage_rows) == 3
    assert len(result.check_results) == 1
    assert len(trace) > len(result.check_results)
    blocked_rows = [item for item in trace if item["coverage_status"] == "BLOCKED"]
    assert len(blocked_rows) == 2
    for item in blocked_rows:
        assert item["check_input_emitted"] is False
        assert item["check_result_emitted"] is False
        assert item["check_result_index"] is None
        assert item["check_result_status"] is None
        diagnostic = diagnostics[item["adapter_diagnostic_index"]]
        assert diagnostic["check_id"] == item["check_id"]
        assert diagnostic["component_type"] == item["component_type"]
        assert diagnostic["component_id"] == item["component_id"]
        assert diagnostic["status"] == item["adapter_status"]
        assert diagnostic["reason"] == item["adapter_reason"]

    assert result.run_summary["coverage_execution_trace_count"] == 3
    assert result.run_summary["check_input_emitted_count"] == 1
    assert result.run_summary["check_input_not_emitted_count"] == 2
    assert result.run_summary["check_result_emitted_count"] == 1
    assert result.run_summary["check_result_not_emitted_count"] == 2
    assert result.run_summary["trace_adapter_status_counts"] == {"BLOCKED": 2, "READY": 1}
    assert result.run_summary["trace_result_status_counts"] == {"OK": 1}


def test_partial_coverage_row_has_diagnostic_terminal_outcome_without_result():
    row = CoverageRow(
        check_id="beam_geometry_min_width",
        component_type="beam",
        component_id="B-PARTIAL",
        coverage_status=CoverageStatus.PARTIAL,
        reason="coverage evidence is partial",
        expected_evidence_requirements={"beam_width_mm": ("raw_value",)},
    )
    diagnostic = CheckInputBuildDiagnostic(
        check_id=row.check_id,
        component_id=row.component_id,
        component_type=row.component_type,
        status="BLOCKED",
        reason=row.reason or "partial coverage",
    )
    check_results: list[CheckResult] = []
    diagnostics: list[CheckInputBuildDiagnostic] = []

    trace = _execute_coverage_assembly(
        coverage_rows=(row,),
        check_inputs=(),
        diagnostics=(diagnostic,),
        engine=_MatchingEngine(),
        check_results=check_results,
        adapter_diagnostics=diagnostics,
    )

    assert len(trace) == 1
    assert trace[0].coverage_status == "PARTIAL"
    assert trace[0].check_input_emitted is False
    assert trace[0].adapter_diagnostic_index == 0
    assert trace[0].check_result_emitted is False
    assert check_results == []
    assert diagnostics == [diagnostic]


def test_adapter_runtime_inputs_retain_exact_authoritative_coverage_objects():
    payload = _read(FIXTURE)["snapshots"][0]
    snapshot = normalize_geometry_feature_snapshot_input(payload)
    assembly = assemble_geometry_check_inputs(
        snapshot=snapshot,
        contract_bundle=load_geometry_contract_bundle(CATALOG_DIR),
    )
    rows_by_key = {
        (row.component_type, row.component_id, row.check_id): row
        for row in assembly.coverage_rows
    }

    for check_input in assembly.build_result.check_inputs:
        key = (check_input.component_type, check_input.component_id, check_input.check_id)
        assert check_input.coverage is rows_by_key[key]


def test_cloned_coverage_object_on_check_input_fails_closed():
    payload = _read(FIXTURE)["snapshots"][0]
    snapshot = normalize_geometry_feature_snapshot_input(payload)
    assembly = assemble_geometry_check_inputs(
        snapshot=snapshot,
        contract_bundle=load_geometry_contract_bundle(CATALOG_DIR),
    )
    authoritative = assembly.coverage_rows[0]
    original_input = next(
        item for item in assembly.build_result.check_inputs if item.check_id == authoritative.check_id
    )
    clone = CoverageRow(**authoritative.as_dict())
    substituted = GeometryCheckInput(
        check_id=original_input.check_id,
        component_id=original_input.component_id,
        component_type=original_input.component_type,
        story=original_input.story,
        section=original_input.section,
        required_features=original_input.required_features,
        snapshot=original_input.snapshot,
        coverage=clone,
        evidence_by_feature=original_input.evidence_by_feature,
    )

    with pytest.raises(ValueError, match="exact authoritative CoverageRow object"):
        _execute_coverage_assembly(
            coverage_rows=(authoritative,),
            check_inputs=(substituted,),
            diagnostics=(),
            engine=_MatchingEngine(),
            check_results=[],
            adapter_diagnostics=[],
        )


def test_check_result_identity_mismatch_fails_closed(tmp_path: Path, monkeypatch):
    def mismatching_run_check(self, check_id, snapshot, coverage):
        return CheckResult(
            check_id=check_id,
            component="WRONG-COMPONENT",
            component_type=coverage.component_type,
            status="OK",
        )

    monkeypatch.setattr(
        "tbdy_engine.checks.geometry_vertical_slice.MinimalCheckEngine.run_check",
        mismatching_run_check,
    )
    with pytest.raises(ValueError, match="CheckResult identity"):
        run_geometry_vertical_slice_from_file(
            feature_snapshot_path=FIXTURE,
            output_dir=tmp_path / "out",
        )


def test_both_input_and_diagnostic_for_one_coverage_row_fails_closed():
    payload = _read(FIXTURE)["snapshots"][0]
    snapshot = normalize_geometry_feature_snapshot_input(payload)
    assembly = assemble_geometry_check_inputs(
        snapshot=snapshot,
        contract_bundle=load_geometry_contract_bundle(CATALOG_DIR),
    )
    row = assembly.coverage_rows[0]
    check_input = next(item for item in assembly.build_result.check_inputs if item.check_id == row.check_id)
    diagnostic = CheckInputBuildDiagnostic(
        check_id=row.check_id,
        component_id=row.component_id,
        component_type=row.component_type,
        status="BLOCKED",
        reason="conflicting terminal outcome",
    )

    with pytest.raises(ValueError, match="both a CheckInput and adapter diagnostic"):
        _execute_coverage_assembly(
            coverage_rows=(row,),
            check_inputs=(check_input,),
            diagnostics=(diagnostic,),
            engine=_MatchingEngine(),
            check_results=[],
            adapter_diagnostics=[],
        )


def test_missing_terminal_outcome_fails_closed():
    row = CoverageRow(
        check_id="beam_geometry_min_width",
        component_type="beam",
        component_id="B-MISSING",
    )
    with pytest.raises(ValueError, match="no terminal adapter outcome"):
        _execute_coverage_assembly(
            coverage_rows=(row,),
            check_inputs=(),
            diagnostics=(),
            engine=_MatchingEngine(),
            check_results=[],
            adapter_diagnostics=[],
        )


def test_trace_duplicate_keys_result_links_and_diagnostic_links_fail_closed():
    ready_a = CoverageExecutionTraceRow(
        component_type="beam",
        component_id="B1",
        check_id="check_a",
        coverage_status="RUNNABLE",
        check_input_emitted=True,
        adapter_status="READY",
        adapter_reason=None,
        adapter_diagnostic_index=None,
        check_result_emitted=True,
        check_result_index=0,
        check_result_status="OK",
    )
    duplicate_key = CoverageExecutionTraceRow(
        component_type="beam",
        component_id="B1",
        check_id="check_a",
        coverage_status="RUNNABLE",
        check_input_emitted=True,
        adapter_status="READY",
        adapter_reason=None,
        adapter_diagnostic_index=None,
        check_result_emitted=True,
        check_result_index=1,
        check_result_status="OK",
    )
    ready_b_same_result = CoverageExecutionTraceRow(
        component_type="beam",
        component_id="B1",
        check_id="check_b",
        coverage_status="RUNNABLE",
        check_input_emitted=True,
        adapter_status="READY",
        adapter_reason=None,
        adapter_diagnostic_index=None,
        check_result_emitted=True,
        check_result_index=0,
        check_result_status="OK",
    )
    blocked_a = CoverageExecutionTraceRow(
        component_type="beam",
        component_id="B1",
        check_id="check_c",
        coverage_status="BLOCKED",
        check_input_emitted=False,
        adapter_status="BLOCKED",
        adapter_reason="blocked",
        adapter_diagnostic_index=0,
        check_result_emitted=False,
        check_result_index=None,
        check_result_status=None,
    )
    blocked_b_same_diagnostic = CoverageExecutionTraceRow(
        component_type="beam",
        component_id="B1",
        check_id="check_d",
        coverage_status="BLOCKED",
        check_input_emitted=False,
        adapter_status="BLOCKED",
        adapter_reason="blocked",
        adapter_diagnostic_index=0,
        check_result_emitted=False,
        check_result_index=None,
        check_result_status=None,
    )

    with pytest.raises(ValueError, match="Duplicate coverage execution trace canonical key"):
        canonicalize_coverage_execution_trace((ready_a, duplicate_key))
    with pytest.raises(ValueError, match="CheckResult index more than once"):
        canonicalize_coverage_execution_trace((ready_a, ready_b_same_result))
    with pytest.raises(ValueError, match="adapter diagnostic index more than once"):
        canonicalize_coverage_execution_trace((blocked_a, blocked_b_same_diagnostic))


def test_trace_is_built_without_reading_generated_artifacts(tmp_path: Path, monkeypatch):
    generated_names = {
        "coverage_rows.json",
        "coverage_execution_trace.json",
        "check_results.json",
        "adapter_diagnostics.json",
        "run_summary.json",
        "run_manifest.json",
    }
    original_read_text = Path.read_text

    def guarded_read_text(self, *args, **kwargs):
        if self.name in generated_names:
            raise AssertionError(f"post-hoc artifact read forbidden: {self.name}")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    result = run_geometry_vertical_slice_from_file(
        feature_snapshot_path=FIXTURE,
        output_dir=tmp_path / "out",
    )

    assert len(result.coverage_execution_trace) == len(result.coverage_rows) == 6


def test_slice_b_artifacts_remain_eol_normalized_byte_stable(tmp_path: Path):
    out = tmp_path / "out"
    run_geometry_vertical_slice_from_file(
        feature_snapshot_path=FIXTURE,
        output_dir=out,
    )

    for name, expected_hash in BASELINE_SHA256.items():
        artifact_bytes = (out / name).read_bytes()
        eol_normalized_bytes = artifact_bytes.replace(
            b"\r\n",
            b"\n",
        )
        assert (
            sha256(eol_normalized_bytes).hexdigest()
            == expected_hash
        )


def test_product_bundle_has_trace_path_counts_and_valid_nine_file_contract(tmp_path: Path):
    bundle = _bundle(tmp_path)
    product_summary = _read(bundle / "product_smoke_summary.json")
    result, validation = _validate(bundle)

    assert result.status == "OK"
    assert result.required_file_count == 9
    assert validation["counts"]["coverage_execution_trace_count"] == 6
    assert product_summary["outputs"]["coverage_execution_trace_json"] == str(
        bundle / "artifacts" / "coverage_execution_trace.json"
    )
    assert product_summary["p4"]["coverage_execution_trace_count"] == 6
    assert product_summary["p4"]["check_input_emitted_count"] == 6
    assert product_summary["p4"]["check_result_emitted_count"] == 6


def test_bundle_validator_rejects_missing_trace(tmp_path: Path):
    bundle = _bundle(tmp_path)
    (bundle / "artifacts" / "coverage_execution_trace.json").unlink()
    result, validation = _validate(bundle)

    assert result.status == "FAIL"
    assert any(
        "Missing required file: artifacts/coverage_execution_trace.json" in message
        for message in validation["errors"]
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("coverage_key", "keys must exactly equal coverage_rows.json keys"),
        ("result_index", "check_result_index out of range"),
        ("result_status", "CheckResult identity/status mismatch"),
        ("coverage_status", "coverage_status mismatch"),
        ("forbidden", "Forbidden engineering payload field"),
        ("terminal", "terminal invariant violation"),
        ("summary", "coverage_execution_trace_count"),
        ("duplicate_key", "Duplicate execution trace canonical key"),
    ],
)
def test_bundle_validator_rejects_invalid_trace_contract(
    tmp_path: Path,
    mutation: str,
    message: str,
):
    bundle = _bundle(tmp_path)
    trace_path = bundle / "artifacts" / "coverage_execution_trace.json"
    trace = _read(trace_path)

    if mutation == "coverage_key":
        trace[0]["component_id"] = "UNKNOWN"
    elif mutation == "result_index":
        trace[0]["check_result_index"] = 999
    elif mutation == "result_status":
        trace[0]["check_result_status"] = "WARNING"
    elif mutation == "coverage_status":
        trace[0]["coverage_status"] = "BLOCKED"
    elif mutation == "forbidden":
        trace[0]["metadata"] = {"ratio": 0.5}
    elif mutation == "terminal":
        trace[0]["adapter_reason"] = "must be null on READY"
    elif mutation == "summary":
        summary_path = bundle / "artifacts" / "run_summary.json"
        summary = _read(summary_path)
        summary["coverage_execution_trace_count"] += 1
        _write(summary_path, summary)
    elif mutation == "duplicate_key":
        duplicate = dict(trace[0])
        duplicate["check_result_index"] = trace[1]["check_result_index"]
        trace.append(duplicate)

    _write(trace_path, trace)
    result, validation = _validate(bundle)
    assert result.status == "FAIL"
    assert any(message in item for item in validation["errors"])


def test_bundle_validator_rejects_duplicate_diagnostic_linkage(tmp_path: Path):
    bundle = _bundle(tmp_path, blocked=True)
    trace_path = bundle / "artifacts" / "coverage_execution_trace.json"
    trace = _read(trace_path)
    blocked = [item for item in trace if item["check_input_emitted"] is False]
    assert len(blocked) == 2
    blocked[1]["adapter_diagnostic_index"] = blocked[0]["adapter_diagnostic_index"]
    _write(trace_path, trace)

    result, validation = _validate(bundle)
    assert result.status == "FAIL"
    assert any("Adapter diagnostic index linked more than once" in item for item in validation["errors"])


def test_run_manifest_declares_runtime_authority_and_no_serialized_reconstruction(tmp_path: Path):
    out = tmp_path / "out"
    result = run_geometry_vertical_slice_from_file(feature_snapshot_path=FIXTURE, output_dir=out)
    manifest = result.manifest

    assert manifest["execution_trace_authority"] == "runtime_coverage_adapter_engine_chain"
    assert manifest["execution_trace_artifact_source"] == "authoritative_runtime_objects"
    assert manifest["execution_trace_reconstructed_from_serialized_artifacts"] is False
    assert manifest["execution_trace_covers_every_coverage_row"] is True
    assert manifest["check_input_coverage_object_identity_required"] is True
    assert "coverage_execution_trace.json" in manifest["artifact_files"]
