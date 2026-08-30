"""Compatibility facade for canonical read-only ETABS DatabaseTables access.

Exact GetTableForDisplayArray invocation, signature probing, mutated COM output
normalization and transactional display-table reads now live in
``tbdy_engine.etabs.oapi.database_tables``. This provider path remains stable
for existing semantic consumers while owning no raw CSI ABI.
"""
from tbdy_engine.etabs.oapi.database_tables import (
    DISPLAY_TABLE_SIGNATURES,
    DisplayTableFetchResult,
    fetch_display_table,
    fetch_display_table_for_output,
    select_output_for_display,
    try_get_display_table,
)

__all__ = [
    "DISPLAY_TABLE_SIGNATURES",
    "DisplayTableFetchResult",
    "fetch_display_table",
    "fetch_display_table_for_output",
    "select_output_for_display",
    "try_get_display_table",
]
