from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from tbdy_engine.design.beams.context import BeamModelContext


@dataclass(frozen=True)
class FlexureCheck:
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
class SelectedFlexureBars:
    designation: str
    diameter_mm: float | None
    legs: int | None
    area_cm2: float | None
    status: str
    required_area_cm2: float | None
    rho_min: float | None
    rho_max: float | None
    rho: float | None


@dataclass(frozen=True)
class FlexureResult:
    Md_left_neg_kNm: float
    Md_mid_pos_kNm: float | None
    Md_right_neg_kNm: float | None
    top_design_moment_kNm: float | None
    bottom_design_moment_kNm: float | None
    required_top_area_cm2: float | None
    required_bottom_area_cm2: float | None
    provided_top_area_cm2: float | None
    provided_bottom_area_cm2: float | None
    top_required_area_from_moment_cm2: float | None
    bottom_required_area_from_moment_cm2: float | None
    top_required_area_source: str
    bottom_required_area_source: str
    top_ratio: float | None
    bottom_ratio: float | None

    beta1: float | None
    top_stress_block_a_mm: float | None
    top_neutral_axis_c_mm: float | None
    top_compression_block_kN: float | None
    bottom_stress_block_a_mm: float | None
    bottom_neutral_axis_c_mm: float | None
    bottom_compression_block_kN: float | None

    rho_min: float | None
    rho_max: float | None
    top_rho: float | None
    bottom_rho: float | None
    top_rho_min_ratio: float | None
    bottom_rho_min_ratio: float | None
    top_rho_max_ratio: float | None
    bottom_rho_max_ratio: float | None

    selected_bars: tuple[SelectedFlexureBars, ...]
    top_selected_bar_diameter_mm: float | None
    top_selected_bar_legs: int | None
    top_selected_bar_area_cm2: float | None
    bottom_selected_bar_diameter_mm: float | None
    bottom_selected_bar_legs: int | None
    bottom_selected_bar_area_cm2: float | None

    checks: tuple[FlexureCheck, ...]
    status: str


class TBDYFlexureCalculator:
    def calculate(self, ctx: BeamModelContext) -> FlexureResult:
        beta1 = _beta1(ctx.fck_mpa)

        top_design_moment_kNm = _top_design_moment(ctx)
        bottom_design_moment_kNm = _positive_moment(ctx.Md_mid_pos_kNm)

        top_moment_required = _required_area_from_moment_cm2(
            Md_kNm=top_design_moment_kNm,
            fyd_mpa=ctx.fyd_mpa,
            fcd_mpa=ctx.fcd_mpa,
            bw_mm=ctx.bw_mm,
            d_mm=ctx.d_mm,
        )
        bottom_moment_required = _required_area_from_moment_cm2(
            Md_kNm=bottom_design_moment_kNm,
            fyd_mpa=ctx.fyd_mpa,
            fcd_mpa=ctx.fcd_mpa,
            bw_mm=ctx.bw_mm,
            d_mm=ctx.d_mm,
        )

        top_required, top_source = _resolve_required_area(
            moment_required_cm2=top_moment_required,
            context_required_cm2=ctx.top_required_area_cm2,
        )
        bottom_required, bottom_source = _resolve_required_area(
            moment_required_cm2=bottom_moment_required,
            context_required_cm2=ctx.bottom_required_area_cm2,
        )

        top_ratio = _ratio(top_required, ctx.top_selected_area_cm2)
        bottom_ratio = _ratio(bottom_required, ctx.bottom_selected_area_cm2)

        top_block = _stress_block(
            selected_area_cm2=ctx.top_selected_area_cm2,
            fyd_mpa=ctx.fyd_mpa,
            fcd_mpa=ctx.fcd_mpa,
            bw_mm=ctx.bw_mm,
            beta1=beta1,
        )
        bottom_block = _stress_block(
            selected_area_cm2=ctx.bottom_selected_area_cm2,
            fyd_mpa=ctx.fyd_mpa,
            fcd_mpa=ctx.fcd_mpa,
            bw_mm=ctx.bw_mm,
            beta1=beta1,
        )

        top_required_calc = _required_area_calculation_values(
            Md_kNm=top_design_moment_kNm,
            As_required_cm2=top_moment_required,
            fyd_mpa=ctx.fyd_mpa,
            fcd_mpa=ctx.fcd_mpa,
            bw_mm=ctx.bw_mm,
            d_mm=ctx.d_mm,
        )
        bottom_required_calc = _required_area_calculation_values(
            Md_kNm=bottom_design_moment_kNm,
            As_required_cm2=bottom_moment_required,
            fyd_mpa=ctx.fyd_mpa,
            fcd_mpa=ctx.fcd_mpa,
            bw_mm=ctx.bw_mm,
            d_mm=ctx.d_mm,
        )

        rho_min = _rho_min(ctx.fctd_mpa, ctx.fyd_mpa)
        rho_max = _rho_max()
        top_rho = _rho(ctx.top_selected_area_cm2, ctx.bw_mm, ctx.d_mm)
        bottom_rho = _rho(ctx.bottom_selected_area_cm2, ctx.bw_mm, ctx.d_mm)
        top_rho_min_ratio = _rho_min_ratio(rho_min, top_rho)
        bottom_rho_min_ratio = _rho_min_ratio(rho_min, bottom_rho)
        top_rho_max_ratio = _rho_max_ratio(top_rho, rho_max)
        bottom_rho_max_ratio = _rho_max_ratio(bottom_rho, rho_max)

        top_rho_min_status = _rho_min_status(rho_min, top_rho, top_rho_min_ratio)
        bottom_rho_min_status = _rho_min_status(rho_min, bottom_rho, bottom_rho_min_ratio)
        top_rho_max_status = _rho_max_status(rho_max, top_rho, top_rho_max_ratio)
        bottom_rho_max_status = _rho_max_status(rho_max, bottom_rho, bottom_rho_max_ratio)

        top_bar_selection = _select_bars(
            designation="top",
            required_area_cm2=top_required,
            bw_mm=ctx.bw_mm,
            d_mm=ctx.d_mm,
            rho_min=rho_min,
            rho_max=rho_max,
        )
        bottom_bar_selection = _select_bars(
            designation="bottom",
            required_area_cm2=bottom_required,
            bw_mm=ctx.bw_mm,
            d_mm=ctx.d_mm,
            rho_min=rho_min,
            rho_max=rho_max,
        )

        top_consolidated = _consolidated_evidence(
            selected_area_cm2=ctx.top_selected_area_cm2,
            required_area_cm2=top_required,
            required_area_source=top_source,
            area_ratio=top_ratio,
            stress_block=top_block,
            rho=rho_min if False else top_rho,
            rho_min=rho_min,
            rho_max=rho_max,
            rho_min_ratio=top_rho_min_ratio,
            rho_max_ratio=top_rho_max_ratio,
            rho_min_status=top_rho_min_status,
            rho_max_status=top_rho_max_status,
        )
        bottom_consolidated = _consolidated_evidence(
            selected_area_cm2=ctx.bottom_selected_area_cm2,
            required_area_cm2=bottom_required,
            required_area_source=bottom_source,
            area_ratio=bottom_ratio,
            stress_block=bottom_block,
            rho=bottom_rho,
            rho_min=rho_min,
            rho_max=rho_max,
            rho_min_ratio=bottom_rho_min_ratio,
            rho_max_ratio=bottom_rho_max_ratio,
            rho_min_status=bottom_rho_min_status,
            rho_max_status=bottom_rho_max_status,
        )

        checks = (
            self._top_area_check(
                ctx=ctx,
                required=top_required,
                required_source=top_source,
                beta1=beta1,
                stress_block=top_block,
                design_moment_kNm=top_design_moment_kNm,
                required_calc=top_required_calc,
                consolidated=top_consolidated,
            ),
            self._bottom_area_check(
                ctx=ctx,
                required=bottom_required,
                required_source=bottom_source,
                beta1=beta1,
                stress_block=bottom_block,
                design_moment_kNm=bottom_design_moment_kNm,
                required_calc=bottom_required_calc,
                consolidated=bottom_consolidated,
            ),
            self._top_rho_min_check(
                ctx=ctx,
                rho_min=rho_min,
                rho=top_rho,
                ratio=top_rho_min_ratio,
                required_source=top_source,
                consolidated=top_consolidated,
            ),
            self._bottom_rho_min_check(
                ctx=ctx,
                rho_min=rho_min,
                rho=bottom_rho,
                ratio=bottom_rho_min_ratio,
                required_source=bottom_source,
                consolidated=bottom_consolidated,
            ),
            self._top_rho_max_check(
                ctx=ctx,
                rho_max=rho_max,
                rho=top_rho,
                ratio=top_rho_max_ratio,
                required_source=top_source,
                consolidated=top_consolidated,
            ),
            self._bottom_rho_max_check(
                ctx=ctx,
                rho_max=rho_max,
                rho=bottom_rho,
                ratio=bottom_rho_max_ratio,
                required_source=bottom_source,
                consolidated=bottom_consolidated,
            ),
            self._bar_selection_check(
                selection=top_bar_selection,
                required_source=top_source,
                consolidated=top_consolidated,
                prior_statuses={
                    "area_status": _area_status(top_required, ctx.top_selected_area_cm2),
                    "rho_min_status": top_rho_min_status,
                    "rho_max_status": top_rho_max_status,
                },
            ),
            self._bar_selection_check(
                selection=bottom_bar_selection,
                required_source=bottom_source,
                consolidated=bottom_consolidated,
                prior_statuses={
                    "area_status": _area_status(bottom_required, ctx.bottom_selected_area_cm2),
                    "rho_min_status": bottom_rho_min_status,
                    "rho_max_status": bottom_rho_max_status,
                },
            ),
        )

        if any(check.status == "NO_DATA" for check in checks):
            status = "NO_DATA"
        elif all(check.status == "OK" for check in checks):
            status = "OK"
        else:
            status = "FAIL"

        return FlexureResult(
            Md_left_neg_kNm=ctx.Md_left_neg_kNm,
            Md_mid_pos_kNm=ctx.Md_mid_pos_kNm,
            Md_right_neg_kNm=ctx.Md_right_neg_kNm,
            top_design_moment_kNm=top_design_moment_kNm,
            bottom_design_moment_kNm=bottom_design_moment_kNm,
            required_top_area_cm2=top_required,
            required_bottom_area_cm2=bottom_required,
            provided_top_area_cm2=ctx.top_selected_area_cm2,
            provided_bottom_area_cm2=ctx.bottom_selected_area_cm2,
            top_required_area_from_moment_cm2=top_moment_required,
            bottom_required_area_from_moment_cm2=bottom_moment_required,
            top_required_area_source=top_source,
            bottom_required_area_source=bottom_source,
            top_ratio=top_ratio,
            bottom_ratio=bottom_ratio,
            beta1=beta1,
            top_stress_block_a_mm=top_block["a_mm"],
            top_neutral_axis_c_mm=top_block["c_mm"],
            top_compression_block_kN=top_block["compression_block_kN"],
            bottom_stress_block_a_mm=bottom_block["a_mm"],
            bottom_neutral_axis_c_mm=bottom_block["c_mm"],
            bottom_compression_block_kN=bottom_block["compression_block_kN"],
            rho_min=rho_min,
            rho_max=rho_max,
            top_rho=top_rho,
            bottom_rho=bottom_rho,
            top_rho_min_ratio=top_rho_min_ratio,
            bottom_rho_min_ratio=bottom_rho_min_ratio,
            top_rho_max_ratio=top_rho_max_ratio,
            bottom_rho_max_ratio=bottom_rho_max_ratio,
            selected_bars=(top_bar_selection, bottom_bar_selection),
            top_selected_bar_diameter_mm=top_bar_selection.diameter_mm,
            top_selected_bar_legs=top_bar_selection.legs,
            top_selected_bar_area_cm2=top_bar_selection.area_cm2,
            bottom_selected_bar_diameter_mm=bottom_bar_selection.diameter_mm,
            bottom_selected_bar_legs=bottom_bar_selection.legs,
            bottom_selected_bar_area_cm2=bottom_bar_selection.area_cm2,
            checks=checks,
            status=status,
        )

    def _top_area_check(
        self,
        *,
        ctx: BeamModelContext,
        required: float | None,
        required_source: str,
        beta1: float | None,
        stress_block: Mapping[str, float | None],
        design_moment_kNm: float | None,
        required_calc: Mapping[str, float | None],
        consolidated: Mapping[str, object],
    ) -> FlexureCheck:
        provided = ctx.top_selected_area_cm2
        status = _area_status(required, provided)
        ratio = _ratio(required, provided)

        return FlexureCheck(
            name="beam_flexure_top_area_provided_ge_required",
            status=status,
            demand=required,
            capacity=provided,
            ratio=ratio,
            unit="cm²",
            code_ref="TBDY 2018 beam flexure reinforcement area",
            evidence={
                **consolidated,
                "Md_kNm": design_moment_kNm,
                "Mu_Nmm": required_calc["Mu_Nmm"],
                "bw_mm": ctx.bw_mm,
                "d_mm": ctx.d_mm,
                "fcd_mpa": ctx.fcd_mpa,
                "fyd_mpa": ctx.fyd_mpa,
                "beta1": beta1,
                "As_required_mm2": required_calc["As_required_mm2"],
                "As_required_cm2": required,
                "provided_area_cm2": provided,
                "required_area_source": required_source,
                "top_required_area_cm2": required,
                "top_selected_area_cm2": provided,
                "stress_block_a_mm": stress_block["a_mm"],
                "neutral_axis_c_mm": stress_block["c_mm"],
                "compression_block_kN": stress_block["compression_block_kN"],
                "formula": "provided_area_cm2 >= As_required_cm2",
                "required_area_formula": "Mu_Nmm = As_mm2 * fyd_mpa * (d_mm - a_mm / 2); a_mm = As_mm2 * fyd_mpa / (0.85 * fcd_mpa * bw_mm)",
                "stress_block_formula": "a_mm = As_mm2 * fyd_mpa / (0.85 * fcd_mpa * bw_mm); c_mm = a_mm / beta1",
            },
            message=_message(status, "top reinforcement area"),
        )

    def _bottom_area_check(
        self,
        *,
        ctx: BeamModelContext,
        required: float | None,
        required_source: str,
        beta1: float | None,
        stress_block: Mapping[str, float | None],
        design_moment_kNm: float | None,
        required_calc: Mapping[str, float | None],
        consolidated: Mapping[str, object],
    ) -> FlexureCheck:
        provided = ctx.bottom_selected_area_cm2
        status = _area_status(required, provided)
        ratio = _ratio(required, provided)

        return FlexureCheck(
            name="beam_flexure_bottom_area_provided_ge_required",
            status=status,
            demand=required,
            capacity=provided,
            ratio=ratio,
            unit="cm²",
            code_ref="TBDY 2018 beam flexure reinforcement area",
            evidence={
                **consolidated,
                "Md_kNm": design_moment_kNm,
                "Mu_Nmm": required_calc["Mu_Nmm"],
                "bw_mm": ctx.bw_mm,
                "d_mm": ctx.d_mm,
                "fcd_mpa": ctx.fcd_mpa,
                "fyd_mpa": ctx.fyd_mpa,
                "beta1": beta1,
                "As_required_mm2": required_calc["As_required_mm2"],
                "As_required_cm2": required,
                "provided_area_cm2": provided,
                "required_area_source": required_source,
                "bottom_required_area_cm2": required,
                "bottom_selected_area_cm2": provided,
                "stress_block_a_mm": stress_block["a_mm"],
                "neutral_axis_c_mm": stress_block["c_mm"],
                "compression_block_kN": stress_block["compression_block_kN"],
                "formula": "provided_area_cm2 >= As_required_cm2",
                "required_area_formula": "Mu_Nmm = As_mm2 * fyd_mpa * (d_mm - a_mm / 2); a_mm = As_mm2 * fyd_mpa / (0.85 * fcd_mpa * bw_mm)",
                "stress_block_formula": "a_mm = As_mm2 * fyd_mpa / (0.85 * fcd_mpa * bw_mm); c_mm = a_mm / beta1",
            },
            message=_message(status, "bottom reinforcement area"),
        )

    def _top_rho_min_check(
        self,
        *,
        ctx: BeamModelContext,
        rho_min: float | None,
        rho: float | None,
        ratio: float | None,
        required_source: str,
        consolidated: Mapping[str, object],
    ) -> FlexureCheck:
        return _rho_min_check(
            name="beam_flexure_top_rho_ge_rho_min",
            selected_area_cm2=ctx.top_selected_area_cm2,
            bw_mm=ctx.bw_mm,
            d_mm=ctx.d_mm,
            fctd_mpa=ctx.fctd_mpa,
            fyd_mpa=ctx.fyd_mpa,
            rho_min=rho_min,
            rho=rho,
            ratio=ratio,
            required_source=required_source,
            label="top reinforcement rho_min",
            consolidated=consolidated,
        )

    def _bottom_rho_min_check(
        self,
        *,
        ctx: BeamModelContext,
        rho_min: float | None,
        rho: float | None,
        ratio: float | None,
        required_source: str,
        consolidated: Mapping[str, object],
    ) -> FlexureCheck:
        return _rho_min_check(
            name="beam_flexure_bottom_rho_ge_rho_min",
            selected_area_cm2=ctx.bottom_selected_area_cm2,
            bw_mm=ctx.bw_mm,
            d_mm=ctx.d_mm,
            fctd_mpa=ctx.fctd_mpa,
            fyd_mpa=ctx.fyd_mpa,
            rho_min=rho_min,
            rho=rho,
            ratio=ratio,
            required_source=required_source,
            label="bottom reinforcement rho_min",
            consolidated=consolidated,
        )

    def _top_rho_max_check(
        self,
        *,
        ctx: BeamModelContext,
        rho_max: float | None,
        rho: float | None,
        ratio: float | None,
        required_source: str,
        consolidated: Mapping[str, object],
    ) -> FlexureCheck:
        return _rho_max_check(
            name="beam_flexure_top_rho_le_rho_max",
            selected_area_cm2=ctx.top_selected_area_cm2,
            bw_mm=ctx.bw_mm,
            d_mm=ctx.d_mm,
            fctd_mpa=ctx.fctd_mpa,
            fyd_mpa=ctx.fyd_mpa,
            rho_max=rho_max,
            rho=rho,
            ratio=ratio,
            required_source=required_source,
            label="top reinforcement rho_max",
            consolidated=consolidated,
        )

    def _bottom_rho_max_check(
        self,
        *,
        ctx: BeamModelContext,
        rho_max: float | None,
        rho: float | None,
        ratio: float | None,
        required_source: str,
        consolidated: Mapping[str, object],
    ) -> FlexureCheck:
        return _rho_max_check(
            name="beam_flexure_bottom_rho_le_rho_max",
            selected_area_cm2=ctx.bottom_selected_area_cm2,
            bw_mm=ctx.bw_mm,
            d_mm=ctx.d_mm,
            fctd_mpa=ctx.fctd_mpa,
            fyd_mpa=ctx.fyd_mpa,
            rho_max=rho_max,
            rho=rho,
            ratio=ratio,
            required_source=required_source,
            label="bottom reinforcement rho_max",
            consolidated=consolidated,
        )


    def _bar_selection_check(
        self,
        *,
        selection: SelectedFlexureBars,
        required_source: str,
        consolidated: Mapping[str, object],
        prior_statuses: Mapping[str, str],
    ) -> FlexureCheck:
        return _bar_selection_check(
            selection=selection,
            required_source=required_source,
            consolidated=consolidated,
            prior_statuses=prior_statuses,
        )
AVAILABLE_FLEXURE_BAR_DIAMETERS_MM = (12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 25.0, 28.0, 32.0)
AVAILABLE_FLEXURE_BAR_LEGS = tuple(range(2, 13))


def _bar_selection_check(
    *,
    selection: SelectedFlexureBars,
    required_source: str,
    consolidated: Mapping[str, object],
    prior_statuses: Mapping[str, str],
) -> FlexureCheck:
    name = f"beam_flexure_{selection.designation}_bar_selection"

    evidence = {
        **consolidated,
        "designation": selection.designation,
        "selected_bar_diameter_mm": selection.diameter_mm,
        "selected_bar_legs": selection.legs,
        "selected_bar_area_cm2": selection.area_cm2,
        "required_area_cm2": selection.required_area_cm2,
        "rho": selection.rho,
        "rho_min": selection.rho_min,
        "rho_max": selection.rho_max,
        "required_area_source": required_source,
        "prior_check_statuses": dict(prior_statuses),
        "available_bar_diameters_mm": AVAILABLE_FLEXURE_BAR_DIAMETERS_MM,
        "available_bar_legs": AVAILABLE_FLEXURE_BAR_LEGS,
        "formula": "select first deterministic candidate where selected_bar_area_cm2 >= max(As_required_cm2, rho_min*bw*d/100) and rho <= rho_max",
        "code_ref": "TBDY 2018 beam longitudinal reinforcement deterministic core bar selection",
    }

    return FlexureCheck(
        name=name,
        status=selection.status,
        demand=selection.required_area_cm2,
        capacity=selection.area_cm2,
        ratio=_ratio(selection.required_area_cm2, selection.area_cm2),
        unit="cm²",
        code_ref="TBDY 2018 beam longitudinal reinforcement deterministic core bar selection",
        evidence=evidence,
        message=_message(selection.status, f"{selection.designation} reinforcement bar selection"),
    )


def _select_bars(
    *,
    designation: str,
    required_area_cm2: float | None,
    bw_mm: float,
    d_mm: float,
    rho_min: float | None,
    rho_max: float | None,
) -> SelectedFlexureBars:
    if (
        designation not in {"top", "bottom"}
        or required_area_cm2 is None
        or required_area_cm2 <= 0.0
        or bw_mm <= 0.0
        or d_mm <= 0.0
        or rho_min is None
        or rho_min <= 0.0
        or rho_max is None
        or rho_max <= 0.0
    ):
        return SelectedFlexureBars(
            designation=designation,
            diameter_mm=None,
            legs=None,
            area_cm2=None,
            status="NO_DATA",
            required_area_cm2=required_area_cm2,
            rho_min=rho_min,
            rho_max=rho_max,
            rho=None,
        )

    min_area_from_rho_cm2 = rho_min * bw_mm * d_mm / 100.0
    max_area_from_rho_cm2 = rho_max * bw_mm * d_mm / 100.0
    target_area_cm2 = max(required_area_cm2, min_area_from_rho_cm2)

    if target_area_cm2 > max_area_from_rho_cm2:
        return SelectedFlexureBars(
            designation=designation,
            diameter_mm=None,
            legs=None,
            area_cm2=None,
            status="FAIL",
            required_area_cm2=required_area_cm2,
            rho_min=rho_min,
            rho_max=rho_max,
            rho=None,
        )

    candidates = sorted(
        _candidate_bars(),
        key=lambda item: (item["area_cm2"], item["legs"], item["diameter_mm"]),
    )

    for candidate in candidates:
        area_cm2 = candidate["area_cm2"]
        rho = area_cm2 * 100.0 / (bw_mm * d_mm)
        if area_cm2 >= target_area_cm2 and rho <= rho_max:
            return SelectedFlexureBars(
                designation=designation,
                diameter_mm=candidate["diameter_mm"],
                legs=int(candidate["legs"]),
                area_cm2=area_cm2,
                status="OK",
                required_area_cm2=required_area_cm2,
                rho_min=rho_min,
                rho_max=rho_max,
                rho=rho,
            )

    return SelectedFlexureBars(
        designation=designation,
        diameter_mm=None,
        legs=None,
        area_cm2=None,
        status="FAIL",
        required_area_cm2=required_area_cm2,
        rho_min=rho_min,
        rho_max=rho_max,
        rho=None,
    )


def _candidate_bars() -> tuple[dict[str, float], ...]:
    candidates: list[dict[str, float]] = []
    for diameter_mm in AVAILABLE_FLEXURE_BAR_DIAMETERS_MM:
        single_area_cm2 = _single_bar_area_cm2(diameter_mm)
        for legs in AVAILABLE_FLEXURE_BAR_LEGS:
            candidates.append(
                {
                    "diameter_mm": diameter_mm,
                    "legs": float(legs),
                    "area_cm2": single_area_cm2 * legs,
                }
            )
    return tuple(candidates)


def _single_bar_area_cm2(diameter_mm: float) -> float:
    return math.pi * diameter_mm * diameter_mm / 4.0 / 100.0


def _consolidated_evidence(
    *,
    selected_area_cm2: float | None,
    required_area_cm2: float | None,
    required_area_source: str,
    area_ratio: float | None,
    stress_block: Mapping[str, float | None],
    rho: float | None,
    rho_min: float | None,
    rho_max: float | None,
    rho_min_ratio: float | None,
    rho_max_ratio: float | None,
    rho_min_status: str,
    rho_max_status: str,
) -> dict[str, object]:
    return {
        "consolidated_flexure_evidence": True,
        "selected_area_cm2": selected_area_cm2,
        "selected_area_mm2": None if selected_area_cm2 is None else selected_area_cm2 * 100.0,
        "required_area_cm2": required_area_cm2,
        "required_area_source": required_area_source,
        "provided_to_required_ratio": area_ratio,
        "stress_block_a_mm": stress_block["a_mm"],
        "neutral_axis_c_mm": stress_block["c_mm"],
        "compression_block_kN": stress_block["compression_block_kN"],
        "rho": rho,
        "rho_min": rho_min,
        "rho_max": rho_max,
        "rho_min_ratio": rho_min_ratio,
        "rho_max_ratio": rho_max_ratio,
        "rho_min_status": rho_min_status,
        "rho_max_status": rho_max_status,
        "rho_min_formula": "rho_min = max(0.8 * fctd_mpa / fyd_mpa, 0.0015)",
        "rho_max_formula": "rho_max = 0.04",
    }


def _valid_area(value: float | None) -> bool:
    return value is not None and value > 0.0


def _ratio(required: float | None, provided: float | None) -> float | None:
    if not _valid_area(required) or not _valid_area(provided):
        return None
    return required / provided


def _area_status(required: float | None, provided: float | None) -> str:
    if not _valid_area(required) or not _valid_area(provided):
        return "NO_DATA"
    return "OK" if provided >= required else "FAIL"


def _rho_min_check(
    *,
    name: str,
    selected_area_cm2: float | None,
    bw_mm: float,
    d_mm: float,
    fctd_mpa: float,
    fyd_mpa: float,
    rho_min: float | None,
    rho: float | None,
    ratio: float | None,
    required_source: str,
    label: str,
    consolidated: Mapping[str, object],
) -> FlexureCheck:
    selected_area_mm2 = None if selected_area_cm2 is None else selected_area_cm2 * 100.0
    status = _rho_min_status(rho_min, rho, ratio)

    return FlexureCheck(
        name=name,
        status=status,
        demand=rho_min,
        capacity=rho,
        ratio=ratio,
        unit="ratio",
        code_ref="TBDY 2018 minimum beam longitudinal reinforcement ratio",
        evidence={
            **consolidated,
            "selected_area_cm2": selected_area_cm2,
            "selected_area_mm2": selected_area_mm2,
            "bw_mm": bw_mm,
            "d_mm": d_mm,
            "fctd_mpa": fctd_mpa,
            "fyd_mpa": fyd_mpa,
            "rho": rho,
            "rho_min": rho_min,
            "formula": "rho = selected_area_mm2 / (bw_mm * d_mm); rho_min = max(0.8 * fctd_mpa / fyd_mpa, 0.0015)",
            "code_ref": "TBDY 2018 minimum beam longitudinal reinforcement ratio",
            "required_area_source": required_source,
        },
        message=_message(status, label),
    )


def _rho_max_check(
    *,
    name: str,
    selected_area_cm2: float | None,
    bw_mm: float,
    d_mm: float,
    fctd_mpa: float,
    fyd_mpa: float,
    rho_max: float | None,
    rho: float | None,
    ratio: float | None,
    required_source: str,
    label: str,
    consolidated: Mapping[str, object],
) -> FlexureCheck:
    selected_area_mm2 = None if selected_area_cm2 is None else selected_area_cm2 * 100.0
    status = _rho_max_status(rho_max, rho, ratio)

    return FlexureCheck(
        name=name,
        status=status,
        demand=rho,
        capacity=rho_max,
        ratio=ratio,
        unit="ratio",
        code_ref="TBDY 2018 maximum beam longitudinal reinforcement ratio",
        evidence={
            **consolidated,
            "selected_area_cm2": selected_area_cm2,
            "selected_area_mm2": selected_area_mm2,
            "bw_mm": bw_mm,
            "d_mm": d_mm,
            "fctd_mpa": fctd_mpa,
            "fyd_mpa": fyd_mpa,
            "rho": rho,
            "rho_max": rho_max,
            "formula": "rho = selected_area_mm2 / (bw_mm * d_mm); rho_max = 0.04",
            "code_ref": "TBDY 2018 maximum beam longitudinal reinforcement ratio",
            "required_area_source": required_source,
        },
        message=_message(status, label),
    )


def _message(status: str, label: str) -> str:
    if status == "NO_DATA":
        return f"{label} data missing"
    if status == "OK":
        return f"{label} satisfies requirement"
    return f"{label} below requirement"


def _top_design_moment(ctx: BeamModelContext) -> float | None:
    candidates = [
        _positive_moment(ctx.Md_left_neg_kNm),
        _positive_moment(ctx.Md_right_neg_kNm),
    ]
    valid = [value for value in candidates if value is not None]
    if not valid:
        return None
    return max(valid)


def _positive_moment(value: float | None) -> float | None:
    if value is None:
        return None
    if value == 0.0:
        return None
    return abs(value)


def _resolve_required_area(
    *,
    moment_required_cm2: float | None,
    context_required_cm2: float | None,
) -> tuple[float | None, str]:
    if _valid_area(moment_required_cm2):
        return moment_required_cm2, "moment_derived"

    if _valid_area(context_required_cm2):
        return context_required_cm2, "context_input"

    return None, "no_data"


def _required_area_calculation_values(
    *,
    Md_kNm: float | None,
    As_required_cm2: float | None,
    fyd_mpa: float,
    fcd_mpa: float,
    bw_mm: float,
    d_mm: float,
) -> dict[str, float | None]:
    Mu_Nmm = None if Md_kNm is None else abs(Md_kNm) * 1_000_000.0
    As_required_mm2 = None if As_required_cm2 is None else As_required_cm2 * 100.0

    return {
        "Mu_Nmm": Mu_Nmm,
        "As_required_mm2": As_required_mm2,
        "fyd_mpa": fyd_mpa,
        "fcd_mpa": fcd_mpa,
        "bw_mm": bw_mm,
        "d_mm": d_mm,
    }


def _required_area_from_moment_cm2(
    *,
    Md_kNm: float | None,
    fyd_mpa: float,
    fcd_mpa: float,
    bw_mm: float,
    d_mm: float,
) -> float | None:
    if (
        Md_kNm is None
        or Md_kNm <= 0.0
        or fyd_mpa <= 0.0
        or fcd_mpa <= 0.0
        or bw_mm <= 0.0
        or d_mm <= 0.0
    ):
        return None

    Mu_Nmm = abs(Md_kNm) * 1_000_000.0
    quadratic_a = (fyd_mpa * fyd_mpa) / (1.7 * fcd_mpa * bw_mm)
    quadratic_b = fyd_mpa * d_mm
    discriminant = quadratic_b * quadratic_b - 4.0 * quadratic_a * Mu_Nmm

    if discriminant < 0.0:
        return None

    As_required_mm2 = (quadratic_b - math.sqrt(discriminant)) / (2.0 * quadratic_a)

    if As_required_mm2 <= 0.0:
        return None

    return As_required_mm2 / 100.0


def _rho(
    selected_area_cm2: float | None,
    bw_mm: float,
    d_mm: float,
) -> float | None:
    if (
        selected_area_cm2 is None
        or selected_area_cm2 <= 0.0
        or bw_mm <= 0.0
        or d_mm <= 0.0
    ):
        return None

    return (selected_area_cm2 * 100.0) / (bw_mm * d_mm)


def _rho_min(fctd_mpa: float, fyd_mpa: float) -> float | None:
    if fctd_mpa <= 0.0 or fyd_mpa <= 0.0:
        return None

    return max(0.8 * fctd_mpa / fyd_mpa, 0.0015)


def _rho_min_ratio(rho_min: float | None, rho: float | None) -> float | None:
    if rho_min is None or rho is None or rho <= 0.0:
        return None
    return rho_min / rho


def _rho_min_status(rho_min: float | None, rho: float | None, ratio: float | None) -> str:
    if rho_min is None or rho is None or ratio is None:
        return "NO_DATA"
    if rho >= rho_min:
        return "OK"
    return "FAIL"


def _rho_max() -> float:
    return 0.04


def _rho_max_ratio(rho: float | None, rho_max: float | None) -> float | None:
    if rho is None or rho <= 0.0 or rho_max is None or rho_max <= 0.0:
        return None
    return rho / rho_max


def _rho_max_status(rho_max: float | None, rho: float | None, ratio: float | None) -> str:
    if rho_max is None or rho is None or ratio is None:
        return "NO_DATA"
    if rho <= rho_max:
        return "OK"
    return "FAIL"


def _beta1(fck_mpa: float | None) -> float | None:
    if fck_mpa is None or fck_mpa <= 0.0:
        return None

    if fck_mpa <= 30.0:
        return 0.85

    return max(0.65, 0.85 - 0.05 * ((fck_mpa - 30.0) / 7.0))


def _stress_block(
    *,
    selected_area_cm2: float | None,
    fyd_mpa: float,
    fcd_mpa: float,
    bw_mm: float,
    beta1: float | None,
) -> dict[str, float | None]:
    if (
        selected_area_cm2 is None
        or selected_area_cm2 <= 0.0
        or fyd_mpa <= 0.0
        or fcd_mpa <= 0.0
        or bw_mm <= 0.0
        or beta1 is None
        or beta1 <= 0.0
    ):
        return {
            "a_mm": None,
            "c_mm": None,
            "compression_block_kN": None,
        }

    selected_area_mm2 = selected_area_cm2 * 100.0
    a_mm = selected_area_mm2 * fyd_mpa / (0.85 * fcd_mpa * bw_mm)
    c_mm = a_mm / beta1
    compression_block_kN = 0.85 * fcd_mpa * bw_mm * a_mm / 1000.0

    return {
        "a_mm": a_mm,
        "c_mm": c_mm,
        "compression_block_kN": compression_block_kN,
    }