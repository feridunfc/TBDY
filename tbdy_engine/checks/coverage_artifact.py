"""Authoritative CoverageRow artifact helpers for the geometry slice.

This module only canonicalizes and serializes runtime CoverageRow objects
produced by CoverageBuilder. It does not rebuild coverage from adapter or
engineering-result output.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import TypeAlias

from tbdy_engine.coverage.models import CoverageRow

CoverageRowKey: TypeAlias = tuple[str, str, str]


def coverage_row_key(row: CoverageRow) -> CoverageRowKey:
    if not isinstance(row, CoverageRow):
        raise TypeError("coverage rows must contain CoverageRow objects")
    return (row.component_type, row.component_id, row.check_id)


def canonicalize_coverage_rows(rows: Iterable[CoverageRow]) -> tuple[CoverageRow, ...]:
    """Validate uniqueness and return the runtime rows in canonical order."""

    collected = tuple(rows)
    keys: set[CoverageRowKey] = set()
    for row in collected:
        key = coverage_row_key(row)
        if key in keys:
            raise ValueError(
                "Duplicate authoritative CoverageRow canonical key: "
                f"component_type={key[0]!r}, component_id={key[1]!r}, check_id={key[2]!r}"
            )
        keys.add(key)
    return tuple(sorted(collected, key=coverage_row_key))


def coverage_rows_payload(rows: Iterable[CoverageRow]) -> list[dict[str, object]]:
    """Return exact CoverageRow.as_dict() payloads in canonical row order."""

    return [row.as_dict() for row in canonicalize_coverage_rows(rows)]


__all__ = [
    "CoverageRowKey",
    "canonicalize_coverage_rows",
    "coverage_row_key",
    "coverage_rows_payload",
]
