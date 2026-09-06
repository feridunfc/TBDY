"""B6-P0 concrete-design freshness preflight.

This module owns only the bounded causal orchestration needed to classify the
pre-design concrete-column result state as ABSENT, PRESENT, or AMBIGUOUS.

It does not call StartDesign, does not create DesignStateIdentity or
DesignResultIdentity, does not select reinforcement, and does not own ETABS
transport/session/COM capability. Factual CSI reads remain in the OAPI layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import ntpath
from typing import Sequence

from tbdy_engine.etabs.oapi.concrete_design import (
    CONCRETE_DESIGN_RESULTS_AVAILABLE_API,
    ConcreteDesignResultsAvailabilityFact,
    read_results_available_from_session,
    read_summary_results_column_from_session,
)
from tbdy_engine.etabs.safety import reread_verified_session_identity
from tbdy_engine.features.column_concrete_design_evidence import (
    ColumnTopologyEvidenceEnvelope,
)
from tbdy_engine.integration.etabs_analysis_lineage import (
    AnalysisLineageQualification,
    AnalysisLineageQualificationError,
)
from tbdy_engine.integration.etabs_scratch_lifecycle import OwnedScratchContext
from tbdy_engine.integration.live_etabs_acquisition_context import (
    TrustedLiveAcquisitionContext,
)

DESIGN_PREFLIGHT_CONTRACT = "TBDY_B6_CONCRETE_DESIGN_PREFLIGHT_V1"
PRE_DESIGN_COLUMN_CENSUS_CONTRACT = "TBDY_B6_PRE_DESIGN_COLUMN_ROW_CENSUS_V1"
PRE_DESIGN_COLUMN_CENSUS_REF_PREFIX = "b6-pre-design-column-census:sha256:"
DESIGN_PREFLIGHT_REF_PREFIX = "b6-design-preflight:sha256:"

_CENSUS_FACTORY_KEY = object()
_PREFLIGHT_FACTORY_KEY = object()


class DesignPreflightError(RuntimeError):
    """Fail-closed B6-P0 binding/preflight error."""


class DesignPreflightStatus(StrEnum):
    ABSENT = "ABSENT"
    PRESENT = "PRESENT"
    AMBIGUOUS = "AMBIGUOUS"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise DesignPreflightError(f"{label} must be a nonblank canonical string")
    return value


def _refs(
    values: Sequence[str],
    label: str,
    *,
    required: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{label} must be a sequence of strings")
    refs = tuple(sorted({_text(value, label) for value in values}))
    if required and not refs:
        raise DesignPreflightError(f"{label} must be nonempty")
    return refs


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _digest(prefix: str, payload: object) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _model_path(value: object, label: str) -> str:
    text = _text(value, label)
    return ntpath.normcase(ntpath.normpath(text))


@dataclass(frozen=True, slots=True)
class ExpectedColumnDesignResultPresence:
    """One factual pre-design result-row presence observation."""

    component_id: str
    frame_name: str
    reported_row_count: int | None
    row_present: bool | None
    source_ref: str | None
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        object.__setattr__(self, "frame_name", _text(self.frame_name, "frame_name"))
        if self.reported_row_count is None:
            if self.row_present is not None or self.source_ref is not None:
                raise DesignPreflightError(
                    "incomplete column presence fact cannot carry positive row/source facts"
                )
            object.__setattr__(
                self,
                "diagnostic",
                _text(self.diagnostic, "presence diagnostic"),
            )
            return

        count = self.reported_row_count
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise DesignPreflightError(
                "reported_row_count must be an integer >= 0 or None"
            )
        if type(self.row_present) is not bool:
            raise DesignPreflightError(
                "complete column presence fact requires a boolean row_present"
            )
        if self.row_present is not (count > 0):
            raise DesignPreflightError(
                "row_present must equal reported_row_count > 0"
            )
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))
        if self.diagnostic is not None:
            raise DesignPreflightError(
                "complete column presence fact cannot carry a failure diagnostic"
            )

    @property
    def complete(self) -> bool:
        return self.reported_row_count is not None

    def semantic_dict(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "frame_name": self.frame_name,
            "reported_row_count": self.reported_row_count,
            "row_present": self.row_present,
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True, slots=True, init=False)
class PreDesignExpectedColumnCensus:
    """Factory-owned exact expected-column pre-design row-presence population."""

    entries: tuple[ExpectedColumnDesignResultPresence, ...]
    census_ref: str
    source_refs: tuple[str, ...]
    contract: str

    def __init__(
        self,
        *,
        _token: object = None,
        entries: Sequence[ExpectedColumnDesignResultPresence],
        source_refs: Sequence[str],
        contract: str = PRE_DESIGN_COLUMN_CENSUS_CONTRACT,
    ) -> None:
        if _token is not _CENSUS_FACTORY_KEY:
            raise TypeError(
                "PreDesignExpectedColumnCensus is factory-created only"
            )
        if contract != PRE_DESIGN_COLUMN_CENSUS_CONTRACT:
            raise DesignPreflightError("pre-design column census contract mismatch")
        rows = tuple(entries)
        if not rows or any(
            not isinstance(item, ExpectedColumnDesignResultPresence) for item in rows
        ):
            raise DesignPreflightError(
                "pre-design column census requires typed expected-column entries"
            )
        rows = tuple(sorted(rows, key=lambda item: (item.component_id, item.frame_name)))
        component_ids = tuple(item.component_id for item in rows)
        frame_names = tuple(item.frame_name for item in rows)
        if len(component_ids) != len(set(component_ids)):
            raise DesignPreflightError("expected column component ids must be unique")
        if len(frame_names) != len(set(frame_names)):
            raise DesignPreflightError("expected column frame names must be unique")
        refs = _refs(source_refs, "census source_ref", required=True)
        payload = {
            "contract": contract,
            "entries": [item.semantic_dict() for item in rows],
        }
        object.__setattr__(self, "entries", rows)
        object.__setattr__(
            self,
            "census_ref",
            _digest(PRE_DESIGN_COLUMN_CENSUS_REF_PREFIX, payload),
        )
        object.__setattr__(self, "source_refs", refs)
        object.__setattr__(self, "contract", contract)

    @property
    def complete(self) -> bool:
        return all(item.complete for item in self.entries)

    @property
    def any_rows_present(self) -> bool:
        return any(item.row_present is True for item in self.entries)

    @property
    def all_rows_absent(self) -> bool:
        return self.complete and all(item.row_present is False for item in self.entries)

    @property
    def expected_component_ids(self) -> tuple[str, ...]:
        return tuple(item.component_id for item in self.entries)

    @property
    def expected_frame_names(self) -> tuple[str, ...]:
        return tuple(item.frame_name for item in self.entries)


@dataclass(frozen=True, slots=True, init=False)
class DesignPreflightSnapshot:
    """Factory-owned B6-P0 freshness gate; not a design-result identity."""

    status: DesignPreflightStatus
    source_model_ref: str
    analysis_result_ref: str
    analysis_lineage_qualification_ref: str
    ownership_proof_ref: str
    model_fingerprint: str
    evidence_epoch_id: str
    availability: ConcreteDesignResultsAvailabilityFact | None
    column_census: PreDesignExpectedColumnCensus
    blockers: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    preflight_ref: str
    contract: str

    def __init__(
        self,
        *,
        _token: object = None,
        status: DesignPreflightStatus,
        source_model_ref: str,
        analysis_result_ref: str,
        analysis_lineage_qualification_ref: str,
        ownership_proof_ref: str,
        model_fingerprint: str,
        evidence_epoch_id: str,
        availability: ConcreteDesignResultsAvailabilityFact | None,
        column_census: PreDesignExpectedColumnCensus,
        blockers: Sequence[str],
        provenance_refs: Sequence[str],
        contract: str = DESIGN_PREFLIGHT_CONTRACT,
    ) -> None:
        if _token is not _PREFLIGHT_FACTORY_KEY:
            raise TypeError("DesignPreflightSnapshot is factory-created only")
        if not isinstance(status, DesignPreflightStatus):
            raise TypeError("status must be DesignPreflightStatus")
        if contract != DESIGN_PREFLIGHT_CONTRACT:
            raise DesignPreflightError("design preflight contract mismatch")
        if availability is not None and not isinstance(
            availability, ConcreteDesignResultsAvailabilityFact
        ):
            raise TypeError(
                "availability must be ConcreteDesignResultsAvailabilityFact or None"
            )
        if not isinstance(column_census, PreDesignExpectedColumnCensus):
            raise TypeError("column_census must be PreDesignExpectedColumnCensus")
        refs = _refs(provenance_refs, "preflight provenance_ref", required=True)
        normalized_blockers = _refs(blockers, "preflight blocker")
        if status is DesignPreflightStatus.ABSENT and normalized_blockers:
            raise DesignPreflightError("ABSENT preflight cannot carry blockers")
        if status is not DesignPreflightStatus.ABSENT and not normalized_blockers:
            raise DesignPreflightError(
                f"{status.value} preflight requires at least one blocker"
            )
        fields = {
            "source_model_ref": _text(source_model_ref, "source_model_ref"),
            "analysis_result_ref": _text(analysis_result_ref, "analysis_result_ref"),
            "analysis_lineage_qualification_ref": _text(
                analysis_lineage_qualification_ref,
                "analysis_lineage_qualification_ref",
            ),
            "ownership_proof_ref": _text(ownership_proof_ref, "ownership_proof_ref"),
            "model_fingerprint": _text(model_fingerprint, "model_fingerprint"),
            "evidence_epoch_id": _text(evidence_epoch_id, "evidence_epoch_id"),
        }
        payload = {
            "contract": contract,
            "status": status.value,
            **fields,
            "availability": (
                None
                if availability is None
                else {
                    "source_api": availability.source_api,
                    "results_available": availability.results_available,
                }
            ),
            "column_census_ref": column_census.census_ref,
            "blockers": list(normalized_blockers),
        }
        for name, value in fields.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "column_census", column_census)
        object.__setattr__(self, "blockers", normalized_blockers)
        object.__setattr__(self, "provenance_refs", refs)
        object.__setattr__(
            self,
            "preflight_ref",
            _digest(DESIGN_PREFLIGHT_REF_PREFIX, payload),
        )
        object.__setattr__(self, "contract", contract)

    @property
    def absent(self) -> bool:
        return self.status is DesignPreflightStatus.ABSENT


def _validate_bindings(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    analysis_lineage: AnalysisLineageQualification,
    topology: ColumnTopologyEvidenceEnvelope,
    timeout_seconds: float,
) -> object:
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    if not isinstance(owned_scratch, OwnedScratchContext):
        raise TypeError("owned_scratch must be OwnedScratchContext")
    if not isinstance(analysis_lineage, AnalysisLineageQualification):
        raise TypeError("analysis_lineage must be AnalysisLineageQualification")
    if not isinstance(topology, ColumnTopologyEvidenceEnvelope):
        raise TypeError("topology must be ColumnTopologyEvidenceEnvelope")

    try:
        analysis_result = analysis_lineage.require_qualified_result()
    except AnalysisLineageQualificationError as exc:
        raise DesignPreflightError(
            "B6 preflight requires a QUALIFIED parent AnalysisResultIdentity"
        ) from exc

    source_ref = context.source_model_identity.source_model_ref
    if analysis_result.source_model_ref != source_ref:
        raise DesignPreflightError(
            "qualified parent analysis result belongs to a different source-model root"
        )
    if owned_scratch.source_model_identity.source_model_ref != source_ref:
        raise DesignPreflightError(
            "OwnedScratchContext belongs to a different source-model root"
        )

    ownership_proof_ref = _text(
        owned_scratch.ownership_proof_ref,
        "owned_scratch.ownership_proof_ref",
    )
    if ownership_proof_ref not in analysis_lineage.capture_provenance_refs:
        raise DesignPreflightError(
            "qualified B5 lineage is not bound to this exact OwnedScratchContext"
        )

    try:
        context.require_model_epoch(
            model_fingerprint=topology.model_fingerprint,
            evidence_epoch_id=topology.evidence_epoch_id,
        )
    except Exception as exc:
        raise DesignPreflightError(
            "expected-column topology does not belong to the active acquisition context"
        ) from exc

    try:
        active_identity = reread_verified_session_identity(
            context.verified_session,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        raise DesignPreflightError(
            "active ETABS model path could not be re-read for B6 preflight"
        ) from exc
    active_path = _model_path(active_identity.model_full_path, "active model path")
    scratch_path = _model_path(owned_scratch.scratch_path, "owned scratch path")
    owned_active_path = _model_path(
        owned_scratch.active_model_path,
        "owned scratch active model path",
    )
    if active_path != scratch_path or active_path != owned_active_path:
        raise DesignPreflightError(
            "B6 preflight active model is not the exact OwnedScratchContext"
        )
    return analysis_result


def _expected_columns(topology: ColumnTopologyEvidenceEnvelope) -> tuple[object, ...]:
    columns = tuple(
        sorted(
            topology.topology.columns,
            key=lambda item: (item.component_id, item.unique_name),
        )
    )
    if not columns:
        raise DesignPreflightError("expected concrete-column population is empty")
    component_ids = tuple(_text(item.component_id, "component_id") for item in columns)
    frame_names = tuple(_text(item.unique_name, "frame_name") for item in columns)
    if len(component_ids) != len(set(component_ids)):
        raise DesignPreflightError(
            "expected concrete-column component population is not unique"
        )
    if len(frame_names) != len(set(frame_names)):
        raise DesignPreflightError(
            "expected concrete-column FrameName population is not unique"
        )
    return columns


def _presence_source_ref(frame_name: str, reported_row_count: int) -> str:
    return (
        "CSI:DesignConcrete.GetSummaryResultsColumn:"
        f"{frame_name}:reported-row-count:{reported_row_count}"
    )


def _capture_expected_column_census(
    *,
    context: TrustedLiveAcquisitionContext,
    topology: ColumnTopologyEvidenceEnvelope,
    timeout_seconds: float,
) -> PreDesignExpectedColumnCensus:
    entries: list[ExpectedColumnDesignResultPresence] = []
    refs: list[str] = [
        context.acquisition_context_ref,
        context.session_provenance_ref,
        *topology.source_refs,
    ]
    for column in _expected_columns(topology):
        component_id = _text(column.component_id, "component_id")
        frame_name = _text(column.unique_name, "frame_name")
        try:
            fact = read_summary_results_column_from_session(
                context.verified_session,
                frame_name,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            entries.append(
                ExpectedColumnDesignResultPresence(
                    component_id=component_id,
                    frame_name=frame_name,
                    reported_row_count=None,
                    row_present=None,
                    source_ref=None,
                    diagnostic=(
                        "SUMMARY_RESULT_PRESENCE_READ_FAILED:"
                        f"{type(exc).__name__}:{exc}"
                    ),
                )
            )
            continue
        count = fact.reported_row_count
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            entries.append(
                ExpectedColumnDesignResultPresence(
                    component_id=component_id,
                    frame_name=frame_name,
                    reported_row_count=None,
                    row_present=None,
                    source_ref=None,
                    diagnostic="SUMMARY_RESULT_PRESENCE_COUNT_INVALID",
                )
            )
            continue
        source_ref = _presence_source_ref(frame_name, count)
        refs.append(source_ref)
        entries.append(
            ExpectedColumnDesignResultPresence(
                component_id=component_id,
                frame_name=frame_name,
                reported_row_count=count,
                row_present=count > 0,
                source_ref=source_ref,
            )
        )
    return PreDesignExpectedColumnCensus(
        _token=_CENSUS_FACTORY_KEY,
        entries=entries,
        source_refs=refs,
    )


def _classify(
    *,
    availability: ConcreteDesignResultsAvailabilityFact | None,
    availability_diagnostic: str | None,
    census: PreDesignExpectedColumnCensus,
) -> tuple[DesignPreflightStatus, tuple[str, ...]]:
    # A positive model-level availability fact is sufficient to prove that
    # pre-existing concrete-design results are present, but not fresh.
    if availability is not None and availability.results_available:
        return (
            DesignPreflightStatus.PRESENT,
            ("PREEXISTING_CONCRETE_DESIGN_RESULTS_AVAILABLE",),
        )

    # Failure to obtain the model-level fact is explicitly ambiguous even if
    # the expected-column row census found no rows.
    if availability is None:
        return (
            DesignPreflightStatus.AMBIGUOUS,
            (
                availability_diagnostic
                or "CONCRETE_DESIGN_RESULTS_AVAILABILITY_UNAVAILABLE",
            ),
        )

    # Direct CSI False combined with existing expected-column rows is
    # contradictory factual state. Freeze it as AMBIGUOUS rather than
    # coercing it into PRESENT or ABSENT.
    if census.any_rows_present:
        return (
            DesignPreflightStatus.AMBIGUOUS,
            ("RESULTS_AVAILABLE_FALSE_WITH_PREEXISTING_COLUMN_ROWS",),
        )

    if not census.complete:
        return (
            DesignPreflightStatus.AMBIGUOUS,
            ("EXPECTED_COLUMN_PRESENCE_CENSUS_INCOMPLETE",),
        )

    if census.all_rows_absent:
        return DesignPreflightStatus.ABSENT, ()

    return (
        DesignPreflightStatus.AMBIGUOUS,
        ("PRE_DESIGN_RESULT_STATE_NOT_PROVEN",),
    )


def capture_design_preflight(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    analysis_lineage: AnalysisLineageQualification,
    topology: ColumnTopologyEvidenceEnvelope,
    timeout_seconds: float = 30.0,
) -> DesignPreflightSnapshot:
    """Capture the exact B6-P0 pre-design freshness state.

    This function performs factual reads only. It never calls ``StartDesign``.
    Positive ABSENT means only:

    * exact qualified B5 parent/source/scratch bindings passed;
    * ``GetResultsAvailable`` factually returned False; and
    * every expected concrete column was successfully read with zero summary
      result rows.

    PRESENT and AMBIGUOUS are both blocking states for later B6-P1 execution.
    """

    if isinstance(timeout_seconds, bool) or not isinstance(
        timeout_seconds, (int, float)
    ) or float(timeout_seconds) <= 0:
        raise DesignPreflightError("timeout_seconds must be positive numeric")

    timeout = float(timeout_seconds)
    analysis_result = _validate_bindings(
        context=context,
        owned_scratch=owned_scratch,
        analysis_lineage=analysis_lineage,
        topology=topology,
        timeout_seconds=timeout,
    )

    availability: ConcreteDesignResultsAvailabilityFact | None
    availability_diagnostic: str | None = None
    try:
        availability = read_results_available_from_session(
            context.verified_session,
            timeout_seconds=timeout,
        )
    except Exception as exc:
        availability = None
        availability_diagnostic = (
            "RESULTS_AVAILABLE_READ_FAILED:"
            f"{type(exc).__name__}:{exc}"
        )

    census = _capture_expected_column_census(
        context=context,
        topology=topology,
        timeout_seconds=timeout,
    )
    status, blockers = _classify(
        availability=availability,
        availability_diagnostic=availability_diagnostic,
        census=census,
    )

    provenance = [
        context.source_model_identity.source_model_ref,
        context.acquisition_context_ref,
        context.session_provenance_ref,
        owned_scratch.ownership_proof_ref,
        analysis_lineage.qualification_ref,
        analysis_result.identity_ref,
        *topology.source_refs,
        census.census_ref,
        *census.source_refs,
    ]
    if availability is not None:
        provenance.append(
            f"CSI:{CONCRETE_DESIGN_RESULTS_AVAILABLE_API}:"
            f"{str(availability.results_available).lower()}"
        )
    elif availability_diagnostic is not None:
        provenance.append(availability_diagnostic)

    return DesignPreflightSnapshot(
        _token=_PREFLIGHT_FACTORY_KEY,
        status=status,
        source_model_ref=context.source_model_identity.source_model_ref,
        analysis_result_ref=analysis_result.identity_ref,
        analysis_lineage_qualification_ref=analysis_lineage.qualification_ref,
        ownership_proof_ref=owned_scratch.ownership_proof_ref,
        model_fingerprint=topology.model_fingerprint,
        evidence_epoch_id=topology.evidence_epoch_id,
        availability=availability,
        column_census=census,
        blockers=blockers,
        provenance_refs=provenance,
    )


__all__ = [
    "DESIGN_PREFLIGHT_CONTRACT",
    "PRE_DESIGN_COLUMN_CENSUS_CONTRACT",
    "DesignPreflightError",
    "DesignPreflightSnapshot",
    "DesignPreflightStatus",
    "ExpectedColumnDesignResultPresence",
    "PreDesignExpectedColumnCensus",
    "capture_design_preflight",
]
