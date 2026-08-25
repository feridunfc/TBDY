"""Strict promotion boundary for TS500 column slenderness basis.

This module converts reviewed/source-bound evidence into the canonical
``ColumnSlendernessBasis`` consumed by the pure TS500 slenderness kernel.
It deliberately refuses to promote ETABS/story/object clear-length candidates
into regulatory ``ln`` by itself.

Two conservative source-bound derivations are allowed:

* for a sway-prevented column, TS500 7.6.2.2 permits ``k=1.0`` when a more
  detailed effective-length calculation has not been made;
* for the TS500 7.6.2.3 sway-prevented neglect check, using ``M1/M2=+1`` gives
  the minimum possible Eq. 7.17 limit (22) over the admissible ratio range
  [-1,+1], so it is a conservative all-curvature screening value when the
  physical end-curvature sign has not yet been promoted.

Neither derivation can replace missing regulatory free-length or sway evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessAxisBasis,
    ColumnSlendernessBasis,
    SWAY_PERMITTED,
    SWAY_PREVENTED,
)


class ColumnSlendernessBasisPromotionError(ValueError):
    """Raised when supplied evidence is malformed or internally inconsistent."""


REGULATORY_FREE_LENGTH_AUTHORITY = "TS500_REGULATORY_FREE_LENGTH"
SWAY_CLASSIFICATION_AUTHORITY = "TS500_SWAY_CLASSIFICATION"
EFFECTIVE_LENGTH_AUTHORITY = "TS500_EFFECTIVE_LENGTH_FACTOR"
MOMENT_RATIO_AUTHORITY = "TS500_END_MOMENT_RATIO"
FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY = "FACTUAL_ANALYSIS_CLEAR_LENGTH_CANDIDATE"


@dataclass(frozen=True, slots=True)
class ColumnSlendernessAxisEvidence:
    axis: str
    section_dimension_mm: float
    factual_clear_length_candidate_mm: float | None = None
    factual_clear_length_source_ref: str | None = None
    factual_clear_length_authority: str | None = None
    regulatory_free_length_ln_mm: float | None = None
    regulatory_free_length_source_ref: str | None = None
    regulatory_free_length_authority: str | None = None
    sway_classification: str | None = None
    sway_source_ref: str | None = None
    sway_authority: str | None = None
    effective_length_factor_k: float | None = None
    effective_length_source_ref: str | None = None
    effective_length_authority: str | None = None
    moment_ratio_m1_over_m2: float | None = None
    moment_ratio_source_ref: str | None = None
    moment_ratio_authority: str | None = None
    allow_conservative_braced_ratio: bool = True


@dataclass(frozen=True, slots=True)
class ColumnSlendernessEvidence:
    component_id: str
    m2: ColumnSlendernessAxisEvidence
    m3: ColumnSlendernessAxisEvidence
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ColumnSlendernessBasisResolution:
    component_id: str
    status: str
    basis: ColumnSlendernessBasis | None
    blocked_items: tuple[str, ...]
    derivation_notes: tuple[str, ...]
    source_refs: tuple[str, ...]
    authority: str = "TS500_7.6_SLENDERNESS_BASIS_PROMOTION"

    @property
    def resolved(self) -> bool:
        return self.status == "PROVEN_TS500_SLENDERNESS_BASIS"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnSlendernessBasisPromotionError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ColumnSlendernessBasisPromotionError(f"{label} must be finite and > 0")
    return result


def _optional_positive(value: float | None, label: str) -> float | None:
    return None if value is None else _positive(value, label)


def _ratio(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < -1.0 - 1e-12 or result > 1.0 + 1e-12:
        raise ColumnSlendernessBasisPromotionError(f"{label} must be within [-1, 1]")
    return max(-1.0, min(1.0, result))


def _optional_ref(value: str | None, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _axis_resolution(
    evidence: ColumnSlendernessAxisEvidence,
) -> tuple[ColumnSlendernessAxisBasis | None, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    axis = _text(evidence.axis, "axis")
    if axis not in {"M2", "M3"}:
        raise ColumnSlendernessBasisPromotionError("axis must be M2 or M3")
    dimension = _positive(evidence.section_dimension_mm, f"{axis}.section_dimension_mm")

    factual_candidate = _optional_positive(
        evidence.factual_clear_length_candidate_mm,
        f"{axis}.factual_clear_length_candidate_mm",
    )
    factual_ref = _optional_ref(evidence.factual_clear_length_source_ref, f"{axis}.factual_clear_length_source_ref")
    if factual_candidate is not None:
        if factual_ref is None:
            raise ColumnSlendernessBasisPromotionError(
                f"{axis} factual clear-length candidate requires source reference"
            )
        if evidence.factual_clear_length_authority != FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY:
            raise ColumnSlendernessBasisPromotionError(
                f"{axis} factual clear-length candidate has unsupported authority"
            )

    blocked: list[str] = []
    notes: list[str] = []
    refs: list[str] = []
    if factual_ref is not None:
        refs.append(factual_ref)
        notes.append(
            f"{axis}: factual clear-length candidate preserved as evidence only; not promoted to TS500 ln"
        )

    ln = _optional_positive(evidence.regulatory_free_length_ln_mm, f"{axis}.regulatory_free_length_ln_mm")
    ln_ref = _optional_ref(evidence.regulatory_free_length_source_ref, f"{axis}.regulatory_free_length_source_ref")
    if ln is None or ln_ref is None or evidence.regulatory_free_length_authority != REGULATORY_FREE_LENGTH_AUTHORITY:
        blocked.append(f"{axis}:REGULATORY_FREE_LENGTH_NOT_PROMOTED")
    else:
        refs.append(ln_ref)

    sway = evidence.sway_classification
    sway_ref = _optional_ref(evidence.sway_source_ref, f"{axis}.sway_source_ref")
    if (
        sway not in {SWAY_PREVENTED, SWAY_PERMITTED}
        or sway_ref is None
        or evidence.sway_authority != SWAY_CLASSIFICATION_AUTHORITY
    ):
        blocked.append(f"{axis}:SWAY_CLASSIFICATION_NOT_PROMOTED")
    else:
        refs.append(sway_ref)

    k = _optional_positive(evidence.effective_length_factor_k, f"{axis}.effective_length_factor_k")
    k_ref = _optional_ref(evidence.effective_length_source_ref, f"{axis}.effective_length_source_ref")
    if sway == SWAY_PREVENTED and k is None:
        k = 1.0
        k_ref = "TS500 7.6.2.2: sway-prevented column k=1.0 when not calculated"
        notes.append(f"{axis}: k=1.0 derived by TS500 7.6.2.2 sway-prevented default")
    elif k is None or k_ref is None or evidence.effective_length_authority != EFFECTIVE_LENGTH_AUTHORITY:
        blocked.append(f"{axis}:EFFECTIVE_LENGTH_FACTOR_NOT_PROMOTED")
    else:
        refs.append(k_ref)
    if k_ref is not None and k_ref not in refs:
        refs.append(k_ref)

    ratio = evidence.moment_ratio_m1_over_m2
    ratio_ref = _optional_ref(evidence.moment_ratio_source_ref, f"{axis}.moment_ratio_source_ref")
    ratio_authority = evidence.moment_ratio_authority
    if sway == SWAY_PREVENTED:
        if ratio is None and evidence.allow_conservative_braced_ratio:
            ratio = 1.0
            ratio_ref = (
                "TS500 7.6.2.3 Eq.7.17 conservative bound: M1/M2=+1 gives minimum neglect limit 22"
            )
            ratio_authority = MOMENT_RATIO_AUTHORITY
            notes.append(
                f"{axis}: M1/M2=+1 conservative all-curvature screening bound used; physical curvature sign not inferred"
            )
        elif ratio is not None:
            ratio = _ratio(ratio, f"{axis}.moment_ratio_m1_over_m2")
        if ratio is None or ratio_ref is None or ratio_authority != MOMENT_RATIO_AUTHORITY:
            blocked.append(f"{axis}:M1_M2_RATIO_NOT_PROMOTED")
        else:
            refs.append(ratio_ref)
    elif ratio is not None:
        ratio = _ratio(ratio, f"{axis}.moment_ratio_m1_over_m2")
        if ratio_ref is not None:
            refs.append(ratio_ref)

    if blocked:
        return None, tuple(blocked), tuple(dict.fromkeys(notes)), tuple(dict.fromkeys(refs))

    assert ln is not None and sway in {SWAY_PREVENTED, SWAY_PERMITTED} and k is not None
    basis = ColumnSlendernessAxisBasis(
        axis=axis,
        section_dimension_mm=dimension,
        free_length_ln_mm=ln,
        effective_length_factor_k=k,
        sway_classification=sway,
        moment_ratio_m1_over_m2=ratio,
        source_refs=tuple(dict.fromkeys(refs)),
        free_length_authority=REGULATORY_FREE_LENGTH_AUTHORITY,
        effective_length_authority=EFFECTIVE_LENGTH_AUTHORITY,
        sway_authority=SWAY_CLASSIFICATION_AUTHORITY,
        moment_ratio_authority=MOMENT_RATIO_AUTHORITY,
    )
    return basis, (), tuple(dict.fromkeys(notes)), tuple(dict.fromkeys(refs))


def resolve_ts500_column_slenderness_basis(
    evidence: ColumnSlendernessEvidence | None,
    *,
    component_id: str,
) -> ColumnSlendernessBasisResolution:
    """Promote strict evidence to canonical TS500 slenderness basis or block."""
    component = _text(component_id, "component_id")
    if evidence is None:
        return ColumnSlendernessBasisResolution(
            component_id=component,
            status="BLOCKED_TS500_SLENDERNESS_BASIS",
            basis=None,
            blocked_items=("MISSING_SLENDERNESS_EVIDENCE",),
            derivation_notes=(),
            source_refs=("TS500 7.6 slenderness evidence not supplied",),
        )
    if _text(evidence.component_id, "evidence.component_id") != component:
        raise ColumnSlendernessBasisPromotionError("evidence.component_id differs from component_id")
    if evidence.m2.axis != "M2" or evidence.m3.axis != "M3":
        raise ColumnSlendernessBasisPromotionError("evidence requires exactly M2 and M3 axis records")

    basis2, blocked2, notes2, refs2 = _axis_resolution(evidence.m2)
    basis3, blocked3, notes3, refs3 = _axis_resolution(evidence.m3)
    global_refs = tuple(_text(ref, "source_ref") for ref in evidence.source_refs)
    if not global_refs or len(set(global_refs)) != len(global_refs):
        raise ColumnSlendernessBasisPromotionError("evidence.source_refs must be nonempty and unique")

    blocked = tuple((*blocked2, *blocked3))
    refs = tuple(dict.fromkeys((*global_refs, *refs2, *refs3)))
    notes = tuple(dict.fromkeys((*notes2, *notes3)))
    if blocked:
        return ColumnSlendernessBasisResolution(
            component_id=component,
            status="BLOCKED_TS500_SLENDERNESS_BASIS",
            basis=None,
            blocked_items=blocked,
            derivation_notes=notes,
            source_refs=refs,
        )

    assert basis2 is not None and basis3 is not None
    return ColumnSlendernessBasisResolution(
        component_id=component,
        status="PROVEN_TS500_SLENDERNESS_BASIS",
        basis=ColumnSlendernessBasis(
            component_id=component,
            m2=basis2,
            m3=basis3,
            source_refs=refs,
        ),
        blocked_items=(),
        derivation_notes=notes,
        source_refs=refs,
    )


__all__ = [
    "ColumnSlendernessAxisEvidence",
    "ColumnSlendernessBasisPromotionError",
    "ColumnSlendernessBasisResolution",
    "ColumnSlendernessEvidence",
    "EFFECTIVE_LENGTH_AUTHORITY",
    "FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY",
    "MOMENT_RATIO_AUTHORITY",
    "REGULATORY_FREE_LENGTH_AUTHORITY",
    "SWAY_CLASSIFICATION_AUTHORITY",
    "resolve_ts500_column_slenderness_basis",
]
