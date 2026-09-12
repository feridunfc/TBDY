"""Exact CSI concrete-design ABI for current/live consumers.

OAPI owns method invocation, positional tuple decoding, return-code validation
where the CSI method actually returns one, and aligned-array validation.
Semantic component binding, unit conversion, EvidenceEpoch/provenance,
freshness, causal design qualification and engineering meaning remain above
this module. Session-bound reads execute only through the verified safety
bridge. The single concrete-design execution primitive uses the same approved
B4T bounded mutation transport as B5; it issues no design lineage itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Sequence

from etabs_gateway.mutation_transport import (
    _B4T_MUTATION_TRANSPORT_KEY,
    _execute_bounded_model_mutation,
)

from tbdy_engine.etabs.safety import (
    EtabsUnitSnapshot,
    EtabsVerifiedSession,
    _execute_verified_read,
    read_etabs_unit_snapshot,
)

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
CONCRETE_DESIGN_CODE_API = "DesignConcrete.GetCode"
CONCRETE_DESIGN_CODE_FACT_CONTRACT = "ETABS_CONCRETE_DESIGN_CODE_FACT_V1"
CONCRETE_DESIGN_CODE_REF_PREFIX = "etabs-concrete-design-code:sha256:"
CONCRETE_DESIGN_RESULTS_AVAILABLE_API = "DesignConcrete.GetResultsAvailable"
CONCRETE_DESIGN_START_FACT_CONTRACT = "ETABS_CONCRETE_DESIGN_START_FACT_V1"
CONCRETE_DESIGN_EXECUTION_EVIDENCE_PREFIX = "etabs-concrete-design-execution:sha256:"


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return CONCRETE_DESIGN_EXECUTION_EVIDENCE_PREFIX + hashlib.sha256(encoded).hexdigest()


def _return_code(value: object, *, method: str) -> int:
    if type(value) is int:
        return int(value)
    if isinstance(value, (tuple, list)):
        candidates = tuple(int(item) for item in value if type(item) is int)
        if len(candidates) == 1:
            return candidates[0]
    raise EtabsOAPIError(f"{method} returned unsupported return-code ABI shape: {value!r}")


@dataclass(frozen=True, slots=True)
class ConcreteDesignSectionFact:
    frame_name: str
    design_section: str
    raw_response: object


@dataclass(frozen=True, slots=True)
class ConcreteDesignCodeFact:
    """Exact factual current concrete-design code returned by CSI ``GetCode``."""

    code_name: str
    raw_response: tuple[object, object]
    design_code_ref: str = field(init=False)
    source_api: str = CONCRETE_DESIGN_CODE_API
    contract: str = CONCRETE_DESIGN_CODE_FACT_CONTRACT

    def __post_init__(self) -> None:
        code_name = _canonical_text(self.code_name, "concrete design code name")
        if self.source_api != CONCRETE_DESIGN_CODE_API:
            raise EtabsOAPIError("concrete design code source API mismatch")
        if self.contract != CONCRETE_DESIGN_CODE_FACT_CONTRACT:
            raise EtabsOAPIError("concrete design code fact contract mismatch")
        if not isinstance(self.raw_response, tuple) or len(self.raw_response) != 2:
            raise EtabsOAPIError("DesignConcrete.GetCode raw response must preserve the exact 2-tuple")
        object.__setattr__(self, "code_name", code_name)
        payload = json.dumps(
            {
                "contract": self.contract,
                "source_api": self.source_api,
                "code_name": code_name,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        object.__setattr__(
            self,
            "design_code_ref",
            CONCRETE_DESIGN_CODE_REF_PREFIX + hashlib.sha256(payload).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class ConcreteDesignResultsAvailabilityFact:
    """Direct Boolean fact from ``DesignConcrete.GetResultsAvailable``."""

    results_available: bool
    raw_response: object
    source_api: str = CONCRETE_DESIGN_RESULTS_AVAILABLE_API

    def __post_init__(self) -> None:
        if type(self.results_available) is not bool:
            raise EtabsOAPIError(
                "DesignConcrete.GetResultsAvailable factual value must be boolean"
            )
        if type(self.raw_response) is not bool or self.raw_response is not self.results_available:
            raise EtabsOAPIError(
                "DesignConcrete.GetResultsAvailable raw response must preserve the exact Boolean fact"
            )
        if self.source_api != CONCRETE_DESIGN_RESULTS_AVAILABLE_API:
            raise EtabsOAPIError(
                "concrete design-results availability source API mismatch"
            )


@dataclass(frozen=True, slots=True)
class ConcreteDesignStartFact:
    """Exact factual return from the one low-level StartDesign invocation."""

    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = CONCRETE_DESIGN_START_FACT_CONTRACT

    def __post_init__(self) -> None:
        if type(self.return_code) is not int:
            raise EtabsOAPIError("StartDesign return_code must be exact int")
        if self.contract != CONCRETE_DESIGN_START_FACT_CONTRACT:
            raise EtabsOAPIError("concrete StartDesign fact contract mismatch")
        object.__setattr__(
            self,
            "evidence_ref",
            _digest({"contract": self.contract, "return_code": self.return_code}),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


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


@dataclass(frozen=True, slots=True)
class ConcreteColumnSummaryBatchFact:
    """One bounded factual batch with source-unit snapshots bracketing all reads."""

    units_before: EtabsUnitSnapshot
    summaries: tuple[ConcreteColumnSummaryFact, ...]
    units_after: EtabsUnitSnapshot


def _canonical_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsOAPIError(f"{label} must be a nonblank canonical string")
    return value


def _canonical_names(values: Sequence[str], label: str) -> tuple[str, ...]:
    names = tuple(_canonical_text(item, label) for item in values)
    if not names or len(names) != len(set(names)):
        raise EtabsOAPIError(f"{label} must be a nonempty unique sequence")
    return names


def decode_design_code_response(raw: object) -> ConcreteDesignCodeFact:
    """Decode CSI ``cDesignConcrete.GetCode(ref string CodeName) -> int`` exactly.

    The supported Python COM ABI is the exact two-member tuple
    ``(CodeName, return_code)``. Only integer return code zero authorizes a fact.
    """
    if not isinstance(raw, tuple) or len(raw) != 2:
        raise EtabsOAPIError(
            "DesignConcrete.GetCode returned unsupported Python COM shape; expected exact (CodeName, return_code) tuple"
        )
    code_raw, ret = raw
    if isinstance(ret, bool) or not isinstance(ret, int) or ret != 0:
        raise EtabsOAPIError(
            f"DesignConcrete.GetCode returned nonzero/invalid code {ret!r}"
        )
    code_name = _canonical_text(code_raw, "concrete design code name")
    return ConcreteDesignCodeFact(
        code_name=code_name,
        raw_response=raw,
    )


def read_design_code(design_concrete: Any) -> ConcreteDesignCodeFact:
    getter = getattr(design_concrete, "GetCode", None)
    if not callable(getter):
        raise EtabsOAPIError("DesignConcrete.GetCode is unavailable")
    try:
        raw = getter()
    except Exception as exc:
        raise EtabsOAPIError(
            f"DesignConcrete.GetCode raised {type(exc).__name__}: {exc}"
        ) from exc
    return decode_design_code_response(raw)


def decode_results_available_response(
    raw: object,
) -> ConcreteDesignResultsAvailabilityFact:
    """Decode the documented direct-Boolean CSI return shape exactly."""

    if type(raw) is not bool:
        raise EtabsOAPIError(
            "DesignConcrete.GetResultsAvailable returned unsupported Python COM "
            f"shape {raw!r}; CSI contract is a direct Boolean return with no "
            "separate integer return code"
        )
    return ConcreteDesignResultsAvailabilityFact(
        results_available=raw,
        raw_response=raw,
    )


def read_results_available(
    design_concrete: Any,
) -> ConcreteDesignResultsAvailabilityFact:
    getter = getattr(design_concrete, "GetResultsAvailable", None)
    if not callable(getter):
        raise EtabsOAPIError("DesignConcrete.GetResultsAvailable is unavailable")
    try:
        raw = getter()
    except Exception as exc:
        raise EtabsOAPIError(
            "DesignConcrete.GetResultsAvailable raised "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return decode_results_available_response(raw)


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


def read_design_code_from_session(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 30.0,
) -> ConcreteDesignCodeFact:
    """Read the current concrete design code through the verified safety boundary."""
    return _execute_verified_read(
        session,
        lambda _app, sap: read_design_code(sap.DesignConcrete),
        operation="oapi_design_concrete_get_code",
        timeout_seconds=timeout_seconds,
    )


def read_results_available_from_session(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 30.0,
) -> ConcreteDesignResultsAvailabilityFact:
    return _execute_verified_read(
        session,
        lambda _app, sap: read_results_available(sap.DesignConcrete),
        operation="oapi_design_concrete_get_results_available",
        timeout_seconds=timeout_seconds,
    )


def start_concrete_design_from_session(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 300.0,
) -> ConcreteDesignStartFact:
    """Invoke exactly one factual ``DesignConcrete.StartDesign`` operation."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    def execute(model_api: Any) -> ConcreteDesignStartFact:
        starter = getattr(model_api.DesignConcrete, "StartDesign", None)
        if not callable(starter):
            raise EtabsOAPIError("DesignConcrete.StartDesign is unavailable")
        raw = starter()
        return ConcreteDesignStartFact(
            return_code=_return_code(raw, method="DesignConcrete.StartDesign")
        )

    return _execute_bounded_model_mutation(
        session._gateway_session,  # noqa: SLF001 - trusted OAPI -> B4T boundary
        execute,
        operation="oapi_design_concrete_start_design",
        timeout_seconds=timeout,
        _transport_key=_B4T_MUTATION_TRANSPORT_KEY,
    )


def read_design_section_from_session(
    session: EtabsVerifiedSession,
    frame_name: str,
) -> ConcreteDesignSectionFact:
    return _execute_verified_read(
        session,
        lambda _app, sap: read_design_section(sap.DesignConcrete, frame_name),
        operation="oapi_design_concrete_get_design_section",
    )


def read_design_sections_from_session(
    session: EtabsVerifiedSession,
    frame_names: Sequence[str],
) -> tuple[ConcreteDesignSectionFact, ...]:
    names = _canonical_names(frame_names, "frame_name")
    return _execute_verified_read(
        session,
        lambda _app, sap: tuple(read_design_section(sap.DesignConcrete, name) for name in names),
        operation="oapi_design_concrete_get_design_sections",
    )


def read_summary_results_column_from_session(
    session: EtabsVerifiedSession,
    frame_name: str,
    *,
    timeout_seconds: float = 30.0,
) -> ConcreteColumnSummaryFact:
    return _execute_verified_read(
        session,
        lambda _app, sap: read_summary_results_column(sap.DesignConcrete, frame_name),
        operation="oapi_design_concrete_get_summary_results_column",
        timeout_seconds=timeout_seconds,
    )


def read_summary_results_columns_with_units_from_session(
    session: EtabsVerifiedSession,
    frame_names: Sequence[str],
) -> ConcreteColumnSummaryBatchFact:
    """Read all requested column summaries between exact safety-owned unit snapshots."""
    names = _canonical_names(frame_names, "frame_name")

    def acquire(_app: object, sap: Any) -> ConcreteColumnSummaryBatchFact:
        before = read_etabs_unit_snapshot(sap)
        facts = tuple(read_summary_results_column(sap.DesignConcrete, name) for name in names)
        after = read_etabs_unit_snapshot(sap)
        return ConcreteColumnSummaryBatchFact(before, facts, after)

    return _execute_verified_read(
        session,
        acquire,
        operation="oapi_design_concrete_summary_batch_with_units",
    )


__all__ = [
    "CONCRETE_DESIGN_CODE_API",
    "CONCRETE_DESIGN_CODE_FACT_CONTRACT",
    "CONCRETE_DESIGN_CODE_REF_PREFIX",
    "CONCRETE_DESIGN_EXECUTION_EVIDENCE_PREFIX",
    "CONCRETE_DESIGN_RESULTS_AVAILABLE_API",
    "CONCRETE_DESIGN_START_FACT_CONTRACT",
    "SUMMARY_RESULT_ARRAY_NAMES",
    "ConcreteColumnSummaryBatchFact",
    "ConcreteColumnSummaryFact",
    "ConcreteColumnSummaryRowFact",
    "ConcreteDesignCodeFact",
    "ConcreteDesignResultsAvailabilityFact",
    "ConcreteDesignSectionFact",
    "ConcreteDesignStartFact",
    "decode_design_code_response",
    "decode_design_section_response",
    "decode_results_available_response",
    "decode_summary_results_column_response",
    "read_design_code",
    "read_design_code_from_session",
    "read_design_section",
    "read_design_section_from_session",
    "read_design_sections_from_session",
    "read_results_available",
    "read_results_available_from_session",
    "read_summary_results_column",
    "read_summary_results_column_from_session",
    "read_summary_results_columns_with_units_from_session",
    "start_concrete_design_from_session",
]
