"""Unit metadata helpers for FeatureSnapshot fact resolution.

This module is intentionally feature-layer only. It preserves raw source unit
context and produces labelled normalized values without unlocking any
engineering check.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

ALLOWED_UNITS = {"kN", "kN.m", "m", "cm", "mm", "mm2", "MPa", "ratio", "percent", "unitless"}
RAW_UNIT_POLICY = "ETABS_LIVE_MODEL_CONTEXT_RAW_UNCONVERTED"
NORMALIZED_UNIT_POLICY = "FEATURESNAPSHOT_DISPLAY_NORMALIZATION_WITH_PROVENANCE"

DEFAULT_REPORT_UNITS = {
    "force": "kN",
    "moment": "kN.m",
    "global_length_elevation": "m",
    "section_dimensions": "mm",
    "deformation_displacement": "mm",
    "drift_ratio": "ratio",
    "drift_percent": "percent",
    "stress_material_strength": "MPa",
    "material_mechanical_constants": "MPa",
    "reinforcement_area": "mm2",
    "identity_context": "unitless",
    "unitless": "unitless",
}


@dataclass(frozen=True, slots=True)
class UnitNormalization:
    raw_value: Any
    raw_unit: str
    normalized_value: Any
    normalized_unit: str
    quantity_kind: str
    unit_policy: str
    provenance: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_value": self.raw_value,
            "raw_unit": self.raw_unit,
            "normalized_value": self.normalized_value,
            "normalized_unit": self.normalized_unit,
            "quantity_kind": self.quantity_kind,
            "unit_policy": self.unit_policy,
            "conversion_provenance": dict(self.provenance),
        }


def default_unit_for(quantity_kind: str) -> str:
    return DEFAULT_REPORT_UNITS.get(quantity_kind, "unitless")


def normalize_value(raw_value: Any, *, raw_unit: str | None, quantity_kind: str) -> UnitNormalization:
    """Return labelled raw+normalized unit metadata.

    This existing public helper converts only from an explicit source unit. It
    never infers units from numeric magnitude. Callers that require a trusted
    ETABS UnitContext must validate that context before calling this function.
    """
    normalized_unit = default_unit_for(quantity_kind)
    raw_unit_text = raw_unit or normalized_unit
    normalized_value = raw_value
    factor = 1.0
    rule = "identity_or_non_numeric"

    if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
        if raw_unit_text == normalized_unit:
            normalized_value = raw_value
            rule = "explicit_identity"
        elif raw_unit_text == "m" and normalized_unit == "mm":
            normalized_value = raw_value * 1000.0
            factor = 1000.0
            rule = "m_to_mm_display"
        elif raw_unit_text == "cm" and normalized_unit == "mm":
            normalized_value = raw_value * 10.0
            factor = 10.0
            rule = "cm_to_mm_display"
        elif raw_unit_text == "mm" and normalized_unit == "m":
            normalized_value = raw_value / 1000.0
            factor = 0.001
            rule = "mm_to_m_display"
        else:
            normalized_value = raw_value
            normalized_unit = raw_unit_text
            rule = "preserved_raw_unit_no_safe_conversion"

    return UnitNormalization(
        raw_value=raw_value,
        raw_unit=raw_unit_text,
        normalized_value=normalized_value,
        normalized_unit=normalized_unit,
        quantity_kind=quantity_kind,
        unit_policy=NORMALIZED_UNIT_POLICY,
        provenance={
            "source_unit_policy": RAW_UNIT_POLICY,
            "normalization_rule": rule,
            "factor": factor,
            "silent_source_contract_conversion": False,
            "check_engine_unlock": False,
        },
    )


def _finite_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text.replace(",", "."))
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def normalize_length_to_mm(
    raw_value: Any,
    *,
    raw_unit: str | None,
    unit_context_trusted: bool,
) -> UnitNormalization:
    """Normalize one factual length to millimetres using explicit unit evidence.

    The function is deliberately narrow and data-only. ``unit_context_trusted``
    must come from the caller's source UnitContext validation. Missing,
    untrusted, or unsupported units fail closed by returning ``None`` as the
    normalized value. Numeric magnitude is never used to infer a unit.
    """
    raw_unit_text = str(raw_unit or "").strip()
    numeric = _finite_number(raw_value)

    def unresolved(rule: str) -> UnitNormalization:
        return UnitNormalization(
            raw_value=raw_value,
            raw_unit=raw_unit_text,
            normalized_value=None,
            normalized_unit="mm",
            quantity_kind="section_dimensions",
            unit_policy=NORMALIZED_UNIT_POLICY,
            provenance={
                "source_unit_policy": RAW_UNIT_POLICY,
                "normalization_rule": rule,
                "factor": None,
                "normalization_status": "UNVERIFIED",
                "silent_source_contract_conversion": False,
                "check_engine_unlock": False,
            },
        )

    if not unit_context_trusted:
        return unresolved("untrusted_unit_context")
    if numeric is None:
        return unresolved("non_numeric_length_value")
    if raw_unit_text not in {"m", "cm", "mm"}:
        return unresolved("unsupported_length_unit")

    normalized = normalize_value(
        numeric,
        raw_unit=raw_unit_text,
        quantity_kind="section_dimensions",
    )
    return UnitNormalization(
        raw_value=raw_value,
        raw_unit=normalized.raw_unit,
        normalized_value=normalized.normalized_value,
        normalized_unit=normalized.normalized_unit,
        quantity_kind=normalized.quantity_kind,
        unit_policy=normalized.unit_policy,
        provenance={
            **normalized.provenance,
            "normalization_status": "RESOLVED",
            "input_numeric_value": numeric,
        },
    )


__all__ = [
    "ALLOWED_UNITS",
    "DEFAULT_REPORT_UNITS",
    "NORMALIZED_UNIT_POLICY",
    "RAW_UNIT_POLICY",
    "UnitNormalization",
    "default_unit_for",
    "normalize_length_to_mm",
    "normalize_value",
]
