"""COLUMN-R1 A19 source-bound TS500 effective-length materialization.

Application composes A18 end-restraint ratios, the existing A17 local-axis sway
binding, and the resolved regulatory free length.  TS500 Eq.7.14/Eq.7.15 and
``Lk = k*ln`` remain owned by ``design.columns.effective_length``.
"""
from __future__ import annotations

from dataclasses import dataclass

from tbdy_engine.application.column_a18_end_restraint import (
    A18_AUTHORITY,
    A18_READY,
    A18EndRestraintMaterialization,
)
from tbdy_engine.application.column_local_sway_runtime import (
    STATUS_READY as A17_READY,
    ColumnLocalAxisSwayRuntime,
)
from tbdy_engine.design.columns.effective_length import (
    ColumnEffectiveLengthAxisBasis,
    ColumnEffectiveLengthError,
    column_effective_length_mm,
    evaluate_ts500_effective_length_factor,
)
from tbdy_engine.design.columns.free_length_basis import (
    FREE_LENGTH_PROVEN,
    ColumnFreeLengthResolution,
)

A19_READY = "READY"
A19_EXPLICIT_UNRESOLVED = "EXPLICIT_UNRESOLVED"
A19_AUTHORITY = "COLUMN_R1_A19_TS500_EFFECTIVE_LENGTH_COMPOSITION"
A19_ONE_END_HINGED_AUTHORITY = (
    "COLUMN_R1_A19_ONE_END_HINGED_FROM_A18_NO_RELEASE_OR_PARTIAL_FIXITY"
)


@dataclass(frozen=True, slots=True)
class A19AxisEffectiveLengthMaterialization:
    component_id: str
    local_bending_axis: str
    disposition: str
    sway_classification: str | None
    alpha_bottom: float | None
    alpha_top: float | None
    one_end_hinged: bool | None
    k: float | None
    free_length_ln_mm: float | None
    effective_length_lk_mm: float | None
    controlling_equation: str | None
    source_refs: tuple[str, ...]
    unresolved_reasons: tuple[str, ...] = ()
    authority: str = A19_AUTHORITY


def _refs(*groups: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(ref for group in groups for ref in group if ref))


def _a18_for(
    rows: tuple[A18EndRestraintMaterialization, ...],
    *,
    axis: str,
    end_tag: str,
) -> A18EndRestraintMaterialization:
    matches = tuple(
        row for row in rows
        if row.local_bending_axis == axis and row.end_tag == end_tag
    )
    if len(matches) != 1:
        raise ValueError(f"A18 requires exactly one {end_tag}/{axis} row; got {len(matches)}")
    return matches[0]


def _derive_one_end_hinged_from_a18(
    *,
    bottom: A18EndRestraintMaterialization,
    top: A18EndRestraintMaterialization,
) -> tuple[bool, tuple[str, ...]]:
    rows = (bottom, top)

    for row in rows:
        if row.disposition != A18_READY:
            raise ValueError(
                f"A18_NOT_READY_FOR_ONE_END_HINGED:"
                f"{row.local_bending_axis}:{row.end_tag}"
            )

        if row.authority != A18_AUTHORITY:
            raise ValueError(
                f"A18_AUTHORITY_MISMATCH_FOR_ONE_END_HINGED:"
                f"{row.local_bending_axis}:{row.end_tag}"
            )

        release_refs = tuple(
            ref
            for ref in row.source_refs
            if ref.startswith("etabs-frame-release:sha256:")
        )

        if not release_refs:
            raise ValueError(
                f"A18_RELEASE_EVIDENCE_NOT_BOUND_FOR_ONE_END_HINGED:"
                f"{row.local_bending_axis}:{row.end_tag}"
            )

    refs = _refs(
        bottom.source_refs,
        top.source_refs,
        (
            A19_ONE_END_HINGED_AUTHORITY,
            "A18_READY_CONTRACT:NO_RELEASE_OR_PARTIAL_FIXITY_EFFECT",
        ),
    )

    # Source-bound negative fact:
    # this supported A18 slice cannot represent an exactly-one-end-hinged
    # target Column.
    return False, refs


def _unresolved(
    *,
    component_id: str,
    axis: str,
    reason: str,
    source_refs: tuple[str, ...],
    alpha_bottom: float | None = None,
    alpha_top: float | None = None,
    one_end_hinged: bool | None = None,
    sway_classification: str | None = None,
    free_length_ln_mm: float | None = None,
) -> A19AxisEffectiveLengthMaterialization:
    return A19AxisEffectiveLengthMaterialization(
        component_id=component_id,
        local_bending_axis=axis,
        disposition=A19_EXPLICIT_UNRESOLVED,
        sway_classification=sway_classification,
        alpha_bottom=alpha_bottom,
        alpha_top=alpha_top,
        one_end_hinged=one_end_hinged,
        k=None,
        free_length_ln_mm=free_length_ln_mm,
        effective_length_lk_mm=None,
        controlling_equation=None,
        source_refs=source_refs,
        unresolved_reasons=(reason,),
    )


def materialize_ts500_effective_lengths(
    *,
    component_id: str,
    a18_rows: tuple[A18EndRestraintMaterialization, ...],
    local_sway: ColumnLocalAxisSwayRuntime,
    free_length: ColumnFreeLengthResolution,
) -> tuple[A19AxisEffectiveLengthMaterialization, ...]:
    """Materialize independent M2/M3 ``k`` and ``Lk`` without any k=1 fallback."""
    if not isinstance(component_id, str) or not component_id.strip():
        raise ValueError("component_id must be nonblank")
    base_refs = _refs(
        (A19_AUTHORITY,),
        tuple(getattr(local_sway, "source_refs", ()) or ()),
        tuple(getattr(free_length, "source_refs", ()) or ()),
    )
    outputs: list[A19AxisEffectiveLengthMaterialization] = []

    for axis in ("M2", "M3"):
        try:
            bottom = _a18_for(a18_rows, axis=axis, end_tag="BOTTOM")
            top = _a18_for(a18_rows, axis=axis, end_tag="TOP")
        except ValueError as exc:
            outputs.append(
                _unresolved(
                    component_id=component_id,
                    axis=axis,
                    reason=str(exc),
                    source_refs=base_refs,
                )
            )
            continue

        refs = _refs(base_refs, bottom.source_refs, top.source_refs)
        alpha_bottom = bottom.alpha if bottom.disposition == A18_READY else None
        alpha_top = top.alpha if top.disposition == A18_READY else None
        if alpha_bottom is None or alpha_top is None:
            outputs.append(
                _unresolved(
                    component_id=component_id,
                    axis=axis,
                    reason=f"A18_NOT_READY:{axis}",
                    source_refs=refs,
                    alpha_bottom=alpha_bottom,
                    alpha_top=alpha_top,
                )
            )
            continue

        try:
            one_end_hinged, hinge_refs = _derive_one_end_hinged_from_a18(
                bottom=bottom,
                top=top,
            )
        except ValueError as exc:
            outputs.append(
                _unresolved(
                    component_id=component_id,
                    axis=axis,
                    reason=str(exc),
                    source_refs=refs,
                    alpha_bottom=alpha_bottom,
                    alpha_top=alpha_top,
                )
            )
            continue

        refs = _refs(refs, hinge_refs)

        local_axis = getattr(local_sway.local_binding, axis.lower(), None)
        sway = None if local_axis is None else local_axis.sway_classification
        if local_sway.status != A17_READY or sway is None:
            outputs.append(
                _unresolved(
                    component_id=component_id,
                    axis=axis,
                    reason=f"A17_LOCAL_SWAY_NOT_RESOLVED:{axis}",
                    source_refs=_refs(refs, tuple(getattr(local_axis, "source_refs", ()) or ())),
                    alpha_bottom=alpha_bottom,
                    alpha_top=alpha_top,
                    one_end_hinged=one_end_hinged,
                )
            )
            continue

        ln = free_length.free_length_ln_mm if free_length.status == FREE_LENGTH_PROVEN else None
        if ln is None:
            outputs.append(
                _unresolved(
                    component_id=component_id,
                    axis=axis,
                    reason="REGULATORY_FREE_LENGTH_NOT_RESOLVED",
                    source_refs=refs,
                    alpha_bottom=alpha_bottom,
                    alpha_top=alpha_top,
                    one_end_hinged=one_end_hinged,
                    sway_classification=sway,
                )
            )
            continue

        try:
            basis = ColumnEffectiveLengthAxisBasis(
                axis=axis,
                alpha_bottom=float(alpha_bottom),
                alpha_top=float(alpha_top),
                sway_classification=sway,
                one_end_hinged=one_end_hinged,
                source_refs=_refs(
                    refs,
                    tuple(getattr(local_axis, "source_refs", ()) or ()),
                    (free_length.authority, A19_AUTHORITY),
                ),
            )
            factor = evaluate_ts500_effective_length_factor(basis)
            lk = column_effective_length_mm(
                free_length_mm=float(ln),
                factor=factor,
            )
        except (ColumnEffectiveLengthError, TypeError, ValueError) as exc:
            outputs.append(
                _unresolved(
                    component_id=component_id,
                    axis=axis,
                    reason=f"EFFECTIVE_LENGTH_EVALUATION_FAILED:{exc}",
                    source_refs=refs,
                    alpha_bottom=alpha_bottom,
                    alpha_top=alpha_top,
                    one_end_hinged=one_end_hinged,
                    sway_classification=sway,
                    free_length_ln_mm=float(ln),
                )
            )
            continue

        outputs.append(
            A19AxisEffectiveLengthMaterialization(
                component_id=component_id,
                local_bending_axis=axis,
                disposition=A19_READY,
                sway_classification=sway,
                alpha_bottom=float(alpha_bottom),
                alpha_top=float(alpha_top),
                one_end_hinged=one_end_hinged,
                k=factor.effective_length_factor_k,
                free_length_ln_mm=float(ln),
                effective_length_lk_mm=lk,
                controlling_equation=None,
                source_refs=_refs(refs, factor.source_refs, (factor.authority, A19_AUTHORITY)),
            )
        )

    return tuple(outputs)


__all__ = [
    "A19_AUTHORITY",
    "A19_ONE_END_HINGED_AUTHORITY",
    "A19_EXPLICIT_UNRESOLVED",
    "A19_READY",
    "A19AxisEffectiveLengthMaterialization",
    "materialize_ts500_effective_lengths",
]
