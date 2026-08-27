"""Read-only schema probe for the candidate Concrete Frame Design combo table.

A successful table read is factual schema evidence only.  This module never
claims that the table is the authoritative selected design-combination
population; that semantic promotion requires live review outside this probe.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table

TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA = "Concrete Frame Design Load Combination Data"
SOURCE_NOT_PROVEN = "SOURCE_NOT_PROVEN"


@dataclass(frozen=True, slots=True)
class ConcreteDesignComboSelectionTableProbe:
    table_key: str
    return_code: int | None
    capture_status: str
    field_keys: tuple[str, ...]
    row_count: int
    row_count_reported: int | None
    combo_names: tuple[str, ...]
    combo_name_field_present: bool
    combo_type_or_selection_fields: tuple[str, ...]
    automatic_user_defined_fields: tuple[str, ...]
    selected_signature_name: str | None
    source_semantics_status: str = SOURCE_NOT_PROVEN


def probe_concrete_frame_design_combo_selection_table(database_tables: Any) -> ConcreteDesignComboSelectionTableProbe:
    fetched = fetch_display_table(
        database_tables,
        TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
        max_rows=None,
    )
    fields = tuple(str(item) for item in fetched.parsed.field_keys)
    field_set = set(fields)
    names = tuple(sorted({
        str(row.get("ComboName"))
        for row in fetched.parsed.rows
        if isinstance(row.get("ComboName"), str) and str(row.get("ComboName")).strip()
    })) if "ComboName" in field_set else ()
    selected_signature = dict(fetched.selected_signature)
    return ConcreteDesignComboSelectionTableProbe(
        table_key=TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
        return_code=fetched.parsed.return_code,
        capture_status=fetched.capture_status.value,
        field_keys=fields,
        row_count=len(fetched.parsed.rows),
        row_count_reported=fetched.parsed.row_count_reported,
        combo_names=names,
        combo_name_field_present="ComboName" in field_set,
        combo_type_or_selection_fields=tuple(
            key for key in fields if "combo" in key.lower() or "type" in key.lower() or "select" in key.lower()
        ),
        automatic_user_defined_fields=tuple(
            key for key in fields if "auto" in key.lower() or "user" in key.lower() or "design" in key.lower()
        ),
        selected_signature_name=(
            str(selected_signature.get("signature_name"))
            if selected_signature.get("signature_name") is not None else None
        ),
    )


__all__ = [
    "ConcreteDesignComboSelectionTableProbe",
    "SOURCE_NOT_PROVEN",
    "TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA",
    "probe_concrete_frame_design_combo_selection_table",
]
