"""Provider-neutral STAB-1 binding for source-bound TS500 Eq.7.13 sway proof.

This module adds no engineering calculation authority.  It binds an existing
``StorySwayStabilityResolution`` produced by :mod:`sway_stability` to the
existing factual ``ColumnSlendernessEvidence`` contract, while enforcing model
and EvidenceEpoch identity.

The ordinary TBDY seismic/design model may legitimately use cracked effective
stiffness.  That model is therefore not mutated or re-labelled as uncracked.
Instead, a positive TS500 7.6.2.1 / Eq.7.13 route must arrive here as a separate
source-bound resolution whose underlying load results were evaluated on the
required UNCRACKED basis by the existing sway-stability authority.

Only when BOTH global X and Y storey directions independently prove
sway-prevented behavior is the component's two local column axes promoted to
``SWAY_PREVENTED``.  Requiring both orthogonal global directions deliberately
avoids inventing a local-axis/global-direction mapping.  Physical M1/M2, the
effective-length factor, free length, and all readiness decisions remain owned
by their existing authorities.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math

from tbdy_engine.design.columns.slenderness import SWAY_PREVENTED
from tbdy_engine.design.columns.slenderness_basis import (
    ColumnSlendernessAxisEvidence,
    ColumnSlendernessEvidence,
    SWAY_CLASSIFICATION_AUTHORITY,
)
from tbdy_engine.design.columns.sway_stability import (
    REQUIRED_STABILITY_LOAD_BASES,
    SWAY_STABILITY_AUTHORITY,
    StorySwayStabilityResolution,
)


EQ713_SWAY_BINDING_AUTHORITY = "STAB_1_TS500_EQ7_13_SWAY_EVIDENCE_BINDING"


class StabilityAnalysisBasisBindingError(ValueError):
    """Raised when context-bound stability evidence cannot be safely composed."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise StabilityAnalysisBasisBindingError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    refs = tuple(_text(value, label) for value in values)
    if not refs:
        raise StabilityAnalysisBasisBindingError(f"{label} must be nonempty")
    if len(refs) != len(set(refs)):
        raise StabilityAnalysisBasisBindingError(f"{label} must be unique")
    return refs


@dataclass(frozen=True, slots=True)
class ColumnSlendernessEvidenceBinding:
    """Bind existing factual column slenderness evidence to one model/epoch/story."""

    evidence: ColumnSlendernessEvidence
    story: str
    model_fingerprint: str
    evidence_epoch_id: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.evidence.component_id, "evidence.component_id")
        _text(self.story, "story")
        _text(self.model_fingerprint, "model_fingerprint")
        _text(self.evidence_epoch_id, "evidence_epoch_id")
        _refs(self.source_refs, "source_ref")


@dataclass(frozen=True, slots=True)
class StorySwayStabilityEvidenceBinding:
    """Bind existing TS500 sway resolutions to one component/model/epoch/story."""

    component_id: str
    story: str
    model_fingerprint: str
    evidence_epoch_id: str
    resolutions: tuple[StorySwayStabilityResolution, ...]
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        component = _text(self.component_id, "component_id")
        story = _text(self.story, "story")
        _text(self.model_fingerprint, "model_fingerprint")
        _text(self.evidence_epoch_id, "evidence_epoch_id")
        _refs(self.source_refs, "source_ref")
        directions: set[str] = set()
        for resolution in self.resolutions:
            _validate_resolution(resolution, story=story)
            if resolution.direction in directions:
                raise StabilityAnalysisBasisBindingError(
                    f"duplicate sway resolution for direction {resolution.direction}"
                )
            directions.add(resolution.direction)
        if not component:
            raise StabilityAnalysisBasisBindingError("component_id must be nonblank")


def _validate_resolution(resolution: StorySwayStabilityResolution, *, story: str) -> None:
    if not isinstance(resolution, StorySwayStabilityResolution):
        raise StabilityAnalysisBasisBindingError(
            "resolutions must contain StorySwayStabilityResolution values"
        )
    if resolution.story != story:
        raise StabilityAnalysisBasisBindingError("sway resolution story differs from binding story")
    if resolution.direction not in {"X", "Y"}:
        raise StabilityAnalysisBasisBindingError("sway resolution direction must be X or Y")
    if resolution.authority != SWAY_STABILITY_AUTHORITY:
        raise StabilityAnalysisBasisBindingError("sway resolution lacks canonical TS500 authority")
    if not resolution.proves_sway_prevented:
        raise StabilityAnalysisBasisBindingError(
            f"{resolution.direction}: sway-prevented behavior is not proven"
        )
    if resolution.missing_load_bases:
        raise StabilityAnalysisBasisBindingError(
            f"{resolution.direction}: required TS500 stability load bases are missing"
        )
    refs = _refs(resolution.source_refs, "resolution.source_ref")

    load_results = resolution.load_results
    bases = tuple(result.load_basis for result in load_results)
    if len(bases) != len(set(bases)) or set(bases) != set(REQUIRED_STABILITY_LOAD_BASES):
        raise StabilityAnalysisBasisBindingError(
            f"{resolution.direction}: exact prescribed TS500 load-basis proof is incomplete"
        )
    if len(load_results) != len(REQUIRED_STABILITY_LOAD_BASES):
        raise StabilityAnalysisBasisBindingError(
            f"{resolution.direction}: unexpected TS500 load-result population"
        )

    for result in load_results:
        if result.story != story or result.direction != resolution.direction:
            raise StabilityAnalysisBasisBindingError("sway load-result identity mismatch")
        if result.authority != SWAY_STABILITY_AUTHORITY or not result.proves_sway_prevented:
            raise StabilityAnalysisBasisBindingError("sway load-result lacks positive TS500 authority")
        if not math.isfinite(result.phi) or result.phi < 0.0 or result.phi > result.limit + 1e-12:
            raise StabilityAnalysisBasisBindingError("sway load-result phi is not a positive proof")
        if not set(result.source_refs).issubset(set(refs)):
            raise StabilityAnalysisBasisBindingError(
                "resolution source_refs do not preserve constituent load-result provenance"
            )

    governing = max(load_results, key=lambda item: (item.phi, item.load_basis))
    if resolution.governing_phi is None or not math.isclose(
        resolution.governing_phi, governing.phi, rel_tol=0.0, abs_tol=1e-12
    ):
        raise StabilityAnalysisBasisBindingError("sway governing phi is inconsistent")
    if resolution.governing_load_basis != governing.load_basis:
        raise StabilityAnalysisBasisBindingError("sway governing load basis is inconsistent")


def _assert_unpopulated_sway(axis: ColumnSlendernessAxisEvidence) -> None:
    values = (axis.sway_classification, axis.sway_source_ref, axis.sway_authority)
    if any(value is not None for value in values):
        raise StabilityAnalysisBasisBindingError(
            f"{axis.axis}: sway evidence is already populated; STAB-1 will not overwrite it"
        )


def promote_eq713_sway_to_column_slenderness_evidence(
    *,
    column: ColumnSlendernessEvidenceBinding,
    sway: StorySwayStabilityEvidenceBinding,
) -> ColumnSlendernessEvidenceBinding:
    """Promote complete, same-context Eq.7.13 sway proof into existing evidence.

    This function performs evidence composition only.  It does not calculate
    Eq.7.13, infer sway-permitted behavior, create physical M1/M2, choose ``k``,
    or decide FND-COL-2 readiness.
    """
    if column.evidence.component_id != sway.component_id:
        raise StabilityAnalysisBasisBindingError("column and sway component identities differ")
    if column.story != sway.story:
        raise StabilityAnalysisBasisBindingError("column and sway story identities differ")
    if column.model_fingerprint != sway.model_fingerprint:
        raise StabilityAnalysisBasisBindingError("cross-model stability evidence is forbidden")
    if column.evidence_epoch_id != sway.evidence_epoch_id:
        raise StabilityAnalysisBasisBindingError("cross-EvidenceEpoch stability evidence is forbidden")

    by_direction = {resolution.direction: resolution for resolution in sway.resolutions}
    if set(by_direction) != {"X", "Y"}:
        missing = tuple(sorted({"X", "Y"} - set(by_direction)))
        raise StabilityAnalysisBasisBindingError(
            f"both orthogonal Eq.7.13 sway proofs are required; missing={missing}"
        )

    _assert_unpopulated_sway(column.evidence.m2)
    _assert_unpopulated_sway(column.evidence.m3)

    proof_ref = f"TS500 7.6.2.1 Eq.7.13 sway proof:{column.story}:X+Y"

    def promote_axis(axis: ColumnSlendernessAxisEvidence) -> ColumnSlendernessAxisEvidence:
        return replace(
            axis,
            sway_classification=SWAY_PREVENTED,
            sway_source_ref=proof_ref,
            sway_authority=SWAY_CLASSIFICATION_AUTHORITY,
        )

    provenance = tuple(
        dict.fromkeys(
            (
                *column.evidence.source_refs,
                *column.source_refs,
                *sway.source_refs,
                *(ref for direction in ("X", "Y") for ref in by_direction[direction].source_refs),
                proof_ref,
                EQ713_SWAY_BINDING_AUTHORITY,
            )
        )
    )
    promoted = replace(
        column.evidence,
        m2=promote_axis(column.evidence.m2),
        m3=promote_axis(column.evidence.m3),
        source_refs=provenance,
    )
    return ColumnSlendernessEvidenceBinding(
        evidence=promoted,
        story=column.story,
        model_fingerprint=column.model_fingerprint,
        evidence_epoch_id=column.evidence_epoch_id,
        source_refs=provenance,
    )


__all__ = [
    "ColumnSlendernessEvidenceBinding",
    "EQ713_SWAY_BINDING_AUTHORITY",
    "StabilityAnalysisBasisBindingError",
    "StorySwayStabilityEvidenceBinding",
    "promote_eq713_sway_to_column_slenderness_evidence",
]
