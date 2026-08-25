#!/usr/bin/env python
"""Read-only VS6 load-combination definition probe.

This probe inspects ETABS response-combination topology only.  It does not run
analysis/design, does not select result output, does not mutate/save the model,
and does not promote combination rows to concurrent P-M2-M3 design states.

The immediate purpose is to prove what Crack_SeisX / Crack_SeisY / Grav_Ult
actually contain before ENGINE_SELECTED_REBAR is allowed to consume them.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable


SAFETY = {
    "analysis_run": False,
    "design_run": False,
    "model_save": False,
    "model_or_property_mutation": False,
    "present_units_set": False,
    "result_output_selection_changed": False,
}

COMBO_TYPE = {
    0: "LINEAR_ADD",
    1: "ENVELOPE",
    2: "ABSOLUTE_ADD",
    3: "SRSS",
    4: "RANGE_ADD",
}

CNAME_TYPE = {
    0: "LOAD_CASE",
    1: "LOAD_COMBO",
}

NONCONCURRENT_COMBO_TYPES = frozenset({1, 2, 3, 4})


def _csv_strings(value: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if not items or len(items) != len(set(items)):
        raise argparse.ArgumentTypeError("value must contain a nonempty unique comma-separated list")
    return items


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _seq(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (tuple, list)):
        return tuple(value)
    return (value,)


def _get_combo_type(resp_combo: Any, name: str) -> tuple[int, Any]:
    """Decode generated-COM GetTypeCombo output as (ComboType, ret)."""
    raw = resp_combo.GetTypeCombo(name)
    if not isinstance(raw, tuple):
        raise RuntimeError(f"GetTypeCombo({name!r}) returned unexpected scalar: {raw!r}")
    if len(raw) != 2:
        raise RuntimeError(f"GetTypeCombo({name!r}) returned unexpected tuple: {raw!r}")

    # comtypes generated CSI bindings return output parameters first and the
    # function return code last.  Keep the raw tuple in the artifact so a
    # version-specific mismatch fails visibly rather than being guessed.
    combo_type, ret = raw
    if not isinstance(ret, int) or ret != 0:
        raise RuntimeError(f"GetTypeCombo({name!r}) failed/raw={raw!r}")
    combo_type = int(combo_type)
    if combo_type not in COMBO_TYPE:
        raise RuntimeError(f"GetTypeCombo({name!r}) returned unsupported type/raw={raw!r}")
    return combo_type, raw


def _get_case_list(resp_combo: Any, name: str) -> tuple[tuple[dict[str, Any], ...], Any]:
    """Decode generated-COM GetCaseList output without inventing constituents."""
    raw = resp_combo.GetCaseList(name)
    if not isinstance(raw, tuple) or len(raw) != 5:
        raise RuntimeError(f"GetCaseList({name!r}) returned unexpected value: {raw!r}")

    number_items, cname_type_raw, cname_raw, sf_raw, ret = raw
    if not isinstance(ret, int) or ret != 0:
        raise RuntimeError(f"GetCaseList({name!r}) failed/raw={raw!r}")

    number_items = int(number_items)
    types = _seq(cname_type_raw)
    names = _seq(cname_raw)
    factors = _seq(sf_raw)
    if not (number_items == len(types) == len(names) == len(factors)):
        raise RuntimeError(
            f"GetCaseList({name!r}) count mismatch: n={number_items} "
            f"types={len(types)} names={len(names)} sf={len(factors)} raw={raw!r}"
        )

    rows: list[dict[str, Any]] = []
    for index, (kind_raw, child_name, factor) in enumerate(zip(types, names, factors)):
        kind = int(kind_raw)
        if kind not in CNAME_TYPE:
            raise RuntimeError(f"GetCaseList({name!r}) returned unsupported CNameType={kind}")
        rows.append(
            {
                "index": index,
                "cname_type_code": kind,
                "cname_type": CNAME_TYPE[kind],
                "name": str(child_name),
                "scale_factor": float(factor),
            }
        )
    return tuple(rows), raw


def _probe_combo(resp_combo: Any, name: str, *, stack: tuple[str, ...] = ()) -> dict[str, Any]:
    if name in stack:
        return {
            "name": name,
            "status": "BLOCKED_RECURSIVE_COMBO_CYCLE",
            "cycle": list((*stack, name)),
        }

    combo_type, raw_type = _get_combo_type(resp_combo, name)
    constituents, raw_case_list = _get_case_list(resp_combo, name)
    nested: list[dict[str, Any]] = []
    for item in constituents:
        if item["cname_type"] == "LOAD_COMBO":
            nested.append(_probe_combo(resp_combo, item["name"], stack=(*stack, name)))

    contains_nonconcurrent = combo_type in NONCONCURRENT_COMBO_TYPES or any(
        child.get("contains_nonconcurrent_combo_type", False) for child in nested
    )
    if combo_type in NONCONCURRENT_COMBO_TYPES:
        concurrency_status = "NONCONCURRENT_EXTREME_COMBINATION"
    elif contains_nonconcurrent:
        concurrency_status = "CONTAINS_NONCONCURRENT_NESTED_COMBINATION"
    else:
        concurrency_status = "REQUIRES_LOAD_CASE_CONCURRENCY_REVIEW"

    return {
        "name": name,
        "status": "PROVEN_COMBO_DEFINITION",
        "combo_type_code": combo_type,
        "combo_type": COMBO_TYPE[combo_type],
        "constituents": list(constituents),
        "nested_combos": nested,
        "contains_nonconcurrent_combo_type": contains_nonconcurrent,
        "p_m2_m3_concurrency_status": concurrency_status,
        "raw_api": {
            "GetTypeCombo": repr(raw_type),
            "GetCaseList": repr(raw_case_list),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-model-fingerprint", required=True)
    parser.add_argument("--combos", type=_csv_strings, required=True)
    args = parser.parse_args(argv)

    attach = attach_to_running_etabs()
    if attach.status != ATTACH_STATUS_ATTACHED:
        payload = {
            "status": "BLOCKED_ATTACH",
            "safety": SAFETY,
            "attempts": [item.as_dict() for item in attach.attempts],
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 3

    sap = attach.sap_model
    identity = read_session_identity(attach.etabs_object, sap, attach_strategy=attach.strategy)
    fingerprint = model_fingerprint_from_path(identity.model_full_path)
    if fingerprint != args.expected_model_fingerprint:
        payload = {
            "status": "BLOCKED_MODEL_IDENTITY_MISMATCH",
            "expected_model_fingerprint": args.expected_model_fingerprint,
            "observed_model_fingerprint": fingerprint,
            "model_path": identity.model_full_path,
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 4

    try:
        combos = [_probe_combo(sap.RespCombo, name) for name in args.combos]
    except Exception as exc:
        payload = {
            "status": "BLOCKED_COMBO_DEFINITION_PROBE",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "model": {"path": identity.model_full_path, "fingerprint": fingerprint},
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5

    payload = {
        "status": "COMPLETE_FACTUAL_COMBO_DEFINITION_PROBE",
        "model": {
            "path": identity.model_full_path,
            "fingerprint": fingerprint,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
            "database_units": identity.units.database_units,
            "present_units": identity.units.present_units,
        },
        "safety": SAFETY,
        "requested_combos": list(args.combos),
        "combos": combos,
        "scope": {
            "combination_definition_proven": True,
            "design_combination_scope_resolved": False,
            "p_m2_m3_concurrency_promoted": False,
            "reinforcement_selected": False,
            "compliance_verdict_emitted": False,
        },
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
