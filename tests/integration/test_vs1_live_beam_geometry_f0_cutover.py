from __future__ import annotations

import hashlib
import inspect
import json
import ntpath
from pathlib import Path

import pytest

from tbdy_engine.checks.member_geometry import (
    BEAM_DEPTH_WIDTH_RATIO,
    BEAM_MIN_DEPTH_300,
    BEAM_MIN_WIDTH,
)
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.evidence_epoch import EvidenceEpochOrigin
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.integration import live_beam_geometry_f0 as vs1
from tbdy_engine.product.live_beam_geometry_f0_product import (
    APPLICABILITY_SOURCE_KIND,
    build_live_beam_geometry_f0_product_from_capture,
)
from tbdy_engine.regulatory.contracts import (
    ApplicabilityState,
    ClosureExecutionStatus,
)
from tbdy_engine.regulatory.kernel import StructuralAssessmentStatus
from tools.run_live_beam_geometry_f0_product import (
    _parser as live_cli_parser,
    _tbdy_7411_cli_value,
)

MODEL_PATH = r"C:\Projects\TBDY\Kres.edb"


def _evidence(
    *,
    column: str,
    value: float,
    width: float | None,
    depth: float | None,
) -> FeatureEvidence:
    return FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table="Frame Section Property Definitions - Concrete Rectangular",
        actual_table_name="Frame Section Property Definitions - Concrete Rectangular",
        source_column=column,
        source_row={
            "component_id": "297",
            "story": "+14.5",
            "section": "B40x70",
            "width_mm": width,
            "depth_mm": depth,
            "source_table_assignment": "Frame Assignments - Section Properties",
            "source_table_property": "Frame Section Property Definitions - Concrete Rectangular",
        },
        raw_value=value,
        normalized_value=value,
        unit="mm",
        resolver="c13_5_p6_1_design_type_alias_probe",
    )


def _snapshot(
    *,
    width: float | None = 249.0,
    depth: float | None = 600.0,
    component_type: str = "beam",
    component_id: str = "297",
) -> FeatureSnapshot:
    features: dict[str, FeatureValue] = {}
    if width is None:
        features["beam_width_mm"] = FeatureValue(
            feature_name="beam_width_mm",
            value=None,
            unit="mm",
            semantic_role="GEOMETRY",
            status=FeatureValueStatus.MISSING,
        )
    else:
        features["beam_width_mm"] = FeatureValue(
            feature_name="beam_width_mm",
            value=width,
            unit="mm",
            semantic_role="GEOMETRY",
            status=FeatureValueStatus.RESOLVED,
            evidence=(
                _evidence(
                    column="t2",
                    value=width,
                    width=width,
                    depth=depth,
                ),
            ),
        )
    if depth is None:
        features["beam_depth_mm"] = FeatureValue(
            feature_name="beam_depth_mm",
            value=None,
            unit="mm",
            semantic_role="GEOMETRY",
            status=FeatureValueStatus.MISSING,
        )
    else:
        features["beam_depth_mm"] = FeatureValue(
            feature_name="beam_depth_mm",
            value=depth,
            unit="mm",
            semantic_role="GEOMETRY",
            status=FeatureValueStatus.RESOLVED,
            evidence=(
                _evidence(
                    column="t3",
                    value=depth,
                    width=width,
                    depth=depth,
                ),
            ),
        )
    snapshot = FeatureSnapshot(
        component_type=component_type,
        component_id=component_id,
        identity={
            "story": "+14.5",
            "label": "B1",
            "section": "B40x70",
            "unique_name": component_id,
        },
        features=features,
    )
    assert "tbdy_7411_applies" not in snapshot.identity
    return snapshot


def _column_snapshot() -> FeatureSnapshot:
    source_table = "Frame Section Property Definitions - Concrete Rectangular"
    common_row = {
        "component_id": "C1",
        "story": "S1",
        "section": "C400x400",
        "width_mm": 400.0,
        "depth_mm": 400.0,
        "source_table_assignment": "Frame Assignments - Section Properties",
        "source_table_property": source_table,
    }
    width_evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table=source_table,
        actual_table_name=source_table,
        source_column="t2",
        source_row=common_row,
        raw_value=400.0,
        normalized_value=400.0,
        unit="mm",
        resolver="c13_5_p6_1_design_type_alias_probe",
    )
    depth_evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table=source_table,
        actual_table_name=source_table,
        source_column="t3",
        source_row=common_row,
        raw_value=400.0,
        normalized_value=400.0,
        unit="mm",
        resolver="c13_5_p6_1_design_type_alias_probe",
    )
    snapshot = FeatureSnapshot(
        component_type="column",
        component_id="C1",
        identity={
            "story": "S1",
            "label": "C1",
            "section": "C400x400",
            "unique_name": "C1",
        },
        features={
            "column_width_mm": FeatureValue(
                feature_name="column_width_mm",
                value=400.0,
                unit="mm",
                semantic_role="GEOMETRY",
                status=FeatureValueStatus.RESOLVED,
                evidence=(width_evidence,),
            ),
            "column_depth_mm": FeatureValue(
                feature_name="column_depth_mm",
                value=400.0,
                unit="mm",
                semantic_role="GEOMETRY",
                status=FeatureValueStatus.RESOLVED,
                evidence=(depth_evidence,),
            ),
        },
    )
    assert "tbdy_7411_applies" not in snapshot.identity
    return snapshot


def _write_capture(path: Path, snapshot: FeatureSnapshot) -> bytes:
    raw = (
        json.dumps(
            {"snapshots": [snapshot.as_dict()]},
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    path.write_bytes(raw)
    return raw


def _expected_model_fingerprint(model_path: str) -> str:
    payload = {
        "contract": "ETABS_MODEL_IDENTITY_V1",
        "model_path": ntpath.normcase(ntpath.normpath(model_path.strip())),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "etabs:model-identity:sha256:" + hashlib.sha256(encoded).hexdigest()


def _run(
    snapshot: FeatureSnapshot,
    *,
    source_bytes: bytes = b"capture",
    tbdy_7411_applies: bool | None,
):
    epoch = vs1.build_live_capture_epoch(
        model_path=MODEL_PATH,
        source_bytes=source_bytes,
    )
    return vs1.run_live_beam_f0_slice(
        epoch=epoch,
        snapshot=snapshot,
        tbdy_7411_applies=tbdy_7411_applies,
    )


def _closures_by_rule(run):
    return {
        outcome.compiled_record_ref.rule_id.value: outcome
        for outcome in run.assessment.closure_outcomes
    }


def _compiled_by_rule(run):
    return {
        record.rule_id.value: record
        for record in run.program.plan.compiled_closure_inventory
    }


def _results_by_rule(run):
    return {
        record.instance_id.rule_id.value: record.result
        for record in run.store.formal_results
    }


def test_model_fingerprint_exact_supervisor_representation() -> None:
    assert vs1.model_fingerprint_from_path(MODEL_PATH) == _expected_model_fingerprint(MODEL_PATH)


def test_identical_path_has_identical_model_fingerprint() -> None:
    assert vs1.model_fingerprint_from_path(MODEL_PATH) == vs1.model_fingerprint_from_path(MODEL_PATH)


def test_windows_path_normalization_variants_have_identical_model_fingerprint() -> None:
    first = r"C:\Projects\TBDY\.\Sub\..\Kres.edb"
    second = r"c:/projects/tbdy/kres.edb"
    assert vs1.model_fingerprint_from_path(first) == vs1.model_fingerprint_from_path(second)


def test_different_model_path_has_different_model_fingerprint() -> None:
    assert vs1.model_fingerprint_from_path(MODEL_PATH) != vs1.model_fingerprint_from_path(
        r"C:\Projects\TBDY\Other.edb"
    )


def test_identical_source_bytes_have_identical_source_fingerprint() -> None:
    source = b'{"snapshots":[]}\n'
    assert vs1.source_fingerprint_from_bytes(source) == vs1.source_fingerprint_from_bytes(source)


def test_changed_source_bytes_change_source_fingerprint() -> None:
    assert vs1.source_fingerprint_from_bytes(b"A") != vs1.source_fingerprint_from_bytes(b"B")


def test_identical_model_and_source_have_identical_epoch_id() -> None:
    first = vs1.build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=b"capture")
    second = vs1.build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=b"capture")
    assert first.epoch_id == second.epoch_id
    assert first.origin is EvidenceEpochOrigin.LIVE_CAPTURE
    assert first.epoch_id.startswith("epoch:live:sha256:")


def test_changed_source_changes_epoch_id() -> None:
    first = vs1.build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=b"capture-a")
    second = vs1.build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=b"capture-b")
    assert first.epoch_id != second.epoch_id


@pytest.mark.parametrize("model_path", [None, "", "   ", "\t\r\n"])
def test_blank_model_path_fails_closed(model_path: object) -> None:
    with pytest.raises(vs1.MissingLiveEpochIdentityError) as exc_info:
        vs1.model_fingerprint_from_path(model_path)
    assert exc_info.value.status == "BLOCKED_BY_MISSING_LIVE_EPOCH_IDENTITY"


def test_identity_functions_have_no_clock_pid_or_random_inputs() -> None:
    model_signature = inspect.signature(vs1.model_fingerprint_from_path)
    epoch_signature = inspect.signature(vs1.live_epoch_id)
    assert tuple(model_signature.parameters) == ("model_path",)
    assert tuple(epoch_signature.parameters) == ("model_fingerprint", "source_fingerprint")
    source = inspect.getsource(vs1.model_fingerprint_from_path) + inspect.getsource(vs1.live_epoch_id)
    for forbidden in (
        "observed_at_utc",
        "process_id",
        "worker_thread_id",
        "attach_strategy",
        "application_version",
        "uuid",
        "random",
        "time.time",
    ):
        assert forbidden not in source


def test_get_model_filename_blank_fails_closed() -> None:
    class Sap:
        def GetModelFilename(self):
            return "   "

    with pytest.raises(vs1.MissingLiveEpochIdentityError):
        vs1.read_observed_etabs_model_path(Sap())


def test_get_model_filename_is_only_live_identity_source() -> None:
    calls: list[str] = []

    class Sap:
        def GetModelFilename(self):
            calls.append("GetModelFilename")
            return MODEL_PATH

    assert vs1.read_observed_etabs_model_path(Sap()) == ntpath.normcase(
        ntpath.normpath(MODEL_PATH)
    )
    assert calls == ["GetModelFilename"]


def test_exact_snapshot_artifact_bytes_are_source_fingerprint_authority(tmp_path: Path) -> None:
    capture_path = tmp_path / "feature_snapshot.json"
    raw = _write_capture(capture_path, _snapshot())
    epoch = vs1.build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=raw)
    assert epoch.source_fingerprint == vs1.source_fingerprint_from_path(capture_path)
    capture_path.write_bytes(raw + b" ")
    assert epoch.source_fingerprint != vs1.source_fingerprint_from_path(capture_path)


def test_explicit_applicability_accepts_bool_or_none_only() -> None:
    assert vs1.validate_tbdy_7411_applies(True) is True
    assert vs1.validate_tbdy_7411_applies(False) is False
    assert vs1.validate_tbdy_7411_applies(None) is None
    for invalid in (1, 0, "true", "false", object()):
        with pytest.raises(TypeError):
            vs1.validate_tbdy_7411_applies(invalid)  # type: ignore[arg-type]


def test_cli_requires_explicit_bounded_applicability_value(tmp_path: Path) -> None:
    parser = live_cli_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--out", str(tmp_path)])
    assert _tbdy_7411_cli_value("true") is True
    assert _tbdy_7411_cli_value("false") is False
    assert _tbdy_7411_cli_value("unknown") is None
    args = parser.parse_args(
        ["--out", str(tmp_path), "--tbdy-7411-applies", "unknown"]
    )
    assert args.tbdy_7411_applies == "unknown"


def test_scenario_a_three_existing_rules_and_one_finding(tmp_path: Path) -> None:
    capture_path = tmp_path / "feature_snapshot.json"
    _write_capture(capture_path, _snapshot(width=249.0, depth=600.0))
    result = build_live_beam_geometry_f0_product_from_capture(
        model_path=MODEL_PATH,
        feature_snapshot_path=capture_path,
        output_path=tmp_path / "product.json",
        tbdy_7411_applies=True,
    )

    product = result.payload
    assert product["origin"] == "LIVE_CAPTURE"
    assert product["applicability_input"] == {
        "tbdy_7411_applies": True,
        "source_kind": APPLICABILITY_SOURCE_KIND,
    }
    assert product["regulatory_authority"] == "F0_ONLY"
    assert product["legacy_minimal_check_engine_executed"] is False
    assert product["legacy_yaml_authority_executed"] is False
    assert product["full_tbdy_compliance_status"] == "NOT_EVALUATED"
    assert product["beam_count"] == 1
    assert product["selected_rule_instance_count"] == 3
    assert product["check_result_count"] == 3
    assert product["finding_count"] == 1

    beam = product["beams"][0]
    assert beam["epoch_ref"] == product["epoch_ref"]
    assert beam["plan_identity"]
    assert beam["applicability_input"] == product["applicability_input"]
    assert beam["rule_instance_count"] == 3
    closures = {item["rule_id"]: item for item in beam["closure_inventory"]}
    assert set(closures) == {BEAM_MIN_WIDTH, BEAM_MIN_DEPTH_300, BEAM_DEPTH_WIDTH_RATIO}
    assert all(item["applicability"] == ApplicabilityState.APPLIES.value for item in closures.values())
    assert all(
        item["closure_status"] == ClosureExecutionStatus.EXECUTED.value
        for item in closures.values()
    )

    check_results = {item["check_id"]: item for item in beam["check_results"]}
    assert check_results[BEAM_MIN_WIDTH]["status"] == "FAIL"
    assert check_results[BEAM_MIN_DEPTH_300]["status"] == "OK"
    assert check_results[BEAM_DEPTH_WIDTH_RATIO]["status"] == "OK"
    assert check_results[BEAM_DEPTH_WIDTH_RATIO]["value"] == pytest.approx(600.0 / 249.0)
    assert beam["finding_count"] == 1
    assert beam["findings"][0]["source_kind"] == "CHECK_RESULT"
    assert beam["findings"][0]["source_status"] == "FAIL"
    assert beam["assessment"]["full_tbdy_compliance_status"] == "NOT_EVALUATED"


def test_scenario_b_same_context_is_deterministic(tmp_path: Path) -> None:
    capture_path = tmp_path / "feature_snapshot.json"
    _write_capture(capture_path, _snapshot())
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = build_live_beam_geometry_f0_product_from_capture(
        model_path=MODEL_PATH,
        feature_snapshot_path=capture_path,
        output_path=first_path,
        tbdy_7411_applies=True,
    )
    second = build_live_beam_geometry_f0_product_from_capture(
        model_path=MODEL_PATH,
        feature_snapshot_path=capture_path,
        output_path=second_path,
        tbdy_7411_applies=True,
    )
    first_beam = first.payload["beams"][0]
    second_beam = second.payload["beams"][0]
    assert first.payload["epoch_id"] == second.payload["epoch_id"]
    assert first_beam["plan_identity"] == second_beam["plan_identity"]
    assert first_beam["assessment"] == second_beam["assessment"]
    assert [item["finding_id"] for item in first.payload["findings"]] == [
        item["finding_id"] for item in second.payload["findings"]
    ]
    assert first_path.read_bytes() == second_path.read_bytes()


def test_scenario_c_column_unknown_context_is_proven_not_applicable() -> None:
    snapshot = _column_snapshot()
    run = _run(snapshot, tbdy_7411_applies=None)
    assert "tbdy_7411_applies" not in snapshot.identity
    assert run.store.formal_results == ()
    assert len(run.assessment.closure_outcomes) == 3
    assert all(
        item.execution_status is ClosureExecutionStatus.PROVEN_NOT_APPLICABLE
        for item in run.assessment.closure_outcomes
    )
    assert all(
        item.applicability is ApplicabilityState.PROVEN_NOT_APPLICABLE
        for item in run.program.plan.compiled_closure_inventory
    )
    assert run.findings == ()


def test_scenario_d_factual_evidence_remains_factual_and_applicability_is_not_identity(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    assert "tbdy_7411_applies" not in snapshot.identity
    capture_path = tmp_path / "feature_snapshot.json"
    _write_capture(capture_path, snapshot)
    result = build_live_beam_geometry_f0_product_from_capture(
        model_path=MODEL_PATH,
        feature_snapshot_path=capture_path,
        output_path=tmp_path / "product.json",
        tbdy_7411_applies=True,
    )
    beam = result.payload["beams"][0]
    assert beam["evidence_refs"]
    assert any(ref.startswith("evidence:") for ref in beam["provenance_refs"])
    for check_result in beam["check_results"]:
        assert check_result["evidence"]
        assert all(
            row["source_table"]
            == "Frame Section Property Definitions - Concrete Rectangular"
            for row in check_result["evidence"]
        )
        assert all(
            row["resolver"] == "c13_5_p6_1_design_type_alias_probe"
            for row in check_result["evidence"]
        )
        assert all("tbdy_7411_applies" not in row["source_row"] for row in check_result["evidence"])


def test_scenario_e_missing_width_is_dependency_scoped_no_data(tmp_path: Path) -> None:
    capture_path = tmp_path / "feature_snapshot.json"
    raw = _write_capture(capture_path, _snapshot(width=None, depth=600.0))
    capture = vs1.load_live_beam_capture_artifact(capture_path)
    epoch = vs1.build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=raw)
    run = vs1.run_live_beam_f0_slice(
        epoch=epoch,
        snapshot=capture.beam_snapshots[0],
        tbdy_7411_applies=True,
    )

    results = _results_by_rule(run)
    closures = _closures_by_rule(run)
    assert BEAM_MIN_WIDTH not in results
    assert results[BEAM_MIN_DEPTH_300].status.value == "OK"
    assert BEAM_DEPTH_WIDTH_RATIO not in results
    assert closures[BEAM_MIN_WIDTH].execution_status is ClosureExecutionStatus.NO_DATA
    assert closures[BEAM_MIN_DEPTH_300].execution_status is ClosureExecutionStatus.EXECUTED
    assert closures[BEAM_DEPTH_WIDTH_RATIO].execution_status is ClosureExecutionStatus.NO_DATA
    assert run.snapshot.features["beam_width_mm"].value is None


def test_scenario_f_unknown_beam_applicability_blocks_without_fake_checkresults() -> None:
    run = _run(_snapshot(), tbdy_7411_applies=None)
    compiled = _compiled_by_rule(run)
    closures = _closures_by_rule(run)
    assert run.store.formal_results == ()
    assert set(compiled) == {BEAM_MIN_WIDTH, BEAM_MIN_DEPTH_300, BEAM_DEPTH_WIDTH_RATIO}
    assert all(item.applicability is ApplicabilityState.UNRESOLVED for item in compiled.values())
    assert all(
        item.execution_status is ClosureExecutionStatus.BLOCKED
        for item in closures.values()
    )
    assert run.assessment.structural_status is StructuralAssessmentStatus.INCOMPLETE
    assert run.assessment.full_tbdy_compliance_status == "NOT_EVALUATED"
    assert len(run.findings) == 3
    assert all(item.source_kind.value == "RULE_CLOSURE" for item in run.findings)
    assert all(item.source_status is ClosureExecutionStatus.BLOCKED for item in run.findings)


def test_scenario_g_explicit_false_is_proven_not_applicable() -> None:
    run = _run(_snapshot(), tbdy_7411_applies=False)
    assert run.store.formal_results == ()
    assert all(
        item.applicability is ApplicabilityState.PROVEN_NOT_APPLICABLE
        for item in run.program.plan.compiled_closure_inventory
    )
    assert all(
        item.execution_status is ClosureExecutionStatus.PROVEN_NOT_APPLICABLE
        for item in run.assessment.closure_outcomes
    )
    assert run.findings == ()


def test_same_factual_capture_same_epoch_but_applicability_changes_plan(tmp_path: Path) -> None:
    capture_path = tmp_path / "feature_snapshot.json"
    factual_bytes = _write_capture(capture_path, _snapshot())
    before = capture_path.read_bytes()

    true_product = build_live_beam_geometry_f0_product_from_capture(
        model_path=MODEL_PATH,
        feature_snapshot_path=capture_path,
        output_path=tmp_path / "true.json",
        tbdy_7411_applies=True,
    )
    unknown_product = build_live_beam_geometry_f0_product_from_capture(
        model_path=MODEL_PATH,
        feature_snapshot_path=capture_path,
        output_path=tmp_path / "unknown.json",
        tbdy_7411_applies=None,
    )

    assert capture_path.read_bytes() == before == factual_bytes
    for key in ("model_fingerprint", "source_fingerprint", "epoch_id"):
        assert true_product.payload[key] == unknown_product.payload[key]
    assert (
        true_product.payload["beams"][0]["plan_identity"]
        != unknown_product.payload["beams"][0]["plan_identity"]
    )
    assert true_product.payload["applicability_input"]["tbdy_7411_applies"] is True
    assert unknown_product.payload["applicability_input"]["tbdy_7411_applies"] is None
    assert true_product.payload["check_result_count"] == 3
    assert unknown_product.payload["check_result_count"] == 0
    assert unknown_product.payload["finding_count"] == 3
    assert unknown_product.payload["structural_assessment_status"] == "INCOMPLETE"
    assert all(
        item["applicability"] == ApplicabilityState.UNRESOLVED.value
        for item in unknown_product.payload["beams"][0]["closure_inventory"]
    )
    assert all(
        item["closure_status"] == ClosureExecutionStatus.BLOCKED.value
        for item in unknown_product.payload["beams"][0]["closure_inventory"]
    )


def test_production_path_excludes_snapshot_applicability_legacy_authority_and_direct_evaluators() -> None:
    production_paths = (
        Path("tbdy_engine/integration/live_beam_geometry_f0.py"),
        Path("tbdy_engine/product/live_beam_geometry_f0_product.py"),
        Path("tools/run_live_beam_geometry_f0_product.py"),
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in production_paths)
    for forbidden in (
        "TBDY_7411_APPLIES_IDENTITY_KEY",
        "_tbdy_7411_applies(snapshot)",
        "design_context",
        "MinimalCheckEngine",
        "EngineContractLoader",
        "geometry_vertical_slice",
        "geometry_product_smoke",
        "import yaml",
        "from yaml",
        "product_reports",
        "evaluate_member_rule",
        "evaluate_beam_min_width",
        "evaluate_beam_min_depth",
        "evaluate_beam_depth_width_ratio",
    ):
        assert forbidden not in source
