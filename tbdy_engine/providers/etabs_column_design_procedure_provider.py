"""Exact Column-R1 concrete-frame design-procedure factual population.

CSI ABI ownership remains in ``tbdy_engine.etabs.oapi.frame_design_procedure``.
This provider binds every exact canonical Column component/frame to its factual
``FrameObj.GetDesignProcedure`` value and enforces the supervisor-authorized
Column-R1 V1 procedure: Concrete Frame Design (code 2).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.oapi.frame_design_procedure import (
    FRAME_DESIGN_PROCEDURE_API,
    FrameDesignProcedureFact,
    read_frame_design_procedures_from_session,
)
from tbdy_engine.etabs.safety import EtabsVerifiedSession
from tbdy_engine.features.column_concrete_design_evidence import ColumnTopologyEvidenceEnvelope

ACCEPTED_CONCRETE_FRAME_DESIGN_PROCEDURE_CODE = 2
DESIGN_PROCEDURE_POPULATION_REF_PREFIX = "design-procedure-population:sha256:"


class EtabsColumnDesignProcedureProviderError(RuntimeError):
    """Fail-closed exact Column design-procedure population error."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsColumnDesignProcedureProviderError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _population_ref(rows: Sequence["ColumnDesignProcedureRow"]) -> str:
    payload = [
        {
            "component_id": row.component_id,
            "frame_name": row.frame_name,
            "procedure_code": row.procedure_code,
        }
        for row in sorted(rows, key=lambda item: (item.component_id, item.frame_name))
    ]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return DESIGN_PROCEDURE_POPULATION_REF_PREFIX + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ColumnDesignProcedureRow:
    component_id: str
    frame_name: str
    procedure_code: int
    source_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        object.__setattr__(self, "frame_name", _text(self.frame_name, "frame_name"))
        if isinstance(self.procedure_code, bool) or not isinstance(self.procedure_code, int):
            raise EtabsColumnDesignProcedureProviderError("procedure_code must be exact int")
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))


@dataclass(frozen=True, slots=True)
class ColumnDesignProcedurePopulation:
    model_fingerprint: str
    evidence_epoch_id: str
    expected_component_ids: tuple[str, ...]
    expected_frame_names: tuple[str, ...]
    rows: tuple[ColumnDesignProcedureRow, ...]
    topology_source_refs: tuple[str, ...]
    design_procedure_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint")
        )
        object.__setattr__(
            self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id")
        )
        expected_ids = tuple(sorted(_text(value, "expected_component_id") for value in self.expected_component_ids))
        expected_names = tuple(sorted(_text(value, "expected_frame_name") for value in self.expected_frame_names))
        if not expected_ids or not expected_names or len(expected_ids) != len(expected_names):
            raise EtabsColumnDesignProcedureProviderError(
                "design-procedure population requires a nonempty one-to-one expected Column population"
            )
        if len(expected_ids) != len(set(expected_ids)):
            raise EtabsColumnDesignProcedureProviderError("duplicate expected component identity")
        if len(expected_names) != len(set(expected_names)):
            raise EtabsColumnDesignProcedureProviderError("duplicate expected FrameName")
        object.__setattr__(self, "expected_component_ids", expected_ids)
        object.__setattr__(self, "expected_frame_names", expected_names)

        rows = tuple(self.rows)
        if len(rows) != len(expected_ids) or any(not isinstance(row, ColumnDesignProcedureRow) for row in rows):
            raise EtabsColumnDesignProcedureProviderError(
                "design-procedure factual rows do not exactly cover the expected Column count"
            )
        component_ids = tuple(row.component_id for row in rows)
        frame_names = tuple(row.frame_name for row in rows)
        if len(component_ids) != len(set(component_ids)):
            raise EtabsColumnDesignProcedureProviderError("duplicate factual component/frame binding")
        if len(frame_names) != len(set(frame_names)):
            raise EtabsColumnDesignProcedureProviderError("duplicate factual FrameName")
        if set(component_ids) != set(expected_ids) or set(frame_names) != set(expected_names):
            raise EtabsColumnDesignProcedureProviderError(
                "design-procedure factual population is incomplete or contains a superset"
            )
        if any(
            row.procedure_code != ACCEPTED_CONCRETE_FRAME_DESIGN_PROCEDURE_CODE
            for row in rows
        ):
            bad = tuple(
                sorted(
                    (row.component_id, row.frame_name, row.procedure_code)
                    for row in rows
                    if row.procedure_code != ACCEPTED_CONCRETE_FRAME_DESIGN_PROCEDURE_CODE
                )
            )
            raise EtabsColumnDesignProcedureProviderError(
                "Column-R1 requires Concrete Frame Design procedure code 2 for every expected Column; "
                f"nonmatching={bad!r}"
            )
        refs = tuple(_text(value, "topology_source_ref") for value in self.topology_source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise EtabsColumnDesignProcedureProviderError(
                "topology_source_refs must be nonempty and unique"
            )
        object.__setattr__(self, "topology_source_refs", refs)
        ordered = tuple(sorted(rows, key=lambda row: (row.component_id, row.frame_name)))
        object.__setattr__(self, "rows", ordered)
        expected_ref = _population_ref(ordered)
        if self.design_procedure_ref not in ("", expected_ref):
            raise EtabsColumnDesignProcedureProviderError(
                "design_procedure_ref does not match exact factual population"
            )
        object.__setattr__(self, "design_procedure_ref", expected_ref)

    @property
    def capture_complete(self) -> bool:
        return (
            len(self.rows) == len(self.expected_component_ids)
            and tuple(row.component_id for row in self.rows)
            == tuple(sorted(self.expected_component_ids))
            and {row.frame_name for row in self.rows} == set(self.expected_frame_names)
        )

    @property
    def source_refs(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                (*self.topology_source_refs, *(row.source_ref for row in self.rows))
            )
        )


def build_column_design_procedure_population(
    *,
    topology: ColumnTopologyEvidenceEnvelope,
    facts: Sequence[FrameDesignProcedureFact],
) -> ColumnDesignProcedurePopulation:
    if not isinstance(topology, ColumnTopologyEvidenceEnvelope):
        raise TypeError("topology must be ColumnTopologyEvidenceEnvelope")
    columns = tuple(sorted(topology.topology.columns, key=lambda item: (item.component_id, item.unique_name)))
    if not columns:
        raise EtabsColumnDesignProcedureProviderError("canonical Column topology is empty")
    expected_ids = tuple(column.component_id for column in columns)
    expected_names = tuple(column.unique_name for column in columns)
    if len(expected_ids) != len(set(expected_ids)) or len(expected_names) != len(set(expected_names)):
        raise EtabsColumnDesignProcedureProviderError(
            "canonical Column topology contains duplicate component/frame identity"
        )

    facts_tuple = tuple(facts)
    if any(not isinstance(fact, FrameDesignProcedureFact) for fact in facts_tuple):
        raise TypeError("facts must contain FrameDesignProcedureFact")
    fact_by_name = {fact.frame_name: fact for fact in facts_tuple}
    if len(fact_by_name) != len(facts_tuple):
        raise EtabsColumnDesignProcedureProviderError("duplicate factual design-procedure FrameName")
    if set(fact_by_name) != set(expected_names):
        raise EtabsColumnDesignProcedureProviderError(
            "factual design-procedure population does not exactly cover canonical Column topology"
        )

    rows = tuple(
        ColumnDesignProcedureRow(
            component_id=column.component_id,
            frame_name=column.unique_name,
            procedure_code=fact_by_name[column.unique_name].procedure_code,
            source_ref=(
                f"CSI:{FRAME_DESIGN_PROCEDURE_API}:{column.unique_name}:"
                f"{fact_by_name[column.unique_name].procedure_code}"
            ),
        )
        for column in columns
    )
    return ColumnDesignProcedurePopulation(
        model_fingerprint=topology.model_fingerprint,
        evidence_epoch_id=topology.evidence_epoch_id,
        expected_component_ids=expected_ids,
        expected_frame_names=expected_names,
        rows=rows,
        topology_source_refs=topology.source_refs,
    )


def capture_column_design_procedure_population_from_session(
    session: EtabsVerifiedSession,
    *,
    topology: ColumnTopologyEvidenceEnvelope,
) -> ColumnDesignProcedurePopulation:
    """Capture exact per-frame procedure facts for the complete Column topology."""
    if not isinstance(topology, ColumnTopologyEvidenceEnvelope):
        raise TypeError("topology must be ColumnTopologyEvidenceEnvelope")
    frame_names = tuple(
        column.unique_name
        for column in sorted(topology.topology.columns, key=lambda item: (item.component_id, item.unique_name))
    )
    try:
        facts = read_frame_design_procedures_from_session(session, frame_names)
    except EtabsOAPIError as exc:
        raise EtabsColumnDesignProcedureProviderError(str(exc)) from exc
    return build_column_design_procedure_population(topology=topology, facts=facts)


__all__ = [
    "ACCEPTED_CONCRETE_FRAME_DESIGN_PROCEDURE_CODE",
    "DESIGN_PROCEDURE_POPULATION_REF_PREFIX",
    "ColumnDesignProcedurePopulation",
    "ColumnDesignProcedureRow",
    "EtabsColumnDesignProcedureProviderError",
    "build_column_design_procedure_population",
    "capture_column_design_procedure_population_from_session",
]
