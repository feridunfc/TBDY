"""Pure VS6-P7 brittle upper-bound mechanics for column shear.

The functions here own only source-bound geometry/equation mechanics.  They
accept canonical N/mm/MPa inputs and emit canonical CheckResult objects.  No
ETABS unit inference, transverse-reinforcement resistance or reporter
calculation is permitted.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.design.columns.column_shear_demand import M2, M3, associated_moment_axis
from tbdy_engine.design.columns.rebar_layout import ColumnBarPoint


class ColumnShearUpperBoundError(ValueError):
    """Raised when exact P7 upper-bound inputs are unavailable or malformed."""


EFFECTIVE_DEPTH_PROVEN = "PROVEN_EXACT_TS500_EFFECTIVE_DEPTH"
EFFECTIVE_DEPTH_BLOCKED = "BLOCKED_EFFECTIVE_DEPTH_BASIS"

TBDY_BRITTLE_CHECK_ID = "TBDY_7_3_7_5_EQ7_7_BRITTLE_UPPER"
TS500_WEB_CHECK_ID = "TS500_8_1_5_WEB_COMPRESSION_UPPER"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnShearUpperBoundError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnShearUpperBoundError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ColumnShearUpperBoundError(f"{label} must be finite and > 0")
    return result


def _nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnShearUpperBoundError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ColumnShearUpperBoundError(f"{label} must be finite and >= 0")
    return result


@dataclass(frozen=True, slots=True)
class ColumnEffectiveDepthResolution:
    component_id: str
    direction: str
    moment_axis: str
    moment_sign: int
    effective_depth_d_mm: float | None
    web_width_bw_mm: float | None
    tension_bar_coordinate_mm: float | None
    status: str
    source_refs: tuple[str, ...]

    @property
    def resolved(self) -> bool:
        return (
            self.status == EFFECTIVE_DEPTH_PROVEN
            and self.effective_depth_d_mm is not None
            and self.web_width_bw_mm is not None
        )


def resolve_exact_rectangular_column_effective_depth(
    *,
    component_id: str,
    direction: str,
    moment_sign: int,
    width_mm: float,
    depth_mm: float,
    bars: Sequence[ColumnBarPoint],
    source_refs: Sequence[str],
) -> ColumnEffectiveDepthResolution:
    """Resolve TS500 d from explicit selected-bar coordinates; never use d=0.9h."""
    component = _text(component_id, "component_id")
    axis = associated_moment_axis(direction)
    if moment_sign not in {-1, 1}:
        raise ColumnShearUpperBoundError("moment_sign must be -1 or +1")
    width = _positive(width_mm, "width_mm")
    depth = _positive(depth_mm, "depth_mm")
    refs = tuple(_text(ref, "source_ref") for ref in source_refs)
    if not refs or len(refs) != len(set(refs)):
        raise ColumnShearUpperBoundError("source_refs must be nonempty and unique")
    items = tuple(bars)
    if not items:
        return ColumnEffectiveDepthResolution(
            component_id=component,
            direction=direction,
            moment_axis=axis,
            moment_sign=moment_sign,
            effective_depth_d_mm=None,
            web_width_bw_mm=None,
            tension_bar_coordinate_mm=None,
            status=EFFECTIVE_DEPTH_BLOCKED,
            source_refs=refs,
        )

    if axis == M3:
        # section_capacity.py uses M3 = -sum(F*x2). Positive M3 therefore
        # places tensile (negative) steel force on the +x2 face.
        coords = tuple(float(bar.x2_mm) for bar in items)
        tension = max(coords) if moment_sign > 0 else min(coords)
        compression_face = -width / 2.0 if moment_sign > 0 else width / 2.0
        d = abs(tension - compression_face)
        bw = depth
    elif axis == M2:
        # section_capacity.py uses M2 = sum(F*x3). Positive M2 therefore
        # places tensile (negative) steel force on the -x3 face.
        coords = tuple(float(bar.x3_mm) for bar in items)
        tension = min(coords) if moment_sign > 0 else max(coords)
        compression_face = depth / 2.0 if moment_sign > 0 else -depth / 2.0
        d = abs(tension - compression_face)
        bw = width
    else:  # pragma: no cover
        raise ColumnShearUpperBoundError("unsupported associated moment axis")

    member_depth = width if axis == M3 else depth
    if not math.isfinite(d) or d <= 0.0 or d >= member_depth + 1e-9:
        return ColumnEffectiveDepthResolution(
            component_id=component,
            direction=direction,
            moment_axis=axis,
            moment_sign=moment_sign,
            effective_depth_d_mm=None,
            web_width_bw_mm=None,
            tension_bar_coordinate_mm=tension,
            status=EFFECTIVE_DEPTH_BLOCKED,
            source_refs=refs,
        )

    return ColumnEffectiveDepthResolution(
        component_id=component,
        direction=direction,
        moment_axis=axis,
        moment_sign=moment_sign,
        effective_depth_d_mm=d,
        web_width_bw_mm=bw,
        tension_bar_coordinate_mm=tension,
        status=EFFECTIVE_DEPTH_PROVEN,
        source_refs=refs,
    )


def evaluate_tbdy_7375_brittle_upper_bound(
    *,
    component_id: str,
    story: str,
    section: str,
    direction: str,
    ve_n: float,
    aw_mm2: float,
    fck_mpa: float,
    evidence: Sequence[object],
) -> CheckResult:
    """TBDY 2018 7.3.7.5 Eq.7.7 second condition: Ve <= 0.85 Aw sqrt(fck)."""
    component = _text(component_id, "component_id")
    _text(story, "story")
    _text(section, "section")
    _text(direction, "direction")
    ve = _nonnegative(ve_n, "ve_n")
    aw = _positive(aw_mm2, "aw_mm2")
    fck = _positive(fck_mpa, "fck_mpa")
    limit = 0.85 * aw * math.sqrt(fck)
    ratio = ve / limit
    satisfied = ve <= limit
    return CheckResult(
        check_id=TBDY_BRITTLE_CHECK_ID,
        component=component,
        component_type="column",
        story=story,
        section=section,
        status=CheckStatus.OK if satisfied else CheckStatus.FAIL,
        value=ve,
        limit=limit,
        demand=ve,
        capacity=limit,
        ratio=ratio,
        ratio_type="demand_over_capacity",
        pass_rule="Ve <= 0.85 * Aw * sqrt(fck)",
        unit="N",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=tuple(evidence),
        messages=(
            "TBDY_7_3_7_5_EQ7_7_BRITTLE_SATISFIED"
            if satisfied
            else "TBDY_7_3_7_5_EQ7_7_BRITTLE_NOT_SATISFIED_REANALYSIS_REQUIRED",
        ),
        code_ref="TBDY 2018 7.3.7.5 Eq. (7.7)",
        diagnostics=(),
    )


def evaluate_ts500_815_web_compression_upper_bound(
    *,
    component_id: str,
    story: str,
    section: str,
    direction: str,
    vd_n: float,
    fcd_mpa: float,
    effective_depth: ColumnEffectiveDepthResolution,
    evidence: Sequence[object],
) -> CheckResult:
    """TS500 8.1.5 web-compression upper bound: Vd <= 0.22 fcd bw d."""
    component = _text(component_id, "component_id")
    _text(story, "story")
    _text(section, "section")
    _text(direction, "direction")
    vd = _nonnegative(vd_n, "vd_n")
    fcd = _positive(fcd_mpa, "fcd_mpa")
    if not isinstance(effective_depth, ColumnEffectiveDepthResolution):
        raise TypeError("effective_depth must be ColumnEffectiveDepthResolution")
    if not effective_depth.resolved:
        return CheckResult(
            check_id=TS500_WEB_CHECK_ID,
            component=component,
            component_type="column",
            story=story,
            section=section,
            status=CheckStatus.BLOCKED,
            evaluation_level=EvaluationLevel.NO_DATA,
            evidence=tuple(evidence),
            messages=(EFFECTIVE_DEPTH_BLOCKED,),
            code_ref="TS 500 8.1.5",
            diagnostics=(),
        )
    if effective_depth.component_id != component or effective_depth.direction != direction:
        raise ColumnShearUpperBoundError("effective-depth identity differs from check identity")

    bw = float(effective_depth.web_width_bw_mm)
    d = float(effective_depth.effective_depth_d_mm)
    limit = 0.22 * fcd * bw * d
    ratio = vd / limit
    satisfied = vd <= limit
    return CheckResult(
        check_id=TS500_WEB_CHECK_ID,
        component=component,
        component_type="column",
        story=story,
        section=section,
        status=CheckStatus.OK if satisfied else CheckStatus.FAIL,
        value=vd,
        limit=limit,
        demand=vd,
        capacity=limit,
        ratio=ratio,
        ratio_type="demand_over_capacity",
        pass_rule="Vd <= 0.22 * fcd * bw * d",
        unit="N",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=tuple(evidence),
        messages=(
            "TS500_8_1_5_WEB_COMPRESSION_SATISFIED"
            if satisfied
            else "TS500_8_1_5_WEB_COMPRESSION_NOT_SATISFIED",
        ),
        code_ref="TS 500 8.1.5",
        diagnostics=(),
    )


__all__ = [
    "EFFECTIVE_DEPTH_PROVEN",
    "EFFECTIVE_DEPTH_BLOCKED",
    "TBDY_BRITTLE_CHECK_ID",
    "TS500_WEB_CHECK_ID",
    "ColumnEffectiveDepthResolution",
    "ColumnShearUpperBoundError",
    "evaluate_tbdy_7375_brittle_upper_bound",
    "evaluate_ts500_815_web_compression_upper_bound",
    "resolve_exact_rectangular_column_effective_depth",
]
