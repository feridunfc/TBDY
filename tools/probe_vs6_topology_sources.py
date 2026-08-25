#!/usr/bin/env python
"""Read-only ETABS source discovery for the VS6 strict topology kernel.

This probe inventories exact object/joint/assignment tables needed to bind
columns, their top/bottom joints, connected beam object ends, local axes and
clear-length inputs. It deliberately performs no heuristic frame
classification, no section-name parsing, no engineering calculation, and no
compliance verdict.

Safety boundary: no analysis/design run, no model save, no property mutation,
no present-unit mutation.
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


TOPOLOGY_TABLES: tuple[str, ...] = (
    "Point Object Connectivity",
    "Objects and Elements - Joints",
    "Column Object Connectivity",
    "Beam Object Connectivity",
    "Objects and Elements - Frames",
    "Frame Assignments - Section Properties",
    "Frame Assignments - End Length Offsets",
    "Frame Assignments - Local Axes",
    "Frame Section Property Definitions - Concrete Rectangular",
)


def _sample_rows(rows: Sequence[Mapping[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    return [dict(row) for row in rows[:limit]]


def _snapshot(database_tables: Any, table_name: str) -> dict[str, Any]:
    try:
        fetched = fetch_display_table(database_tables, table_name, max_rows=None)
    except Exception as exc:  # pragma: no cover - live COM only
        return {
            "table": table_name,
            "status": "FETCH_EXCEPTION",
            "exception_type": type(exc).__name__,
            "exception": str(exc),
        }

    rows = tuple(dict(row) for row in fetched.parsed.rows)
    return {
        "table": table_name,
        "status": "FETCHED",
        "capture_status": fetched.capture_status.value,
        "return_code": fetched.parsed.return_code,
        "field_keys": list(fetched.parsed.field_keys),
        "row_count_reported": fetched.parsed.row_count_reported,
        "row_count_captured": len(rows),
        "sample_rows": _sample_rows(rows),
        "selected_signature": dict(fetched.selected_signature),
    }


def _connectivity_joint_ids(snapshot: Mapping[str, Any]) -> set[str]:
    rows = snapshot.get("sample_rows")
    if not isinstance(rows, list):
        return set()
    out: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        for field in ("UniquePtI", "UniquePtJ"):
            value = row.get(field)
            if value not in (None, ""):
                out.add(str(value))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    attach = attach_to_running_etabs()
    if attach.status != ATTACH_STATUS_ATTACHED:
        payload = {
            "status": "BLOCKED_ATTACH",
            "attempts": [item.as_dict() for item in attach.attempts],
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False))
        return 3

    sap = attach.sap_model
    identity = read_session_identity(attach.etabs_object, sap, attach_strategy=attach.strategy)
    fingerprint = model_fingerprint_from_path(identity.model_full_path)
    snapshots = {name: _snapshot(sap.DatabaseTables, name) for name in TOPOLOGY_TABLES}

    payload = {
        "status": "COMPLETE",
        "model": {
            "path": identity.model_full_path,
            "fingerprint": fingerprint,
            "program_name": identity.program_name,
            "program_version": identity.program_version,
            "database_units": identity.units.database_units,
            "present_units": identity.units.present_units,
        },
        "safety": {
            "analysis_run": False,
            "design_run": False,
            "model_save": False,
            "model_or_property_mutation": False,
            "present_units_set": False,
        },
        "probe_scope": "STRICT_TOPOLOGY_SOURCE_DISCOVERY_ONLY",
        "heuristics": {
            "frame_classification_from_angle": False,
            "section_dimensions_from_name": False,
            "default_dimensions": False,
            "coordinate_fallbacks": False,
        },
        "tables": snapshots,
        "sample_connectivity_joint_ids": sorted(
            _connectivity_joint_ids(snapshots["Column Object Connectivity"])
            | _connectivity_joint_ids(snapshots["Beam Object Connectivity"])
        ),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(to_jsonable(payload), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
