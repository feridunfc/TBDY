"""Public factual/provider seam for ETABS frame-section inertia SI normalization.

The application layer must not own CSI present-unit conversion.  This module
reuses the existing factual frame-flexural unit conversion and emits a stable
normalization provenance reference alongside the SI value.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError, SourceUnitProvenance

from tbdy_engine.providers.etabs_frame_flexural_base_provider import (
    FrameFlexuralBaseFactError,
    _length_to_mm,
)

FRAME_SECTION_INERTIA_SI_AUTHORITY = (
    "ETABS_FRAME_SECTION_INERTIA_QUALIFIED_SOURCE_TO_SI_M4_V2"
)


@dataclass(frozen=True, slots=True)
class NormalizedFrameSectionInertia:
    inertia_m4: float
    source_ref: str
    authority: str = FRAME_SECTION_INERTIA_SI_AUTHORITY
    raw_value: str = ""
    source_unit: str = ""
    canonical_unit: str = "m4"
    factor: str = ""
    unit_evidence_ref: str = ""


def normalize_frame_section_inertia_m4(
    value: object,
    source_unit_provenance: object,
    *,
    source_ref: str,
    source_model_ref: str | None = None,
    session_ref: str | None = None,
    subject_key: str | None = None,
    output_key: str | None = None,
    capture_ref: str | None = None,
    raw_response_ref: str | None = None,
) -> NormalizedFrameSectionInertia:
    """Normalize only from the GetSectProps output's own qualified binding."""
    if not isinstance(source_unit_provenance, SourceUnitProvenance):
        raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:MISSING_INERTIA_SOURCE_BINDING")
    if not all((source_model_ref, session_ref, subject_key, output_key, capture_ref, raw_response_ref)):
        raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:MISSING_INERTIA_CONTEXT")
    try:
        unit = source_unit_provenance.require(
            source_call="SapModel.PropFrame.GetSectProps", subject_key=subject_key,
            output_key=output_key, dimension="L4", source_model_ref=source_model_ref,
            session_ref=session_ref, capture_ref=capture_ref, raw_response_ref=raw_response_ref)
    except EtabsOAPIError as exc:
        raise FrameFlexuralBaseFactError(str(exc)) from exc
    codes = {"mm4": 4, "mm^4": 4, "cm4": 5, "cm^4": 5, "m4": 6, "m^4": 6}
    if unit not in codes:
        raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:UNKNOWN_OR_WRONG_DIMENSION_UNIT")
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
        codes[unit],
        "frame section inertia present length unit",
    )
    scale_m = one_unit_mm / Decimal("1000")
    value_m4 = raw * (scale_m ** 4)
    result = float(value_m4)
    if not math.isfinite(result) or result <= 0.0:
        raise FrameFlexuralBaseFactError(
            "normalized frame section inertia must be positive finite"
        )


    return NormalizedFrameSectionInertia(
        inertia_m4=result,
        raw_value=str(value), source_unit=unit, factor=str(scale_m ** 4),
        unit_evidence_ref=source_unit_provenance.evidence_ref,
        source_ref=(
            f"{FRAME_SECTION_INERTIA_SI_AUTHORITY}:"
            f"unit={unit}:binding={source_unit_provenance.evidence_ref}:source={source_ref}"
        ),
    )


__all__ = [
    "FRAME_SECTION_INERTIA_SI_AUTHORITY",
    "NormalizedFrameSectionInertia",
    "normalize_frame_section_inertia_m4",
]
