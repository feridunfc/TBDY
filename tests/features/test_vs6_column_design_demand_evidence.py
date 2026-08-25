from __future__ import annotations

import pytest

from tbdy_engine.features.column_design_demand_evidence import (
    ColumnDesignDemandEvidenceError,
    build_column_design_demand_evidence,
)


def _row(*, p: float = -1000.0, m2: float = 120.0, m3: float = -45.0) -> dict[str, object]:
    return {
        "Story": "+0.00",
        "Column": "C2",
        "UniqueName": "236",
        "OutputCase": "Crack_SeisX",
        "CaseType": "Combination",
        "StepType": "Max",
        "StepNumber": None,
        "Station": 0.0,
        "P": p,
        "M2": m2,
        "M3": m3,
        "Element": "1001",
        "ElemStation": 0.0,
    }


def test_vs6_epoch_fingerprints_moment_payload_not_only_axial_force():
    base = build_column_design_demand_evidence(
        model_fingerprint="model:test",
        rows=(_row(),),
        output_names=("Crack_SeisX",),
        reviewed_force_unit="kN",
        reviewed_moment_unit="kN-m",
    )
    changed_m2 = build_column_design_demand_evidence(
        model_fingerprint="model:test",
        rows=(_row(m2=121.0),),
        output_names=("Crack_SeisX",),
        reviewed_force_unit="kN",
        reviewed_moment_unit="kN-m",
    )
    changed_m3 = build_column_design_demand_evidence(
        model_fingerprint="model:test",
        rows=(_row(m3=-46.0),),
        output_names=("Crack_SeisX",),
        reviewed_force_unit="kN",
        reviewed_moment_unit="kN-m",
    )
    assert base.evidence_epoch_id != changed_m2.evidence_epoch_id
    assert base.evidence_epoch_id != changed_m3.evidence_epoch_id
    assert base.evidence_epoch_id.startswith("epoch:vs6-column-design-demand:sha256:")


def test_vs6_epoch_is_order_independent_for_exact_row_population():
    row_a = _row()
    row_b = dict(_row(p=-900.0, m2=-80.0, m3=30.0))
    row_b["Station"] = 4.45
    row_b["StepType"] = "Min"
    first = build_column_design_demand_evidence(
        model_fingerprint="model:test",
        rows=(row_a, row_b),
        output_names=("Crack_SeisX",),
        reviewed_force_unit="kN",
        reviewed_moment_unit="kN-m",
    )
    second = build_column_design_demand_evidence(
        model_fingerprint="model:test",
        rows=(row_b, row_a),
        output_names=("Crack_SeisX",),
        reviewed_force_unit="kN",
        reviewed_moment_unit="kN-m",
    )
    assert first.evidence_epoch_id == second.evidence_epoch_id


def test_vs6_design_demand_evidence_fails_closed_when_moment_payload_missing():
    row = _row()
    del row["M3"]
    with pytest.raises(ColumnDesignDemandEvidenceError, match="M3"):
        build_column_design_demand_evidence(
            model_fingerprint="model:test",
            rows=(row,),
            output_names=("Crack_SeisX",),
            reviewed_force_unit="kN",
            reviewed_moment_unit="kN-m",
        )
