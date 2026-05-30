from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from tbdy_engine.design.beams.context import BeamModelContext


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
    checks: tuple[ShearCheck, ...]
    status: str


class TBDYShearCalculator:
    def calculate(self, ctx: BeamModelContext) -> ShearResult:
        Ve_kN = abs(ctx.Ve_left_kN)
        Vc_kN = 0.0

        single_bar_area_mm2 = math.pi * ctx.stirrup_diameter_mm**2 / 4.0
        Asw_mm2 = ctx.stirrup_legs * single_bar_area_mm2
        Asw_cm2 = Asw_mm2 / 100.0

        Vw_kN = Asw_mm2 * ctx.fywd_mpa * ctx.d_mm / ctx.stirrup_spacing_mm / 1000.0
        Vr_kN = Vc_kN + Vw_kN
        Vmax_kN = 0.85 * 0.22 * ctx.fcd_mpa * ctx.bw_mm * ctx.d_mm / 1000.0

        checks = (
            self._ve_le_vr(ctx, Ve_kN, Vc_kN, Vw_kN, Vr_kN, Vmax_kN, Asw_mm2, Asw_cm2),
            self._ve_le_085_vmax(ctx, Ve_kN, Vc_kN, Vw_kN, Vr_kN, Vmax_kN, Asw_mm2, Asw_cm2),
            self._spacing_le_d_over_4(ctx, Ve_kN, Vc_kN, Vw_kN, Vr_kN, Vmax_kN, Asw_mm2, Asw_cm2),
            self._spacing_le_150(ctx, Ve_kN, Vc_kN, Vw_kN, Vr_kN, Vmax_kN, Asw_mm2, Asw_cm2),
            self._stirrup_diameter_ge_8(ctx, Ve_kN, Vc_kN, Vw_kN, Vr_kN, Vmax_kN, Asw_mm2, Asw_cm2),
            self._stirrup_legs_ge_2(ctx, Ve_kN, Vc_kN, Vw_kN, Vr_kN, Vmax_kN, Asw_mm2, Asw_cm2),
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
            "fywd_mpa": ctx.fywd_mpa,
            "stirrup_diameter_mm": ctx.stirrup_diameter_mm,
            "stirrup_legs": ctx.stirrup_legs,
            "stirrup_spacing_mm": ctx.stirrup_spacing_mm,
            "Asw_mm2": Asw_mm2,
            "Asw_cm2": Asw_cm2,
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
                formula="s <= 150 mm",
            ),
            message="s <= 150 mm" if ctx.stirrup_spacing_mm <= capacity else "s exceeds 150 mm",
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
                formula="stirrup_legs >= 2",
            ),
            message="stirrup legs >= 2" if ctx.stirrup_legs >= capacity else "stirrup legs below 2",
        )