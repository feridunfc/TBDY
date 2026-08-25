#!/usr/bin/env python
"""Read-only live ETABS source discovery for VS6 RC-column shear.

This probe does not run analysis/design, save the model, change properties, or
set present units. It only inventories candidate factual sources needed by the
TBDY 7.3.7 + TS500 8.1 column-shear slice.
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

from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable


def _short(value: Any, limit: int = 4000) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "...<truncated>"


def _call(obj: Any, method: str, *args: Any) -> dict[str, Any]:
    fn = getattr(obj, method, None)
    if fn is None:
        return {"method": method, "available": False}
    try:
        raw = fn(*args)
    except Exception as exc:  # pragma: no cover - live COM only
        return {
            "method": method,
            "available": True,
            "success": False,
            "exception_type": type(exc).__name__,
            "exception": str(exc),
        }
    return {
        "method": method,
        "available": True,
        "success": True,
        "raw_type": type(raw).__name__,
        "raw_repr": _short(raw),
        "raw": to_jsonable(raw),
    }


def _available_tables(database_tables: Any) -> dict[str, Any]:
    result = _call(database_tables, "GetAvailableTables")
    raw = result.get("raw")
    filtered: list[dict[str, Any]] = []
    if isinstance(raw, list) and len(raw) >= 2:
        keys = raw[1] if isinstance(raw[1], list) else []
        names = raw[2] if len(raw) > 2 and isinstance(raw[2], list) else []
        imports = raw[3] if len(raw) > 3 and isinstance(raw[3], list) else []
        needles = ("column", "rebar", "concrete", "design", "force", "frame section")
        for index, key in enumerate(keys):
            key_text = str(key)
            name_text = str(names[index]) if index < len(names) else ""
            haystack = f"{key_text} {name_text}".lower()
            if any(needle in haystack for needle in needles):
                filtered.append({
                    "key": key_text,
                    "name": name_text,
                    "import_type": imports[index] if index < len(imports) else None,
                })
    result["filtered_candidates"] = filtered
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--section", default="Column_80x80")
    parser.add_argument("--column-name", default="236")
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

    design_concrete = getattr(sap, "DesignConcrete", None)
    prop_frame = getattr(sap, "PropFrame", None)

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
        "database_tables": _available_tables(sap.DatabaseTables),
        "section_rebar": (
            {"available": False}
            if prop_frame is None
            else _call(prop_frame, "GetRebarColumn", args.section)
        ),
        "design_results_available": (
            {"available": False}
            if design_concrete is None
            else _call(design_concrete, "GetResultsAvailable")
        ),
        "column_design_summary": (
            {"available": False}
            if design_concrete is None
            else _call(design_concrete, "GetSummaryResultsColumn", args.column_name)
        ),
        "requested": {
            "section": args.section,
            "column_name": args.column_name,
        },
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
