"""Read-only ETABS provider for the strict VS6 column topology bundle.

This provider owns factual display-table semantics only. Regulatory free
length, sway classification, effective-length factors and any design authority
remain outside this layer. Supported live acquisition consumes session-bound
OAPI DatabaseTables facts and never receives raw DatabaseTables/SapModel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from tbdy_engine.etabs.oapi import fetch_display_table_from_session
from tbdy_engine.etabs.safety import EtabsVerifiedSession, RuntimeCaptureStatus
from tbdy_engine.features.column_shear_topology import (
    ColumnShearTopologyError,
    StrictColumnTopologyBundle,
    build_strict_column_topology,
)
from tbdy_engine.providers.etabs_display_table_fetcher import (
    DisplayTableFetchResult,
    fetch_display_table,
)


TABLE_POINT = "Point Object Connectivity"
TABLE_COLUMNS = "Column Object Connectivity"
TABLE_BEAMS = "Beam Object Connectivity"
TABLE_SECTIONS = "Frame Assignments - Section Properties"
TABLE_OFFSETS = "Frame Assignments - End Length Offsets"
TABLE_LOCAL_AXES = "Frame Assignments - Local Axes"
TABLE_RECTANGULAR = "Frame Section Property Definitions - Concrete Rectangular"

REQUIRED_TABLES: tuple[str, ...] = (
    TABLE_POINT,
    TABLE_COLUMNS,
    TABLE_BEAMS,
    TABLE_SECTIONS,
    TABLE_OFFSETS,
    TABLE_LOCAL_AXES,
    TABLE_RECTANGULAR,
)


@dataclass(frozen=True, slots=True)
class EtabsStrictColumnTopologyEvidence:
    topology: StrictColumnTopologyBundle
    table_row_counts: tuple[tuple[str, int], ...]
    authority: str = "ETABS_FACTUAL_STRICT_COLUMN_TOPOLOGY"

    def row_count_map(self) -> dict[str, int]:
        return dict(self.table_row_counts)


def _rows_from_fetched(
    fetched: DisplayTableFetchResult,
    table: str,
) -> tuple[dict[str, Any], ...]:
    if fetched.capture_status is not RuntimeCaptureStatus.FULL:
        raise ColumnShearTopologyError(
            f"{table} requires FULL capture; got {fetched.capture_status.value}"
        )
    if fetched.parsed.return_code not in (None, 0):
        raise ColumnShearTopologyError(
            f"{table} returned nonzero code {fetched.parsed.return_code}"
        )
    rows = tuple(dict(row) for row in fetched.parsed.rows)
    reported = fetched.parsed.row_count_reported
    if reported is not None and len(rows) != int(reported):
        raise ColumnShearTopologyError(
            f"{table} FULL row mismatch captured={len(rows)} reported={reported}"
        )
    return rows


def _fetch_full_rows(
    database_tables: Any,
    table: str,
    *,
    fetcher: Callable[..., Any] = fetch_display_table,
) -> tuple[dict[str, Any], ...]:
    return _rows_from_fetched(fetcher(database_tables, table, max_rows=None), table)


def _build_topology(
    rows: dict[str, tuple[dict[str, Any], ...]],
    *,
    reviewed_length_unit: str,
) -> EtabsStrictColumnTopologyEvidence:
    topology = build_strict_column_topology(
        point_rows=rows[TABLE_POINT],
        column_rows=rows[TABLE_COLUMNS],
        beam_rows=rows[TABLE_BEAMS],
        section_assignment_rows=rows[TABLE_SECTIONS],
        end_offset_rows=rows[TABLE_OFFSETS],
        local_axis_rows=rows[TABLE_LOCAL_AXES],
        rectangular_section_rows=rows[TABLE_RECTANGULAR],
        reviewed_length_unit=reviewed_length_unit,
    )
    return EtabsStrictColumnTopologyEvidence(
        topology=topology,
        table_row_counts=tuple((table, len(rows[table])) for table in REQUIRED_TABLES),
    )


def capture_etabs_strict_column_topology(
    database_tables: Any,
    *,
    reviewed_length_unit: str,
    fetcher: Callable[..., Any] = fetch_display_table,
) -> EtabsStrictColumnTopologyEvidence:
    """Compatibility path for an already-bounded DatabaseTables interface."""
    rows = {
        table: _fetch_full_rows(database_tables, table, fetcher=fetcher)
        for table in REQUIRED_TABLES
    }
    return _build_topology(rows, reviewed_length_unit=reviewed_length_unit)


def capture_etabs_strict_column_topology_from_session(
    session: EtabsVerifiedSession,
    *,
    reviewed_length_unit: str,
) -> EtabsStrictColumnTopologyEvidence:
    """Supported live path through OAPI -> safety -> gateway."""
    rows = {
        table: _rows_from_fetched(
            fetch_display_table_from_session(session, table, max_rows=None),
            table,
        )
        for table in REQUIRED_TABLES
    }
    return _build_topology(rows, reviewed_length_unit=reviewed_length_unit)


__all__ = [
    "EtabsStrictColumnTopologyEvidence",
    "REQUIRED_TABLES",
    "TABLE_BEAMS",
    "TABLE_COLUMNS",
    "TABLE_LOCAL_AXES",
    "TABLE_OFFSETS",
    "TABLE_POINT",
    "TABLE_RECTANGULAR",
    "TABLE_SECTIONS",
    "capture_etabs_strict_column_topology",
    "capture_etabs_strict_column_topology_from_session",
]
