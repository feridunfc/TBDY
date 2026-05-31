from __future__ import annotations

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
class FlexureResult:
    Md_left_neg_kNm: float
    Md_mid_pos_kNm: float | None
    Md_right_neg_kNm: float | None
    required_top_area_cm2: float | None
    required_bottom_area_cm2: float | None
    provided_top_area_cm2: float | None
    provided_bottom_area_cm2: float | None
    top_ratio: float | None
    bottom_ratio: float | None

    beta1: float | None
    top_stress_block_a_mm: float | None
    top_neutral_axis_c_mm: float | None
    top_compression_block_kN: float | None
    bottom_stress_block_a_mm: float | None
    bottom_neutral_axis_c_mm: float | None
    bottom_compression_block_kN: float | None

    checks: tuple[FlexureCheck, ...]
    status: str


class TBDYFlexureCalculator:
    def calculate(self, ctx: BeamModelContext) -> FlexureResult:
        top_ratio = _ratio(ctx.top_required_area_cm2, ctx.top_selected_area_cm2)
        bottom_ratio = _ratio(ctx.bottom_required_area_cm2, ctx.bottom_selected_area_cm2)

        beta1 = _beta1(ctx.fck_mpa)
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

        checks = (
            self._top_area_check(ctx, beta1, top_block),
            self._bottom_area_check(ctx, beta1, bottom_block),
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
            required_top_area_cm2=ctx.top_required_area_cm2,
            required_bottom_area_cm2=ctx.bottom_required_area_cm2,
            provided_top_area_cm2=ctx.top_selected_area_cm2,
            provided_bottom_area_cm2=ctx.bottom_selected_area_cm2,
            top_ratio=top_ratio,
            bottom_ratio=bottom_ratio,
            beta1=beta1,
            top_stress_block_a_mm=top_block["a_mm"],
            top_neutral_axis_c_mm=top_block["c_mm"],
            top_compression_block_kN=top_block["compression_block_kN"],
            bottom_stress_block_a_mm=bottom_block["a_mm"],
            bottom_neutral_axis_c_mm=bottom_block["c_mm"],
            bottom_compression_block_kN=bottom_block["compression_block_kN"],
            checks=checks,
            status=status,
        )

    def _top_area_check(
        self,
        ctx: BeamModelContext,
        beta1: float | None,
        stress_block: Mapping[str, float | None],
    ) -> FlexureCheck:
        required = ctx.top_required_area_cm2
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
                "top_required_area_cm2": required,
                "top_selected_area_cm2": provided,
                "beta1": beta1,
                "stress_block_a_mm": stress_block["a_mm"],
                "neutral_axis_c_mm": stress_block["c_mm"],
                "compression_block_kN": stress_block["compression_block_kN"],
                "fyd_mpa": ctx.fyd_mpa,
                "fcd_mpa": ctx.fcd_mpa,
                "bw_mm": ctx.bw_mm,
                "formula": "top_selected_area_cm2 >= top_required_area_cm2",
                "stress_block_formula": "a_mm = As_mm2 * fyd_mpa / (0.85 * fcd_mpa * bw_mm); c_mm = a_mm / beta1",
            },
            message=_message(status, "top reinforcement area"),
        )

    def _bottom_area_check(
        self,
        ctx: BeamModelContext,
        beta1: float | None,
        stress_block: Mapping[str, float | None],
    ) -> FlexureCheck:
        required = ctx.bottom_required_area_cm2
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
                "bottom_required_area_cm2": required,
                "bottom_selected_area_cm2": provided,
                "beta1": beta1,
                "stress_block_a_mm": stress_block["a_mm"],
                "neutral_axis_c_mm": stress_block["c_mm"],
                "compression_block_kN": stress_block["compression_block_kN"],
                "fyd_mpa": ctx.fyd_mpa,
                "fcd_mpa": ctx.fcd_mpa,
                "bw_mm": ctx.bw_mm,
                "formula": "bottom_selected_area_cm2 >= bottom_required_area_cm2",
                "stress_block_formula": "a_mm = As_mm2 * fyd_mpa / (0.85 * fcd_mpa * bw_mm); c_mm = a_mm / beta1",
            },
            message=_message(status, "bottom reinforcement area"),
        )


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


def _message(status: str, label: str) -> str:
    if status == "NO_DATA":
        return f"{label} data missing"
    if status == "OK":
        return f"{label} provided area satisfies required area"
    return f"{label} provided area below required area"


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