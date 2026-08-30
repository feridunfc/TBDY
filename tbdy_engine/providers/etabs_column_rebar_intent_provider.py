"""Semantic ETABS column reinforcement design-intent provider.

Exact ``PropFrame.GetRebarColumn`` invocation and positional decoding live in
``tbdy_engine.etabs.oapi.object_model``. This provider keeps design-intent
meaning, reviewed unit interpretation, and authority boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.oapi.object_model import read_rebar_column

REBAR_INTENT_DESIGN_ONLY = "DESIGN_INTENT_ONLY"
REBAR_INTENT_SECTION_CHECK_INPUT = "SECTION_REBAR_CHECK_INPUT"


class EtabsColumnRebarIntentProviderError(RuntimeError):
    """Raised when factual GetRebarColumn evidence cannot be promoted."""


@dataclass(frozen=True, slots=True)
class EtabsColumnRebarIntentEvidence:
    section_name: str
    mat_prop_long: str
    mat_prop_confine: str
    pattern: int
    confine_type: int
    cover: float
    number_c_bars: int
    number_r3_bars: int
    number_r2_bars: int
    rebar_size_name: str
    tie_size_name: str
    tie_spacing_longit: float
    number_2_dir_tie_bars: int
    number_3_dir_tie_bars: int
    to_be_designed: bool
    reviewed_length_unit: str
    raw_api: str
    status: str = "PROVEN_ETABS_COLUMN_REBAR_INTENT"

    @property
    def authority(self) -> str:
        return REBAR_INTENT_DESIGN_ONLY if self.to_be_designed else REBAR_INTENT_SECTION_CHECK_INPUT

    @property
    def cover_mm(self) -> float:
        return self.cover * (1000.0 if self.reviewed_length_unit == "m" else 1.0)

    @property
    def tie_spacing_longit_mm(self) -> float:
        return self.tie_spacing_longit * (1000.0 if self.reviewed_length_unit == "m" else 1.0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "authority": self.authority,
            "section_name": self.section_name,
            "mat_prop_long": self.mat_prop_long,
            "mat_prop_confine": self.mat_prop_confine,
            "pattern": self.pattern,
            "confine_type": self.confine_type,
            "cover": self.cover,
            "cover_mm": self.cover_mm,
            "number_c_bars": self.number_c_bars,
            "number_r3_bars": self.number_r3_bars,
            "number_r2_bars": self.number_r2_bars,
            "rebar_size_name": self.rebar_size_name,
            "tie_size_name": self.tie_size_name,
            "tie_spacing_longit": self.tie_spacing_longit,
            "tie_spacing_longit_mm": self.tie_spacing_longit_mm,
            "number_2_dir_tie_bars": self.number_2_dir_tie_bars,
            "number_3_dir_tie_bars": self.number_3_dir_tie_bars,
            "to_be_designed": self.to_be_designed,
            "reviewed_length_unit": self.reviewed_length_unit,
            "raw_api": self.raw_api,
            "final_or_provided_rebar_authority": False,
        }


def capture_etabs_column_rebar_intent(
    prop_frame: Any,
    section_name: str,
    *,
    reviewed_length_unit: str,
) -> EtabsColumnRebarIntentEvidence:
    if reviewed_length_unit not in {"m", "mm"}:
        raise EtabsColumnRebarIntentProviderError("reviewed_length_unit must be explicitly 'm' or 'mm'")
    try:
        fact = read_rebar_column(prop_frame, section_name)
    except EtabsOAPIError as exc:
        raise EtabsColumnRebarIntentProviderError(str(exc)) from exc
    return EtabsColumnRebarIntentEvidence(
        section_name=fact.section_name,
        mat_prop_long=fact.mat_prop_long,
        mat_prop_confine=fact.mat_prop_confine,
        pattern=fact.pattern,
        confine_type=fact.confine_type,
        cover=fact.cover,
        number_c_bars=fact.number_c_bars,
        number_r3_bars=fact.number_r3_bars,
        number_r2_bars=fact.number_r2_bars,
        rebar_size_name=fact.rebar_size_name,
        tie_size_name=fact.tie_size_name,
        tie_spacing_longit=fact.tie_spacing_longit,
        number_2_dir_tie_bars=fact.number_2_dir_tie_bars,
        number_3_dir_tie_bars=fact.number_3_dir_tie_bars,
        to_be_designed=fact.to_be_designed,
        reviewed_length_unit=reviewed_length_unit,
        raw_api=repr(fact.raw_response),
    )


__all__ = [
    "REBAR_INTENT_DESIGN_ONLY",
    "REBAR_INTENT_SECTION_CHECK_INPUT",
    "EtabsColumnRebarIntentEvidence",
    "EtabsColumnRebarIntentProviderError",
    "capture_etabs_column_rebar_intent",
]
