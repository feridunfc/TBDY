from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.integration import live_seismic_response_f0 as seismic
from tbdy_engine.integration.live_seismic_response_f0 import (
    A1_TABLE,
    BASE_REACTIONS_TABLE,
    MODAL_TABLE,
    STORY_DRIFT_TABLE,
    build_seismic_authorities,
    capture_seismic_response,
    run_live_seismic_response_f0_pack,
)
from tbdy_engine.product.live_seismic_response_product import (
    BASE_REACTIONS_NOT_EVALUATED_REASON,
    PRODUCT_CONTRACT,
    STORY_DRIFT_NOT_EVALUATED_REASON,
    build_live_seismic_response_product,
)
from tbdy_engine.regulatory.seismic_response import A1_RULE_ID, MODAL_RULE_ID

MODEL_PATH = r"C:\Projects\TBDY\Kres.edb"


def _fetched(table_name: str, case_name: str, rows, *, capture_status=RuntimeCaptureStatus.FULL):
    return SimpleNamespace(
        table_name=table_name,
        parsed=SimpleNamespace(
            rows=tuple(dict(row) for row in rows),
            actual_table_name=table_name,
            debug={},
            fetch_status="FETCHED",
        ),
        capture_status=capture_status,
        display_selection={
            "preferred_output_case": case_name,
            "display_selection_success": True,
            "display_selection_selected_method": "SetLoadCasesSelectedForDisplay",
            "selection_scope": "VERIFIED_SUPERSET_SELECTION",
            "target_only_capture_claimed": False,
            "fetch_after_display_selection": True,
        },
    )


def _source_rows(*, modal_x=0.96, modal_y=0.97, a1_x=1.10, a1_y=1.25, drift=0.020, omit_modal_x=False, omit_exn_s1=False):
    modal_final = {"Case": "MODAL", "Mode": 2, "SumUY": modal_y}
    if not omit_modal_x:
        modal_final["SumUX"] = modal_x
    rows = {
        (MODAL_TABLE, "MODAL"): [
            {"Case": "MODAL", "Mode": 1, "SumUX": min(modal_x, 0.70), "SumUY": min(modal_y, 0.72)},
            modal_final,
        ],
    }
    for case in ("EXP", "EXN"):
        a1_rows = [] if (case == "EXN" and omit_exn_s1) else [{"OutputCase": case, "Story": "S1", "Direction": "X", "Ratio": a1_x}]
        rows[(A1_TABLE, case)] = a1_rows
        rows[(STORY_DRIFT_TABLE, case)] = [{"OutputCase": case, "Story": "S1", "Direction": "X", "Drift": drift}]
        rows[(BASE_REACTIONS_TABLE, case)] = [{"OutputCase": case, "FX": 100.0, "FY": 10.0}]
    for case in ("EYP", "EYN"):
        rows[(A1_TABLE, case)] = [{"OutputCase": case, "Story": "S1", "Direction": "Y", "Ratio": a1_y}]
        rows[(STORY_DRIFT_TABLE, case)] = [{"OutputCase": case, "Story": "S1", "Direction": "Y", "Drift": drift}]
        rows[(BASE_REACTIONS_TABLE, case)] = [{"OutputCase": case, "FX": 20.0, "FY": 120.0}]
    return rows


def _capture(monkeypatch, *, rows=None, reverse=False):
    rows = rows or _source_rows()

    def fake_fetch(database_tables, table_name, *, preferred_output_case, max_rows=None):
        assert max_rows is None
        selected = list(rows.get((table_name, preferred_output_case), []))
        if reverse:
            selected.reverse()
        return _fetched(table_name, preferred_output_case, selected)

    monkeypatch.setattr(seismic, "fetch_display_table_for_output", fake_fetch)
    return capture_seismic_response(
        database_tables=object(),
        model_path=MODEL_PATH,
        modal_case="MODAL",
        a1_x_cases=("EXP", "EXN"),
        a1_y_cases=("EYP", "EYN"),
        unit_provenance={"present_force_unit": "kN"},
    )


def _product(tmp_path: Path, capture, *, modal_applies=True, modal_basis="verified", a1_basis="verified", name="product.json"):
    return build_live_seismic_response_product(
        capture=capture,
        modal_4812_applies=modal_applies,
        modal_case_basis_verified=modal_basis,
        a1_eccentricity_basis=a1_basis,
        output_path=tmp_path / name,
        capture_path=tmp_path / (name + ".capture.json"),
    )


def _formal_by_rule(result):
    return {
        (row["rule_id"], row["direction"]): row["check_result"]
        for row in result.payload["results"]
    }


def test_scenario_A_healthy_modal_and_a1_warning(monkeypatch, tmp_path):
    result = _product(tmp_path, _capture(monkeypatch))
    formal = _formal_by_rule(result)
    assert formal[(MODAL_RULE_ID.value, "X")]["status"] == "OK"
    assert formal[(MODAL_RULE_ID.value, "Y")]["status"] == "OK"
    assert formal[(A1_RULE_ID.value, "X")]["status"] == "OK"
    assert formal[(A1_RULE_ID.value, "X")]["messages"] == ["A1_NOT_PRESENT"]
    assert formal[(A1_RULE_ID.value, "Y")]["status"] == "WARNING"
    assert formal[(A1_RULE_ID.value, "Y")]["messages"] == ["A1_PRESENT"]
    assert result.finding_count == 1
    assert result.payload["findings"][0]["source_status"] == "WARNING"
    assert result.payload["domains"]["story_drift"]["check_result_count"] == 0
    assert result.payload["domains"]["base_reactions"]["check_result_count"] == 0
    assert result.payload["full_tbdy_compliance_status"] == "NOT_EVALUATED"


def test_scenario_B_modal_deficiency_is_valid_execution(monkeypatch, tmp_path):
    capture = _capture(monkeypatch, rows=_source_rows(modal_x=0.94, a1_y=1.10))
    result = _product(tmp_path, capture)
    formal = _formal_by_rule(result)
    assert formal[(MODAL_RULE_ID.value, "X")]["status"] == "FAIL"
    assert formal[(MODAL_RULE_ID.value, "Y")]["status"] == "OK"
    fail_findings = [item for item in result.payload["findings"] if item["source_status"] == "FAIL"]
    assert len(fail_findings) == 1
    assert result.payload["structural_assessment_status"] == "COMPLETE"


def test_scenario_C_modal_missing_x_blocks_only_x(monkeypatch, tmp_path):
    capture = _capture(monkeypatch, rows=_source_rows(omit_modal_x=True, a1_y=1.10))
    result = _product(tmp_path, capture)
    rows = {(item["rule_id"], item["direction"]): item for item in result.payload["results"]}
    assert rows[(MODAL_RULE_ID.value, "X")]["check_result"] is None
    assert rows[(MODAL_RULE_ID.value, "X")]["closure_status"] == "NO_DATA"
    assert rows[(MODAL_RULE_ID.value, "Y")]["check_result"]["status"] == "OK"
    assert rows[(A1_RULE_ID.value, "X")]["check_result"] is not None
    assert rows[(A1_RULE_ID.value, "Y")]["check_result"] is not None


def test_scenario_D_a1_basis_unknown_blocks_all_a1_but_keeps_facts(monkeypatch, tmp_path):
    result = _product(tmp_path, _capture(monkeypatch), a1_basis="unknown")
    a1_rows = [item for item in result.payload["results"] if item["rule_id"] == A1_RULE_ID.value]
    modal_rows = [item for item in result.payload["results"] if item["rule_id"] == MODAL_RULE_ID.value]
    assert all(item["closure_status"] == "BLOCKED" and item["check_result"] is None for item in a1_rows)
    assert all(item["check_result"] is not None for item in modal_rows)
    assert result.payload["domains"]["torsional_irregularity_a1"]["factual_row_count"] > 0


def test_scenario_E_partial_a1_case_set_does_not_use_optimistic_subset(monkeypatch, tmp_path):
    capture = _capture(monkeypatch, rows=_source_rows(omit_exn_s1=True, a1_y=1.10))
    result = _product(tmp_path, capture)
    row = next(item for item in result.payload["results"] if item["rule_id"] == A1_RULE_ID.value and item["direction"] == "X")
    assert row["check_result"] is None
    assert row["closure_status"] == "NO_DATA"
    y = next(item for item in result.payload["results"] if item["rule_id"] == A1_RULE_ID.value and item["direction"] == "Y")
    assert y["check_result"]["status"] == "OK"


def test_scenario_F_a1_121_is_warning_never_fail(monkeypatch, tmp_path):
    result = _product(tmp_path, _capture(monkeypatch, rows=_source_rows(a1_x=1.21, a1_y=1.10)))
    row = next(item for item in result.payload["results"] if item["rule_id"] == A1_RULE_ID.value and item["direction"] == "X")
    assert row["check_result"]["status"] == "WARNING"
    assert row["check_result"]["messages"] == ["A1_PRESENT"]
    assert all(
        item["check_result"] is None or item["check_result"]["status"] != "FAIL"
        for item in result.payload["results"]
        if item["rule_id"] == A1_RULE_ID.value
    )
    assert any(item["source_status"] == "WARNING" for item in result.payload["findings"])


def test_scenario_G_drift_0020_is_factual_only(monkeypatch, tmp_path):
    result = _product(tmp_path, _capture(monkeypatch, rows=_source_rows(drift=0.020, a1_y=1.10)))
    domain = result.payload["domains"]["story_drift"]
    assert domain["factual_row_count"] > 0
    assert any(row["normalized_numeric_values"].get("Drift") == 0.020 for row in domain["factual_rows"])
    assert domain["regulatory_support_status"] == "NOT_EVALUATED"
    assert domain["reason"] == STORY_DRIFT_NOT_EVALUATED_REASON
    assert domain["check_result_count"] == 0


def test_scenario_H_base_reactions_are_factual_only(monkeypatch, tmp_path):
    result = _product(tmp_path, _capture(monkeypatch, rows=_source_rows(a1_y=1.10)))
    domain = result.payload["domains"]["base_reactions"]
    assert domain["factual_row_count"] > 0
    assert domain["regulatory_support_status"] == "NOT_EVALUATED"
    assert domain["reason"] == BASE_REACTIONS_NOT_EVALUATED_REASON
    assert domain["check_result_count"] == 0


def test_scenario_I_raw_order_and_regulatory_context_determinism(monkeypatch, tmp_path):
    first_capture = _capture(monkeypatch, reverse=False)
    first = _product(tmp_path, first_capture, name="a.json")
    second_capture = _capture(monkeypatch, reverse=True)
    second = _product(tmp_path, second_capture, name="b.json")
    assert first_capture.raw_bytes == second_capture.raw_bytes
    assert first_capture.epoch.source_fingerprint == second_capture.epoch.source_fingerprint
    assert first_capture.epoch.epoch_id == second_capture.epoch.epoch_id
    assert [item.authority_id for item in build_seismic_authorities(first_capture)] == [item.authority_id for item in build_seismic_authorities(second_capture)]
    assert first.payload["registry_version"] == second.payload["registry_version"]
    assert first.payload["plan_identity"] == second.payload["plan_identity"]
    assert first.payload["results"] == second.payload["results"]
    assert first.payload["findings"] == second.payload["findings"]
    assert first.output_path.read_bytes() == second.output_path.read_bytes()

    unknown = _product(tmp_path, first_capture, a1_basis="unknown", name="c.json")
    assert unknown.payload["model_fingerprint"] == first.payload["model_fingerprint"]
    assert unknown.payload["capture_epoch"] == first.payload["capture_epoch"]
    assert unknown.payload["plan_identity"] != first.payload["plan_identity"]


def test_scenario_J_legacy_authority_is_excluded_from_new_production_files():
    root = Path(__file__).resolve().parents[2]
    strict_paths = (
        root / "tbdy_engine/integration/live_seismic_response_f0.py",
        root / "tbdy_engine/product/live_seismic_response_product.py",
        root / "tools/run_live_seismic_response_product.py",
    )
    forbidden = (
        "product_reports",
        "MODAL_LIMIT_CONTRACT_ID",
        "STORY_DRIFT_LIMIT_CONTRACT_ID",
        "TORSION_A1_LIMIT_CONTRACT_ID",
        "MAX_STORY_DRIFT_RATIO",
        "MAX_TORSION_A1_COEFFICIENT",
        "NAME_PATTERN_FALLBACK",
        "build_modal_mass_check_result_file",
        "build_story_drift_check_result_file",
        "build_torsional_irregularity_a1_check_result_file",
        "MinimalCheckEngine",
        "EngineContractLoader",
        "CheckResult(",
        "Finding(",
    )
    for path in strict_paths:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"forbidden legacy/direct authority token {token!r} in {path}"

    rule_text = (root / "tbdy_engine/regulatory/seismic_response.py").read_text(encoding="utf-8")
    for token in forbidden[:-2]:
        assert token not in rule_text
    assert PRODUCT_CONTRACT == "VS3_LIVE_SEISMIC_RESPONSE_PRODUCT_V1"


def test_formal_capture_accepts_only_full_status_through_production_boundary(monkeypatch):
    capture = _capture(monkeypatch)
    assert capture.raw_bytes
    diagnostics = capture.payload["capture_diagnostics"]
    assert diagnostics
    assert all(item["capture_status"] == RuntimeCaptureStatus.FULL.value for item in diagnostics)


@pytest.mark.parametrize(
    "blocked_table",
    (MODAL_TABLE, A1_TABLE, STORY_DRIFT_TABLE, BASE_REACTIONS_TABLE),
)
@pytest.mark.parametrize(
    "capture_status",
    (
        RuntimeCaptureStatus.TRUNCATED,
        RuntimeCaptureStatus.PARTIAL,
        RuntimeCaptureStatus.SAMPLED,
        "UNKNOWN",
    ),
)
def test_formal_capture_rejects_every_non_full_selected_table_through_production_boundary(
    monkeypatch,
    blocked_table,
    capture_status,
):
    rows = _source_rows()

    def fake_fetch(database_tables, table_name, *, preferred_output_case, max_rows=None):
        assert max_rows is None
        selected = rows.get((table_name, preferred_output_case), [])
        status = capture_status if table_name == blocked_table else RuntimeCaptureStatus.FULL
        return _fetched(table_name, preferred_output_case, selected, capture_status=status)

    monkeypatch.setattr(seismic, "fetch_display_table_for_output", fake_fetch)
    with pytest.raises(seismic.LiveSeismicEvidenceConflictError) as exc:
        capture_seismic_response(
            database_tables=object(),
            model_path=MODEL_PATH,
            modal_case="MODAL",
            a1_x_cases=("EXP", "EXN"),
            a1_y_cases=("EYP", "EYN"),
            unit_provenance={"present_force_unit": "kN"},
        )
    assert exc.value.status == seismic.BLOCKED_BY_LIVE_SEISMIC_EVIDENCE_CONFLICT
    assert "not FULL" in str(exc.value)


LIVE_MODAL_CASE = "Modal"
LIVE_X_CASES = ("~Static+EccRSX", "~Static-EccRSX")
LIVE_Y_CASES = ("~Static+EccRSY", "~Static-EccRSY")


def _live_superset_source_rows(*, target_y_eta=1.10, unrelated_y_eta=5.0, missing_y_minus_target=False):
    rows = {
        (MODAL_TABLE, LIVE_MODAL_CASE): [
            {"Case": "Crack_SeisX", "Mode": 99, "SumUX": 1.0, "SumUY": 1.0},
            {"Case": LIVE_MODAL_CASE, "Mode": 1, "SumUX": 0.70, "SumUY": 0.72},
            {"Case": LIVE_MODAL_CASE, "Mode": 2, "SumUX": 0.96, "SumUY": 0.97},
        ]
    }
    for case in (*LIVE_X_CASES, *LIVE_Y_CASES):
        direction = "X" if case in LIVE_X_CASES else "Y"
        eta = 1.10 if direction == "X" else target_y_eta
        target_a1 = {"OutputCase": case, "Story": "S1", "Direction": direction, "Ratio": eta}
        if case == "~Static-EccRSY":
            a1_rows = [
                {"OutputCase": "Crack_SeisX", "Story": "S1", "Direction": "X", "Ratio": unrelated_y_eta},
                {"OutputCase": "Duct_SeisY", "Story": "S1", "Direction": "Y", "Ratio": 1.05},
            ]
            if not missing_y_minus_target:
                a1_rows.append(target_a1)
        else:
            a1_rows = [target_a1]
        rows[(A1_TABLE, case)] = a1_rows
        rows[(STORY_DRIFT_TABLE, case)] = [
            {"OutputCase": "Crack_SeisX", "Story": "S1", "Direction": direction, "Drift": 0.50},
            {"OutputCase": case, "Story": "S1", "Direction": direction, "Drift": 0.020},
        ]
        rows[(BASE_REACTIONS_TABLE, case)] = [
            {"OutputCase": "Crack_SeisX", "FX": 9999.0, "FY": 9999.0},
            {"OutputCase": case, "FX": 100.0 if direction == "X" else 20.0, "FY": 10.0 if direction == "X" else 120.0},
        ]
    return rows


def _live_superset_capture(monkeypatch, *, rows=None, reverse=False):
    rows = rows or _live_superset_source_rows()

    def fake_fetch(database_tables, table_name, *, preferred_output_case, max_rows=None):
        assert max_rows is None
        selected = list(rows.get((table_name, preferred_output_case), []))
        if reverse:
            selected.reverse()
        return _fetched(table_name, preferred_output_case, selected)

    monkeypatch.setattr(seismic, "fetch_display_table_for_output", fake_fetch)
    return capture_seismic_response(
        database_tables=object(),
        model_path=MODEL_PATH,
        modal_case=LIVE_MODAL_CASE,
        a1_x_cases=LIVE_X_CASES,
        a1_y_cases=LIVE_Y_CASES,
        unit_provenance={"present_force_unit": "kN"},
    )


def _isolation_diag(capture, table_name, case_name):
    return next(
        item
        for item in capture.payload["capture_diagnostics"]
        if item["source_table"] == table_name and item["capture_case"] == case_name
    )


def test_live_superset_a1_retains_only_exact_requested_output_case(monkeypatch):
    capture = _live_superset_capture(monkeypatch)
    rows = [
        row
        for row in capture.payload["a1"]["by_direction"]["Y"]["rows"]
        if row["capture_case"] == "~Static-EccRSY"
    ]
    assert len(rows) == 1
    assert rows[0]["factual_output_case"] == "~Static-EccRSY"
    assert rows[0]["output_identity_field"] == "OutputCase"
    assert rows[0]["raw_values"]["OutputCase"] == "~Static-EccRSY"
    diag = _isolation_diag(capture, A1_TABLE, "~Static-EccRSY")
    assert diag["fetched_superset_row_count"] == 3
    assert diag["exact_target_row_count"] == 1
    assert diag["excluded_non_target_row_count"] == 2
    assert diag["output_identity_field"] == "OutputCase"
    assert diag["target_only_capture_proven"] is True


def test_unrelated_high_a1_ratio_cannot_create_warning(monkeypatch, tmp_path):
    capture = _live_superset_capture(
        monkeypatch,
        rows=_live_superset_source_rows(target_y_eta=1.10, unrelated_y_eta=5.0),
    )
    result = _product(tmp_path, capture)
    row = next(
        item for item in result.payload["results"]
        if item["rule_id"] == A1_RULE_ID.value and item["direction"] == "Y"
    )
    assert row["check_result"]["status"] == "OK"
    assert row["check_result"]["value"] == 1.10


def test_target_high_a1_ratio_creates_warning_even_when_unrelated_is_low(monkeypatch, tmp_path):
    capture = _live_superset_capture(
        monkeypatch,
        rows=_live_superset_source_rows(target_y_eta=1.30, unrelated_y_eta=1.05),
    )
    result = _product(tmp_path, capture)
    row = next(
        item for item in result.payload["results"]
        if item["rule_id"] == A1_RULE_ID.value and item["direction"] == "Y"
    )
    assert row["check_result"]["status"] == "WARNING"
    assert row["check_result"]["value"] == 1.30


def test_required_a1_case_with_only_unrelated_superset_rows_is_no_data(monkeypatch, tmp_path):
    capture = _live_superset_capture(
        monkeypatch,
        rows=_live_superset_source_rows(missing_y_minus_target=True),
    )
    assert _isolation_diag(capture, A1_TABLE, "~Static-EccRSY")["exact_target_row_count"] == 0
    result = _product(tmp_path, capture)
    row = next(
        item for item in result.payload["results"]
        if item["rule_id"] == A1_RULE_ID.value and item["direction"] == "Y"
    )
    assert row["check_result"] is None
    assert row["closure_status"] == "NO_DATA"


def test_story_drifts_superset_retains_only_exact_requested_output_case(monkeypatch):
    capture = _live_superset_capture(monkeypatch)
    rows = [
        row
        for row in capture.payload["story_drift"]["rows"]
        if row["capture_case"] == "~Static-EccRSY"
    ]
    assert len(rows) == 1
    assert rows[0]["factual_output_case"] == "~Static-EccRSY"
    assert rows[0]["raw_values"]["OutputCase"] == "~Static-EccRSY"
    assert _isolation_diag(capture, STORY_DRIFT_TABLE, "~Static-EccRSY")["excluded_non_target_row_count"] == 1


def test_base_reactions_superset_retains_only_exact_requested_output_case(monkeypatch):
    capture = _live_superset_capture(monkeypatch)
    rows = [
        row
        for row in capture.payload["base_reactions"]["rows"]
        if row["capture_case"] == "~Static-EccRSY"
    ]
    assert len(rows) == 1
    assert rows[0]["factual_output_case"] == "~Static-EccRSY"
    assert rows[0]["raw_values"]["OutputCase"] == "~Static-EccRSY"
    assert _isolation_diag(capture, BASE_REACTIONS_TABLE, "~Static-EccRSY")["excluded_non_target_row_count"] == 1


def test_modal_superset_retains_only_exact_modal_case_using_case_identity(monkeypatch):
    capture = _live_superset_capture(monkeypatch)
    rows = capture.payload["modal"]["rows"]
    assert len(rows) == 2
    assert all(row["factual_output_case"] == LIVE_MODAL_CASE for row in rows)
    assert all(row["output_identity_field"] == "Case" for row in rows)
    assert all(row["raw_values"]["Case"] == LIVE_MODAL_CASE for row in rows)
    diag = _isolation_diag(capture, MODAL_TABLE, LIVE_MODAL_CASE)
    assert diag["fetched_superset_row_count"] == 3
    assert diag["exact_target_row_count"] == 2
    assert diag["excluded_non_target_row_count"] == 1
    assert diag["output_identity_field"] == "Case"
    assert diag["target_only_capture_proven"] is True


@pytest.mark.parametrize(
    "table_name, case_name, identity_field",
    (
        (MODAL_TABLE, LIVE_MODAL_CASE, "Case"),
        (A1_TABLE, LIVE_X_CASES[0], "OutputCase"),
        (STORY_DRIFT_TABLE, LIVE_X_CASES[0], "OutputCase"),
        (BASE_REACTIONS_TABLE, LIVE_X_CASES[0], "OutputCase"),
    ),
)
def test_nonempty_fetched_row_without_factual_case_identity_fails_closed(
    monkeypatch, table_name, case_name, identity_field
):
    rows = _live_superset_source_rows()
    selected = [dict(row) for row in rows[(table_name, case_name)]]
    selected[0].pop(identity_field, None)
    rows[(table_name, case_name)] = selected
    with pytest.raises(seismic.LiveSeismicEvidenceConflictError) as exc:
        _live_superset_capture(monkeypatch, rows=rows)
    assert exc.value.status == seismic.BLOCKED_BY_LIVE_SEISMIC_EVIDENCE_CONFLICT
    assert "output-case identity" in str(exc.value)


def test_superset_reordering_is_deterministic_after_exact_target_isolation(monkeypatch, tmp_path):
    rows = _live_superset_source_rows(target_y_eta=1.10, unrelated_y_eta=5.0)
    first_capture = _live_superset_capture(monkeypatch, rows=rows, reverse=False)
    first = _product(tmp_path, first_capture, name="superset-a.json")
    second_capture = _live_superset_capture(monkeypatch, rows=rows, reverse=True)
    second = _product(tmp_path, second_capture, name="superset-b.json")
    assert first_capture.raw_bytes == second_capture.raw_bytes
    assert first_capture.epoch.source_fingerprint == second_capture.epoch.source_fingerprint
    assert first_capture.epoch.epoch_id == second_capture.epoch.epoch_id
    assert [item.authority_id for item in build_seismic_authorities(first_capture)] == [
        item.authority_id for item in build_seismic_authorities(second_capture)
    ]
    assert first.payload["results"] == second.payload["results"]
    assert first.payload["findings"] == second.payload["findings"]
    assert first.output_path.read_bytes() == second.output_path.read_bytes()
