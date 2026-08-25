"""Read-only ETABS reinforcing-bar catalog acquisition for VS6.

The provider captures the factual ``Reinforcing Bar Sizes`` display table and
keeps the raw field names/rows intact. A generic explicit promotion boundary is
kept for fixtures/version experiments, while the production path can use the
live-proven ETABS schema ``Name`` + ``Diameter`` and a separately reviewed
length-unit contract. Any schema drift fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from tbdy_engine.design.columns.rebar_catalog import RebarCatalog, build_rebar_catalog_from_rows
from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table


TABLE_REINFORCING_BAR_SIZES = "Reinforcing Bar Sizes"
ETABS_REBAR_NAME_FIELD = "Name"
ETABS_REBAR_DIAMETER_FIELD = "Diameter"


class EtabsRebarCatalogProviderError(RuntimeError):
    """Raised when factual ETABS reinforcing-bar catalog evidence is incomplete."""


@dataclass(frozen=True, slots=True)
class EtabsRebarCatalogEvidence:
    table_name: str
    field_keys: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]
    runtime_capture_status: RuntimeCaptureStatus
    return_code: int | None
    row_count_reported: int | None
    selected_signature_reason: str
    status: str = "PROVEN_FACTUAL_REBAR_CATALOG_TABLE"

    def __post_init__(self) -> None:
        if self.table_name != TABLE_REINFORCING_BAR_SIZES:
            raise EtabsRebarCatalogProviderError(
                f"unexpected rebar catalog source table: {self.table_name}"
            )
        if self.runtime_capture_status is not RuntimeCaptureStatus.FULL:
            raise EtabsRebarCatalogProviderError(
                f"{self.table_name} requires FULL acquisition; got {self.runtime_capture_status.value}"
            )
        if self.return_code not in (None, 0):
            raise EtabsRebarCatalogProviderError(
                f"{self.table_name} returned nonzero code {self.return_code}"
            )
        fields = tuple(str(item) for item in self.field_keys)
        if not fields or len(fields) != len(set(fields)):
            raise EtabsRebarCatalogProviderError("rebar catalog field_keys must be nonempty and unique")
        object.__setattr__(self, "field_keys", fields)

        frozen_rows = tuple(MappingProxyType(dict(row)) for row in self.rows)
        if not frozen_rows:
            raise EtabsRebarCatalogProviderError("rebar catalog requires at least one factual row")
        if self.row_count_reported is not None and len(frozen_rows) != int(self.row_count_reported):
            raise EtabsRebarCatalogProviderError(
                f"rebar catalog FULL row mismatch: captured={len(frozen_rows)} reported={self.row_count_reported}"
            )
        object.__setattr__(self, "rows", frozen_rows)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "table_name": self.table_name,
            "field_keys": list(self.field_keys),
            "row_count": len(self.rows),
            "row_count_reported": self.row_count_reported,
            "runtime_capture_status": self.runtime_capture_status.value,
            "return_code": self.return_code,
            "selected_signature_reason": self.selected_signature_reason,
            "rows": [dict(row) for row in self.rows],
        }


def capture_etabs_rebar_catalog_evidence(
    database_tables: Any,
) -> EtabsRebarCatalogEvidence:
    """Capture the full factual ETABS reinforcing-bar-size table without semantic guessing."""
    fetch = fetch_display_table(
        database_tables,
        TABLE_REINFORCING_BAR_SIZES,
        max_rows=None,
    )
    return EtabsRebarCatalogEvidence(
        table_name=TABLE_REINFORCING_BAR_SIZES,
        field_keys=tuple(fetch.parsed.field_keys),
        rows=tuple(dict(row) for row in fetch.parsed.rows),
        runtime_capture_status=fetch.capture_status,
        return_code=fetch.parsed.return_code,
        row_count_reported=fetch.parsed.row_count_reported,
        selected_signature_reason=fetch.selected_signature_reason,
    )


def promote_etabs_rebar_catalog(
    evidence: EtabsRebarCatalogEvidence,
    *,
    name_field: str,
    diameter_field: str,
    diameter_unit: str,
    source_name: str,
) -> RebarCatalog:
    """Promote factual rows after an explicit semantic field/unit binding."""
    if name_field not in evidence.field_keys:
        raise EtabsRebarCatalogProviderError(
            f"reviewed name_field={name_field!r} not present in factual field_keys"
        )
    if diameter_field not in evidence.field_keys:
        raise EtabsRebarCatalogProviderError(
            f"reviewed diameter_field={diameter_field!r} not present in factual field_keys"
        )
    return build_rebar_catalog_from_rows(
        evidence.rows,
        name_field=name_field,
        diameter_field=diameter_field,
        diameter_unit=diameter_unit,
        source_name=source_name,
    )


def promote_live_proven_etabs_rebar_catalog(
    evidence: EtabsRebarCatalogEvidence,
    *,
    reviewed_length_unit: str,
    source_name: str,
) -> RebarCatalog:
    """Promote the live-proven ETABS ``Name``/``Diameter`` schema fail-closed.

    The field semantics are no longer caller-selectable in the production path:
    they were verified on the accepted ETABS 23.2.0 live table.  The numerical
    unit is still a reviewed session/database contract and must be supplied
    explicitly. Future ETABS schema drift therefore blocks instead of guessing.
    """
    required = {ETABS_REBAR_NAME_FIELD, ETABS_REBAR_DIAMETER_FIELD}
    missing = required - set(evidence.field_keys)
    if missing:
        raise EtabsRebarCatalogProviderError(
            "live-proven ETABS rebar schema missing required field(s): "
            + ", ".join(sorted(missing))
        )
    if reviewed_length_unit not in {"m", "mm"}:
        raise EtabsRebarCatalogProviderError(
            "reviewed_length_unit for Reinforcing Bar Sizes.Diameter must be explicitly 'm' or 'mm'"
        )
    return promote_etabs_rebar_catalog(
        evidence,
        name_field=ETABS_REBAR_NAME_FIELD,
        diameter_field=ETABS_REBAR_DIAMETER_FIELD,
        diameter_unit=reviewed_length_unit,
        source_name=source_name,
    )


__all__ = [
    "TABLE_REINFORCING_BAR_SIZES",
    "ETABS_REBAR_NAME_FIELD",
    "ETABS_REBAR_DIAMETER_FIELD",
    "EtabsRebarCatalogEvidence",
    "EtabsRebarCatalogProviderError",
    "capture_etabs_rebar_catalog_evidence",
    "promote_etabs_rebar_catalog",
    "promote_live_proven_etabs_rebar_catalog",
]
