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
    checks: tuple[FlexureCheck, ...]
    status: str


class TBDYFlexureCalculator:
    def calculate(self, ctx: BeamModelContext) -> FlexureResult:
        top_ratio = _ratio(ctx.top_required_area_cm2, ctx.top_selected_area_cm2)
        bottom_ratio = _ratio(ctx.bottom_required_area_cm2, ctx.bottom_selected_area_cm2)

        checks = (
            self._top_area_check(ctx),
            self._bottom_area_check(ctx),
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
            checks=checks,
            status=status,
        )

    def _top_area_check(self, ctx: BeamModelContext) -> FlexureCheck:
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
                "formula": "top_selected_area_cm2 >= top_required_area_cm2",
            },
            message=_message(status, "top reinforcement area"),
        )

    def _bottom_area_check(self, ctx: BeamModelContext) -> FlexureCheck:
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
                "formula": "bottom_selected_area_cm2 >= bottom_required_area_cm2",
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