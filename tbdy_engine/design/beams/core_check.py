from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from tbdy_engine.design.beams.calculators.geometry import GeometryCheck


_ALLOWED_STATUSES = {"OK", "FAIL", "WARNING", "NO_DATA", "ERROR"}


@dataclass(frozen=True)
class CoreCheck:
    id: str
    component: str
    check_type: str
    name: str
    status: str
    demand: float | None
    capacity: float | None
    ratio: float | None
    unit: str | None
    code_ref: str | None
    evidence: Mapping[str, object]
    message: str


def geometry_check_to_core_check(
    *,
    beam_id: str,
    story: str,
    section_name: str,
    check: GeometryCheck,
) -> CoreCheck:
    status = check.status if check.status in _ALLOWED_STATUSES else "ERROR"
    evidence = dict(check.evidence)
    evidence["story"] = story
    evidence["section_name"] = section_name
    return CoreCheck(
        id=f"{beam_id}:geometry:{check.name}",
        component=beam_id,
        check_type="geometry",
        name=check.name,
        status=status,
        demand=check.demand,
        capacity=check.capacity,
        ratio=check.ratio,
        unit=check.unit,
        code_ref=check.code_ref,
        evidence=evidence,
        message=check.message,
    )


def shear_check_to_core_check(
    *,
    beam_id: str,
    story: str,
    section_name: str,
    check: object,
) -> CoreCheck:
    status = check.status if check.status in _ALLOWED_STATUSES else "ERROR"
    evidence = dict(check.evidence)
    evidence["story"] = story
    evidence["section_name"] = section_name
    return CoreCheck(
        id=f"{beam_id}:shear:{check.name}",
        component=beam_id,
        check_type="shear",
        name=check.name,
        status=status,
        demand=check.demand,
        capacity=check.capacity,
        ratio=check.ratio,
        unit=check.unit,
        code_ref=check.code_ref,
        evidence=evidence,
        message=check.message,
    )

def flexure_check_to_core_check(
    *,
    beam_id: str,
    story: str,
    section_name: str,
    check: object,
) -> CoreCheck:
    status = check.status if check.status in _ALLOWED_STATUSES else "ERROR"
    evidence = dict(check.evidence)
    evidence["story"] = story
    evidence["section_name"] = section_name
    return CoreCheck(
        id=f"{beam_id}:flexure:{check.name}",
        component=beam_id,
        check_type="flexure",
        name=check.name,
        status=status,
        demand=check.demand,
        capacity=check.capacity,
        ratio=check.ratio,
        unit=check.unit,
        code_ref=check.code_ref,
        evidence=evidence,
        message=check.message,
    )