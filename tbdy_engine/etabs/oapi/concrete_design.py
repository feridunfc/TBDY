"""Exact read-only CSI concrete-design ABI for current production consumers.

OAPI owns method invocation, positional tuple decoding, return-code validation,
and aligned-array validation. Semantic component binding, unit conversion,
EvidenceEpoch/provenance, and engineering meaning remain above this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import EtabsOAPIError

SUMMARY_RESULT_ARRAY_NAMES = (
    "FrameName",
    "MyOption",
    "Location",
    "PMMCombo",
    "PMMArea",
    "PMMRatio",
    "VMajorCombo",
    "AVMajor",
    "VMinorCombo",
    "AVMinor",
    "ErrorSummary",
    "WarningSummary",
)


@dataclass(frozen=True, slots=True)
class ConcreteDesignSectionFact:
    frame_name: str
    design_section: str
    raw_response: object


@dataclass(frozen=True, slots=True)
class ConcreteColumnSummaryRowFact:
    source_index: int
    frame_name: object
    my_option: object
    location: object
    pmm_combo: object
    pmm_area: object
    pmm_ratio: object
    vmajor_combo: object
    avmajor: object
    vminor_combo: object
    avminor: object
    error_summary: object
    warning_summary: object


@dataclass(frozen=True, slots=True)
class ConcreteColumnSummaryFact:
    requested_frame_name: str
    reported_row_count: int
    rows: tuple[ConcreteColumnSummaryRowFact, ...]
    raw_response: object


def _canonical_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsOAPIError(f"{label} must be a nonblank canonical string")
    return value


def decode_design_section_response(raw: object, *, frame_name: str) -> ConcreteDesignSectionFact:
    requested = _canonical_text(frame_name, "frame_name")
    if not isinstance(raw, (tuple, list)) or len(raw) != 2:
        raise EtabsOAPIError(
            f"DesignConcrete.GetDesignSection({requested!r}) returned unexpected shape: {raw!r}"
        )
    section_raw, ret = raw
    if isinstance(ret, bool) or not isinstance(ret, int) or ret != 0:
        raise EtabsOAPIError(
            f"DesignConcrete.GetDesignSection({requested!r}) returned nonzero/invalid code {ret!r}"
        )
    section = _canonical_text(section_raw, "design_section")
    return ConcreteDesignSectionFact(requested, section, raw)


def read_design_section(design_concrete: Any, frame_name: str) -> ConcreteDesignSectionFact:
    requested = _canonical_text(frame_name, "frame_name")
    getter = getattr(design_concrete, "GetDesignSection", None)
    if not callable(getter):
        raise EtabsOAPIError("DesignConcrete.GetDesignSection is unavailable")
    try:
        raw = getter(requested)
    except Exception as exc:
        raise EtabsOAPIError(
            f"DesignConcrete.GetDesignSection({requested!r}) raised {type(exc).__name__}: {exc}"
        ) from exc
    return decode_design_section_response(raw, frame_name=requested)


def decode_summary_results_column_response(
    raw: object,
    *,
    requested_frame_name: str,
) -> ConcreteColumnSummaryFact:
    requested = _canonical_text(requested_frame_name, "requested_frame_name")
    if not isinstance(raw, (tuple, list)) or len(raw) != 14:
        raise EtabsOAPIError(
            "DesignConcrete.GetSummaryResultsColumn returned unsupported Python COM shape; expected 14 values"
        )
    number_raw = raw[0]
    if isinstance(number_raw, bool):
        raise EtabsOAPIError("GetSummaryResultsColumn NumberItems must be an integer >= 0")
    try:
        number_items = int(number_raw)
    except (TypeError, ValueError) as exc:
        raise EtabsOAPIError("GetSummaryResultsColumn NumberItems must be an integer >= 0") from exc
    if number_items < 0:
        raise EtabsOAPIError("GetSummaryResultsColumn NumberItems must be >= 0")

    ret = raw[13]
    if isinstance(ret, bool) or not isinstance(ret, int) or ret != 0:
        raise EtabsOAPIError(
            f"DesignConcrete.GetSummaryResultsColumn returned nonzero/invalid code {ret!r}"
        )

    arrays = tuple(raw[1:13])
    if len(arrays) != len(SUMMARY_RESULT_ARRAY_NAMES) or any(
        not isinstance(values, (tuple, list)) for values in arrays
    ):
        raise EtabsOAPIError("GetSummaryResultsColumn returned non-array result members")
    lengths = tuple(len(values) for values in arrays)
    if any(length != number_items for length in lengths):
        raise EtabsOAPIError(
            f"GetSummaryResultsColumn NumberItems/array lengths differ: n={number_items} lengths={lengths}"
        )

    rows: list[ConcreteColumnSummaryRowFact] = []
    for index in range(number_items):
        values = [arrays[position][index] for position in range(len(SUMMARY_RESULT_ARRAY_NAMES))]
        returned_frame = _canonical_text(values[0], "FrameName")
        if returned_frame != requested:
            raise EtabsOAPIError(
                f"FrameName {returned_frame!r} does not equal requested canonical frame {requested!r}"
            )
        rows.append(
            ConcreteColumnSummaryRowFact(
                source_index=index,
                frame_name=values[0],
                my_option=values[1],
                location=values[2],
                pmm_combo=values[3],
                pmm_area=values[4],
                pmm_ratio=values[5],
                vmajor_combo=values[6],
                avmajor=values[7],
                vminor_combo=values[8],
                avminor=values[9],
                error_summary=values[10],
                warning_summary=values[11],
            )
        )
    return ConcreteColumnSummaryFact(
        requested_frame_name=requested,
        reported_row_count=number_items,
        rows=tuple(rows),
        raw_response=raw,
    )


def read_summary_results_column(
    design_concrete: Any,
    frame_name: str,
) -> ConcreteColumnSummaryFact:
    requested = _canonical_text(frame_name, "frame_name")
    getter = getattr(design_concrete, "GetSummaryResultsColumn", None)
    if not callable(getter):
        raise EtabsOAPIError("DesignConcrete.GetSummaryResultsColumn is unavailable")
    try:
        raw = getter(requested)
    except Exception as exc:
        raise EtabsOAPIError(
            f"DesignConcrete.GetSummaryResultsColumn({requested!r}) raised {type(exc).__name__}: {exc}"
        ) from exc
    return decode_summary_results_column_response(raw, requested_frame_name=requested)


__all__ = [
    "SUMMARY_RESULT_ARRAY_NAMES",
    "ConcreteColumnSummaryFact",
    "ConcreteColumnSummaryRowFact",
    "ConcreteDesignSectionFact",
    "decode_design_section_response",
    "decode_summary_results_column_response",
    "read_design_section",
    "read_summary_results_column",
]
