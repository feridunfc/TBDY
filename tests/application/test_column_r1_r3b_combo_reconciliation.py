"""Offline signatures retain source truth without manufacturing stability states."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from tools import column_r1_r3b_combo_reconciliation as tool

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "docs/COLUMN_R1_R3B_RECONCILIATION_RECEIPT_2026-10-09.json"


def definition(name="numeric-authority", terms=(("G", 1.0),), children=(), combo_type=0):
    return {
        "name": name, "status": "PROVEN_FACTUAL_COMBO_DEFINITION",
        "combo_type_code": combo_type, "combo_type": tool.COMBO_TYPE_BY_CODE[combo_type],
        "constituents": [{"index": i, "cname_type_code": 1 if any(c["name"] == n for c in children) else 0,
            "cname_type": "LOAD_COMBO" if any(c["name"] == n for c in children) else "LOAD_CASE",
            "name": n, "scale_factor": f} for i, (n, f) in enumerate(terms)],
        "nested_combos": list(children), "raw_get_type_combo": repr([combo_type, 0]),
        "raw_get_case_list": repr(terms),
    }


def test_nested_linear_add_multiplies_factors_and_keeps_signed_duplicate_paths():
    child = definition("nested", (("S", .2), ("E", -.3)))
    raw = definition("outer", (("nested", .5), ("S", -.1), ("E", 1.0)), (child,))
    before = deepcopy(raw)
    assert tool.linear_signature(tool.decode_definition(raw)) == {"E": "0.85", "S": "0"}
    assert raw == before  # Raw acquisition evidence and graph aren't rewritten.


@pytest.mark.parametrize("factor", [1., 1.2, .9, .2, .5, -.3, -1.])
def test_distinct_concrete_steel_seismic_wind_and_sign_coefficients_remain_exact(factor):
    assert tool.linear_signature(tool.decode_definition(definition(terms=(("case", factor),)))) == {
        "case": format(tool.Decimal(str(factor)).normalize(), "f")}


@pytest.mark.parametrize("name", ["Ez-Ex+", "GQE", "WindDuplicate", "PureX"])
def test_names_do_not_change_numeric_signature_or_promote_a_physical_state(name):
    fact = tool.decode_definition(definition(name, (("EDZ", .3), ("RSY", .3), ("RSX", 1.))))
    assert tool.linear_signature(fact) == {"EDZ": "0.3", "RSX": "1", "RSY": "0.3"}
    assert not hasattr(fact, "state_semantics")


@pytest.mark.parametrize("kind", [1, 2, 3, 4])
def test_envelope_srss_range_and_absolute_add_never_become_linear_signatures(kind):
    from tbdy_engine.application.column_public_a5 import PublicA5CompositionError
    with pytest.raises(PublicA5CompositionError):
        tool.linear_signature(tool.decode_definition(definition(combo_type=kind)))


@pytest.mark.parametrize("bad_factor", [True, float("nan"), float("inf"), "0.3"])
def test_malformed_factors_fail_closed(bad_factor):
    with pytest.raises(ValueError, match="finite numeric"):
        tool.decode_definition(definition(terms=(("S", bad_factor),)))


@pytest.mark.parametrize("change", ["combo_type", "term_type", "missing_child", "extra_child", "status"])
def test_incomplete_or_mistyped_definition_graph_fails_closed(change):
    child = definition("child")
    raw = definition("outer", (("child", 1.),), (child,))
    if change == "combo_type": raw["combo_type"] = "SRSS"
    if change == "term_type": raw["constituents"][0]["cname_type"] = "LOAD_CASE"
    if change == "missing_child": raw["nested_combos"] = []
    if change == "extra_child": raw["nested_combos"].append(definition("unreferenced"))
    if change == "status": raw["status"] = "PARTIAL"
    with pytest.raises(ValueError): tool.decode_definition(raw)


def test_changed_preflight_bytes_fail_before_any_interpretation():
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        tool.verify_preflight_bytes(b'{"source_sha256_before":"FC09"}')


@pytest.mark.parametrize("guard", ["source_sha256_before", "source_sha256_after", "expected_source_sha256", "errors", "status"])
def test_source_immutability_and_factual_status_are_independent_guards(monkeypatch, guard):
    raw = {k: tool.CURRENT_SOURCE_SHA256 for k in ("source_sha256_before", "source_sha256_after", "expected_source_sha256")}
    raw.update(errors=[], status="PASS_NATIVE_PENDING_R0_REVIEW")
    raw[guard] = ["failure"] if guard == "errors" else "WRONG"
    source = json.dumps(raw).encode()
    monkeypatch.setattr(tool, "PREFLIGHT_SHA256", hashlib.sha256(source).hexdigest().upper())
    with pytest.raises(ValueError): tool.verify_preflight_bytes(source)


def test_repository_receipt_keeps_12_policy_equality_separate_from_real_snow_mismatch():
    receipt = json.loads(RECEIPT.read_text())
    selected = receipt["12_SELECTED_DESIGN_COMBO_RECONCILIATION"]
    assert selected["count"] == 12 and len(selected["rows"]) == 12
    assert all(x["unchanged_reviewed_policy"] == "MATCH" for x in selected["rows"])
    snow = receipt["SNOW_1.0_VS_0.2_DISPOSITION"]
    assert snow["status"] == "SOURCE_CORRECTION_REQUIRED"
    assert len(snow["rows"]) == 4
    assert all((x["actual_LC_S"], x["accepted_seismic_S"], x["difference"]) == ("1", "0.2", "0.8") for x in snow["rows"])
    assert snow["case"]["value"]["loads"][0]["scale_factor"] == 1.0
    assert snow["pattern"]["value"]["type_code"] == 7
    assert snow["policy_or_model_changed"] is False


def test_current_missing_rs_fields_do_not_become_direction_modal_or_concurrency_proofs():
    receipt = json.loads(RECEIPT.read_text())
    for name in ("RSX", "RSY"):
        record = receipt["FC09_FACTUAL_CASE_SIGNATURES"][name]
        assert record["fact"]["value"]["case_type_code"] == 4
        assert record["signature_status"] == "PARTIAL"
        assert set(record["not_captured"]) == set(tool.RS_FIELDS_NOT_CAPTURED)
    assert receipt["DIRECTIONAL_COMBINATION_LOCATION"]["double_100_30_excluded"] is False
    assert receipt["MODAL_COMBINATION_METHOD"] == "NOT_CAPTURED_IN_FC09_PREFLIGHT"
    assert receipt["EQ713_STABILITY_STATE_CAPABILITY"]["A17_142"].startswith("TRUTHFULLY_BLOCKED")
    assert receipt["EQ713_STABILITY_STATE_CAPABILITY"]["next_live_run_authorized"] is False
    assert receipt["PROTA_REFERENCE_SIGNATURES"]["supplied_80_row_reference"]["concrete_rows_9_40"]["Ey_fields"] == "INCOMPLETE_DO_NOT_RECONSTRUCT"


def test_edz_and_all_35_existing_dependency_graphs_are_retained():
    receipt = json.loads(RECEIPT.read_text())
    capture = receipt["FC09_FACTUAL_COMBO_SIGNATURES"]
    assert capture["count"] == len(capture["combos"]) == 35
    assert sum(x["selected_for_concrete_design"] for x in capture["combos"]) == 12
    names = {x["name"] for x in capture["combos"]}
    for combo in capture["combos"]:
        assert set(combo["nested_dependency_names"]) <= names
        if combo["combo_type"] != "LINEAR_ADD":
            assert combo["flattened_leaf_signature"] is None
    edz = receipt["EDZ_SOURCE_AND_FACTOR"]
    assert [x["scale_factor"] for x in edz["fact"]["value"]["loads"]] == [.351]*3
    assert edz["downward_effective_G_factor"] == "0.1053"
    assert edz["upward_effective_G_factor"] == "-0.1053"


def test_exact_external_receipt_and_9d7_inputs_reproduce_repository_computed_sections(monkeypatch):
    path = os.environ.get("COLUMN_R1_FC09_PREFLIGHT_TEST_PATH")
    inputs = os.environ.get("COLUMN_R1_ACCEPTED_INPUTS_TEST_PATH")
    if not path or not inputs:
        pytest.skip("Separately held exact preflight and reviewed bytes not supplied")
    import tools.column_r1_bblok_e1_reviewed_inputs as loader
    from tools.column_r1_bblok_fc09_reviewed_inputs import load_inputs
    monkeypatch.setattr(loader, "ACCEPTED_INPUTS", Path(inputs))
    _, deps = load_inputs()
    raw = Path(path).read_bytes()
    result = tool.reconcile(tool.verify_preflight_bytes(raw), deps["expected_combo_policy"])
    committed = json.loads(RECEIPT.read_text())
    assert all(committed[key] == value for key, value in result.items())
    assert Path(path).read_bytes() == raw
