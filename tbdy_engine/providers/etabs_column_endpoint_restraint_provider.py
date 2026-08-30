"""Semantic ETABS provider for column endpoint point-restraint facts.

Exact ``PointObj.GetRestraint`` invocation and ABI decoding are owned by
``tbdy_engine.etabs.oapi.object_model``. This provider retains column/topology
meaning and semantic evidence construction only. Supported live acquisition
consumes a verified session and typed OAPI facts; raw PointObj never escapes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError, PointRestraintFact
from tbdy_engine.etabs.oapi.object_model import (
    read_point_restraint,
    read_point_restraint_from_session,
)
from tbdy_engine.etabs.safety import EtabsVerifiedSession
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


def _promote_point_fact(fact: PointRestraintFact) -> EtabsPointRestraintEvidence:
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


def capture_etabs_point_restraint(point_obj: Any, point_name: str) -> EtabsPointRestraintEvidence:
    """Compatibility path for an already-bounded raw PointObj interface."""
    try:
        fact = read_point_restraint(point_obj, str(point_name))
    except EtabsOAPIError as exc:
        raise EtabsColumnEndpointRestraintError(str(exc)) from exc
    return _promote_point_fact(fact)


def capture_etabs_point_restraint_from_session(
    session: EtabsVerifiedSession,
    point_name: str,
) -> EtabsPointRestraintEvidence:
    """Supported live path through OAPI -> safety -> gateway."""
    try:
        fact = read_point_restraint_from_session(session, str(point_name))
    except EtabsOAPIError as exc:
        raise EtabsColumnEndpointRestraintError(str(exc)) from exc
    return _promote_point_fact(fact)


def capture_etabs_column_endpoint_restraints(
    point_obj: Any,
    column: ColumnTopologyEvidence,
) -> EtabsColumnEndpointRestraintEvidence:
    """Compatibility path for an already-bounded raw PointObj interface."""
    return EtabsColumnEndpointRestraintEvidence(
        component_id=column.component_id,
        bottom=capture_etabs_point_restraint(point_obj, column.joint_bottom),
        top=capture_etabs_point_restraint(point_obj, column.joint_top),
    )


def capture_etabs_column_endpoint_restraints_from_session(
    session: EtabsVerifiedSession,
    column: ColumnTopologyEvidence,
) -> EtabsColumnEndpointRestraintEvidence:
    """Capture exact endpoint facts without exposing PointObj to the provider caller."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    if not isinstance(column, ColumnTopologyEvidence):
        raise TypeError("column must be ColumnTopologyEvidence")
    return EtabsColumnEndpointRestraintEvidence(
        component_id=column.component_id,
        bottom=capture_etabs_point_restraint_from_session(session, column.joint_bottom),
        top=capture_etabs_point_restraint_from_session(session, column.joint_top),
    )


__all__ = [
    "EtabsColumnEndpointRestraintError",
    "EtabsColumnEndpointRestraintEvidence",
    "EtabsPointRestraintEvidence",
    "capture_etabs_column_endpoint_restraints",
    "capture_etabs_column_endpoint_restraints_from_session",
    "capture_etabs_point_restraint",
    "capture_etabs_point_restraint_from_session",
]
