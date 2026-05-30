from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from tbdy_engine.design.beams.context import BeamModelContext


@dataclass(frozen=True)
class GeometryCheck:
    name: str
    status: str
    demand: float
    capacity: float
    ratio: float
    unit: str
    code_ref: str
    evidence: Mapping[str, object]
    message: str


@dataclass(frozen=True)
class GeometryResult:
    checks: tuple[GeometryCheck, ...]
    status: str


class TBDYGeometryCalculator:
    code_ref = "TBDY 2018 §7.4.1"

    def calculate(self, ctx: BeamModelContext) -> GeometryResult:
        checks = (
            self._minimum_width(ctx),
            self._minimum_depth(ctx),
            self._span_to_depth(ctx),
            self._depth_to_width(ctx),
        )
        status = "OK" if all(check.status == "OK" for check in checks) else "FAIL"
        return GeometryResult(checks=checks, status=status)

    def _minimum_width(self, ctx: BeamModelContext) -> GeometryCheck:
        demand = ctx.bw_mm
        capacity = 250.0
        ratio = demand / capacity
        return GeometryCheck(
            name="beam_geometry_min_width",
            status="OK" if demand >= capacity else "FAIL",
            demand=demand,
            capacity=capacity,
            ratio=ratio,
            unit="mm",
            code_ref=self.code_ref,
            evidence={"bw_mm": ctx.bw_mm, "limit": capacity, "computed_ratio": ratio, "formula": "bw_mm >= 250 mm"},
            message="bw_mm satisfies minimum width" if demand >= capacity else "bw_mm below minimum width",
        )

    def _minimum_depth(self, ctx: BeamModelContext) -> GeometryCheck:
        demand = ctx.h_mm
        capacity = 300.0
        ratio = demand / capacity
        return GeometryCheck(
            name="beam_geometry_min_depth",
            status="OK" if demand >= capacity else "FAIL",
            demand=demand,
            capacity=capacity,
            ratio=ratio,
            unit="mm",
            code_ref=self.code_ref,
            evidence={"h_mm": ctx.h_mm, "limit": capacity, "computed_ratio": ratio, "formula": "h_mm >= 300 mm"},
            message="h_mm satisfies minimum depth" if demand >= capacity else "h_mm below minimum depth",
        )

    def _span_to_depth(self, ctx: BeamModelContext) -> GeometryCheck:
        ln_over_h = ctx.Ln_mm / ctx.h_mm
        capacity = 4.0
        ratio = ln_over_h / capacity
        return GeometryCheck(
            name="beam_geometry_span_depth_ratio",
            status="OK" if ln_over_h >= capacity else "FAIL",
            demand=ln_over_h,
            capacity=capacity,
            ratio=ratio,
            unit="ratio",
            code_ref=self.code_ref,
            evidence={"Ln_mm": ctx.Ln_mm, "h_mm": ctx.h_mm, "Ln_over_h": ln_over_h, "limit": capacity, "computed_ratio": ratio, "formula": "Ln_mm / h_mm >= 4"},
            message="Ln_mm/h_mm satisfies minimum ratio" if ln_over_h >= capacity else "Ln_mm/h_mm below minimum ratio",
        )

    def _depth_to_width(self, ctx: BeamModelContext) -> GeometryCheck:
        h_over_bw = ctx.h_mm / ctx.bw_mm
        capacity = 3.5
        ratio = h_over_bw / capacity
        return GeometryCheck(
            name="beam_geometry_depth_width_ratio",
            status="OK" if h_over_bw <= capacity else "FAIL",
            demand=h_over_bw,
            capacity=capacity,
            ratio=ratio,
            unit="ratio",
            code_ref=self.code_ref,
            evidence={"h_mm": ctx.h_mm, "bw_mm": ctx.bw_mm, "h_over_bw": h_over_bw, "limit": capacity, "computed_ratio": ratio, "formula": "h_mm / bw_mm <= 3.5"},
            message="h_mm/bw_mm satisfies maximum ratio" if h_over_bw <= capacity else "h_mm/bw_mm above maximum ratio",
        )
