from __future__ import annotations

import json
from pathlib import Path

from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.checks.dry_run import C11_CHECK_DEFINITIONS
from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.coverage.models import CoverageRow
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.resolver.live_smoke import C8LiveFeatureResolverSmoke
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus


def _modal_table(rows):
    return CanonicalTable(
        table_key="modal_participating_mass",
        actual_table_name="Modal Participating Mass Ratios",
        columns=("Mode", "Case", "SumUX", "SumUY"),
        rows=tuple(dict(row) for row in rows),
        units={},
        source="C11_1_TEST_FIXTURE",
    )


def _resolver(rows):
    return C8LiveFeatureResolverSmoke(load_contracts(), {"modal_participating_mass": _modal_table(rows)})


def _global_snapshot(ux: float, uy: float) -> FeatureSnapshot:
    def fv(name: str, value: float) -> FeatureValue:
        return FeatureValue(
            feature_name=name,
            value=value,
            unit="ratio",
            semantic_role="MODAL_CUMULATIVE_PARTICIPATION",
            status=FeatureValueStatus.RESOLVED,
            evidence=[
                FeatureEvidence(
                    evidence_status=FeatureEvidenceStatus.FULL,
                    source_table="modal_participating_mass",
                    actual_table_name="Modal Participating Mass Ratios",
                    source_column="SumUX" if name.endswith("ux") else "SumUY",
                    source_row={"aggregation_method": "max_cumulative", "mode_count": 2},
                    raw_value=value,
                    normalized_value=value,
                    unit="ratio",
                    resolver="c8_3_live_geometry_resolver",
                )
            ],
        )

    return FeatureSnapshot(
        component_type="global",
        component_id="GLOBAL",
        identity={"component": "GLOBAL"},
        features={"modal_sum_ux": fv("modal_sum_ux", ux), "modal_sum_uy": fv("modal_sum_uy", uy)},
    )


def _runnable_modal_row() -> CoverageRow:
    return CoverageRow(
        check_id="modal_mass_participation",
        component_type="global",
        component_id="GLOBAL",
        required_features=("modal_sum_ux", "modal_sum_uy"),
        resolved_features=("modal_sum_ux", "modal_sum_uy"),
        coverage_status="RUNNABLE",
        evidence_status="FULL",
        reason="C11.1 modal test fixture",
    )


def _run_modal_check(ux: float, uy: float):
    engine = MinimalCheckEngine(C11_CHECK_DEFINITIONS)
    return engine.run_check("modal_mass_participation", _global_snapshot(ux, uy), _runnable_modal_row())


def test_modal_sum_aggregation_uses_max_cumulative_not_mode_10():
    resolver = _resolver(
        [
            {"Mode": 10, "Case": "Modal", "SumUX": 0.7235, "SumUY": 0.7503},
            {"Mode": 53, "Case": "Modal", "SumUX": 0.9001, "SumUY": 0.9100},
            {"Mode": 65, "Case": "Modal", "SumUX": 0.9999, "SumUY": 0.9500},
            {"Mode": 100, "Case": "Modal", "SumUX": 0.9998, "SumUY": 0.9999},
        ]
    )
    snapshot = resolver.build_global_snapshot()
    assert snapshot.features["modal_sum_ux"].value == 0.9999
    assert snapshot.features["modal_sum_uy"].value == 0.9999


def test_modal_mass_check_ok_when_later_modes_exceed_90():
    resolver = _resolver(
        [
            {"Mode": 10, "Case": "Modal", "SumUX": 0.7235, "SumUY": 0.7503},
            {"Mode": 100, "Case": "Modal", "SumUX": 0.9999, "SumUY": 0.9999},
        ]
    )
    snapshot = resolver.build_global_snapshot()
    result = MinimalCheckEngine(C11_CHECK_DEFINITIONS).run_check("modal_mass_participation", snapshot, _runnable_modal_row())
    assert result.status.value == "OK"
    assert result.value >= 0.90


def test_modal_mass_false_fail_regression():
    old_mode_10_result = _run_modal_check(0.7235, 0.7503)
    assert old_mode_10_result.status.value == "FAIL"

    resolver = _resolver(
        [
            {"Mode": 10, "Case": "Modal", "SumUX": 0.7235, "SumUY": 0.7503},
            {"Mode": 100, "Case": "Modal", "SumUX": 0.9999, "SumUY": 0.9999},
        ]
    )
    fixed_snapshot = resolver.build_global_snapshot()
    fixed_result = MinimalCheckEngine(C11_CHECK_DEFINITIONS).run_check("modal_mass_participation", fixed_snapshot, _runnable_modal_row())
    assert fixed_result.status.value == "OK"


def test_modal_evidence_records_selected_modes_and_aggregation_method():
    snapshot = _resolver(
        [
            {"Mode": 10, "Case": "Modal", "SumUX": 0.7235, "SumUY": 0.7503},
            {"Mode": 65, "Case": "Modal", "SumUX": 0.9999, "SumUY": 0.9500},
            {"Mode": 100, "Case": "Modal", "SumUX": 0.9998, "SumUY": 0.9999},
        ]
    ).build_global_snapshot()
    ux_row = snapshot.features["modal_sum_ux"].evidence[0].source_row
    uy_row = snapshot.features["modal_sum_uy"].evidence[0].source_row
    assert ux_row["aggregation_method"] == "max_cumulative"
    assert ux_row["selected_mode_for_ux"] == 65
    assert uy_row["selected_mode_for_uy"] == 100
    assert ux_row["mode_count"] == 3
    assert any(d.code.value == "MODAL_AGGREGATION_MAX_CUMULATIVE_USED" for d in snapshot.features["modal_sum_ux"].diagnostics)


def test_modal_sum_aggregation_handles_unsorted_rows():
    snapshot = _resolver(
        [
            {"Mode": 100, "Case": "Modal", "SumUX": 0.9998, "SumUY": 0.9999},
            {"Mode": 10, "Case": "Modal", "SumUX": 0.7235, "SumUY": 0.7503},
            {"Mode": 65, "Case": "Modal", "SumUX": 0.9999, "SumUY": 0.9500},
        ]
    ).build_global_snapshot()
    assert snapshot.features["modal_sum_ux"].value == 0.9999
    assert snapshot.features["modal_sum_uy"].value == 0.9999


def test_modal_sum_missing_column_blocks_feature():
    table = CanonicalTable(
        table_key="modal_participating_mass",
        actual_table_name="Modal Participating Mass Ratios",
        columns=("Mode", "Case", "UX", "UY"),
        rows=({"Mode": 1, "Case": "Modal", "UX": 0.1, "UY": 0.2},),
        units={},
        source="C11_1_TEST_FIXTURE",
    )
    snapshot = C8LiveFeatureResolverSmoke(load_contracts(), {"modal_participating_mass": table}).build_global_snapshot()
    assert snapshot.features["modal_sum_ux"].status in {FeatureValueStatus.PARTIAL, FeatureValueStatus.MISSING}
    assert any(d.code.value == "MODAL_SUM_COLUMN_MISSING" for d in snapshot.features["modal_sum_ux"].diagnostics)


def test_modal_table_empty_blocks_check():
    snapshot = _resolver([]).build_global_snapshot()
    result = MinimalCheckEngine(C11_CHECK_DEFINITIONS).run_check("modal_mass_participation", snapshot, _runnable_modal_row())
    assert result.status.value != "OK"


def test_c11_modal_check_uses_controlling_min_of_ux_uy():
    result = _run_modal_check(0.95, 0.88)
    assert result.value == 0.88
    assert result.status.value == "FAIL"


def test_c11_modal_check_passes_when_both_ux_uy_ge_90():
    result = _run_modal_check(0.91, 0.92)
    assert result.value == 0.91
    assert result.status.value == "OK"


def test_no_checkengine_boundary_change(tmp_path):
    # C8 feature resolution can aggregate modal rows without creating a CheckResult.
    global_snapshot = _resolver([{"Mode": 100, "Case": "Modal", "SumUX": 0.9999, "SumUY": 0.9999}]).build_global_snapshot()
    serialized_snapshot = json.dumps(global_snapshot.as_dict())
    assert "CheckResult" not in serialized_snapshot

    # C11 dry-run remains the only place where a CheckResult is emitted.
    result = _run_modal_check(0.9999, 0.9999)
    assert result.as_dict()["check_id"] == "modal_mass_participation"
