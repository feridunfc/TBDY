"""Neutral immutable analysis-basis lifecycle contracts for F0.5."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

from tbdy_engine.features.evidence_epoch import EvidenceEpoch
from tbdy_engine.regulatory.contracts import RuleInstanceId
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus


def _canonical_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _canonical_epoch_ref(value: str, label: str = "epoch_ref") -> str:
    value = _canonical_text(value, label)
    if not value.startswith("epoch:") or not value.removeprefix("epoch:"):
        raise ValueError(f"{label} must use canonical epoch:<id> form")
    return value


def _refs(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise TypeError(f"{label} must be a tuple of strings")
    if any(not isinstance(item, str) for item in values):
        raise TypeError(f"{label} must contain strings only")
    return tuple(_canonical_text(item, label) for item in values)


def evidence_epoch_ref(epoch: EvidenceEpoch) -> str:
    if not isinstance(epoch, EvidenceEpoch):
        raise TypeError("epoch must be EvidenceEpoch")
    return f"epoch:{epoch.epoch_id}"


@dataclass(frozen=True, slots=True)
class ReviewedDirectionalSystemDeclaration:
    declaration_id: str
    structural_zone_ref: str
    direction: str
    declared_basis_ref: str
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _canonical_text(self.declaration_id, "declaration_id")
        _canonical_text(self.structural_zone_ref, "structural_zone_ref")
        _canonical_text(self.direction, "direction")
        _canonical_text(self.declared_basis_ref, "declared_basis_ref")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))


@dataclass(frozen=True, slots=True)
class AnalysisSystemAssumption:
    assumption_id: str
    epoch_ref: str
    structural_zone_ref: str
    direction: str
    observed_basis_ref: str
    analysis_evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _canonical_text(self.assumption_id, "assumption_id")
        _canonical_epoch_ref(self.epoch_ref)
        _canonical_text(self.structural_zone_ref, "structural_zone_ref")
        _canonical_text(self.direction, "direction")
        _canonical_text(self.observed_basis_ref, "observed_basis_ref")
        object.__setattr__(
            self, "analysis_evidence_refs", _refs(self.analysis_evidence_refs, "analysis_evidence_ref")
        )
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))


@dataclass(frozen=True, slots=True)
class AnalysisBasisCompatibility:
    compatibility_id: str
    epoch_ref: str
    structural_zone_ref: str
    direction: str
    required_basis_ref: str
    analysis_assumption_ref: str
    status: AnalysisBasisStatus
    diagnostic_refs: tuple[str, ...] = field(default_factory=tuple)
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _canonical_text(self.compatibility_id, "compatibility_id")
        _canonical_epoch_ref(self.epoch_ref)
        _canonical_text(self.structural_zone_ref, "structural_zone_ref")
        _canonical_text(self.direction, "direction")
        _canonical_text(self.required_basis_ref, "required_basis_ref")
        _canonical_text(self.analysis_assumption_ref, "analysis_assumption_ref")
        if not isinstance(self.status, AnalysisBasisStatus):
            raise TypeError("status must be the canonical AnalysisBasisStatus")
        object.__setattr__(self, "diagnostic_refs", _refs(self.diagnostic_refs, "diagnostic_ref"))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))


@dataclass(frozen=True, slots=True)
class AnalysisBasisSnapshot:
    """Deterministic audit/provenance join artifact; never an authority."""

    snapshot_id: str
    epoch_ref: str
    structural_zone_ref: str
    direction: str
    reviewed_declaration_ref: str
    resolved_policy_ref: str
    analysis_assumption_ref: str
    compatibility_ref: str
    analysis_evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        snapshot_id = _canonical_text(self.snapshot_id, "snapshot_id")
        if not snapshot_id.startswith("analysis-basis-snapshot:"):
            raise ValueError("snapshot_id must use analysis-basis-snapshot:<sha256> form")
        digest = snapshot_id.removeprefix("analysis-basis-snapshot:")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("snapshot_id must contain a lowercase sha256 digest")
        _canonical_epoch_ref(self.epoch_ref)
        _canonical_text(self.structural_zone_ref, "structural_zone_ref")
        _canonical_text(self.direction, "direction")
        _canonical_text(self.reviewed_declaration_ref, "reviewed_declaration_ref")
        _canonical_text(self.resolved_policy_ref, "resolved_policy_ref")
        _canonical_text(self.analysis_assumption_ref, "analysis_assumption_ref")
        _canonical_text(self.compatibility_ref, "compatibility_ref")
        object.__setattr__(
            self, "analysis_evidence_refs", _refs(self.analysis_evidence_refs, "analysis_evidence_ref")
        )
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))


@dataclass(frozen=True, slots=True)
class RuleAnalysisBasisRequirement:
    rule_instance_id: RuleInstanceId
    structural_zone_ref: str
    direction: str
    compatibility_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.rule_instance_id, RuleInstanceId):
            raise TypeError("rule_instance_id must be RuleInstanceId")
        _canonical_text(self.structural_zone_ref, "structural_zone_ref")
        _canonical_text(self.direction, "direction")
        _canonical_text(self.compatibility_ref, "compatibility_ref")
        if self.rule_instance_id.direction != self.direction:
            raise ValueError("requirement direction must match target RuleInstanceId direction")


def build_analysis_basis_snapshot(
    *,
    epoch: EvidenceEpoch,
    declaration: ReviewedDirectionalSystemDeclaration,
    resolved_policy_ref: str,
    assumption: AnalysisSystemAssumption,
    compatibility: AnalysisBasisCompatibility,
    analysis_evidence_refs: tuple[str, ...] = (),
    provenance_refs: tuple[str, ...] = (),
) -> AnalysisBasisSnapshot:
    """Build a deterministic join artifact after structural-coherence validation only."""

    if not isinstance(epoch, EvidenceEpoch):
        raise TypeError("epoch must be EvidenceEpoch")
    if not isinstance(declaration, ReviewedDirectionalSystemDeclaration):
        raise TypeError("declaration must be ReviewedDirectionalSystemDeclaration")
    if not isinstance(assumption, AnalysisSystemAssumption):
        raise TypeError("assumption must be AnalysisSystemAssumption")
    if not isinstance(compatibility, AnalysisBasisCompatibility):
        raise TypeError("compatibility must be AnalysisBasisCompatibility")
    resolved_policy_ref = _canonical_text(resolved_policy_ref, "resolved_policy_ref")
    analysis_evidence_refs = _refs(analysis_evidence_refs, "analysis_evidence_ref")
    provenance_refs = _refs(provenance_refs, "provenance_ref")

    current_epoch_ref = evidence_epoch_ref(epoch)
    if assumption.epoch_ref != current_epoch_ref:
        raise ValueError("assumption epoch does not match supplied EvidenceEpoch")
    if compatibility.epoch_ref != current_epoch_ref:
        raise ValueError("compatibility epoch does not match supplied EvidenceEpoch")

    zone_refs = {
        declaration.structural_zone_ref,
        assumption.structural_zone_ref,
        compatibility.structural_zone_ref,
    }
    if len(zone_refs) != 1:
        raise ValueError("declaration/assumption/compatibility structural_zone_ref mismatch")
    directions = {declaration.direction, assumption.direction, compatibility.direction}
    if len(directions) != 1:
        raise ValueError("declaration/assumption/compatibility direction mismatch")
    if compatibility.analysis_assumption_ref != assumption.assumption_id:
        raise ValueError("compatibility analysis_assumption_ref does not match assumption")
    if compatibility.required_basis_ref != resolved_policy_ref:
        raise ValueError("compatibility required_basis_ref does not match resolved_policy_ref")

    identity_payload = {
        "epoch_ref": current_epoch_ref,
        "structural_zone_ref": declaration.structural_zone_ref,
        "direction": declaration.direction,
        "reviewed_declaration_ref": declaration.declaration_id,
        "resolved_policy_ref": resolved_policy_ref,
        "analysis_assumption_ref": assumption.assumption_id,
        "compatibility_ref": compatibility.compatibility_id,
        "analysis_evidence_refs": list(analysis_evidence_refs),
        "provenance_refs": list(provenance_refs),
    }
    encoded = json.dumps(
        identity_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    snapshot_id = "analysis-basis-snapshot:" + hashlib.sha256(encoded).hexdigest()
    return AnalysisBasisSnapshot(
        snapshot_id=snapshot_id,
        epoch_ref=current_epoch_ref,
        structural_zone_ref=declaration.structural_zone_ref,
        direction=declaration.direction,
        reviewed_declaration_ref=declaration.declaration_id,
        resolved_policy_ref=resolved_policy_ref,
        analysis_assumption_ref=assumption.assumption_id,
        compatibility_ref=compatibility.compatibility_id,
        analysis_evidence_refs=analysis_evidence_refs,
        provenance_refs=provenance_refs,
    )


__all__ = [
    "ReviewedDirectionalSystemDeclaration",
    "AnalysisSystemAssumption",
    "AnalysisBasisCompatibility",
    "AnalysisBasisSnapshot",
    "RuleAnalysisBasisRequirement",
    "build_analysis_basis_snapshot",
    "evidence_epoch_ref",
]
