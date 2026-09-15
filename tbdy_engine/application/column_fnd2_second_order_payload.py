"""Typed COLUMN-R1 A21-A23 payload adapter for the existing FND-COL-2 authority.

This module performs serialization/composition only.  It does not evaluate
slenderness or moment magnification and it cannot authorize READY.  The
regulatory FND-COL-2 decoder reconstructs the typed bases and the canonical
``column_design_readiness`` authority re-evaluates them.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Sequence

from tbdy_engine.application.column_a21_slenderness import (
    A21_READY,
    A21StateSlendernessMaterialization,
)
from tbdy_engine.application.column_a22_moment_magnification import (
    A22_EXPLICIT_UNRESOLVED,
    A22_REANALYSIS_REQUIRED,
    A22MomentMagnificationMaterialization,
)
from tbdy_engine.application.column_a23_design_demands import (
    A23_EXPLICIT_UNRESOLVED,
    A23_READY,
    A23_REANALYSIS_REQUIRED,
    A23CanonicalDemandPopulation,
)

TYPED_FND2_PAYLOAD_AUTHORITY = "COLUMN_R1_A21_A23_TYPED_FND2_PAYLOAD"


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if isinstance(value, str) and value.strip()))


def _a21_payload(row: A21StateSlendernessMaterialization) -> dict[str, object]:
    if row.disposition != A21_READY or row.basis is None or row.result is None:
        raise ValueError(f"A21_NOT_READY:{row.output_case}")
    payload = asdict(row.basis)
    payload["output_case"] = row.output_case
    payload["materialization_source_refs"] = tuple(row.source_refs)
    return payload


def build_canonical_second_order_fnd2_payload(
    *,
    component_id: str,
    upstream_blockers: Sequence[str] = (),
    upstream_source_refs: Sequence[str] = (),
    a21_rows: Sequence[A21StateSlendernessMaterialization] = (),
    a22: A22MomentMagnificationMaterialization | None = None,
    a23: A23CanonicalDemandPopulation | None = None,
) -> dict[str, object]:
    """Encode canonical second-order evidence without granting readiness.

    An unresolved source-bound upstream edge is represented as a blocker and is
    intentionally sufficient to route FND2 to ``UNRESOLVED``.  With no upstream
    blockers, A21+A22+A23 must all be present and identity-complete.
    """
    if not isinstance(component_id, str) or not component_id.strip() or component_id != component_id.strip():
        raise ValueError("component_id must be a nonblank canonical string")
    blockers = [item for item in upstream_blockers if isinstance(item, str) and item.strip()]
    reanalysis: list[str] = []
    refs = list(upstream_source_refs)

    state_slenderness: tuple[dict[str, object], ...] = ()
    magnification_bases: tuple[dict[str, object], ...] = ()
    expected_final_states: tuple[dict[str, object], ...] = ()

    if not blockers:
        rows = tuple(a21_rows)
        if not rows:
            raise ValueError("canonical second-order payload requires A21 rows when upstream is resolved")
        if a22 is None or a23 is None:
            raise ValueError("canonical second-order payload requires A22 and A23 when upstream is resolved")
        state_slenderness = tuple(_a21_payload(row) for row in rows)
        refs.extend(ref for row in rows for ref in row.source_refs)
        refs.extend(a22.source_refs)
        refs.extend(a23.source_refs)

        for row in a22.rows:
            if row.disposition == A22_REANALYSIS_REQUIRED:
                reanalysis.extend(
                    f"A22:{row.demand_state_id}:{row.local_bending_axis}:{reason}"
                    for reason in (row.unresolved_reasons or (row.disposition,))
                )
            elif row.disposition == A22_EXPLICIT_UNRESOLVED:
                blockers.extend(
                    f"A22:{row.demand_state_id}:{row.local_bending_axis}:{reason}"
                    for reason in (row.unresolved_reasons or (row.disposition,))
                )

        magnification_bases = tuple(asdict(basis) for basis in a22.bases)
        if a23.status == A23_REANALYSIS_REQUIRED:
            reanalysis.extend(f"A23:{item}" for item in a23.blocked_items)
        elif a23.status == A23_EXPLICIT_UNRESOLVED:
            blockers.extend(f"A23:{item}" for item in a23.blocked_items)
        elif a23.status != A23_READY:
            blockers.append(f"A23:UNSUPPORTED_STATUS:{a23.status}")
        else:
            expected_final_states = tuple(asdict(state) for state in a23.demand_states)

    refs = list(_refs((TYPED_FND2_PAYLOAD_AUTHORITY, *refs)))
    return {
        "component_id": component_id,
        "canonical_second_order": {
            "blockers": tuple(dict.fromkeys(blockers)),
            "reanalysis_items": tuple(dict.fromkeys(reanalysis)),
            "state_slenderness_bases": state_slenderness,
            "moment_magnification_bases": magnification_bases,
            "expected_final_states": expected_final_states,
        },
        "source_refs": tuple(refs),
    }


__all__ = [
    "TYPED_FND2_PAYLOAD_AUTHORITY",
    "build_canonical_second_order_fnd2_payload",
]
