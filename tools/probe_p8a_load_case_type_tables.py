#!/usr/bin/env python
"""Bounded live/read-only P8A prerequisite proof for ETABS load-case tables.

This tool does not classify load cases and does not create case-type authority.
It acquires every catalog-declared candidate table through the repository's
shared display-table fetcher, preserving full raw factual rows and the
DatabaseTables reversible-state diagnostics for supervisor review.
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

from tbdy_engine.etabs.safety import (
    DatabaseTablesReadTransaction,
    EtabsSafetyError,
    RuntimeCaptureStatus,
    attach_verified_to_running_etabs,
)
from tbdy_engine.etabs.table_catalog import TABLE_CATALOG
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.model_identity import model_fingerprint_from_path
from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table

TABLE_KEYS = ("load_case_summary", "linear_static_cases", "rs_cases")
PROOF_CONTRACT = "P8A_LOAD_CASE_TYPE_TABLE_PROOF_V1"

SAFETY = {
    "analysis_run": False,
    "design_run": False,
    "model_save": False,
    "model_or_property_mutation": False,
    "present_units_set": False,
    "results_output_selection_changed": False,
    "database_table_acquisition": "shared_fetch_display_table_only",
    "database_selection_boundary": "DatabaseTablesReadTransaction",
}


def _selection_snapshot_payload(snapshot: Any) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "cases": list(snapshot.cases),
        "combos": list(snapshot.combos),
        "patterns": None if snapshot.patterns is None else list(snapshot.patterns),
        "output_options": None if snapshot.output_options is None else list(snapshot.output_options),
    }


def _fetch_payload(canonical_key: str, requested_table_name: str, result: Any) -> dict[str, Any]:
    parsed = result.parsed
    return {
        "canonical_table_key": canonical_key,
        "requested_table_name": requested_table_name,
        "actual_table_name": parsed.actual_table_name,
        "field_headers": list(parsed.field_keys),
        "row_count_reported": parsed.row_count_reported,
        "parsed_row_count": len(parsed.rows),
        "rows": [dict(row) for row in parsed.rows],
        "fetch_status": parsed.fetch_status,
        "return_code": parsed.return_code,
        "capture_status": result.capture_status.value,
        "full_capture": result.capture_status is RuntimeCaptureStatus.FULL,
        "selected_signature": dict(result.selected_signature),
        "selected_signature_reason": result.selected_signature_reason,
        "signature_attempts": [dict(item) for item in result.signature_attempts],
        "display_selection": dict(result.display_selection),
        "state_diagnostics": [dict(item) for item in result.state_diagnostics],
        "parser_diagnostics": [dict(item) for item in parsed.diagnostics],
        "parser_debug": dict(parsed.debug),
    }


def _write(path: Path | None, payload: dict[str, Any]) -> None:
    text = json.dumps(
        to_jsonable(payload),
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-model", required=True, help="Exact full ETABS model path")
    parser.add_argument("--pid", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    payload: dict[str, Any] = {
        "contract": PROOF_CONTRACT,
        "safety": SAFETY,
        "table_catalog": {
            key: {
                "canonical": TABLE_CATALOG[key].canonical,
                "declared_etabs_names": list(TABLE_CATALOG[key].etabs_names),
                "required_cols": list(TABLE_CATALOG[key].required_cols),
            }
            for key in TABLE_KEYS
        },
        "classifier_population_created": False,
        "mapping_status": "NOT_AUTHORIZED_UNTIL_LIVE_SCHEMA_PROVES_EXACT_MAPPING",
    }

    try:
        verified = attach_verified_to_running_etabs(
            args.expected_model,
            pid=args.pid,
            allow_pid_fallback=False,
        )
    except EtabsSafetyError as exc:
        payload.update({
            "status": "BLOCKED_VERIFIED_ETABS_ATTACH",
            "attach_error": exc.as_diagnostic_dict(),
        })
        _write(args.out, payload)
        return 2

    sap_model = verified.attach_result.sap_model
    identity = verified.identity
    fingerprint = model_fingerprint_from_path(identity.model_full_path)
    payload["session_identity"] = {
        **identity.as_dict(),
        "canonical_model_fingerprint": fingerprint,
    }
    payload["capabilities"] = verified.capabilities.as_dict()

    database_tables = getattr(sap_model, "DatabaseTables", None)
    if database_tables is None:
        payload["status"] = "BLOCKED_DATABASE_TABLES_UNAVAILABLE"
        _write(args.out, payload)
        return 3

    transaction: DatabaseTablesReadTransaction | None = None
    fetches: list[dict[str, Any]] = []
    try:
        with DatabaseTablesReadTransaction(database_tables) as transaction:
            payload["database_tables_state_before"] = _selection_snapshot_payload(transaction.snapshot)
            for canonical_key in TABLE_KEYS:
                spec = TABLE_CATALOG[canonical_key]
                for table_name in spec.etabs_names:
                    result = fetch_display_table(database_tables, table_name)
                    fetches.append(_fetch_payload(canonical_key, table_name, result))
    except EtabsSafetyError as exc:
        payload.update({
            "status": "BLOCKED_DATABASE_TABLES_STATE_OR_FETCH",
            "fetches": fetches,
            "database_tables_transaction_diagnostics": (
                [] if transaction is None else [dict(item) for item in transaction.diagnostics]
            ),
            "state_or_fetch_error": exc.as_diagnostic_dict(),
        })
        _write(args.out, payload)
        return 4

    transaction_diagnostics = [] if transaction is None else [dict(item) for item in transaction.diagnostics]
    restore_records = [
        item
        for item in transaction_diagnostics
        if str(item.get("phase", "")).startswith("restore")
    ]
    payload.update({
        "fetches": fetches,
        "database_tables_transaction_diagnostics": transaction_diagnostics,
        "database_tables_state_after": restore_records[-1] if restore_records else None,
        "identity_analysis": {
            "status": "REQUIRES_SUPERVISOR_REVIEW_OF_OBSERVED_FIELD_HEADERS",
            "identity_field": None,
            "duplicate_case_identities": None,
            "missing_case_identities": None,
            "reason": (
                "The first acquisition proof intentionally does not guess which observed "
                "ETABS field is the exact case-identity field. Full rows and headers are emitted."
            ),
        },
    })

    full_by_key = {
        key: any(
            item["canonical_table_key"] == key and item["full_capture"]
            for item in fetches
        )
        for key in TABLE_KEYS
    }
    payload["full_capture_by_catalog_key"] = full_by_key
    payload["status"] = (
        "FACTUAL_TABLE_ACQUISITION_PROOF_CAPTURED_REQUIRES_MAPPING_REVIEW"
        if all(full_by_key.values())
        else "BLOCKED_FULL_TABLE_CAPTURE_REQUIRED"
    )
    _write(args.out, payload)
    return 0 if all(full_by_key.values()) else 5


if __name__ == "__main__":
    raise SystemExit(main())
