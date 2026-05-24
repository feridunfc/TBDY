
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


def _tables(ctx: Any) -> dict:
    return getattr(ctx, "tables", {}) or {}


def _s(x: Any) -> str:
    return "" if x is None else str(x).strip()


def _num(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, str) and not x.strip():
            return None
        v = float(str(x).replace(",", "."))
        if v != v:
            return None
        return v
    except Exception:
        return None


def _norm_key(x: Any) -> str:
    return _s(x).lower().replace(" ", "").replace("_", "").replace("-", "")


def find_col(df: pd.DataFrame, names: Iterable[str]) -> Optional[str]:
    targets = {_norm_key(n) for n in names}

    for c in df.columns:
        if _norm_key(c) in targets:
            return c

    for c in df.columns:
        cn = _norm_key(c)
        if any(t in cn for t in targets):
            return c

    return None


BAR_AREA_MM2 = {
    6: 28.27,
    8: 50.27,
    10: 78.54,
    12: 113.10,
    14: 153.94,
    16: 201.06,
    18: 254.47,
    20: 314.16,
    22: 380.13,
    24: 452.39,
    25: 490.87,
    26: 530.93,
    28: 615.75,
    30: 706.86,
    32: 804.25,
    36: 1017.88,
    40: 1256.64,
}


def bar_area_mm2(dia_mm: Any) -> Optional[float]:
    d = _num(dia_mm)
    if d is None or d <= 0:
        return None

    nearest = int(round(d))
    if nearest in BAR_AREA_MM2 and abs(d - nearest) < 0.05:
        return BAR_AREA_MM2[nearest]

    return 3.141592653589793 * d * d / 4.0


def bars_area_mm2(count: Any, dia_mm: Any) -> Optional[float]:
    n = _num(count)
    a = bar_area_mm2(dia_mm)

    if n is None or a is None:
        return None

    return n * a


REBAR_TABLE_CANDIDATES = {
    "BEAM": ["rebar_beams", "beam_rebar_schedule", "real_rebar_beams"],
    "COLUMN": ["rebar_columns", "column_rebar_schedule", "real_rebar_columns"],
    "WALL": ["rebar_walls", "wall_rebar_schedule", "real_rebar_walls"],
    "FOUNDATION": ["rebar_foundation", "raft_rebar_schedule", "real_rebar_foundation"],
}


def get_real_rebar_tables(ctx: Any) -> Dict[str, pd.DataFrame]:
    tables = _tables(ctx)
    out: Dict[str, pd.DataFrame] = {}

    combined = tables.get("real_rebar_schedule")
    if combined is None or getattr(combined, "empty", True):
        combined = tables.get("rebar_schedule")

    if combined is not None and not getattr(combined, "empty", True):
        type_col = find_col(combined, ["element_type", "type", "member_type", "category"])
        if type_col:
            for family in REBAR_TABLE_CANDIDATES:
                mask = combined[type_col].astype(str).str.upper().str.contains(family, na=False)
                sub = combined[mask].copy()
                if not sub.empty:
                    out[family] = sub

    for family, names in REBAR_TABLE_CANDIDATES.items():
        if family in out:
            continue

        for name in names:
            df = tables.get(name)
            if df is not None and not getattr(df, "empty", True):
                out[family] = df
                break

    return out


def _base_record(df: pd.DataFrame, row: pd.Series, family: str, source: str, idx: int) -> Dict[str, Any]:
    story_col = find_col(df, ["story", "kat", "level"])
    label_col = find_col(
        df,
        [
            "element_id",
            "label",
            "beam_label",
            "column_label",
            "pier",
            "wall",
            "raft_id",
            "id",
            "unique_name",
            "name",
            "object",
        ],
    )
    zone_col = find_col(df, ["zone", "station_zone", "region", "location"])

    return {
        "element_type": family,
        "element_id": _s(row.get(label_col)) if label_col else "",
        "story": _s(row.get(story_col)) if story_col else "",
        "zone": _s(row.get(zone_col)) if zone_col else "",
        "source_table": source,
        "source_row": int(idx) + 1,
    }


def normalize_beam_rebar(df: pd.DataFrame, source: str = "rebar_beams") -> List[Dict[str, Any]]:
    cols = {
        "top_as": find_col(df, ["as_top_provided_mm2", "as_top", "top_as", "top_area_mm2"]),
        "bot_as": find_col(df, ["as_bottom_provided_mm2", "as_bottom", "bottom_as", "bot_as", "bottom_area_mm2"]),
        "top_n": find_col(df, ["top_bar_count", "top_count", "n_top"]),
        "top_d": find_col(df, ["top_bar_diameter_mm", "top_diameter", "top_dia", "phi_top"]),
        "bot_n": find_col(df, ["bottom_bar_count", "bot_bar_count", "bottom_count", "n_bottom", "n_bot"]),
        "bot_d": find_col(df, ["bottom_bar_diameter_mm", "bot_diameter", "bottom_dia", "phi_bottom", "phi_bot"]),
        "st_d": find_col(df, ["stirrup_diameter_mm", "stirrup_dia", "phi_stirrup", "tie_dia"]),
        "st_s": find_col(df, ["stirrup_spacing_mm", "stirrup_spacing", "s_stirrup", "spacing_mm", "tie_spacing"]),
        "legs": find_col(df, ["stirrup_leg_count", "legs", "leg_count", "tie_legs"]),
        "avs": find_col(df, ["av_s_provided_mm2_per_m", "av_over_s", "avs", "av_s"]),
    }

    out: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        rec = _base_record(df, row, "BEAM", source, idx)

        top = _num(row.get(cols["top_as"])) if cols["top_as"] else None
        if top is None and cols["top_n"] and cols["top_d"]:
            top = bars_area_mm2(row.get(cols["top_n"]), row.get(cols["top_d"]))

        bot = _num(row.get(cols["bot_as"])) if cols["bot_as"] else None
        if bot is None and cols["bot_n"] and cols["bot_d"]:
            bot = bars_area_mm2(row.get(cols["bot_n"]), row.get(cols["bot_d"]))

        avs = _num(row.get(cols["avs"])) if cols["avs"] else None
        stirrup_dia = _num(row.get(cols["st_d"])) if cols["st_d"] else None
        stirrup_spacing = _num(row.get(cols["st_s"])) if cols["st_s"] else None
        stirrup_legs = _num(row.get(cols["legs"])) if cols["legs"] else 2.0

        if avs is None and stirrup_dia and stirrup_spacing and stirrup_spacing > 0:
            area = bar_area_mm2(stirrup_dia)
            if area:
                avs = area * (stirrup_legs or 2.0) * 1000.0 / stirrup_spacing

        missing = []
        if top is None:
            missing.append("top rebar")
        if bot is None:
            missing.append("bottom rebar")
        if avs is None:
            missing.append("stirrup Av/s")

        rec.update(
            {
                "as_top_provided_mm2": top,
                "as_bottom_provided_mm2": bot,
                "av_s_provided_mm2_per_m": avs,
                "stirrup_diameter_mm": stirrup_dia,
                "stirrup_spacing_mm": stirrup_spacing,
                "stirrup_leg_count": stirrup_legs,
                "status": "OK" if not missing else "WARNING",
                "note": "provided beam rebar parsed" if not missing else "missing: " + ", ".join(missing),
            }
        )
        out.append(rec)

    return out


def normalize_column_rebar(df: pd.DataFrame, source: str = "rebar_columns") -> List[Dict[str, Any]]:
    cols = {
        "as": find_col(df, ["as_provided_mm2", "as", "longitudinal_as_mm2"]),
        "n": find_col(df, ["longitudinal_bar_count", "bar_count", "n_bars", "nbarstotal"]),
        "d": find_col(df, ["longitudinal_bar_diameter_mm", "bar_diameter", "bar_dia", "phi", "bardiameter"]),
        "tie_d": find_col(df, ["tie_diameter_mm", "tie_dia", "phi_tie", "stirrupdiameter"]),
        "tie_s_end": find_col(df, ["tie_spacing_end_mm", "s_end", "spacing_end", "stirrupspacing"]),
        "tie_s_mid": find_col(df, ["tie_spacing_mid_mm", "s_mid", "spacing_mid"]),
        "tie_legs_1": find_col(df, ["tie_legs_dir1", "stirrup_legs_dir1", "legs_dir1"]),
        "tie_legs_2": find_col(df, ["tie_legs_dir2", "stirrup_legs_dir2", "legs_dir2"]),
        "b": find_col(df, ["b_mm", "width_mm", "b"]),
        "h": find_col(df, ["h_mm", "height_mm", "h", "depth_mm"]),
    }

    out: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        rec = _base_record(df, row, "COLUMN", source, idx)

        n_bars = _num(row.get(cols["n"])) if cols["n"] else None
        bar_dia = _num(row.get(cols["d"])) if cols["d"] else None

        As = _num(row.get(cols["as"])) if cols["as"] else None
        if As is None and n_bars and bar_dia:
            As = bars_area_mm2(n_bars, bar_dia)

        b = _num(row.get(cols["b"])) if cols["b"] else None
        h = _num(row.get(cols["h"])) if cols["h"] else None
        gross = b * h if b and h else None
        ratio = As / gross if As is not None and gross and gross > 0 else None

        tie_dia = _num(row.get(cols["tie_d"])) if cols["tie_d"] else None
        tie_s_end = _num(row.get(cols["tie_s_end"])) if cols["tie_s_end"] else None
        tie_s_mid = _num(row.get(cols["tie_s_mid"])) if cols["tie_s_mid"] else None
        tie_legs_1 = _num(row.get(cols["tie_legs_1"])) if cols["tie_legs_1"] else 2.0
        tie_legs_2 = _num(row.get(cols["tie_legs_2"])) if cols["tie_legs_2"] else 2.0

        missing = []
        if As is None:
            missing.append("longitudinal As")
        if n_bars is None:
            missing.append("bar count")
        if bar_dia is None:
            missing.append("bar diameter")
        if tie_dia is None:
            missing.append("tie diameter")
        if tie_s_end is None and tie_s_mid is None:
            missing.append("tie spacing")

        rec.update(
            {
                "as_provided_mm2": As,
                "n_bars_total": int(n_bars) if n_bars is not None else None,
                "bar_diameter_mm": bar_dia,
                "gross_area_mm2": gross,
                "rebar_ratio": ratio,
                "tie_diameter_mm": tie_dia,
                "tie_spacing_end_mm": tie_s_end,
                "tie_spacing_mid_mm": tie_s_mid,
                "tie_leg_count_dir1": int(tie_legs_1 or 2),
                "tie_leg_count_dir2": int(tie_legs_2 or 2),
                "status": "OK" if not missing else "WARNING",
                "note": "provided column rebar parsed" if not missing else "missing: " + ", ".join(missing),
            }
        )
        out.append(rec)

    return out


def normalize_real_rebar(ctx: Any) -> Dict[str, List[Dict[str, Any]]]:
    dfs = get_real_rebar_tables(ctx)
    out: Dict[str, List[Dict[str, Any]]] = {"BEAM": [], "COLUMN": [], "WALL": [], "FOUNDATION": []}

    if "BEAM" in dfs:
        out["BEAM"] = normalize_beam_rebar(dfs["BEAM"], "rebar_beams")

    if "COLUMN" in dfs:
        out["COLUMN"] = normalize_column_rebar(dfs["COLUMN"], "rebar_columns")

    return out
