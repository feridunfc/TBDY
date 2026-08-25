#!/usr/bin/env python
"""Read-only live ETABS source discovery for VS6 RC-column shear.

This probe does not run analysis/design, save the model, change properties, or
set present units. It inventories the factual sources needed by the bounded
TBDY 7.3.7 + TS500 8.1 column-shear capacity-design chain.

The probe is deliberately diagnostic. It does not compute Ve/Vr, select a
regulatory demand, or emit a compliance verdict.
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

from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.providers.etabs_display_table_fetcher import (
    fetch_display_table,
    fetch_display_table_for_output,
)


STATIC_TABLES: tuple[str, ...] = (
    "Column Object Connectivity",
    "Beam Object Connectivity",
    "Objects and Elements - Frames",
    "Frame Assignments - Section Properties",
    "Frame Assignments - End Length Offsets",
    "Frame Assignments - Local Axes",
    "Frame Section Property Definitions - Concrete Rectangular",
    "Frame Section Property Definitions - Concrete Column Reinforcing",
    "Frame Section Property Definitions - Concrete Beam Reinforcing",
    "Material Properties - Rebar Data",
    "Reinforcing Bar Sizes",
    "Load Combination Definitions",
    "Concrete Frame Design Load Combination Data",
)
RESULT_TABLES: tuple[str, ...] = (
    "Element Forces - Columns",
    "Element Forces - Beams",
)

# ETABS API GetRebarColumn output order after the input section Name. The final
# item returned by the Python COM wrapper is the ETABS return code.
GET_REBAR_COLUMN_FIELDS: tuple[str, ...] = (
    "MatPropLong",
    "MatPropConfine",
    "Pattern",
    "ConfineType",
    "Cover",
    "NumberCBars",
    "NumberR3Bars",
    "NumberR2Bars",
    "RebarSize",
    "TieSize",
    "TieSpacingLongit",
    "Number2DirTieBars",
    "Number3DirTieBars",
    "ToBeDesigned",
)


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


def decode_get_rebar_column(call_result: Mapping[str, Any]) -> dict[str, Any]:
    """Label a successful GetRebarColumn tuple without promoting it to final rebar.

    ``ToBeDesigned=True`` means the section reinforcement is design intent, not
    proof of final/provided reinforcement suitable for a compliance verdict.
    ``ToBeDesigned=False`` is only classified as section check input here; final
    detailing authority remains a separate reviewed concern.
    """
    raw = call_result.get("raw")
    if not call_result.get("success") or not isinstance(raw, list):
        return {
            "status": "UNAVAILABLE",
            "authority_status": "NOT_PROVEN",
            "data": None,
        }
    if len(raw) != len(GET_REBAR_COLUMN_FIELDS) + 1:
        return {
            "status": "UNEXPECTED_SHAPE",
            "authority_status": "NOT_PROVEN",
            "raw_length": len(raw),
            "expected_length": len(GET_REBAR_COLUMN_FIELDS) + 1,
            "data": None,
        }
    data = dict(zip(GET_REBAR_COLUMN_FIELDS, raw[:-1], strict=True))
    return_code = raw[-1]
    if return_code not in (None, 0):
        authority = "NOT_PROVEN"
        status = "NONZERO_RETURN_CODE"
    elif data.get("ToBeDesigned") is True:
        authority = "DESIGN_INTENT_ONLY"
        status = "DECODED"
    elif data.get("ToBeDesigned") is False:
        authority = "SECTION_REBAR_CHECK_INPUT"
        status = "DECODED"
    else:
        authority = "NOT_PROVEN"
        status = "AMBIGUOUS_TO_BE_DESIGNED"
    return {
        "status": status,
        "return_code": return_code,
        "authority_status": authority,
        "data": data,
    }


def _available_tables(database_tables: Any) -> dict[str, Any]:
    result = _call(database_tables, "GetAvailableTables")
    raw = result.get("raw")
    filtered: list[dict[str, Any]] = []
    if isinstance(raw, list) and len(raw) >= 2:
        keys = raw[1] if isinstance(raw[1], list) else []
        names = raw[2] if len(raw) > 2 and isinstance(raw[2], list) else []
        imports = raw[3] if len(raw) > 3 and isinstance(raw[3], list) else []
        needles = (
            "column",
            "beam",
            "rebar",
            "concrete",
            "design",
            "force",
            "frame section",
            "end length",
            "local axes",
        )
        for index, key in enumerate(keys):
            key_text = str(key)
            name_text = str(names[index]) if index < len(names) else ""
            haystack = f"{key_text} {name_text}".lower()
            if any(needle in haystack for needle in needles):
                filtered.append(
                    {
                        "key": key_text,
                        "name": name_text,
                        "import_type": imports[index] if index < len(imports) else None,
                    }
                )
    result["filtered_candidates"] = filtered
    return result


def _sample_rows(rows: Sequence[Mapping[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    return [dict(row) for row in rows[:limit]]


def _table_snapshot(database_tables: Any, table_name: str) -> dict[str, Any]:
    """Fetch one non-result display table without mutating output selection."""
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


def _result_snapshot(
    database_tables: Any,
    table_name: str,
    output_name: str,
    *,
    preferred_unique_name: str | None = None,
) -> dict[str, Any]:
    """Fetch one result table through the reversible output-selection boundary."""
    try:
        fetched = fetch_display_table_for_output(
            database_tables,
            table_name,
            preferred_output_case=output_name,
            max_rows=None,
        )
    except Exception as exc:  # pragma: no cover - live COM only
        return {
            "table": table_name,
            "output": output_name,
            "status": "FETCH_EXCEPTION",
            "exception_type": type(exc).__name__,
            "exception": str(exc),
        }

    rows = tuple(dict(row) for row in fetched.parsed.rows)
    exact = tuple(row for row in rows if row.get("OutputCase") == output_name)
    preferred = tuple(
        row
        for row in exact
        if preferred_unique_name is not None
        and str(row.get("UniqueName")) == preferred_unique_name
    )
    restore_verified = any(
        item.get("phase") == "restore_verify" and item.get("success") is True
        for item in fetched.state_diagnostics
    )
    return {
        "table": table_name,
        "output": output_name,
        "status": "FETCHED",
        "capture_status": fetched.capture_status.value,
        "return_code": fetched.parsed.return_code,
        "field_keys": list(fetched.parsed.field_keys),
        "row_count_reported": fetched.parsed.row_count_reported,
        "row_count_captured": len(rows),
        "exact_output_row_count": len(exact),
        "preferred_unique_name": preferred_unique_name,
        "preferred_unique_name_row_count": len(preferred),
        "sample_rows": _sample_rows(preferred if preferred else exact),
        "output_selection_restore_verified": restore_verified,
        "selected_signature": dict(fetched.selected_signature),
    }


def _parse_outputs(value: str) -> tuple[str, ...]:
    outputs = tuple(item.strip() for item in value.split(",") if item.strip())
    if not outputs or len(outputs) != len(set(outputs)):
        raise argparse.ArgumentTypeError("--outputs must contain unique comma-separated names")
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--section", default="Column_80x80")
    parser.add_argument("--column-name", default="236")
    parser.add_argument(
        "--outputs",
        type=_parse_outputs,
        default=("Crack_SeisX", "Crack_SeisY", "Grav_Ult"),
        help="Exact comma-separated outputs used only for reversible result-table schema discovery",
    )
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
    database_tables = sap.DatabaseTables

    section_rebar_call = (
        {"available": False}
        if prop_frame is None
        else _call(prop_frame, "GetRebarColumn", args.section)
    )
    section_rebar_decoded = decode_get_rebar_column(section_rebar_call)

    design_results_available = (
        {"available": False}
        if design_concrete is None
        else _call(design_concrete, "GetResultsAvailable")
    )
    column_design_summary = (
        {"available": False}
        if design_concrete is None
        else _call(design_concrete, "GetSummaryResultsColumn", args.column_name)
    )

    static_tables = {
        table: _table_snapshot(database_tables, table)
        for table in STATIC_TABLES
    }
    result_tables: dict[str, dict[str, Any]] = {}
    for output_name in args.outputs:
        result_tables[output_name] = {
            "columns": _result_snapshot(
                database_tables,
                RESULT_TABLES[0],
                output_name,
                preferred_unique_name=args.column_name,
            ),
            "beams": _result_snapshot(
                database_tables,
                RESULT_TABLES[1],
                output_name,
            ),
        }

    to_be_designed = (section_rebar_decoded.get("data") or {}).get("ToBeDesigned")
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
            "result_output_selection": "REVERSIBLE_TRANSACTION_ONLY",
        },
        "requested": {
            "section": args.section,
            "column_name": args.column_name,
            "outputs": list(args.outputs),
        },
        "database_tables": _available_tables(database_tables),
        "section_rebar": {
            "raw_call": section_rebar_call,
            "decoded": section_rebar_decoded,
        },
        "design_results_available": design_results_available,
        "column_design_summary": column_design_summary,
        "static_table_snapshots": static_tables,
        "result_table_snapshots": result_tables,
        "readiness": {
            "probe_scope": "DISCOVERY_ONLY_NO_COMPLIANCE_VERDICT",
            "etabs_section_rebar_to_be_designed": to_be_designed,
            "etabs_section_rebar_authority": section_rebar_decoded.get("authority_status"),
            "final_or_provided_rebar_proven_by_this_probe": False,
            "note": (
                "ToBeDesigned=True is design intent only; do not use it as final/provided rebar. "
                "A later VS6 authority must bind reviewed provided/selected reinforcement before "
                "moment-capacity or Vr compliance is asserted."
            ),
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
