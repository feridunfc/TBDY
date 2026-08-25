"""Source-bound ETABS auto-seismic direction evidence for TS500 stability use.

The factual source is the live-proven ETABS display table
``Load Pattern Definitions - Auto Seismic - TSC 2018``.  This provider captures
that table fail-closed and promotes only exact pattern-identity + direction-flag
bindings.  Case/pattern names are never parsed for X/Y meaning.

This module does not construct TS500 load combinations, read story results,
calculate a stability index, classify sway, or run analysis/design.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from tbdy_engine.design.columns.stability_action_basis import (
    StabilityActionSource,
    TS500_ACTION_E,
)
from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table


TABLE_AUTO_SEISMIC_TSC2018 = "Load Pattern Definitions - Auto Seismic - TSC 2018"
REQUIRED_DIRECTION_FIELDS = (
    "Name",
    "XDir",
    "XDirPlusE",
    "XDirMinusE",
    "YDir",
    "YDirPlusE",
    "YDirMinusE",
)
DIRECTION_AUTHORITY = "ETABS_AUTO_SEISMIC_TSC2018_DIRECTION_FLAGS"


class EtabsAutoSeismicDirectionProviderError(RuntimeError):
    """Raised when factual ETABS direction evidence is incomplete or malformed."""


@dataclass(frozen=True, slots=True)
class EtabsAutoSeismicDirectionRow:
    pattern_name: str
    flags: Mapping[str, bool]
    raw_row: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.pattern_name.strip() or self.pattern_name != self.pattern_name.strip():
            raise EtabsAutoSeismicDirectionProviderError("pattern_name must be canonical and nonblank")
        object.__setattr__(self, "flags", MappingProxyType(dict(self.flags)))
        object.__setattr__(self, "raw_row", MappingProxyType(dict(self.raw_row)))

    @property
    def x_selected(self) -> bool:
        return any(self.flags[name] for name in ("XDir", "XDirPlusE", "XDirMinusE"))

    @property
    def y_selected(self) -> bool:
        return any(self.flags[name] for name in ("YDir", "YDirPlusE", "YDirMinusE"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern_name": self.pattern_name,
            "flags": dict(self.flags),
            "x_selected": self.x_selected,
            "y_selected": self.y_selected,
            "raw_row": dict(self.raw_row),
        }


@dataclass(frozen=True, slots=True)
class EtabsAutoSeismicDirectionEvidence:
    field_keys: tuple[str, ...]
    rows: tuple[EtabsAutoSeismicDirectionRow, ...]
    runtime_capture_status: RuntimeCaptureStatus
    return_code: int | None
    row_count_reported: int | None
    selected_signature_reason: str
    status: str = "PROVEN_FACTUAL_ETABS_AUTO_SEISMIC_DIRECTION_TABLE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "table_name": TABLE_AUTO_SEISMIC_TSC2018,
            "field_keys": list(self.field_keys),
            "row_count": len(self.rows),
            "row_count_reported": self.row_count_reported,
            "runtime_capture_status": self.runtime_capture_status.value,
            "return_code": self.return_code,
            "selected_signature_reason": self.selected_signature_reason,
            "rows": [row.as_dict() for row in self.rows],
        }


@dataclass(frozen=True, slots=True)
class SeismicDirectionBinding:
    case_name: str
    pattern_name: str
    direction: str
    selected_flag_names: tuple[str, ...]
    source_refs: tuple[str, ...]
    authority: str = DIRECTION_AUTHORITY

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_name": self.case_name,
            "pattern_name": self.pattern_name,
            "direction": self.direction,
            "selected_flag_names": list(self.selected_flag_names),
            "source_refs": list(self.source_refs),
            "authority": self.authority,
        }


@dataclass(frozen=True, slots=True)
class SeismicDirectionBindingResolution:
    status: str
    bindings: tuple[SeismicDirectionBinding, ...]
    missing_pattern_names: tuple[str, ...]
    ambiguous_pattern_names: tuple[str, ...]
    source_refs: tuple[str, ...]
    authority: str = DIRECTION_AUTHORITY

    @property
    def complete(self) -> bool:
        return self.status == "PROVEN_ETABS_SEISMIC_DIRECTION_BINDING"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "complete": self.complete,
            "bindings": [item.as_dict() for item in self.bindings],
            "missing_pattern_names": list(self.missing_pattern_names),
            "ambiguous_pattern_names": list(self.ambiguous_pattern_names),
            "source_refs": list(self.source_refs),
            "authority": self.authority,
            "case_names_used_for_direction_inference": False,
        }


def _yes_no(value: Any, *, field: str, pattern_name: str) -> bool:
    text = str(value)
    if text == "Yes":
        return True
    if text == "No":
        return False
    raise EtabsAutoSeismicDirectionProviderError(
        f"{TABLE_AUTO_SEISMIC_TSC2018}.{pattern_name}.{field} must be exact Yes/No, got {value!r}"
    )


def capture_etabs_auto_seismic_direction_evidence(
    database_tables: Any,
) -> EtabsAutoSeismicDirectionEvidence:
    fetched = fetch_display_table(database_tables, TABLE_AUTO_SEISMIC_TSC2018, max_rows=None)
    if fetched.capture_status is not RuntimeCaptureStatus.FULL:
        raise EtabsAutoSeismicDirectionProviderError(
            f"{TABLE_AUTO_SEISMIC_TSC2018} requires FULL capture; got {fetched.capture_status.value}"
        )
    if fetched.parsed.return_code not in (0, None):
        raise EtabsAutoSeismicDirectionProviderError(
            f"{TABLE_AUTO_SEISMIC_TSC2018} returned nonzero code {fetched.parsed.return_code}"
        )
    fields = tuple(str(item) for item in fetched.parsed.field_keys)
    missing = tuple(name for name in REQUIRED_DIRECTION_FIELDS if name not in fields)
    if missing:
        raise EtabsAutoSeismicDirectionProviderError(
            "live-proven auto-seismic direction schema missing field(s): " + ", ".join(missing)
        )
    raw_rows = tuple(dict(row) for row in fetched.parsed.rows)
    if not raw_rows:
        raise EtabsAutoSeismicDirectionProviderError("auto-seismic direction table requires rows")
    if fetched.parsed.row_count_reported is not None and len(raw_rows) != int(fetched.parsed.row_count_reported):
        raise EtabsAutoSeismicDirectionProviderError(
            f"FULL row mismatch: captured={len(raw_rows)} reported={fetched.parsed.row_count_reported}"
        )

    rows: list[EtabsAutoSeismicDirectionRow] = []
    seen: set[str] = set()
    for raw_row in raw_rows:
        pattern_name = str(raw_row.get("Name", ""))
        if not pattern_name.strip() or pattern_name != pattern_name.strip():
            raise EtabsAutoSeismicDirectionProviderError("auto-seismic row Name must be canonical/nonblank")
        if pattern_name in seen:
            raise EtabsAutoSeismicDirectionProviderError(
                f"duplicate auto-seismic direction row for pattern {pattern_name!r}"
            )
        seen.add(pattern_name)
        flags = {
            field: _yes_no(raw_row[field], field=field, pattern_name=pattern_name)
            for field in REQUIRED_DIRECTION_FIELDS
            if field != "Name"
        }
        rows.append(
            EtabsAutoSeismicDirectionRow(
                pattern_name=pattern_name,
                flags=flags,
                raw_row=raw_row,
            )
        )

    return EtabsAutoSeismicDirectionEvidence(
        field_keys=fields,
        rows=tuple(rows),
        runtime_capture_status=fetched.capture_status,
        return_code=fetched.parsed.return_code,
        row_count_reported=fetched.parsed.row_count_reported,
        selected_signature_reason=fetched.selected_signature_reason,
    )


def bind_etabs_seismic_action_directions(
    action_sources: tuple[StabilityActionSource, ...],
    evidence: EtabsAutoSeismicDirectionEvidence,
) -> SeismicDirectionBindingResolution:
    """Bind promoted seismic actions to X/Y from exact ETABS direction flags."""
    seismic_sources = tuple(item for item in action_sources if item.action_role == TS500_ACTION_E)
    if not seismic_sources:
        raise EtabsAutoSeismicDirectionProviderError("at least one promoted TS500 E action source is required")
    if len({item.case_name for item in seismic_sources}) != len(seismic_sources):
        raise EtabsAutoSeismicDirectionProviderError("seismic action case names must be unique")
    rows_by_name = {row.pattern_name: row for row in evidence.rows}

    bindings: list[SeismicDirectionBinding] = []
    missing: list[str] = []
    ambiguous: list[str] = []
    for source in seismic_sources:
        row = rows_by_name.get(source.pattern_name)
        if row is None:
            missing.append(source.pattern_name)
            continue
        if row.x_selected == row.y_selected:
            ambiguous.append(source.pattern_name)
            continue
        direction = "X" if row.x_selected else "Y"
        selected_flags = tuple(name for name, selected in row.flags.items() if selected)
        bindings.append(
            SeismicDirectionBinding(
                case_name=source.case_name,
                pattern_name=source.pattern_name,
                direction=direction,
                selected_flag_names=selected_flags,
                source_refs=tuple(dict.fromkeys((
                    *source.source_refs,
                    f"ETABS:{TABLE_AUTO_SEISMIC_TSC2018}:{source.pattern_name}",
                    DIRECTION_AUTHORITY,
                ))),
            )
        )

    directions = {item.direction for item in bindings}
    if missing:
        status = "BLOCKED_ETABS_SEISMIC_DIRECTION_MISSING_PATTERN_ROW"
    elif ambiguous:
        status = "BLOCKED_ETABS_SEISMIC_DIRECTION_AMBIGUOUS_FLAGS"
    elif directions != {"X", "Y"}:
        status = "BLOCKED_ETABS_SEISMIC_DIRECTION_INCOMPLETE_AXES"
    else:
        status = "PROVEN_ETABS_SEISMIC_DIRECTION_BINDING"

    refs = tuple(dict.fromkeys(ref for item in bindings for ref in item.source_refs))
    return SeismicDirectionBindingResolution(
        status=status,
        bindings=tuple(bindings),
        missing_pattern_names=tuple(missing),
        ambiguous_pattern_names=tuple(ambiguous),
        source_refs=refs,
    )


__all__ = [
    "DIRECTION_AUTHORITY",
    "EtabsAutoSeismicDirectionEvidence",
    "EtabsAutoSeismicDirectionProviderError",
    "EtabsAutoSeismicDirectionRow",
    "REQUIRED_DIRECTION_FIELDS",
    "SeismicDirectionBinding",
    "SeismicDirectionBindingResolution",
    "TABLE_AUTO_SEISMIC_TSC2018",
    "bind_etabs_seismic_action_directions",
    "capture_etabs_auto_seismic_direction_evidence",
]
