"""COLUMN-R1 A21 canonical axis-specific TS500 slenderness composition."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.application.column_a19_effective_length import (
    A19_READY,
    A19AxisEffectiveLengthMaterialization,
)
from tbdy_engine.application.column_a20_end_moment_ratio import (
    A20_READY,
    A20AxisEndMomentMaterialization,
)
from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessAxisBasis,
    ColumnSlendernessBasis,
    ColumnSlendernessResult,
    evaluate_ts500_column_slenderness,
)
from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence

A21_READY = "READY"
A21_EXPLICIT_UNRESOLVED = "EXPLICIT_UNRESOLVED"
A21_AUTHORITY = "COLUMN_R1_A21_TS500_SLENDERNESS_COMPOSITION"


@dataclass(frozen=True, slots=True)
class A21StateSlendernessMaterialization:
    component_id: str
    output_case: str
    disposition: str
    result: ColumnSlendernessResult | None
    source_refs: tuple[str, ...]
    unresolved_reasons: tuple[str, ...] = ()
    authority: str = A21_AUTHORITY


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if isinstance(value, str) and value.strip()))


def _one_a19(rows: Sequence[A19AxisEffectiveLengthMaterialization], axis: str):
    matches = tuple(row for row in rows if row.local_bending_axis == axis)
    if len(matches) != 1:
        raise ValueError(f"A19 requires exactly one {axis} row; got {len(matches)}")
    row = matches[0]
    if (
        row.disposition != A19_READY
        or row.k is None
        or row.free_length_ln_mm is None
        or row.sway_classification is None
    ):
        raise ValueError(f"A19_NOT_READY:{axis}")
    return row


def _one_a20(rows: Sequence[A20AxisEndMomentMaterialization], output_case: str, axis: str):
    matches = tuple(
        row for row in rows
        if row.output_case == output_case and row.local_bending_axis == axis
    )
    if len(matches) != 1:
        raise ValueError(f"A20 requires exactly one {output_case}/{axis} row; got {len(matches)}")
    row = matches[0]
    if row.disposition != A20_READY or row.evidence is None:
        raise ValueError(f"A20_NOT_READY:{output_case}:{axis}")
    return row


def materialize_ts500_slenderness_decisions(
    *,
    target_column: ColumnTopologyEvidence,
    a19_rows: Sequence[A19AxisEffectiveLengthMaterialization],
    a20_rows: Sequence[A20AxisEndMomentMaterialization],
    qualified_static_case_names: Sequence[str],
) -> tuple[A21StateSlendernessMaterialization, ...]:
    """Compose A17/A19/A20/geometry into the existing slenderness owner per state."""
    component_id = target_column.component_id
    cases = tuple(qualified_static_case_names)
    if not cases or len(cases) != len(set(cases)):
        raise ValueError("qualified_static_case_names must be nonempty and unique")

    outputs: list[A21StateSlendernessMaterialization] = []
    for output_case in cases:
        try:
            m2_len = _one_a19(a19_rows, "M2")
            m3_len = _one_a19(a19_rows, "M3")
            m2_mom = _one_a20(a20_rows, output_case, "M2")
            m3_mom = _one_a20(a20_rows, output_case, "M3")
            common = _refs(
                (
                    A21_AUTHORITY,
                    *m2_len.source_refs,
                    *m3_len.source_refs,
                    *m2_mom.source_refs,
                    *m3_mom.source_refs,
                    f"strict-topology:column:{target_column.unique_name}:section:{target_column.section}",
                )
            )
            basis = ColumnSlendernessBasis(
                component_id=component_id,
                m2=ColumnSlendernessAxisBasis(
                    axis="M2",
                    section_dimension_mm=float(target_column.depth_t3_m * 1000.0),
                    free_length_ln_mm=float(m2_len.free_length_ln_mm),
                    effective_length_factor_k=float(m2_len.k),
                    sway_classification=str(m2_len.sway_classification),
                    moment_ratio_m1_over_m2=m2_mom.evidence.moment_ratio_m1_over_m2,
                    source_refs=_refs((*m2_len.source_refs, *m2_mom.source_refs)),
                ),
                m3=ColumnSlendernessAxisBasis(
                    axis="M3",
                    section_dimension_mm=float(target_column.width_t2_m * 1000.0),
                    free_length_ln_mm=float(m3_len.free_length_ln_mm),
                    effective_length_factor_k=float(m3_len.k),
                    sway_classification=str(m3_len.sway_classification),
                    moment_ratio_m1_over_m2=m3_mom.evidence.moment_ratio_m1_over_m2,
                    source_refs=_refs((*m3_len.source_refs, *m3_mom.source_refs)),
                ),
                source_refs=common,
            )
            result = evaluate_ts500_column_slenderness(
                component_id=component_id,
                basis=basis,
            )
        except (TypeError, ValueError) as exc:
            outputs.append(
                A21StateSlendernessMaterialization(
                    component_id=component_id,
                    output_case=output_case,
                    disposition=A21_EXPLICIT_UNRESOLVED,
                    result=None,
                    source_refs=(A21_AUTHORITY,),
                    unresolved_reasons=(f"SLENDERNESS_COMPOSITION_FAILED:{exc}",),
                )
            )
            continue

        outputs.append(
            A21StateSlendernessMaterialization(
                component_id=component_id,
                output_case=output_case,
                disposition=A21_READY,
                result=result,
                source_refs=_refs((*common, *result.source_refs, result.authority)),
            )
        )
    return tuple(outputs)


__all__ = [
    "A21_AUTHORITY",
    "A21_EXPLICIT_UNRESOLVED",
    "A21_READY",
    "A21StateSlendernessMaterialization",
    "materialize_ts500_slenderness_decisions",
]
