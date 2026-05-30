from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from tbdy_engine.design.beams.calculators.geometry import GeometryResult, TBDYGeometryCalculator
from tbdy_engine.design.beams.context import BeamModelContext, build_beam_model_context, validate_beam_model_context


@dataclass(frozen=True)
class GeometryCoreResult:
    context: BeamModelContext
    validation_errors: tuple[str, ...]
    geometry: GeometryResult | None
    status: str


def evaluate_beam_geometry_core(data: Mapping[str, object]) -> GeometryCoreResult:
    context = build_beam_model_context(data)
    validation_errors = validate_beam_model_context(context)
    if validation_errors:
        return GeometryCoreResult(
            context=context,
            validation_errors=validation_errors,
            geometry=None,
            status="INVALID_INPUT",
        )

    geometry = TBDYGeometryCalculator().calculate(context)
    return GeometryCoreResult(
        context=context,
        validation_errors=(),
        geometry=geometry,
        status=geometry.status,
    )
