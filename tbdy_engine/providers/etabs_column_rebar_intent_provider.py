"""Read-only ETABS column reinforcement design-intent acquisition.

``PropFrame.GetRebarColumn`` describes section reinforcement inputs/design intent.
It is not final/provided/as-built reinforcement authority. The provider preserves
that boundary explicitly while exposing factual cover, bar-size names and tie
configuration for later reviewed use by the column design engine.

The module is import-safe without ETABS/comtypes; callers pass an already
attached ``PropFrame`` object and an explicit reviewed length-unit contract.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


REBAR_INTENT_DESIGN_ONLY = "DESIGN_INTENT_ONLY"
REBAR_INTENT_SECTION_CHECK_INPUT = "SECTION_REBAR_CHECK_INPUT"


class EtabsColumnRebarIntentProviderError(RuntimeError):
    """Raised when factual GetRebarColumn evidence is failed or malformed."""


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsColumnRebarIntentProviderError(f"{label} must be a nonblank canonical string")
    return value


def _finite(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise EtabsColumnRebarIntentProviderError(f"{label} must be finite numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EtabsColumnRebarIntentProviderError(f"{label} must be finite numeric") from exc
    if not math.isfinite(result):
        raise EtabsColumnRebarIntentProviderError(f"{label} must be finite")
    return result


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise EtabsColumnRebarIntentProviderError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise EtabsColumnRebarIntentProviderError(f"{label} must be an integer") from exc
    if result < 0:
        raise EtabsColumnRebarIntentProviderError(f"{label} must be >= 0")
    return result


def _api_sequence(raw: Any, *, section_name: str) -> tuple[Any, ...]:
    if not isinstance(raw, (tuple, list)):
        raise EtabsColumnRebarIntentProviderError(
            f"GetRebarColumn({section_name!r}) returned unexpected scalar: {raw!r}"
        )
    values = tuple(raw)
    if len(values) != 15:
        raise EtabsColumnRebarIntentProviderError(
            f"GetRebarColumn({section_name!r}) returned {len(values)} values; expected 15: {raw!r}"
        )
    return values


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
    """Capture factual section rebar intent without upgrading its authority."""
    section = _text(section_name, "section_name")
    if reviewed_length_unit not in {"m", "mm"}:
        raise EtabsColumnRebarIntentProviderError("reviewed_length_unit must be explicitly 'm' or 'mm'")

    raw = prop_frame.GetRebarColumn(section)
    (
        mat_prop_long_raw,
        mat_prop_confine_raw,
        pattern_raw,
        confine_type_raw,
        cover_raw,
        number_c_bars_raw,
        number_r3_bars_raw,
        number_r2_bars_raw,
        rebar_size_raw,
        tie_size_raw,
        tie_spacing_raw,
        number_2_dir_tie_bars_raw,
        number_3_dir_tie_bars_raw,
        to_be_designed_raw,
        ret,
    ) = _api_sequence(raw, section_name=section)

    if not isinstance(ret, int) or ret != 0:
        raise EtabsColumnRebarIntentProviderError(
            f"GetRebarColumn({section!r}) failed/raw={raw!r}"
        )
    if not isinstance(to_be_designed_raw, bool):
        raise EtabsColumnRebarIntentProviderError(
            f"GetRebarColumn({section!r}) returned non-boolean ToBeDesigned={to_be_designed_raw!r}"
        )

    cover = _finite(cover_raw, "Cover")
    tie_spacing = _finite(tie_spacing_raw, "TieSpacingLongit")
    if cover <= 0.0 or tie_spacing <= 0.0:
        raise EtabsColumnRebarIntentProviderError("Cover and TieSpacingLongit must be > 0")

    return EtabsColumnRebarIntentEvidence(
        section_name=section,
        mat_prop_long=_text(mat_prop_long_raw, "MatPropLong"),
        mat_prop_confine=_text(mat_prop_confine_raw, "MatPropConfine"),
        pattern=_nonnegative_int(pattern_raw, "Pattern"),
        confine_type=_nonnegative_int(confine_type_raw, "ConfineType"),
        cover=cover,
        number_c_bars=_nonnegative_int(number_c_bars_raw, "NumberCBars"),
        number_r3_bars=_nonnegative_int(number_r3_bars_raw, "NumberR3Bars"),
        number_r2_bars=_nonnegative_int(number_r2_bars_raw, "NumberR2Bars"),
        rebar_size_name=_text(rebar_size_raw, "RebarSize"),
        tie_size_name=_text(tie_size_raw, "TieSize"),
        tie_spacing_longit=tie_spacing,
        number_2_dir_tie_bars=_nonnegative_int(number_2_dir_tie_bars_raw, "Number2DirTieBars"),
        number_3_dir_tie_bars=_nonnegative_int(number_3_dir_tie_bars_raw, "Number3DirTieBars"),
        to_be_designed=to_be_designed_raw,
        reviewed_length_unit=reviewed_length_unit,
        raw_api=repr(raw),
    )


__all__ = [
    "REBAR_INTENT_DESIGN_ONLY",
    "REBAR_INTENT_SECTION_CHECK_INPUT",
    "EtabsColumnRebarIntentEvidence",
    "EtabsColumnRebarIntentProviderError",
    "capture_etabs_column_rebar_intent",
]
