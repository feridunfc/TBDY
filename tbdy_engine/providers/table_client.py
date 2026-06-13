"""Provider table-client protocol for C3 infrastructure.

No live ETABS integration is implemented in C3.
"""
from __future__ import annotations

from typing import Mapping, Protocol

from tbdy_engine.canonical_tables.table import CanonicalTable


class TableClient(Protocol):
    def list_tables(self) -> list[str]: ...

    def get_table(self, table_key: str) -> CanonicalTable: ...

    def get_units(self) -> Mapping[str, str]: ...
