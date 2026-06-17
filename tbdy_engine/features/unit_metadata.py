"""Unit metadata helpers for the C13.3-P0 FeatureSnapshot proof.

This module is intentionally feature-layer only.  It preserves raw source unit
context and produces labelled normalized display values without unlocking any
engineering check.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ALLOWED_UNITS = {"kN", "kN.m", "m", "mm", "mm2", "MPa", "ratio", "percent", "unitless"}
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

    The C13.3-P0 proof does not know ETABS model units independently; therefore it
    only converts when the raw unit is explicit and the conversion is lossless for
    display.  Otherwise the raw value is preserved and the normalized unit is the
    declared default display unit when the raw unit already matches it.
    """
    normalized_unit = default_unit_for(quantity_kind)
    raw_unit_text = raw_unit or normalized_unit
    normalized_value = raw_value
    factor = 1.0
    rule = "identity_or_non_numeric"

    if isinstance(raw_value, (int, float)):
        if raw_unit_text == normalized_unit:
            normalized_value = raw_value
            rule = "explicit_identity"
        elif raw_unit_text == "m" and normalized_unit == "mm":
            normalized_value = raw_value * 1000.0
            factor = 1000.0
            rule = "m_to_mm_display"
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


__all__ = [
    "ALLOWED_UNITS",
    "DEFAULT_REPORT_UNITS",
    "NORMALIZED_UNIT_POLICY",
    "RAW_UNIT_POLICY",
    "UnitNormalization",
    "default_unit_for",
    "normalize_value",
]
