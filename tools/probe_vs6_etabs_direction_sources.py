#!/usr/bin/env python
"""Read-only ETABS source discovery for lateral-action direction binding.

This probe inventories available ETABS database tables and captures only tables
whose key/name suggests load-pattern, seismic, wind or auto-lateral metadata.
It does not infer X/Y direction from case names, does not promote any TS500
E/W direction authority, does not run analysis/design and does not mutate the
model or output-selection state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table


MATCH_TOKENS = ("load pattern", "seismic", "wind", "auto lateral")
SAFETY = {
    "analysis_run": False,
    "design_run": False,
    "model_save": False,
    "model_or_property_mutation": False,
    "present_units_set": False,
    "result_output_selection_changed": False,
}


def _seq(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (tuple, list)):
        return tuple(value)
    return (value,)


def _available_tables(database_tables: Any) -> tuple[dict[str, Any], ...]:
    raw = database_tables.GetAvailableTables()
    if not isinstance(raw, (tuple, list)) or len(raw) not in {4, 5}:
        raise RuntimeError(f"GetAvailableTables returned unexpected result: {raw!r}")
    values = tuple(raw)
    count = int(values[0])
    keys = _seq(values[1])
    names = _seq(values[2])
    import_types = _seq(values[3])
    if count < 0 or not (count == len(keys) == len(names) == len(import_types)):
        raise RuntimeError(
            f"GetAvailableTables count mismatch: n={count} keys={len(keys)} names={len(names)} imports={len(import_types)}"
        )
    if len(values) == 5:
        ret = values[4]
        if not isinstance(ret, int) or ret != 0:
            raise RuntimeError(f"GetAvailableTables failed/raw={raw!r}")
    rows: list[dict[str, Any]] = []
    for index, (key, name, import_type) in enumerate(zip(keys, names, import_types)):
        key_text = str(key)
        name_text = str(name)
        if not key_text.strip() or not name_text.strip():
            raise RuntimeError("GetAvailableTables returned blank key/name")
        rows.append({
            "index": index,
            "table_key": key_text,
            "table_name": name_text,
            "import_type": int(import_type),
        })
    return tuple(rows)


def _direction_candidate_tables(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = str(row["table_key"])
        name = str(row["table_name"])
        haystack = f"{key} {name}".lower()
        if any(token in haystack for token in MATCH_TOKENS) and key not in seen:
            selected.append(dict(row))
            seen.add(key)
    return tuple(selected)


def _snapshot(database_tables: Any, table_key: str) -> dict[str, Any]:
    try:
        fetched = fetch_display_table(database_tables, table_key, max_rows=None)
    except Exception as exc:  # pragma: no cover - live COM only
        return {
            "table_key": table_key,
            "status": "FETCH_EXCEPTION",
            "exception_type": type(exc).__name__,
            "exception": str(exc),
        }
    rows = tuple(dict(row) for row in fetched.parsed.rows)
    return {
        "table_key": table_key,
        "status": "FETCHED",
        "capture_status": fetched.capture_status.value,
        "return_code": fetched.parsed.return_code,
        "field_keys": list(fetched.parsed.field_keys),
        "row_count_reported": fetched.parsed.row_count_reported,
        "row_count_captured": len(rows),
        "rows": list(rows[:80]),
        "rows_truncated": len(rows) > 80,
        "selected_signature": dict(fetched.selected_signature),
    }


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-model-fingerprint", required=True)
    args = parser.parse_args(argv)

    attach = attach_to_running_etabs()
    if attach.status != ATTACH_STATUS_ATTACHED:
        payload = {"status": "BLOCKED_ATTACH", "safety": SAFETY}
        _write(args.out, payload)
        return 3

    sap = attach.sap_model
    identity = read_session_identity(attach.etabs_object, sap, attach_strategy=attach.strategy)
    fingerprint = model_fingerprint_from_path(identity.model_full_path)
    if fingerprint != args.expected_model_fingerprint:
        payload = {
            "status": "BLOCKED_MODEL_IDENTITY_MISMATCH",
            "expected_model_fingerprint": args.expected_model_fingerprint,
            "observed_model_fingerprint": fingerprint,
            "safety": SAFETY,
        }
        _write(args.out, payload)
        return 4

    try:
        available = _available_tables(sap.DatabaseTables)
        candidates = _direction_candidate_tables(available)
        snapshots = tuple(_snapshot(sap.DatabaseTables, row["table_key"]) for row in candidates)
    except Exception as exc:
        payload = {
            "status": "BLOCKED_FACTUAL_DIRECTION_SOURCE_DISCOVERY",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5

    payload = {
        "status": "COMPLETE_FACTUAL_DIRECTION_SOURCE_DISCOVERY",
        "model": {
            "path": identity.model_full_path,
            "fingerprint": fingerprint,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
        },
        "safety": SAFETY,
        "available_table_count": len(available),
        "candidate_tables": list(candidates),
        "candidate_table_snapshots": list(snapshots),
        "promotion_boundary": {
            "case_names_used_for_direction_inference": False,
            "seismic_direction_promoted": False,
            "wind_direction_promoted": False,
            "ts500_load_basis_constructed": False,
            "stability_index_calculated": False,
            "sway_classification_promoted": False,
            "engineering_calculation_performed": False,
            "compliance_verdict_emitted": False,
        },
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable({
        "status": payload["status"],
        "available_table_count": payload["available_table_count"],
        "candidate_tables": list(candidates),
        "snapshots": [
            {
                "table_key": item.get("table_key"),
                "status": item.get("status"),
                "capture_status": item.get("capture_status"),
                "field_keys": item.get("field_keys"),
                "row_count_captured": item.get("row_count_captured"),
            }
            for item in snapshots
        ],
        "safety": SAFETY,
    }), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
