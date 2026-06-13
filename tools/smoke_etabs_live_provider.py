#!/usr/bin/env python
"""Manual/local ETABS table-inventory + header/sample smoke script.

Opt-in only. CI must not run this script. It never starts ETABS, never modifies a
model, never runs design, never executes checks, and never emits CheckResult or
OK/FAIL statuses.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# Import-safe without ETABS/comtypes installed.
from tbdy_engine.audit.etabs_table_fit import EtabsTableFitAuditor
from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.providers.table_registry import TableRegistry

_STATUS_VALUES_TO_REDACT = {"OK", "FAIL"}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _graceful_unavailable(out_dir: Path, message: str) -> int:
    payload = {"diagnostic": message, "manual_local_only": True, "checks_executed": False, "model_modified": False}
    _write_json(out_dir / "etabs_table_inventory.json", {"tables": [], "diagnostics": [payload]})
    _write_json(out_dir / "table_registry_match_summary.json", {"matches": [], "diagnostics": [payload]})
    _write_json(out_dir / "missing_expected_tables.json", {"missing": [], "diagnostics": [payload]})
    _write_json(out_dir / "table_headers_report.json", [])
    _write_json(out_dir / "table_contract_fit_report.json", [])
    _write_json(out_dir / "feature_source_fit_report.json", [])
    _write_json(out_dir / "combo_family_fit_report.json", [])
    _write_json(out_dir / "element_identity_fit_report.json", [])
    _write_json(out_dir / "missing_required_sources.json", {"diagnostics": [payload]})
    print(message)
    return 0


def _parse_available_tables_result(result: Any) -> list[str]:
    available_tables: list[str] = []
    if isinstance(result, (list, tuple)):
        for item in result:
            if isinstance(item, (list, tuple)):
                available_tables.extend(str(x) for x in item if isinstance(x, str))
            elif isinstance(item, str):
                available_tables.append(item)
    return sorted(set(available_tables))


def _parse_display_array_result(result: Any) -> tuple[tuple[str, ...], tuple[Mapping[str, Any], ...], Mapping[str, Any]]:
    """Best-effort parser for CSI ``GetTableForDisplayArray`` return variants.

    CSI COM wrappers differ by ETABS/comtypes versions. This parser looks for a
    field/header string list and a flat table-data list, but it deliberately
    avoids engineering interpretation. Returned rows are only smoke samples.
    """
    if not isinstance(result, (list, tuple)):
        return tuple(), tuple(), {"parse_note": "Unexpected non-sequence GetTableForDisplayArray result"}

    sequences = [item for item in result if isinstance(item, (list, tuple))]
    string_sequences = [tuple(str(x) for x in seq if isinstance(x, str)) for seq in sequences]
    string_sequences = [seq for seq in string_sequences if seq]
    if not string_sequences:
        return tuple(), tuple(), {"parse_note": "No string header/data arrays found in GetTableForDisplayArray result"}

    # Prefer a short string sequence as headers. Longest sequence is usually the
    # flattened data array; this heuristic is intentionally conservative.
    headers = min(string_sequences, key=len)
    data_seq = max(string_sequences, key=len)
    if len(data_seq) <= len(headers):
        rows: tuple[Mapping[str, Any], ...] = tuple()
    else:
        width = max(1, len(headers))
        rows_list: list[dict[str, Any]] = []
        for start in range(0, len(data_seq), width):
            chunk = data_seq[start : start + width]
            if len(chunk) != width:
                break
            rows_list.append({headers[i]: _sanitize_sample_value(chunk[i]) for i in range(width)})
        rows = tuple(rows_list)
    return headers, rows, {"parse_note": "best_effort_get_table_for_display_array_parse"}


def _sanitize_sample_value(value: Any) -> Any:
    if isinstance(value, str) and value.strip().upper() in _STATUS_VALUES_TO_REDACT:
        return "[REDACTED_STATUS_VALUE]"
    return value


def _sanitize_rows(rows: Sequence[Mapping[str, Any]], limit: int) -> tuple[Mapping[str, Any], ...]:
    sanitized: list[dict[str, Any]] = []
    for row in rows[:limit]:
        sanitized.append({str(k): _sanitize_sample_value(v) for k, v in dict(row).items()})
    return tuple(sanitized)


def _try_get_table_for_display(database_tables: Any, table_name: str, sample_limit: int) -> tuple[tuple[str, ...], tuple[Mapping[str, Any], ...], list[dict[str, Any]]]:
    """Try safe read-only ETABS display-table calls and return headers/sample rows.

    The function never selects tables, never changes model state, and never runs
    design. If the local CSI API signature differs, it returns diagnostics and
    leaves headers/sample empty rather than crashing the smoke.
    """
    attempts: list[tuple[Any, ...]] = [
        (table_name, [], "", 0, [], 0, []),
        (table_name, [], "", 0, [], 0, []),
        (table_name, "", "", 0, [], 0, []),
        (table_name, "", ""),
        (table_name,),
    ]
    diagnostics: list[dict[str, Any]] = []
    last_exc: Exception | None = None
    for args in attempts:
        try:  # pragma: no cover - depends on local ETABS environment
            result = database_tables.GetTableForDisplayArray(*args)
            headers, rows, parse_diag = _parse_display_array_result(result)
            diagnostics.append({"attempt_args_count": len(args), **dict(parse_diag)})
            return headers, _sanitize_rows(rows, sample_limit), diagnostics
        except Exception as exc:  # pragma: no cover - depends on local ETABS environment
            last_exc = exc
            diagnostics.append({"attempt_args_count": len(args), "error": str(exc)})
            continue
    diagnostics.append({
        "limitation": "Could not fetch headers/sample rows with GetTableForDisplayArray in this ETABS/API wrapper. Table-name inventory remains valid, but column/header fit cannot be proven from this smoke output.",
        "last_error": str(last_exc) if last_exc else None,
    })
    return tuple(), tuple(), diagnostics


def _build_canonical_tables_from_smoke(
    *,
    actual_tables: Iterable[str],
    database_tables: Any,
    registry: TableRegistry,
    sample_limit: int,
) -> tuple[CanonicalTable, ...]:
    tables: list[CanonicalTable] = []
    for actual in sorted(set(actual_tables)):
        canonical = registry.canonical_key_for_alias(actual) or actual
        headers, rows, _diagnostics = _try_get_table_for_display(database_tables, actual, sample_limit)
        tables.append(
            CanonicalTable(
                table_key=canonical,
                actual_table_name=actual,
                columns=headers,
                rows=rows,
                units={},
                source="ETABS_LIVE_MANUAL_SMOKE",
            )
        )
    return tuple(tables)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manual ETABS table inventory/header smoke. Does not run checks.")
    parser.add_argument("--out", default="local_out/etabs_smoke", help="Output directory for smoke JSON files")
    parser.add_argument("--sample-rows", type=int, default=3, help="Maximum redacted sample rows per matched table")
    args = parser.parse_args(argv)
    out_dir = Path(args.out)
    try:
        try:
            import comtypes.client  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - depends on local Windows/ETABS environment
            return _graceful_unavailable(out_dir, f"ETABS COM/comtypes unavailable; manual smoke not run: {exc}")

        try:  # pragma: no cover - depends on local ETABS environment
            etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
            sap_model = etabs_object.SapModel
            database_tables = sap_model.DatabaseTables
        except Exception as exc:
            return _graceful_unavailable(out_dir, f"Could not attach to an open ETABS model: {exc}")

        try:
            available_tables = _parse_available_tables_result(database_tables.GetAvailableTables())
        except Exception as exc:
            return _graceful_unavailable(out_dir, f"ETABS available-table query failed: {exc}")

        bundle = load_contracts()
        registry = TableRegistry.from_dict(bundle.catalog("table_registry.yaml"))
        inventory = []
        matches = []
        matched_keys = set()
        for actual in sorted(set(available_tables)):
            key = registry.canonical_key_for_alias(actual)
            inventory.append({"actual_table_name": actual, "canonical_table_key": key, "checks_executed": False})
            if key:
                matched_keys.add(key)
                matches.append({"actual_table_name": actual, "canonical_table_key": key, "matched_by": "alias"})
        missing = [
            {"table_key": key, "expected_aliases": list(registry.aliases_for_key(key))}
            for key in registry.canonical_keys()
            if key not in matched_keys
        ]
        _write_json(out_dir / "etabs_table_inventory.json", {"tables": inventory, "manual_local_only": True})
        _write_json(out_dir / "table_registry_match_summary.json", {"matches": matches})
        _write_json(out_dir / "missing_expected_tables.json", {"missing": missing})

        tables = _build_canonical_tables_from_smoke(
            actual_tables=available_tables,
            database_tables=database_tables,
            registry=registry,
            sample_limit=max(0, args.sample_rows),
        )
        EtabsTableFitAuditor(bundle, tables).write_deep_fit_reports(out_dir)
        print(f"Wrote ETABS smoke inventory/header audit to {out_dir}")
        return 0
    except Exception as exc:  # pragma: no cover - unexpected runtime error
        print(f"Unexpected smoke runtime error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
