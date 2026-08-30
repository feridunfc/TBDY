"""Canonical low-level factual CSI ETABS OAPI boundary.

Engineering/regulatory meaning is intentionally excluded from this package.
Semantic providers consume typed facts exposed by the bounded modules here.
The small DatabaseTables session adapters below preserve the existing single
``database_tables`` implementation while keeping raw DatabaseTables capability
inside the gateway-owned STA operation.
"""
from __future__ import annotations

from tbdy_engine.etabs.safety import EtabsVerifiedSession, _execute_verified_read

from .database_tables import (
    DisplayTableFetchResult,
    fetch_display_table,
    fetch_display_table_for_output,
)


def fetch_display_table_from_session(
    session: EtabsVerifiedSession,
    table_name: str,
    *,
    max_rows: int | None = None,
) -> DisplayTableFetchResult:
    return _execute_verified_read(
        session,
        lambda _app, sap: fetch_display_table(
            sap.DatabaseTables,
            table_name,
            max_rows=max_rows,
        ),
        operation="oapi_database_tables_get_table_for_display_array",
    )


def fetch_display_table_for_output_from_session(
    session: EtabsVerifiedSession,
    table_name: str,
    *,
    preferred_output_case: str,
    max_rows: int | None = None,
) -> DisplayTableFetchResult:
    """Execute the safety-owned reversible display-selection transaction on STA."""
    return _execute_verified_read(
        session,
        lambda _app, sap: fetch_display_table_for_output(
            sap.DatabaseTables,
            table_name,
            preferred_output_case=preferred_output_case,
            max_rows=max_rows,
        ),
        operation="oapi_database_tables_selected_display_read",
    )


__all__ = [
    "concrete_design",
    "contracts",
    "database_tables",
    "load_definitions",
    "object_model",
    "response_combinations",
    "fetch_display_table_from_session",
    "fetch_display_table_for_output_from_session",
]
