"""Offline FC09 signature reconciliation, never a result/state qualification.

Read the exact accepted preflight bytes; reuse the existing combo mathematics
and PUBLIC-A5 flatten owners. No ETABS capability, engineering-rule mutation,
modal force aggregation, or READY promotion is introduced here.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tbdy_engine.application.column_public_a5 import _flatten_combo
from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    neutral_combo_definition, normalized_combo_definition_fingerprint,
)
from tbdy_engine.providers.etabs_combo_definition_provider import (
    CNAME_TYPE_BY_CODE, COMBO_TYPE_BY_CODE,
    EtabsComboConstituentEvidence, EtabsComboDefinitionEvidence,
)
from tools.column_r1_bblok_fc09_reviewed_inputs import CURRENT_SOURCE_SHA256

PREFLIGHT_SHA256 = "79A7BCA0DD50F42B6D9852D2ED56DFC03D0A1CDB40A1C534EA7071F6E8C4CE00"
RS_FIELDS_NOT_CAPTURED = (
    "modal_case", "loads_U1_U2_U3", "functions", "scales", "coordinate_systems",
    "angles", "modal_combination_method", "directional_combination_method",
    "damping", "eccentricity",
)


def decode_definition(value):
    """Rehydrate the preflight's lossless DTO serialization, not raw COM."""
    if value["status"] != "PROVEN_FACTUAL_COMBO_DEFINITION":
        raise ValueError("combo capture is not factual/complete")
    if COMBO_TYPE_BY_CODE[value["combo_type_code"]] != value["combo_type"]:
        raise ValueError("combo type code/semantic mismatch")
    terms = []
    for item in value["constituents"]:
        if CNAME_TYPE_BY_CODE[item["cname_type_code"]] != item["cname_type"]:
            raise ValueError("constituent type code/semantic mismatch")
        factor = item["scale_factor"]
        if isinstance(factor, bool) or not isinstance(factor, (int, float)) or not math.isfinite(factor):
            raise ValueError("factor must be finite numeric")
        terms.append(EtabsComboConstituentEvidence(**item))
    result = EtabsComboDefinitionEvidence(
        name=value["name"], combo_type_code=value["combo_type_code"],
        combo_type=value["combo_type"], constituents=tuple(terms),
        nested_combos=tuple(decode_definition(x) for x in value["nested_combos"]),
        raw_get_type_combo=value["raw_get_type_combo"],
        raw_get_case_list=value["raw_get_case_list"],
    )
    # Canonical owner checks exact nested dependency identities/completeness.
    neutral_combo_definition(result)
    return result


def linear_signature(definition):
    """Numeric leaf signature; preserve signed terms, don't qualify states."""
    _, leaves = _flatten_combo(definition)
    totals = {}
    for name, factor in leaves:
        totals[name] = totals.get(name, Decimal(0)) + Decimal(str(factor))
    return {name: format(value.normalize(), "f") for name, value in sorted(totals.items())}


def verify_preflight_bytes(source):
    if hashlib.sha256(source).hexdigest().upper() != PREFLIGHT_SHA256:
        raise ValueError("exact FC09 preflight SHA256 mismatch")
    receipt = json.loads(source)
    if any(receipt[key] != CURRENT_SOURCE_SHA256 for key in (
        "source_sha256_before", "source_sha256_after", "expected_source_sha256",
    )):
        raise ValueError("protected source identity/immutability mismatch")
    if receipt["errors"] or receipt["status"] != "PASS_NATIVE_PENDING_R0_REVIEW":
        raise ValueError("preflight did not pass its factual acquisition")
    return receipt


def _fact(receipt, key):
    entry = receipt["r0_facts"][key]
    if entry["status"] != "CAPTURED" or entry["context_refs"] != receipt["r0_context_refs"]:
        raise ValueError(f"fact not captured in exact context: {key}")
    return entry


def reconcile(receipt, policy):
    """Reconcile verified capture mathematics against the unchanged policy.

    Policy equality is separate from the supervisor's accepted TBDY template:
    the factual Snow discrepancy below must not be erased by 12/12 equality.
    """
    selection = _fact(receipt, "selected_concrete_design_combos")
    population = selection["value"]
    selected = population["rows"]
    identities = [(x["combo_type"], x["combo_name"]) for x in selected]
    if population["capture_status"] != "FULL" or population["row_count_reported"] != 12 or len(identities) != 12 or len(set(identities)) != 12:
        raise ValueError("exact 12 selected-combo denominator required")
    if set(identities) != set(policy.identities):
        raise ValueError("selected identity population differs from reviewed policy")
    definitions = _fact(receipt, "all_combo_definitions")
    decoded = tuple(decode_definition(x) for x in definitions["value"])
    by_name = {x.name: x for x in decoded}
    if len(by_name) != len(decoded):
        raise ValueError("duplicate factual combo identity")
    rows = []
    for row, identity in sorted(zip(selected, identities), key=lambda x: x[1]):
        definition = by_name[identity[1]]
        expected = next(x for x in policy.combos if x.identity == identity)
        actual_fp = normalized_combo_definition_fingerprint(definition)
        reviewed_fp = normalized_combo_definition_fingerprint(expected.reviewed_definition)
        rows.append({
            "identity": list(identity), "selected_source_row_ref": row["source_row_ref"],
            "actual_definition_fingerprint": actual_fp, "reviewed_definition_fingerprint": reviewed_fp,
            "unchanged_reviewed_policy": "MATCH" if actual_fp == reviewed_fp else "MISMATCH",
            "leaf_signature": linear_signature(definition),
        })
    combos = []
    for definition in sorted(decoded, key=lambda x: x.name):
        combos.append({
            "name": definition.name, "combo_type": definition.combo_type,
            "selected_for_concrete_design": definition.name in policy.names,
            "constituents": [x.as_dict() for x in definition.constituents],
            "nested_dependency_names": [x.name for x in definition.nested_combos],
            "raw_get_type_combo": definition.raw_get_type_combo,
            "raw_get_case_list": definition.raw_get_case_list,
            "definition_fingerprint": normalized_combo_definition_fingerprint(definition),
            "flattened_leaf_signature": linear_signature(definition) if definition.combo_type == "LINEAR_ADD" else None,
            "flatten_status": "PROVEN_LINEAR_ADD" if definition.combo_type == "LINEAR_ADD" else "NOT_LINEAR_ADD_DO_NOT_FLATTEN",
        })
    # Only captured numeric fields are used. No name-derived seismic direction.
    cases = {name: {"fact": _fact(receipt, "load_case:"+name),
                    "signature_status": "PARTIAL", "not_captured": list(RS_FIELDS_NOT_CAPTURED)}
             for name in ("RSX", "RSY")}
    snow_case = _fact(receipt, "static_linear_loads:LC_S")
    snow_pattern = _fact(receipt, "load_pattern:LC_S")
    snow_is_unit = (snow_pattern["value"]["type_code"] == 7 and
        [(x["load_type"], x["load_name"], x["scale_factor"]) for x in snow_case["value"]["loads"]] == [("Load", "LC_S", 1.0)])
    snow_rows = [{"identity": x["identity"], "actual_LC_S": x["leaf_signature"]["LC_S"],
                  "accepted_seismic_S": "0.2", "difference": str(Decimal(x["leaf_signature"]["LC_S"])-Decimal("0.2")),
                  "classification": "TRUE_POLICY_MISMATCH" if snow_is_unit else "INSUFFICIENT_FACTS"}
                 for x in rows if x["identity"][1] in ("Crack_SeisX", "Crack_SeisY", "Crack_SeisX_Soil", "Crack_SeisY_Soil")]
    return {
        "FC09_FACTUAL_CASE_SIGNATURES": cases,
        "FC09_FACTUAL_COMBO_SIGNATURES": {"count": len(combos), "source": definitions["payload_ref"], "combos": combos},
        "12_SELECTED_DESIGN_COMBO_RECONCILIATION": {"count": len(rows), "source": selection["payload_ref"], "rows": rows,
            "meaning": "Exact unchanged reviewed policy equality is not TBDY-template compliance or Eq713 state authority"},
        "SNOW_1.0_VS_0.2_DISPOSITION": {"status": "SOURCE_CORRECTION_REQUIRED" if snow_is_unit else "UNRESOLVED",
            "case": snow_case, "pattern": snow_pattern, "rows": snow_rows,
            "source_correction": "Review LC_S coefficient 1.0 -> 0.2 in the four listed selected downward Crack combos; any EDB change requires new hash and reviewed-policy reconciliation",
            "policy_or_model_changed": False},
        "EDZ_SOURCE_AND_FACTOR": {"fact": _fact(receipt, "static_linear_loads:EDZ"),
            "case_definition": "0.351*(LC_DL+LC_SDL+LC_WDL)", "combo_factors": {x["identity"][1]: x["leaf_signature"].get("EDZ") for x in rows},
            "downward_effective_G_factor": "0.1053", "upward_effective_G_factor": "-0.1053",
            "status": "PROVEN_FACTUAL_FACTOR; SDS relationship is supervisor/project policy, not independently captured SDS"},
        "DIRECTIONAL_COMBINATION_LOCATION": {"combo_level": "RSX/RSY 1.0/0.3 or 0.3/1.0 in all eight selected Crack combos",
            "internal_case_level": "NOT_CAPTURED", "double_100_30_excluded": False},
        "MODAL_COMBINATION_METHOD": "NOT_CAPTURED_IN_FC09_PREFLIGHT",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--reviewed-inputs", required=True, type=Path)
    args = parser.parse_args(argv)
    receipt = verify_preflight_bytes(args.preflight.read_bytes())
    import tools.column_r1_bblok_e1_reviewed_inputs as loader
    from tools.column_r1_bblok_fc09_reviewed_inputs import load_inputs
    loader.ACCEPTED_INPUTS = args.reviewed_inputs
    _, dependencies = load_inputs()  # Existing exact 9D7-byte verification.
    result = reconcile(receipt, dependencies["expected_combo_policy"])
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
