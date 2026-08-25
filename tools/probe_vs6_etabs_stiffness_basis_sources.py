#!/usr/bin/env python
"""Read-only ETABS source discovery for TS500 7.6.2.1 stiffness-basis closure.

The probe inventories ETABS database tables and captures only tables that may
prove or disprove the analysis stiffness basis (property modifiers, stiffness,
geometric-nonlinearity/P-Delta metadata, and concrete section definitions).
It performs no TS500 promotion, no analysis/design run, no model mutation and
no sway classification.
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

MATCH_TOKENS = (
    "modifier",
    "stiffness",
    "p-delta",
    "p delta",
    "geometric nonlinearity",
    "concrete rectangular",
    "load case definitions",
)
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
    return tuple(
        {
            "index": index,
            "table_key": str(key),
            "table_name": str(name),
            "import_type": int(import_type),
        }
        for index, (key, name, import_type) in enumerate(zip(keys, names, import_types))
    )


def _candidate_tables(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
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


def _interesting_rows(rows: tuple[dict[str, Any], ...], *, limit: int = 160) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return list(rows)
    selected: list[dict[str, Any]] = []
    for row in rows:
        keys = {str(k).lower() for k in row}
        values = " ".join(str(v).lower() for v in row.values())
        if (
            any("mod" in key or "stiff" in key for key in keys)
            or "236" in values
            or "column_" in values
            or "linear static" in values
            or "p-delta" in values
        ):
            selected.append(row)
        if len(selected) >= limit:
            break
    return selected


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
    projected = _interesting_rows(rows)
    return {
        "table_key": table_key,
        "status": "FETCHED",
        "capture_status": fetched.capture_status.value,
        "return_code": fetched.parsed.return_code,
        "field_keys": list(fetched.parsed.field_keys),
        "row_count_reported": fetched.parsed.row_count_reported,
        "row_count_captured": len(rows),
        "rows": projected,
        "rows_projection_count": len(projected),
        "rows_projection_is_full": len(projected) == len(rows),
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
        candidates = _candidate_tables(available)
        snapshots = tuple(_snapshot(sap.DatabaseTables, row["table_key"]) for row in candidates)
    except Exception as exc:
        payload = {
            "status": "BLOCKED_FACTUAL_STIFFNESS_BASIS_SOURCE_DISCOVERY",
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "safety": SAFETY,
        }
        _write(args.out, payload)
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
        return 5

    payload = {
        "status": "COMPLETE_FACTUAL_STIFFNESS_BASIS_SOURCE_DISCOVERY",
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
            "uncracked_stiffness_basis_promoted": False,
            "analysis_order_promoted": False,
            "reanalysis_required_emitted": False,
            "stability_index_calculated": False,
            "sway_classification_promoted": False,
            "engineering_calculation_performed": False,
            "compliance_verdict_emitted": False,
        },
    }
    _write(args.out, payload)
    print(json.dumps(to_jsonable({
        "status": payload["status"],
        "available_table_count": len(available),
        "candidate_tables": list(candidates),
        "snapshots": [
            {
                "table_key": item.get("table_key"),
                "status": item.get("status"),
                "capture_status": item.get("capture_status"),
                "field_keys": item.get("field_keys"),
                "row_count_captured": item.get("row_count_captured"),
                "rows_projection_count": item.get("rows_projection_count"),
            }
            for item in snapshots
        ],
        "safety": SAFETY,
    }), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
