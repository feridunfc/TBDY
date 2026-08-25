"""Read-only ETABS provider for column endpoint point-restraint facts.

This layer decodes ``PointObj.GetRestraint`` only. It does not decide TS500 free
length, sway classification, effective length, or design authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence


class EtabsColumnEndpointRestraintError(RuntimeError):
    """Raised when ETABS endpoint restraint data cannot be decoded exactly."""


@dataclass(frozen=True, slots=True)
class EtabsPointRestraintEvidence:
    point_unique_name: str
    ux: bool
    uy: bool
    uz: bool
    rx: bool
    ry: bool
    rz: bool
    raw_response: object
    source_ref: str
    authority: str = "ETABS_FACTUAL_POINT_RESTRAINT"

    @property
    def dofs(self) -> tuple[bool, bool, bool, bool, bool, bool]:
        return (self.ux, self.uy, self.uz, self.rx, self.ry, self.rz)


@dataclass(frozen=True, slots=True)
class EtabsColumnEndpointRestraintEvidence:
    component_id: str
    bottom: EtabsPointRestraintEvidence
    top: EtabsPointRestraintEvidence
    authority: str = "ETABS_FACTUAL_COLUMN_ENDPOINT_RESTRAINTS"


def _decode_get_restraint(point_name: str, raw: Any) -> EtabsPointRestraintEvidence:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        raise EtabsColumnEndpointRestraintError(
            f"PointObj.GetRestraint({point_name!r}) returned unsupported shape {type(raw).__name__}"
        )

    return_code = raw[-1]
    if not isinstance(return_code, int) or return_code != 0:
        raise EtabsColumnEndpointRestraintError(
            f"PointObj.GetRestraint({point_name!r}) returned code {return_code!r}"
        )

    candidates: list[Sequence[Any]] = [
        item for item in raw[:-1]
        if isinstance(item, (list, tuple)) and len(item) == 6
    ]
    if len(candidates) != 1:
        raise EtabsColumnEndpointRestraintError(
            f"PointObj.GetRestraint({point_name!r}) requires exactly one six-DOF array; got {len(candidates)}"
        )
    dofs = candidates[0]
    if not all(isinstance(item, bool) for item in dofs):
        raise EtabsColumnEndpointRestraintError(
            f"PointObj.GetRestraint({point_name!r}) DOF array must contain booleans"
        )

    return EtabsPointRestraintEvidence(
        point_unique_name=str(point_name),
        ux=bool(dofs[0]),
        uy=bool(dofs[1]),
        uz=bool(dofs[2]),
        rx=bool(dofs[3]),
        ry=bool(dofs[4]),
        rz=bool(dofs[5]),
        raw_response=raw,
        source_ref=f"ETABS:PointObj.GetRestraint:{point_name}",
    )


def capture_etabs_point_restraint(point_obj: Any, point_name: str) -> EtabsPointRestraintEvidence:
    try:
        raw = point_obj.GetRestraint(str(point_name))
    except Exception as exc:  # pragma: no cover - live COM only
        raise EtabsColumnEndpointRestraintError(
            f"PointObj.GetRestraint({point_name!r}) failed: {type(exc).__name__}: {exc}"
        ) from exc
    return _decode_get_restraint(str(point_name), raw)


def capture_etabs_column_endpoint_restraints(
    point_obj: Any,
    column: ColumnTopologyEvidence,
) -> EtabsColumnEndpointRestraintEvidence:
    return EtabsColumnEndpointRestraintEvidence(
        component_id=column.component_id,
        bottom=capture_etabs_point_restraint(point_obj, column.joint_bottom),
        top=capture_etabs_point_restraint(point_obj, column.joint_top),
    )


__all__ = [
    "EtabsColumnEndpointRestraintError",
    "EtabsColumnEndpointRestraintEvidence",
    "EtabsPointRestraintEvidence",
    "capture_etabs_column_endpoint_restraints",
    "capture_etabs_point_restraint",
]
