"""Factual contracts for concrete-column design evidence authority foundation.

No reinforcement quantity is promoted here. The contracts bind reviewed
expected design-combination identity, downstream enrichment of the accepted
PASS-1 factual selected population, exact result/component identity,
design-section identity and one EvidenceEpoch/model identity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Sequence

from tbdy_engine.features.column_shear_topology import StrictColumnTopologyBundle
from tbdy_engine.features.evidence_epoch import EvidenceEpoch


class ColumnConcreteDesignEvidenceError(ValueError):
    pass


class ComponentBindingStatus(StrEnum):
    BOUND = "BOUND"
    BLOCKED_COMPONENT_IDENTITY = "BLOCKED_COMPONENT_IDENTITY"
    BLOCKED_SECTION_IDENTITY = "BLOCKED_SECTION_IDENTITY"
    BLOCKED_EVIDENCE_EPOCH = "BLOCKED_EVIDENCE_EPOCH"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnConcreteDesignEvidenceError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    refs = tuple(_text(item, label) for item in values)
    if len(refs) != len(set(refs)):
        raise ColumnConcreteDesignEvidenceError(f"{label} values must be unique")
    return refs


@dataclass(frozen=True, slots=True)
class ExpectedConcreteDesignCombo:
    design_combo_type: str
    combo_name: str
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "design_combo_type", _text(self.design_combo_type, "design_combo_type"))
        object.__setattr__(self, "combo_name", _text(self.combo_name, "combo_name"))
        refs = _refs(self.provenance_refs, "expected_combo.provenance_ref")
        if not refs:
            raise ColumnConcreteDesignEvidenceError("expected combo requires provenance")
        object.__setattr__(self, "provenance_refs", refs)

    @property
    def identity(self) -> tuple[str, str]:
        return self.design_combo_type, self.combo_name


@dataclass(frozen=True, slots=True)
class ExpectedConcreteDesignComboPolicy:
    policy_id: str
    combos: tuple[ExpectedConcreteDesignCombo, ...]
    review_provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        combos = tuple(self.combos)
        if not combos or any(not isinstance(item, ExpectedConcreteDesignCombo) for item in combos):
            raise ColumnConcreteDesignEvidenceError("expected combo policy requires typed combo entries")
        identities = tuple(item.identity for item in combos)
        if len(identities) != len(set(identities)):
            raise ColumnConcreteDesignEvidenceError("expected design-combo identities must be unique")
        object.__setattr__(self, "combos", tuple(sorted(combos, key=lambda item: item.identity)))
        refs = _refs(self.review_provenance_refs, "policy.review_provenance_ref")
        if not refs:
            raise ColumnConcreteDesignEvidenceError("expected combo policy requires review provenance")
        object.__setattr__(self, "review_provenance_refs", refs)

    @property
    def identities(self) -> tuple[tuple[str, str], ...]:
        return tuple(item.identity for item in self.combos)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(item.combo_name for item in self.combos)


@dataclass(frozen=True, slots=True)
class ActualSelectedConcreteDesignCombo:
    """Downstream enrichment of one accepted PASS-1 factual selected row."""

    design_combo_type: str
    combo_name: str
    selected_row_id: str
    normalized_definition_fingerprint: str
    source_row_ref: str
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "design_combo_type", _text(self.design_combo_type, "design_combo_type"))
        object.__setattr__(self, "combo_name", _text(self.combo_name, "combo_name"))
        object.__setattr__(self, "selected_row_id", _text(self.selected_row_id, "selected_row_id"))
        fp = _text(self.normalized_definition_fingerprint, "normalized_definition_fingerprint")
        digest = fp.removeprefix("combo-definition:sha256:")
        if not fp.startswith("combo-definition:sha256:") or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ColumnConcreteDesignEvidenceError("normalized definition fingerprint must be canonical sha256")
        object.__setattr__(self, "normalized_definition_fingerprint", fp)
        object.__setattr__(self, "source_row_ref", _text(self.source_row_ref, "source_row_ref"))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "selected_combo.provenance_ref"))

    @property
    def identity(self) -> tuple[str, str]:
        return self.design_combo_type, self.combo_name


@dataclass(frozen=True, slots=True)
class ActualConcreteDesignComboPopulation:
    """Definition-enriched projection of the sole PASS-1 actual population."""

    model_fingerprint: str
    evidence_epoch_id: str
    selected_population_source_refs: tuple[str, ...]
    definition_capture_refs: tuple[str, ...]
    combos: tuple[ActualSelectedConcreteDesignCombo, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        selected_refs = _refs(self.selected_population_source_refs, "selected_population.source_ref")
        definition_refs = _refs(self.definition_capture_refs, "definition_capture.ref")
        if not selected_refs or not definition_refs:
            raise ColumnConcreteDesignEvidenceError("actual enrichment requires PASS-1 and definition-capture provenance")
        object.__setattr__(self, "selected_population_source_refs", selected_refs)
        object.__setattr__(self, "definition_capture_refs", definition_refs)
        combos = tuple(self.combos)
        if not combos or any(not isinstance(item, ActualSelectedConcreteDesignCombo) for item in combos):
            raise ColumnConcreteDesignEvidenceError("actual selected population requires typed enriched combos")
        identities = tuple(item.identity for item in combos)
        row_ids = tuple(item.selected_row_id for item in combos)
        if len(identities) != len(set(identities)):
            raise ColumnConcreteDesignEvidenceError("actual selected design-combo identities must be unique")
        if len(row_ids) != len(set(row_ids)):
            raise ColumnConcreteDesignEvidenceError("actual selected PASS-1 row identities must be unique")
        object.__setattr__(self, "combos", tuple(sorted(combos, key=lambda item: item.identity)))

    @property
    def identities(self) -> tuple[tuple[str, str], ...]:
        return tuple(item.identity for item in self.combos)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(item.combo_name for item in self.combos)

    @property
    def source_refs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((
            *self.selected_population_source_refs,
            *self.definition_capture_refs,
            *(item.source_row_ref for item in self.combos),
            *(ref for item in self.combos for ref in item.provenance_refs),
        )))


@dataclass(frozen=True, slots=True)
class ColumnTopologyEvidenceEnvelope:
    topology: StrictColumnTopologyBundle
    model_fingerprint: str
    evidence_epoch_id: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.topology, StrictColumnTopologyBundle):
            raise TypeError("topology must be StrictColumnTopologyBundle")
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        refs = _refs(self.source_refs, "topology.source_ref")
        if not refs:
            raise ColumnConcreteDesignEvidenceError("topology envelope requires source refs")
        object.__setattr__(self, "source_refs", refs)

    @classmethod
    def bind(cls, *, topology: StrictColumnTopologyBundle, epoch: EvidenceEpoch, source_refs: Sequence[str]):
        if not isinstance(epoch, EvidenceEpoch):
            raise TypeError("epoch must be EvidenceEpoch")
        return cls(topology=topology, model_fingerprint=epoch.model_fingerprint, evidence_epoch_id=epoch.epoch_id, source_refs=tuple(source_refs))


@dataclass(frozen=True, slots=True)
class ColumnDesignResultIdentity:
    frame_name: str
    story: str
    label: str
    model_fingerprint: str
    evidence_epoch_id: str
    result_design_section: str | None
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("frame_name", "story", "label", "model_fingerprint", "evidence_epoch_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.result_design_section is not None:
            object.__setattr__(self, "result_design_section", _text(self.result_design_section, "result_design_section"))
        refs = _refs(self.source_refs, "result_identity.source_ref")
        if not refs:
            raise ColumnConcreteDesignEvidenceError("result identity requires source refs")
        object.__setattr__(self, "source_refs", refs)


@dataclass(frozen=True, slots=True)
class ColumnDesignSectionEvidence:
    frame_name: str
    design_section: str
    model_fingerprint: str
    evidence_epoch_id: str
    source_api: str
    source_ref: str

    def __post_init__(self) -> None:
        for name in ("frame_name", "design_section", "model_fingerprint", "evidence_epoch_id", "source_api", "source_ref"):
            object.__setattr__(self, name, _text(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class ColumnDesignComponentBinding:
    status: ComponentBindingStatus
    component_id: str | None
    unique_name: str | None
    story: str | None
    label: str | None
    assigned_section: str | None
    design_section: str | None
    model_fingerprint: str
    evidence_epoch_id: str
    source_refs: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def bound(self) -> bool:
        return self.status is ComponentBindingStatus.BOUND


def bind_column_design_result_identity(*, result: ColumnDesignResultIdentity, topology: ColumnTopologyEvidenceEnvelope, design_section: ColumnDesignSectionEvidence) -> ColumnDesignComponentBinding:
    refs = tuple(dict.fromkeys((*result.source_refs, *topology.source_refs, design_section.source_ref)))
    epoch_values = {
        (result.model_fingerprint, result.evidence_epoch_id),
        (topology.model_fingerprint, topology.evidence_epoch_id),
        (design_section.model_fingerprint, design_section.evidence_epoch_id),
    }
    if len(epoch_values) != 1:
        return ColumnDesignComponentBinding(ComponentBindingStatus.BLOCKED_EVIDENCE_EPOCH, None, None, None, None, None, None, result.model_fingerprint, result.evidence_epoch_id, refs, ("model fingerprint/evidence epoch mismatch",))
    try:
        column = topology.topology.column(result.frame_name)
    except KeyError:
        return ColumnDesignComponentBinding(ComponentBindingStatus.BLOCKED_COMPONENT_IDENTITY, None, None, None, None, None, None, result.model_fingerprint, result.evidence_epoch_id, refs, ("FrameName did not bind to exactly one strict-topology UniqueName",))
    if column.story != result.story or column.column_label != result.label or design_section.frame_name != result.frame_name:
        return ColumnDesignComponentBinding(ComponentBindingStatus.BLOCKED_COMPONENT_IDENTITY, column.component_id, column.unique_name, column.story, column.column_label, column.section, design_section.design_section, result.model_fingerprint, result.evidence_epoch_id, refs, ("Story/Label/FrameName factual identity mismatch",))
    if result.result_design_section is not None and result.result_design_section != design_section.design_section:
        return ColumnDesignComponentBinding(ComponentBindingStatus.BLOCKED_SECTION_IDENTITY, column.component_id, column.unique_name, column.story, column.column_label, column.section, design_section.design_section, result.model_fingerprint, result.evidence_epoch_id, refs, ("design-result section does not match DesignConcrete.GetDesignSection",))
    return ColumnDesignComponentBinding(ComponentBindingStatus.BOUND, column.component_id, column.unique_name, column.story, column.column_label, column.section, design_section.design_section, result.model_fingerprint, result.evidence_epoch_id, refs, ())


def decode_get_design_section(frame_name: str, raw: object, *, model_fingerprint: str, evidence_epoch_id: str) -> ColumnDesignSectionEvidence:
    name = _text(frame_name, "frame_name")
    if not isinstance(raw, (tuple, list)) or len(raw) != 2:
        raise ColumnConcreteDesignEvidenceError(f"GetDesignSection({name!r}) returned unexpected shape: {raw!r}")
    section_raw, ret = raw
    if not isinstance(ret, int) or ret != 0:
        raise ColumnConcreteDesignEvidenceError(f"GetDesignSection({name!r}) failed/raw={raw!r}")
    section = _text(section_raw, "design_section")
    return ColumnDesignSectionEvidence(name, section, model_fingerprint, evidence_epoch_id, "DesignConcrete.GetDesignSection", f"CSI:DesignConcrete.GetDesignSection:{name}:{section}")


__all__ = [name for name in globals() if name.startswith("Column") or name.startswith("Expected") or name.startswith("Actual") or name in {"bind_column_design_result_identity", "decode_get_design_section", "ComponentBindingStatus"}]
