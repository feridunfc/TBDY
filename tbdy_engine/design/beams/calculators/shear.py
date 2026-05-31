from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from tbdy_engine.design.beams.context import BeamModelContext



@dataclass(frozen=True)
class CapacityShearDemandResult:
    left_plastic_moment_kNm: float | None
    right_plastic_moment_kNm: float | None
    Ln_mm: float
    Ln_m: float | None
    gravity_shear_kN: float | None
    Ve_capacity_kN: float | None
    status: str
    evidence: Mapping[str, object]
@dataclass(frozen=True)
class ShearCheck:
    name: str
    status: str
    demand: float | None
    capacity: float | None
    ratio: float | None
    unit: str | None
    code_ref: str
    evidence: Mapping[str, object]
    message: str


@dataclass(frozen=True)
class ShearResult:
    Ve_kN: float
    Vc_kN: float
    Vw_kN: float
    Vr_kN: float
    Vmax_kN: float
    Asw_mm2: float
    Asw_cm2: float
    Asw_min_mm2: float
    Asw_min_cm2: float
    checks: tuple[ShearCheck, ...]
    status: str


class TBDYShearCalculator:
    def calculate(self, ctx: BeamModelContext) -> ShearResult:
        Ve_kN = abs(ctx.Ve_left_kN)
        Vc_kN = 0.0

        single_bar_area_mm2 = math.pi * ctx.stirrup_diameter_mm**2 / 4.0
        Asw_mm2 = ctx.stirrup_legs * single_bar_area_mm2
        Asw_cm2 = Asw_mm2 / 100.0

        Asw_min_mm2 = 0.3 * ctx.fctd_mpa * ctx.bw_mm * ctx.stirrup_spacing_mm / ctx.fywd_mpa
        Asw_min_cm2 = Asw_min_mm2 / 100.0

        Vw_kN = Asw_mm2 * ctx.fywd_mpa * ctx.d_mm / ctx.stirrup_spacing_mm / 1000.0
        Vr_kN = Vc_kN + Vw_kN
        Vmax_kN = 0.85 * 0.22 * ctx.fcd_mpa * ctx.bw_mm * ctx.d_mm / 1000.0

        checks = (
            self._ve_le_vr(ctx, Ve_kN, Vc_kN, Vw_kN, Vr_kN, Vmax_kN, Asw_mm2, Asw_cm2, Asw_min_mm2, Asw_min_cm2),
            self._ve_le_085_vmax(ctx, Ve_kN, Vc_kN, Vw_kN, Vr_kN, Vmax_kN, Asw_mm2, Asw_cm2, Asw_min_mm2, Asw_min_cm2),
            self._spacing_le_d_over_4(ctx, Ve_kN, Vc_kN, Vw_kN, Vr_kN, Vmax_kN, Asw_mm2, Asw_cm2, Asw_min_mm2, Asw_min_cm2),
            self._spacing_le_150(ctx, Ve_kN, Vc_kN, Vw_kN, Vr_kN, Vmax_kN, Asw_mm2, Asw_cm2, Asw_min_mm2, Asw_min_cm2),
            self._spacing_le_8_longitudinal_diameter(ctx),
            self._stirrup_diameter_ge_8(ctx, Ve_kN, Vc_kN, Vw_kN, Vr_kN, Vmax_kN, Asw_mm2, Asw_cm2, Asw_min_mm2, Asw_min_cm2),
            self._stirrup_legs_ge_2(ctx, Ve_kN, Vc_kN, Vw_kN, Vr_kN, Vmax_kN, Asw_mm2, Asw_cm2, Asw_min_mm2, Asw_min_cm2),
            self._asw_ge_asw_min(ctx, Asw_mm2, Asw_cm2, Asw_min_mm2, Asw_min_cm2),
        )
        status = "OK" if all(check.status == "OK" for check in checks) else "FAIL"

        return ShearResult(
            Ve_kN=Ve_kN,
            Vc_kN=Vc_kN,
            Vw_kN=Vw_kN,
            Vr_kN=Vr_kN,
            Vmax_kN=Vmax_kN,
            Asw_mm2=Asw_mm2,
            Asw_cm2=Asw_cm2,
            Asw_min_mm2=Asw_min_mm2,
            Asw_min_cm2=Asw_min_cm2,
            checks=checks,
            status=status,
        )

    def _base_evidence(
        self,
        ctx: BeamModelContext,
        *,
        Ve_kN: float,
        Vc_kN: float,
        Vw_kN: float,
        Vr_kN: float,
        Vmax_kN: float,
        Asw_mm2: float,
        Asw_cm2: float,
        Asw_min_mm2: float,
        Asw_min_cm2: float,
        formula: str,
        limit_kN: float | None = None,
    ) -> dict[str, object]:
        evidence: dict[str, object] = {
            "Ve_kN": Ve_kN,
            "Vr_kN": Vr_kN,
            "Vc_kN": Vc_kN,
            "Vw_kN": Vw_kN,
            "Vmax_kN": Vmax_kN,
            "bw_mm": ctx.bw_mm,
            "d_mm": ctx.d_mm,
            "fcd_mpa": ctx.fcd_mpa,
            "fctd_mpa": ctx.fctd_mpa,
            "fywd_mpa": ctx.fywd_mpa,
            "stirrup_diameter_mm": ctx.stirrup_diameter_mm,
            "stirrup_legs": ctx.stirrup_legs,
            "stirrup_spacing_mm": ctx.stirrup_spacing_mm,
            "Asw_mm2": Asw_mm2,
            "Asw_cm2": Asw_cm2,
            "Asw_min_mm2": Asw_min_mm2,
            "Asw_min_cm2": Asw_min_cm2,
            "formula": formula,
        }
        if limit_kN is not None:
            evidence["limit_kN"] = limit_kN
        return evidence

    def _ve_le_vr(
        self,
        ctx: BeamModelContext,
        Ve_kN: float,
        Vc_kN: float,
        Vw_kN: float,
        Vr_kN: float,
        Vmax_kN: float,
        Asw_mm2: float,
        Asw_cm2: float,
        Asw_min_mm2: float,
        Asw_min_cm2: float,
    ) -> ShearCheck:
        ratio = Ve_kN / Vr_kN if Vr_kN > 0 else None
        return ShearCheck(
            name="beam_shear_ve_le_vr",
            status="OK" if Ve_kN <= Vr_kN else "FAIL",
            demand=Ve_kN,
            capacity=Vr_kN,
            ratio=ratio,
            unit="kN",
            code_ref="TBDY 2018 7.4.5.2",
            evidence=self._base_evidence(
                ctx,
                Ve_kN=Ve_kN,
                Vc_kN=Vc_kN,
                Vw_kN=Vw_kN,
                Vr_kN=Vr_kN,
                Vmax_kN=Vmax_kN,
                Asw_mm2=Asw_mm2,
                Asw_cm2=Asw_cm2,
                Asw_min_mm2=Asw_min_mm2,
                Asw_min_cm2=Asw_min_cm2,
                formula="Ve = abs(Ve_left_kN); Vr = Vc + Vw",
                limit_kN=Vr_kN,
            ),
            message="Ve <= Vr" if Ve_kN <= Vr_kN else "Ve exceeds Vr",
        )

    def _ve_le_085_vmax(
        self,
        ctx: BeamModelContext,
        Ve_kN: float,
        Vc_kN: float,
        Vw_kN: float,
        Vr_kN: float,
        Vmax_kN: float,
        Asw_mm2: float,
        Asw_cm2: float,
        Asw_min_mm2: float,
        Asw_min_cm2: float,
    ) -> ShearCheck:
        capacity = 0.85 * Vmax_kN
        ratio = Ve_kN / capacity if Vmax_kN > 0 else None
        return ShearCheck(
            name="beam_shear_ve_le_085_vmax",
            status="OK" if Ve_kN <= capacity else "FAIL",
            demand=Ve_kN,
            capacity=capacity,
            ratio=ratio,
            unit="kN",
            code_ref="TBDY 2018 7.4.5.4",
            evidence=self._base_evidence(
                ctx,
                Ve_kN=Ve_kN,
                Vc_kN=Vc_kN,
                Vw_kN=Vw_kN,
                Vr_kN=Vr_kN,
                Vmax_kN=Vmax_kN,
                Asw_mm2=Asw_mm2,
                Asw_cm2=Asw_cm2,
                Asw_min_mm2=Asw_min_mm2,
                Asw_min_cm2=Asw_min_cm2,
                formula="Ve <= 0.85 * Vmax",
                limit_kN=capacity,
            ),
            message="Ve <= 0.85 Vmax" if Ve_kN <= capacity else "Ve exceeds 0.85 Vmax",
        )

    def _spacing_le_d_over_4(
        self,
        ctx: BeamModelContext,
        Ve_kN: float,
        Vc_kN: float,
        Vw_kN: float,
        Vr_kN: float,
        Vmax_kN: float,
        Asw_mm2: float,
        Asw_cm2: float,
        Asw_min_mm2: float,
        Asw_min_cm2: float,
    ) -> ShearCheck:
        capacity = ctx.d_mm / 4.0
        return ShearCheck(
            name="beam_shear_spacing_le_d_over_4",
            status="OK" if ctx.stirrup_spacing_mm <= capacity else "FAIL",
            demand=ctx.stirrup_spacing_mm,
            capacity=capacity,
            ratio=ctx.stirrup_spacing_mm / capacity,
            unit="mm",
            code_ref="TBDY 2018 7.4.4.1",
            evidence=self._base_evidence(
                ctx,
                Ve_kN=Ve_kN,
                Vc_kN=Vc_kN,
                Vw_kN=Vw_kN,
                Vr_kN=Vr_kN,
                Vmax_kN=Vmax_kN,
                Asw_mm2=Asw_mm2,
                Asw_cm2=Asw_cm2,
                Asw_min_mm2=Asw_min_mm2,
                Asw_min_cm2=Asw_min_cm2,
                formula="s <= d_mm / 4",
            ),
            message="s <= d/4" if ctx.stirrup_spacing_mm <= capacity else "s exceeds d/4",
        )

    def _spacing_le_150(
        self,
        ctx: BeamModelContext,
        Ve_kN: float,
        Vc_kN: float,
        Vw_kN: float,
        Vr_kN: float,
        Vmax_kN: float,
        Asw_mm2: float,
        Asw_cm2: float,
        Asw_min_mm2: float,
        Asw_min_cm2: float,
    ) -> ShearCheck:
        capacity = 150.0
        return ShearCheck(
            name="beam_shear_spacing_le_150",
            status="OK" if ctx.stirrup_spacing_mm <= capacity else "FAIL",
            demand=ctx.stirrup_spacing_mm,
            capacity=capacity,
            ratio=ctx.stirrup_spacing_mm / capacity,
            unit="mm",
            code_ref="TBDY 2018 7.4.4.1",
            evidence=self._base_evidence(
                ctx,
                Ve_kN=Ve_kN,
                Vc_kN=Vc_kN,
                Vw_kN=Vw_kN,
                Vr_kN=Vr_kN,
                Vmax_kN=Vmax_kN,
                Asw_mm2=Asw_mm2,
                Asw_cm2=Asw_cm2,
                Asw_min_mm2=Asw_min_mm2,
                Asw_min_cm2=Asw_min_cm2,
                formula="s <= 150 mm",
            ),
            message="s <= 150 mm" if ctx.stirrup_spacing_mm <= capacity else "s exceeds 150 mm",
        )

    def _spacing_le_8_longitudinal_diameter(self, ctx: BeamModelContext) -> ShearCheck:
        diameter = ctx.longitudinal_bar_diameter_mm
        if diameter is None or diameter <= 0:
            return ShearCheck(
                name="beam_shear_spacing_le_8_longitudinal_diameter",
                status="NO_DATA",
                demand=ctx.stirrup_spacing_mm,
                capacity=None,
                ratio=None,
                unit="mm",
                code_ref="TBDY 2018 7.4.4.1",
                evidence={
                    "stirrup_spacing_mm": ctx.stirrup_spacing_mm,
                    "longitudinal_bar_diameter_mm": diameter,
                    "limit_mm": None,
                    "formula": "stirrup_spacing_mm <= 8 * longitudinal_bar_diameter_mm",
                },
                message="longitudinal bar diameter missing",
            )

        limit_mm = 8.0 * diameter
        ratio = ctx.stirrup_spacing_mm / limit_mm
        return ShearCheck(
            name="beam_shear_spacing_le_8_longitudinal_diameter",
            status="OK" if ctx.stirrup_spacing_mm <= limit_mm else "FAIL",
            demand=ctx.stirrup_spacing_mm,
            capacity=limit_mm,
            ratio=ratio,
            unit="mm",
            code_ref="TBDY 2018 7.4.4.1",
            evidence={
                "stirrup_spacing_mm": ctx.stirrup_spacing_mm,
                "longitudinal_bar_diameter_mm": diameter,
                "limit_mm": limit_mm,
                "formula": "stirrup_spacing_mm <= 8 * longitudinal_bar_diameter_mm",
            },
            message="s <= 8Øl" if ctx.stirrup_spacing_mm <= limit_mm else "s exceeds 8Øl",
        )

    def _stirrup_diameter_ge_8(
        self,
        ctx: BeamModelContext,
        Ve_kN: float,
        Vc_kN: float,
        Vw_kN: float,
        Vr_kN: float,
        Vmax_kN: float,
        Asw_mm2: float,
        Asw_cm2: float,
        Asw_min_mm2: float,
        Asw_min_cm2: float,
    ) -> ShearCheck:
        capacity = 8.0
        return ShearCheck(
            name="beam_shear_stirrup_diameter_ge_8",
            status="OK" if ctx.stirrup_diameter_mm >= capacity else "FAIL",
            demand=ctx.stirrup_diameter_mm,
            capacity=capacity,
            ratio=ctx.stirrup_diameter_mm / capacity,
            unit="mm",
            code_ref="TBDY 2018 7.4.4.2",
            evidence=self._base_evidence(
                ctx,
                Ve_kN=Ve_kN,
                Vc_kN=Vc_kN,
                Vw_kN=Vw_kN,
                Vr_kN=Vr_kN,
                Vmax_kN=Vmax_kN,
                Asw_mm2=Asw_mm2,
                Asw_cm2=Asw_cm2,
                Asw_min_mm2=Asw_min_mm2,
                Asw_min_cm2=Asw_min_cm2,
                formula="stirrup_diameter_mm >= 8",
            ),
            message="stirrup diameter >= 8 mm" if ctx.stirrup_diameter_mm >= capacity else "stirrup diameter below 8 mm",
        )

    def _stirrup_legs_ge_2(
        self,
        ctx: BeamModelContext,
        Ve_kN: float,
        Vc_kN: float,
        Vw_kN: float,
        Vr_kN: float,
        Vmax_kN: float,
        Asw_mm2: float,
        Asw_cm2: float,
        Asw_min_mm2: float,
        Asw_min_cm2: float,
    ) -> ShearCheck:
        capacity = 2.0
        return ShearCheck(
            name="beam_shear_stirrup_legs_ge_2",
            status="OK" if ctx.stirrup_legs >= capacity else "FAIL",
            demand=float(ctx.stirrup_legs),
            capacity=capacity,
            ratio=ctx.stirrup_legs / capacity,
            unit=None,
            code_ref="TBDY 2018 beam shear minimum stirrup legs",
            evidence=self._base_evidence(
                ctx,
                Ve_kN=Ve_kN,
                Vc_kN=Vc_kN,
                Vw_kN=Vw_kN,
                Vr_kN=Vr_kN,
                Vmax_kN=Vmax_kN,
                Asw_mm2=Asw_mm2,
                Asw_cm2=Asw_cm2,
                Asw_min_mm2=Asw_min_mm2,
                Asw_min_cm2=Asw_min_cm2,
                formula="stirrup_legs >= 2",
            ),
            message="stirrup legs >= 2" if ctx.stirrup_legs >= capacity else "stirrup legs below 2",
        )

    def _asw_ge_asw_min(
        self,
        ctx: BeamModelContext,
        Asw_mm2: float,
        Asw_cm2: float,
        Asw_min_mm2: float,
        Asw_min_cm2: float,
    ) -> ShearCheck:
        ratio = Asw_mm2 / Asw_min_mm2 if Asw_min_mm2 > 0 else None
        return ShearCheck(
            name="beam_shear_asw_ge_asw_min",
            status="OK" if Asw_mm2 >= Asw_min_mm2 else "FAIL",
            demand=Asw_mm2,
            capacity=Asw_min_mm2,
            ratio=ratio,
            unit="mm²",
            code_ref="TBDY 2018 7.4.5.6",
            evidence={
                "Asw_mm2": Asw_mm2,
                "Asw_cm2": Asw_cm2,
                "Asw_min_mm2": Asw_min_mm2,
                "Asw_min_cm2": Asw_min_cm2,
                "fctd_mpa": ctx.fctd_mpa,
                "fywd_mpa": ctx.fywd_mpa,
                "bw_mm": ctx.bw_mm,
                "stirrup_spacing_mm": ctx.stirrup_spacing_mm,
                "formula": "Asw_min_mm2 = 0.3 * fctd_mpa * bw_mm * stirrup_spacing_mm / fywd_mpa",
            },
            message="Asw >= Asw_min" if Asw_mm2 >= Asw_min_mm2 else "Asw below Asw_min",
        )

def calculate_capacity_shear_demand(
    *,
    left_plastic_moment_kNm: float | None,
    right_plastic_moment_kNm: float | None,
    Ln_mm: float,
    gravity_shear_kN: float | None,
) -> CapacityShearDemandResult:
    Ln_m = None if Ln_mm <= 0.0 else Ln_mm / 1000.0

    if (
        left_plastic_moment_kNm is None
        or right_plastic_moment_kNm is None
        or left_plastic_moment_kNm <= 0.0
        or right_plastic_moment_kNm <= 0.0
        or Ln_m is None
        or gravity_shear_kN is None
    ):
        return CapacityShearDemandResult(
            left_plastic_moment_kNm=left_plastic_moment_kNm,
            right_plastic_moment_kNm=right_plastic_moment_kNm,
            Ln_mm=Ln_mm,
            Ln_m=Ln_m,
            gravity_shear_kN=gravity_shear_kN,
            Ve_capacity_kN=None,
            status="NO_DATA",
            evidence={
                "left_plastic_moment_kNm": left_plastic_moment_kNm,
                "right_plastic_moment_kNm": right_plastic_moment_kNm,
                "Ln_mm": Ln_mm,
                "Ln_m": Ln_m,
                "gravity_shear_kN": gravity_shear_kN,
                "Ve_capacity_kN": None,
                "formula": "Ve_capacity_kN = (left_plastic_moment_kNm + right_plastic_moment_kNm) / (Ln_mm / 1000) + gravity_shear_kN",
                "source_of_plastic_moments": "O1 flexure plastic moment boundary",
                "source_of_gravity_shear": "explicit gravity_shear_kN input",
                "capacity_design_shear_complete": False,
                "ve_capacity_check_against_vr": False,
            },
        )

    Ve_capacity_kN = (
        (left_plastic_moment_kNm + right_plastic_moment_kNm) / Ln_m
        + gravity_shear_kN
    )

    return CapacityShearDemandResult(
        left_plastic_moment_kNm=left_plastic_moment_kNm,
        right_plastic_moment_kNm=right_plastic_moment_kNm,
        Ln_mm=Ln_mm,
        Ln_m=Ln_m,
        gravity_shear_kN=gravity_shear_kN,
        Ve_capacity_kN=Ve_capacity_kN,
        status="OK",
        evidence={
            "left_plastic_moment_kNm": left_plastic_moment_kNm,
            "right_plastic_moment_kNm": right_plastic_moment_kNm,
            "Ln_mm": Ln_mm,
            "Ln_m": Ln_m,
            "gravity_shear_kN": gravity_shear_kN,
            "Ve_capacity_kN": Ve_capacity_kN,
            "formula": "Ve_capacity_kN = (left_plastic_moment_kNm + right_plastic_moment_kNm) / (Ln_mm / 1000) + gravity_shear_kN",
            "source_of_plastic_moments": "O1 flexure plastic moment boundary",
            "source_of_gravity_shear": "explicit gravity_shear_kN input",
            "capacity_design_shear_complete": False,
            "ve_capacity_check_against_vr": False,
        },
    )


def _capacity_design_message(status: str, label: str) -> str:
    if status == "OK":
        return f"{label} satisfies requirement"
    if status == "FAIL":
        return f"{label} exceeds capacity"
    return f"{label} data missing"
def capacity_design_ve_le_vr_check(
    *,
    capacity_shear_demand: CapacityShearDemandResult,
    Vr_kN: float | None,
    Vc_kN: float | None,
    Vw_kN: float | None,
    Asw_mm2: float | None,
    fywd_mpa: float,
    d_mm: float,
    stirrup_spacing_mm: float,
) -> ShearCheck:
    Ve_capacity_kN = capacity_shear_demand.Ve_capacity_kN

    if Ve_capacity_kN is None or Ve_capacity_kN <= 0.0 or Vr_kN is None or Vr_kN <= 0.0:
        status = "NO_DATA"
        demand = Ve_capacity_kN if Ve_capacity_kN is not None and Ve_capacity_kN > 0.0 else None
        capacity = Vr_kN if Vr_kN is not None and Vr_kN > 0.0 else None
        ratio = None
    else:
        demand = Ve_capacity_kN
        capacity = Vr_kN
        ratio = Ve_capacity_kN / Vr_kN
        status = "OK" if Ve_capacity_kN <= Vr_kN else "FAIL"

    evidence = {
        "Ve_capacity_kN": Ve_capacity_kN,
        "Vr_kN": Vr_kN,
        "Vc_kN": Vc_kN,
        "Vw_kN": Vw_kN,
        "Asw_mm2": Asw_mm2,
        "fywd_mpa": fywd_mpa,
        "d_mm": d_mm,
        "stirrup_spacing_mm": stirrup_spacing_mm,
        "left_plastic_moment_kNm": capacity_shear_demand.left_plastic_moment_kNm,
        "right_plastic_moment_kNm": capacity_shear_demand.right_plastic_moment_kNm,
        "Ln_mm": capacity_shear_demand.Ln_mm,
        "Ln_m": capacity_shear_demand.Ln_m,
        "gravity_shear_kN": capacity_shear_demand.gravity_shear_kN,
        "formula_capacity_demand": "Ve_capacity_kN = (left_plastic_moment_kNm + right_plastic_moment_kNm) / (Ln_mm / 1000) + gravity_shear_kN",
        "formula_capacity_check": "Ve_capacity_kN <= Vr_kN",
        "source_of_plastic_moments": capacity_shear_demand.evidence.get("source_of_plastic_moments"),
        "source_of_gravity_shear": capacity_shear_demand.evidence.get("source_of_gravity_shear"),
        "capacity_design_shear_complete": False,
        "capacity_design_vmax_check": False,
        "ve_capacity_check_against_vr": True,
    }

    return ShearCheck(
        name="beam_shear_capacity_design_ve_le_vr",
        status=status,
        demand=demand,
        capacity=capacity,
        ratio=ratio,
        unit="kN",
        code_ref="TBDY 2018 capacity-design shear Ve <= Vr deterministic core boundary",
        evidence=evidence,
        message=_capacity_design_message(status, "capacity design Ve <= Vr"),
    )

def capacity_design_ve_le_085_vmax_check(
    *,
    capacity_shear_demand: CapacityShearDemandResult,
    Vmax_kN: float | None,
    fcd_mpa: float,
    bw_mm: float,
    d_mm: float,
) -> ShearCheck:
    Ve_capacity_kN = capacity_shear_demand.Ve_capacity_kN

    if Vmax_kN is None or Vmax_kN <= 0.0:
        capacity = None
    else:
        capacity = 0.85 * Vmax_kN

    if Ve_capacity_kN is None or Ve_capacity_kN <= 0.0 or capacity is None or capacity <= 0.0:
        status = "NO_DATA"
        demand = Ve_capacity_kN if Ve_capacity_kN is not None and Ve_capacity_kN > 0.0 else None
        ratio = None
    else:
        demand = Ve_capacity_kN
        ratio = Ve_capacity_kN / capacity
        status = "OK" if Ve_capacity_kN <= capacity else "FAIL"

    evidence = {
        "Ve_capacity_kN": Ve_capacity_kN,
        "Vmax_kN": Vmax_kN,
        "capacity_design_vmax_limit_kN": capacity,
        "fcd_mpa": fcd_mpa,
        "bw_mm": bw_mm,
        "d_mm": d_mm,
        "left_plastic_moment_kNm": capacity_shear_demand.left_plastic_moment_kNm,
        "right_plastic_moment_kNm": capacity_shear_demand.right_plastic_moment_kNm,
        "Ln_mm": capacity_shear_demand.Ln_mm,
        "Ln_m": capacity_shear_demand.Ln_m,
        "gravity_shear_kN": capacity_shear_demand.gravity_shear_kN,
        "formula_vmax": "Vmax_kN = 0.85 * 0.22 * fcd_mpa * bw_mm * d_mm / 1000",
        "formula_capacity_vmax_limit": "capacity_design_vmax_limit_kN = 0.85 * Vmax_kN",
        "formula_capacity_demand": "Ve_capacity_kN = (left_plastic_moment_kNm + right_plastic_moment_kNm) / (Ln_mm / 1000) + gravity_shear_kN",
        "formula_capacity_check": "Ve_capacity_kN <= 0.85 * Vmax_kN",
        "source_of_plastic_moments": capacity_shear_demand.evidence.get("source_of_plastic_moments"),
        "source_of_gravity_shear": capacity_shear_demand.evidence.get("source_of_gravity_shear"),
        "capacity_design_shear_complete": False,
        "capacity_design_vmax_check": True,
        "ve_capacity_check_against_vr": False,
    }

    return ShearCheck(
        name="beam_shear_capacity_design_ve_le_085_vmax",
        status=status,
        demand=demand,
        capacity=capacity,
        ratio=ratio,
        unit="kN",
        code_ref="TBDY 2018 capacity-design shear Ve <= 0.85 Vmax deterministic core boundary",
        evidence=evidence,
        message=_capacity_design_message(status, "capacity design Ve <= 0.85 Vmax"),
    )
