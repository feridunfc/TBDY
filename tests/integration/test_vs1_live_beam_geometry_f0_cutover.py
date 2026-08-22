from __future__ import annotations

import inspect
import json
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
    build_live_beam_geometry_f0_product_from_capture,
)
from tbdy_engine.regulatory.contracts import ClosureExecutionStatus


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
        resolver="c13_5_live_etabs_read_only_geometry_probe",
    )


def _snapshot(
    *,
    width: float | None = 249.0,
    depth: float | None = 600.0,
) -> FeatureSnapshot:
    features = {}
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
    return FeatureSnapshot(
        component_type="beam",
        component_id="297",
        identity={
            "story": "+14.5",
            "label": "B1",
            "section": "B40x70",
            "unique_name": "297",
        },
        features=features,
    )


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


def test_exact_snapshot_artifact_bytes_are_source_fingerprint_authority(tmp_path: Path) -> None:
    capture_path = tmp_path / "feature_snapshot.json"
    raw = _write_capture(capture_path, _snapshot())
    epoch = vs1.build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=raw)
    assert epoch.source_fingerprint == vs1.source_fingerprint_from_path(capture_path)
    capture_path.write_bytes(raw + b" ")
    assert epoch.source_fingerprint != vs1.source_fingerprint_from_path(capture_path)


def test_vs1_scenario_a_executes_exact_three_existing_rules_and_one_finding(tmp_path: Path) -> None:
    capture_path = tmp_path / "feature_snapshot.json"
    _write_capture(capture_path, _snapshot(width=249.0, depth=600.0))
    output = tmp_path / "product.json"
    result = build_live_beam_geometry_f0_product_from_capture(
        model_path=MODEL_PATH,
        feature_snapshot_path=capture_path,
        output_path=output,
    )

    product = result.payload
    assert product["origin"] == "LIVE_CAPTURE"
    assert product["regulatory_authority"] == "F0_ONLY"
    assert product["legacy_minimal_check_engine_executed"] is False
    assert product["legacy_yaml_authority_executed"] is False
    assert product["full_tbdy_compliance_status"] == "NOT_EVALUATED"
    assert product["beam_count"] == 1
    assert product["selected_rule_instance_count"] == 3
    assert product["check_result_count"] == 3
    assert product["finding_count"] == 1

    beam = product["beams"][0]
    assert beam["rule_instance_count"] == 3
    rules = {item["rule_id"]: item for item in beam["rules"]}
    assert set(rules) == {BEAM_MIN_WIDTH, BEAM_MIN_DEPTH_300, BEAM_DEPTH_WIDTH_RATIO}
    assert all(item["closure_status"] == ClosureExecutionStatus.EXECUTED.value for item in rules.values())
    assert rules[BEAM_MIN_WIDTH]["check_result"]["status"] == "FAIL"
    assert rules[BEAM_MIN_DEPTH_300]["check_result"]["status"] == "OK"
    assert rules[BEAM_DEPTH_WIDTH_RATIO]["check_result"]["status"] == "OK"
    assert rules[BEAM_DEPTH_WIDTH_RATIO]["check_result"]["value"] == pytest.approx(600.0 / 249.0)
    assert beam["finding_count"] == 1
    assert beam["findings"][0]["source_kind"] == "CHECK_RESULT"
    assert beam["findings"][0]["source_status"] == "FAIL"


def test_missing_width_does_not_block_independent_depth_rule(tmp_path: Path) -> None:
    capture_path = tmp_path / "feature_snapshot.json"
    raw = _write_capture(capture_path, _snapshot(width=None, depth=600.0))
    capture = vs1.load_live_beam_capture_artifact(capture_path)
    epoch = vs1.build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=raw)
    run = vs1.run_live_beam_f0_slice(epoch=epoch, snapshot=capture.beam_snapshots[0])

    result_by_rule = {
        record.instance_id.rule_id.value: record.result
        for record in run.store.formal_results
    }
    closure_by_rule = {
        outcome.compiled_record_ref.rule_id.value: outcome
        for outcome in run.assessment.closure_outcomes
    }
    assert BEAM_MIN_WIDTH not in result_by_rule
    assert result_by_rule[BEAM_MIN_DEPTH_300].status.value == "OK"
    assert BEAM_DEPTH_WIDTH_RATIO not in result_by_rule
    assert closure_by_rule[BEAM_MIN_WIDTH].execution_status is ClosureExecutionStatus.NO_DATA
    assert closure_by_rule[BEAM_MIN_DEPTH_300].execution_status is ClosureExecutionStatus.EXECUTED
    assert closure_by_rule[BEAM_DEPTH_WIDTH_RATIO].execution_status is ClosureExecutionStatus.NO_DATA


def test_product_bytes_are_deterministic_for_identical_model_and_capture(tmp_path: Path) -> None:
    capture_path = tmp_path / "feature_snapshot.json"
    _write_capture(capture_path, _snapshot())
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    build_live_beam_geometry_f0_product_from_capture(
        model_path=MODEL_PATH,
        feature_snapshot_path=capture_path,
        output_path=first,
    )
    build_live_beam_geometry_f0_product_from_capture(
        model_path=MODEL_PATH,
        feature_snapshot_path=capture_path,
        output_path=second,
    )
    assert first.read_bytes() == second.read_bytes()


def test_vs1_production_module_excludes_legacy_authority_imports() -> None:
    source = inspect.getsource(vs1)
    for forbidden in (
        "MinimalCheckEngine",
        "runner_v2",
        "load_contracts",
        "check_catalog.yaml",
        "checks.yaml",
    ):
        assert forbidden not in source
