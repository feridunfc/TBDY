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
        demand = ctx.bw
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
            evidence={"bw": ctx.bw, "limit": capacity, "ratio": ratio, "formula": "bw >= 250 mm"},
            message="bw satisfies minimum width" if demand >= capacity else "bw below minimum width",
        )

    def _minimum_depth(self, ctx: BeamModelContext) -> GeometryCheck:
        demand = ctx.h
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
            evidence={"h": ctx.h, "limit": capacity, "ratio": ratio, "formula": "h >= 300 mm"},
            message="h satisfies minimum depth" if demand >= capacity else "h below minimum depth",
        )

    def _span_to_depth(self, ctx: BeamModelContext) -> GeometryCheck:
        ratio = ctx.Ln / ctx.h
        capacity = 4.0
        return GeometryCheck(
            name="beam_geometry_span_depth_ratio",
            status="OK" if ratio >= capacity else "FAIL",
            demand=ratio,
            capacity=capacity,
            ratio=ratio / capacity,
            unit="ratio",
            code_ref=self.code_ref,
            evidence={"Ln": ctx.Ln, "h": ctx.h, "Ln_over_h": ratio, "limit": capacity, "ratio": ratio / capacity, "formula": "Ln / h >= 4"},
            message="Ln/h satisfies minimum ratio" if ratio >= capacity else "Ln/h below minimum ratio",
        )

    def _depth_to_width(self, ctx: BeamModelContext) -> GeometryCheck:
        ratio = ctx.h / ctx.bw
        capacity = 3.5
        return GeometryCheck(
            name="beam_geometry_depth_width_ratio",
            status="OK" if ratio <= capacity else "FAIL",
            demand=ratio,
            capacity=capacity,
            ratio=ratio / capacity,
            unit="ratio",
            code_ref=self.code_ref,
            evidence={"h": ctx.h, "bw": ctx.bw, "h_over_bw": ratio, "limit": capacity, "ratio": ratio / capacity, "formula": "h / bw <= 3.5"},
            message="h/bw satisfies maximum ratio" if ratio <= capacity else "h/bw above maximum ratio",
        )
