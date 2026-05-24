from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class ProvidedRebarRecord:
    element_type: str
    story: str
    label: str
    key: str
    source: str = "provided_rebar"

    as_top_mm2: Optional[float] = None
    as_bottom_mm2: Optional[float] = None
    as_compression_mm2: Optional[float] = None

    as_total_mm2: Optional[float] = None
    bar_count: Optional[int] = None
    bar_diameter_mm: Optional[float] = None

    stirrup_diameter_mm: Optional[float] = None
    stirrup_spacing_mm: Optional[float] = None
    stirrup_legs: Optional[int] = None
    stirrup_legs_x: Optional[int] = None
    stirrup_legs_y: Optional[int] = None

    av_s_mm2_per_m: Optional[float] = None
    ash_x_mm2: Optional[float] = None
    ash_y_mm2: Optional[float] = None

    status: str = "OK"
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        v = float(str(value).replace(",", "."))
        if v != v:
            return default
        return v
    except Exception:
        return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    v = _safe_float(value, None)
    if v is None:
        return default
    return int(round(v))


def _norm_col(df: Any, names: list[str]) -> Optional[str]:
    if df is None or not hasattr(df, "columns"):
        return None

    targets = {
        str(n).strip().lower().replace(" ", "").replace("_", "")
        for n in names
    }

    for c in df.columns:
        cc = str(c).strip().lower().replace(" ", "").replace("_", "")
        if cc in targets:
            return c

    for c in df.columns:
        cc = str(c).strip().lower().replace(" ", "").replace("_", "")
        if any(t in cc for t in targets):
            return c

    return None


def _get_table(ctx: Any, *names: str):
    tables = getattr(ctx, "tables", {}) or {}
    design_metadata = getattr(ctx, "design_metadata", {}) or {}

    for name in names:
        obj = tables.get(name)
        if obj is not None:
            return obj

    for name in names:
        obj = design_metadata.get(name)
        if obj is not None:
            return obj

    return None


class ProvidedRebarResolver:
    """
    Reads final/provided rebar schedules from ModelContext.

    This resolver never assumes rebar.
    If provided tables do not exist, it returns an empty dict.
    """

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx

    def resolve(self) -> Dict[str, ProvidedRebarRecord]:
        df = _get_table(
            self.ctx,
            "provided_rebar",
            "user_rebar_schedule",
            "beam_provided_rebar",
            "column_provided_rebar",
        )

        if df is None or not hasattr(df, "empty") or df.empty:
            return {}

        type_col = _norm_col(df, ["element_type", "type", "member_type"])
        story_col = _norm_col(df, ["story", "level"])
        label_col = _norm_col(df, ["label", "element", "frame", "member"])
        source_col = _norm_col(df, ["source"])

        if not label_col:
            return {}

        result: Dict[str, ProvidedRebarRecord] = {}

        for _, row in df.iterrows():
            element_type = str(row.get(type_col) or "").strip().upper() if type_col else ""
            story = str(row.get(story_col) or "").strip() if story_col else ""
            label = str(row.get(label_col) or "").strip()

            if not label:
                continue

            if not element_type:
                if label.upper().startswith("B"):
                    element_type = "BEAM"
                elif label.upper().startswith("C"):
                    element_type = "COLUMN"
                else:
                    element_type = "UNKNOWN"

            key = f"{story}|{label}"

            rec = ProvidedRebarRecord(
                element_type=element_type,
                story=story,
                label=label,
                key=key,
                source=str(row.get(source_col) or "provided_rebar") if source_col else "provided_rebar",

                as_top_mm2=_safe_float(row.get(_norm_col(df, ["as_top_mm2", "astop", "as_top"]))),
                as_bottom_mm2=_safe_float(row.get(_norm_col(df, ["as_bottom_mm2", "asbot", "as_bottom"]))),
                as_compression_mm2=_safe_float(row.get(_norm_col(df, ["as_compression_mm2", "as_comp"]))),

                as_total_mm2=_safe_float(row.get(_norm_col(df, ["as_total_mm2", "astotal", "as_total"]))),
                bar_count=_safe_int(row.get(_norm_col(df, ["bar_count", "n_bars", "bars"]))),
                bar_diameter_mm=_safe_float(row.get(_norm_col(df, ["bar_diameter_mm", "bar_dia", "phi"]))),

                stirrup_diameter_mm=_safe_float(row.get(_norm_col(df, ["stirrup_diameter_mm", "tie_diameter_mm", "etr_dia"]))),
                stirrup_spacing_mm=_safe_float(row.get(_norm_col(df, ["stirrup_spacing_mm", "tie_spacing_mm", "s_mm"]))),
                stirrup_legs=_safe_int(row.get(_norm_col(df, ["stirrup_legs", "legs"]))),
                stirrup_legs_x=_safe_int(row.get(_norm_col(df, ["stirrup_legs_x", "legs_x"]))),
                stirrup_legs_y=_safe_int(row.get(_norm_col(df, ["stirrup_legs_y", "legs_y"]))),

                av_s_mm2_per_m=_safe_float(row.get(_norm_col(df, ["av_s_mm2_per_m", "avs_mm2_per_m", "av_per_m"]))),
                ash_x_mm2=_safe_float(row.get(_norm_col(df, ["ash_x_mm2", "ashx"]))),
                ash_y_mm2=_safe_float(row.get(_norm_col(df, ["ash_y_mm2", "ashy"]))),
            )

            result[key] = rec

            # Label-only alias only if unique enough for fallback.
            result.setdefault(label, rec)

        return result

    def resolve_beams(self) -> Dict[str, ProvidedRebarRecord]:
        return {
            k: v for k, v in self.resolve().items()
            if v.element_type == "BEAM"
        }

    def resolve_columns(self) -> Dict[str, ProvidedRebarRecord]:
        return {
            k: v for k, v in self.resolve().items()
            if v.element_type == "COLUMN"
        }