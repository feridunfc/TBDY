"""Semantic ETABS provider for column endpoint point-restraint facts.

Exact ``PointObj.GetRestraint`` invocation and ABI decoding are owned by
``tbdy_engine.etabs.oapi.object_model``. This provider retains column/topology
meaning and semantic evidence construction only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.oapi.object_model import read_point_restraint
from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence


class EtabsColumnEndpointRestraintError(RuntimeError):
    """Raised when ETABS endpoint restraint evidence cannot be promoted."""


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


def capture_etabs_point_restraint(point_obj: Any, point_name: str) -> EtabsPointRestraintEvidence:
    try:
        fact = read_point_restraint(point_obj, str(point_name))
    except EtabsOAPIError as exc:
        raise EtabsColumnEndpointRestraintError(str(exc)) from exc
    ux, uy, uz, rx, ry, rz = fact.dofs
    return EtabsPointRestraintEvidence(
        point_unique_name=fact.point_name,
        ux=ux,
        uy=uy,
        uz=uz,
        rx=rx,
        ry=ry,
        rz=rz,
        raw_response=fact.raw_response,
        source_ref=f"ETABS:PointObj.GetRestraint:{fact.point_name}",
    )


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
