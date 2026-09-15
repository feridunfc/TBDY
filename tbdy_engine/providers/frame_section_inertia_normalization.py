"""Public factual/provider seam for ETABS frame-section inertia SI normalization.

The application layer must not own CSI present-unit conversion.  This module
reuses the existing factual frame-flexural unit conversion and emits a stable
normalization provenance reference alongside the SI value.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math

from tbdy_engine.providers.etabs_frame_flexural_base_provider import (
    FrameFlexuralBaseFactError,
    _length_to_mm,
)

FRAME_SECTION_INERTIA_SI_AUTHORITY = (
    "ETABS_FRAME_SECTION_INERTIA_PRESENT_UNITS_TO_SI_M4_V1"
)


@dataclass(frozen=True, slots=True)
class NormalizedFrameSectionInertia:
    inertia_m4: float
    source_ref: str
    authority: str = FRAME_SECTION_INERTIA_SI_AUTHORITY


def normalize_frame_section_inertia_m4(
    value: object,
    present_length_unit: object,
    *,
    source_ref: str,
) -> NormalizedFrameSectionInertia:
    """Normalize a factual ETABS section inertia from present length^4 to m^4."""
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise FrameFlexuralBaseFactError("frame inertia normalization requires source_ref")
    if isinstance(value, bool) or value is None:
        raise FrameFlexuralBaseFactError("frame section inertia must be numeric")
    try:
        raw = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise FrameFlexuralBaseFactError("frame section inertia must be numeric") from exc
    if not raw.is_finite() or raw <= 0:
        raise FrameFlexuralBaseFactError(
            "frame section inertia must be positive finite"
        )

    one_unit_mm = _length_to_mm(
        Decimal("1"),
        present_length_unit,
        "frame section inertia present length unit",
    )
    scale_m = one_unit_mm / Decimal("1000")
    value_m4 = raw * (scale_m ** 4)
    result = float(value_m4)
    if not math.isfinite(result) or result <= 0.0:
        raise FrameFlexuralBaseFactError(
            "normalized frame section inertia must be positive finite"
        )

    unit_code = getattr(present_length_unit, "value", present_length_unit)
    try:
        unit_code = int(unit_code)
    except (TypeError, ValueError) as exc:
        raise FrameFlexuralBaseFactError(
            "frame section inertia present length unit is unavailable"
        ) from exc
    return NormalizedFrameSectionInertia(
        inertia_m4=result,
        source_ref=(
            f"{FRAME_SECTION_INERTIA_SI_AUTHORITY}:"
            f"CSI_eLength={unit_code}:source={source_ref}"
        ),
    )


__all__ = [
    "FRAME_SECTION_INERTIA_SI_AUTHORITY",
    "NormalizedFrameSectionInertia",
    "normalize_frame_section_inertia_m4",
]
