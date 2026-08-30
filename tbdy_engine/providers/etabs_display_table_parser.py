"""Compatibility facade for the canonical ETABS DatabaseTables parser.

Raw GetTableForDisplayArray ABI interpretation now lives in
``tbdy_engine.etabs.oapi.database_tables``. Existing provider imports are kept
stable during migration; this module owns no CSI invocation or raw tuple ABI.
"""
from tbdy_engine.etabs.oapi.database_tables import (
    ParsedDisplayTable,
    _extract_compact_six_item_etabs_shape,
    _rows_from_data,
    _table_data_length,
    parse_available_tables_result,
    parse_etabs_display_table_result,
)

__all__ = [
    "ParsedDisplayTable",
    "_extract_compact_six_item_etabs_shape",
    "_rows_from_data",
    "_table_data_length",
    "parse_available_tables_result",
    "parse_etabs_display_table_result",
]
