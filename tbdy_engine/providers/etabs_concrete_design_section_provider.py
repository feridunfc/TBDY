"""Read-only ETABS concrete-design section acquisition for canonical columns.

CSI invocation and positional ABI decoding are owned by
``tbdy_engine.etabs.oapi.concrete_design``. This provider binds typed factual
sections only to the accepted strict-topology population and provenance.
Supported live acquisition consumes a verified session, never raw
DesignConcrete/SapModel capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from tbdy_engine.etabs.oapi.concrete_design import (
    ConcreteDesignSectionFact,
    read_design_section,
    read_design_sections_from_session,
)
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.safety import EtabsVerifiedSession
from tbdy_engine.features.column_concrete_design_evidence import (
    ColumnDesignSectionEvidence,
    ColumnTopologyEvidenceEnvelope,
)


class EtabsConcreteDesignSectionProviderError(RuntimeError):
    """Raised when canonical design-section factual capture cannot close."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsConcreteDesignSectionProviderError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    refs = tuple(_text(item, label) for item in values)
    if not refs:
        raise EtabsConcreteDesignSectionProviderError(f"{label} requires provenance")
    if len(refs) != len(set(refs)):
        raise EtabsConcreteDesignSectionProviderError(f"{label} values must be unique")
    return refs


@dataclass(frozen=True, slots=True)
class CapturedConcreteColumnDesignSection:
    component_id: str
    unique_name: str
    story: str
    label: str
    assigned_section: str
    design_section_evidence: ColumnDesignSectionEvidence
    model_fingerprint: str
    evidence_epoch_id: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "component_id", "unique_name", "story", "label", "assigned_section",
            "model_fingerprint", "evidence_epoch_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.design_section_evidence, ColumnDesignSectionEvidence):
            raise TypeError("design_section_evidence must be ColumnDesignSectionEvidence")
        evidence = self.design_section_evidence
        if evidence.frame_name != self.unique_name:
            raise EtabsConcreteDesignSectionProviderError(
                "GetDesignSection FrameName must equal canonical topology UniqueName"
            )
        if (
            evidence.model_fingerprint != self.model_fingerprint
            or evidence.evidence_epoch_id != self.evidence_epoch_id
        ):
            raise EtabsConcreteDesignSectionProviderError(
                "design-section evidence model/evidence epoch mismatch"
            )
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "design_section.source_ref"))

    @property
    def design_section(self) -> str:
        return self.design_section_evidence.design_section

    @property
    def source_api(self) -> str:
        return self.design_section_evidence.source_api

    @property
    def source_ref(self) -> str:
        return self.design_section_evidence.source_ref


@dataclass(frozen=True, slots=True)
class ConcreteColumnDesignSectionPopulation:
    model_fingerprint: str
    evidence_epoch_id: str
    expected_component_ids: tuple[str, ...]
    expected_frame_names: tuple[str, ...]
    rows: tuple[CapturedConcreteColumnDesignSection, ...]
    topology_source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        expected_ids = tuple(sorted(_text(item, "expected_component_id") for item in self.expected_component_ids))
        expected_names = tuple(sorted(_text(item, "expected_frame_name") for item in self.expected_frame_names))
        if not expected_ids or not expected_names:
            raise EtabsConcreteDesignSectionProviderError(
                "design-section population requires canonical expected components"
            )
        if len(expected_ids) != len(set(expected_ids)):
            raise EtabsConcreteDesignSectionProviderError("duplicate expected canonical component identity")
        if len(expected_names) != len(set(expected_names)):
            raise EtabsConcreteDesignSectionProviderError("duplicate expected canonical FrameName")
        object.__setattr__(self, "expected_component_ids", expected_ids)
        object.__setattr__(self, "expected_frame_names", expected_names)
        rows = tuple(self.rows)
        if not rows or any(not isinstance(item, CapturedConcreteColumnDesignSection) for item in rows):
            raise EtabsConcreteDesignSectionProviderError(
                "design-section population requires typed captured rows"
            )
        component_ids = tuple(item.component_id for item in rows)
        frame_names = tuple(item.unique_name for item in rows)
        if len(component_ids) != len(set(component_ids)):
            raise EtabsConcreteDesignSectionProviderError("duplicate captured canonical component evidence")
        if len(frame_names) != len(set(frame_names)):
            raise EtabsConcreteDesignSectionProviderError("duplicate captured canonical FrameName evidence")
        if any(
            item.model_fingerprint != self.model_fingerprint
            or item.evidence_epoch_id != self.evidence_epoch_id
            for item in rows
        ):
            raise EtabsConcreteDesignSectionProviderError(
                "captured design-section row model/evidence epoch mismatch"
            )
        if set(component_ids) != set(expected_ids) or set(frame_names) != set(expected_names):
            raise EtabsConcreteDesignSectionProviderError(
                "captured design-section population does not exactly cover canonical topology"
            )
        object.__setattr__(self, "rows", tuple(sorted(rows, key=lambda item: (item.component_id, item.unique_name))))
        object.__setattr__(self, "topology_source_refs", _refs(self.topology_source_refs, "topology.source_ref"))

    @property
    def captured_component_ids(self) -> tuple[str, ...]:
        return tuple(item.component_id for item in self.rows)

    @property
    def captured_frame_names(self) -> tuple[str, ...]:
        return tuple(item.unique_name for item in self.rows)

    @property
    def source_refs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.topology_source_refs, *(ref for row in self.rows for ref in row.source_refs))))

    def by_component_id(self, component_id: str) -> CapturedConcreteColumnDesignSection:
        key = _text(component_id, "component_id")
        matches = tuple(item for item in self.rows if item.component_id == key)
        if len(matches) != 1:
            raise KeyError(f"expected exactly one captured component_id={key}, got {len(matches)}")
        return matches[0]


def _columns(topology: ColumnTopologyEvidenceEnvelope):
    if not isinstance(topology, ColumnTopologyEvidenceEnvelope):
        raise TypeError("topology must be ColumnTopologyEvidenceEnvelope")
    columns = tuple(sorted(topology.topology.columns, key=lambda item: (item.component_id, item.unique_name)))
    expected_ids = tuple(item.component_id for item in columns)
    expected_names = tuple(item.unique_name for item in columns)
    if len(expected_ids) != len(set(expected_ids)):
        raise EtabsConcreteDesignSectionProviderError("duplicate canonical component identity in strict topology")
    if len(expected_names) != len(set(expected_names)):
        raise EtabsConcreteDesignSectionProviderError("duplicate canonical FrameName in strict topology")
    return columns, expected_ids, expected_names


def _build_population(
    *,
    topology: ColumnTopologyEvidenceEnvelope,
    facts: Sequence[ConcreteDesignSectionFact],
) -> ConcreteColumnDesignSectionPopulation:
    columns, expected_ids, expected_names = _columns(topology)
    fact_by_name = {fact.frame_name: fact for fact in facts}
    if len(fact_by_name) != len(tuple(facts)) or set(fact_by_name) != set(expected_names):
        raise EtabsConcreteDesignSectionProviderError(
            "typed design-section facts do not exactly cover canonical topology"
        )
    rows: list[CapturedConcreteColumnDesignSection] = []
    for column in columns:
        fact = fact_by_name[column.unique_name]
        evidence = ColumnDesignSectionEvidence(
            frame_name=fact.frame_name,
            design_section=fact.design_section,
            model_fingerprint=topology.model_fingerprint,
            evidence_epoch_id=topology.evidence_epoch_id,
            source_api="DesignConcrete.GetDesignSection",
            source_ref=f"CSI:DesignConcrete.GetDesignSection:{fact.frame_name}:{fact.design_section}",
        )
        rows.append(
            CapturedConcreteColumnDesignSection(
                component_id=column.component_id,
                unique_name=column.unique_name,
                story=column.story,
                label=column.column_label,
                assigned_section=column.section,
                design_section_evidence=evidence,
                model_fingerprint=topology.model_fingerprint,
                evidence_epoch_id=topology.evidence_epoch_id,
                source_refs=tuple(dict.fromkeys((*topology.source_refs, evidence.source_ref))),
            )
        )
    return ConcreteColumnDesignSectionPopulation(
        model_fingerprint=topology.model_fingerprint,
        evidence_epoch_id=topology.evidence_epoch_id,
        expected_component_ids=expected_ids,
        expected_frame_names=expected_names,
        rows=tuple(rows),
        topology_source_refs=topology.source_refs,
    )


def capture_concrete_column_design_sections(
    design_concrete: Any,
    *,
    topology: ColumnTopologyEvidenceEnvelope,
) -> ConcreteColumnDesignSectionPopulation:
    """Compatibility path for an already-bounded raw DesignConcrete interface."""
    _columns(topology)
    try:
        facts = tuple(
            read_design_section(design_concrete, column.unique_name)
            for column in sorted(topology.topology.columns, key=lambda item: (item.component_id, item.unique_name))
        )
    except EtabsOAPIError as exc:
        raise EtabsConcreteDesignSectionProviderError(str(exc)) from exc
    return _build_population(topology=topology, facts=facts)


def capture_concrete_column_design_sections_from_session(
    session: EtabsVerifiedSession,
    *,
    topology: ColumnTopologyEvidenceEnvelope,
) -> ConcreteColumnDesignSectionPopulation:
    """Supported live path: session -> typed OAPI facts -> topology-bound evidence."""
    _, _, frame_names = _columns(topology)
    try:
        facts = read_design_sections_from_session(session, frame_names)
    except EtabsOAPIError as exc:
        raise EtabsConcreteDesignSectionProviderError(str(exc)) from exc
    return _build_population(topology=topology, facts=facts)


__all__ = [
    "CapturedConcreteColumnDesignSection",
    "ConcreteColumnDesignSectionPopulation",
    "EtabsConcreteDesignSectionProviderError",
    "capture_concrete_column_design_sections",
    "capture_concrete_column_design_sections_from_session",
]
