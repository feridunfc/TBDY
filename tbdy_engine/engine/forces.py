"""
Force envelope builder – Production Grade.
Case-based ETABS force tables -> reusable design/screening envelopes.
"""

from typing import Dict, Tuple
import pandas as pd


def _detect_ends(df: pd.DataFrame, station_col: str = "Station") -> pd.DataFrame:
    if df.empty or station_col not in df.columns:
        return df.copy()
    work = df.copy()
    work[station_col] = pd.to_numeric(work[station_col], errors="coerce").fillna(0.0)
    id_col = "ElementID" if "ElementID" in work.columns else None
    if id_col is None:
        return work
    work["end_type"] = "mid"
    for name, grp in work.groupby(id_col):
        s_min = grp[station_col].min()
        s_max = grp[station_col].max()
        tol = max((s_max - s_min) * 0.01, 1e-6)
        work.loc[grp[(grp[station_col] - s_min).abs() <= tol].index, "end_type"] = "i"
        work.loc[grp[(grp[station_col] - s_max).abs() <= tol].index, "end_type"] = "j"
    return work


def build_column_end_envelope(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    if df.empty:
        return pd.DataFrame(), {}
    work = _detect_ends(df, "Station")
    for c in ["P", "V2", "V3", "M2", "M3"]:
        if c not in work.columns:
            work[c] = 0.0
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)
    id_col = "ElementID" if "ElementID" in work.columns else ("Column" if "Column" in work.columns else None)
    if id_col is None:
        return pd.DataFrame(), {}
    group_cols = [id_col] + (["Story"] if "Story" in work.columns else [])
    records, lookup = [], {}
    for keys, grp in work.groupby(group_cols):
        if isinstance(keys, tuple):
            name = str(keys[0]).strip(); story = str(keys[1]).strip() if len(keys) > 1 else None
        else:
            name = str(keys).strip(); story = None
        if not name:
            continue
        top_rows = grp[grp["end_type"] == "j"]
        bot_rows = grp[grp["end_type"] == "i"]
        rec = {
            "Column": name,
            "P_max": grp["P"].abs().max(),
            "V2_max": grp["V2"].abs().max(),
            "V3_max": grp["V3"].abs().max(),
            "M2_top": top_rows["M2"].abs().max() if not top_rows.empty else 0.0,
            "M3_top": top_rows["M3"].abs().max() if not top_rows.empty else 0.0,
            "M2_bot": bot_rows["M2"].abs().max() if not bot_rows.empty else 0.0,
            "M3_bot": bot_rows["M3"].abs().max() if not bot_rows.empty else 0.0,
        }
        if story is not None:
            rec["Story"] = story
        records.append(rec)
        lookup[name] = {k: v for k, v in rec.items() if k not in {"Column", "Story"}}
    return pd.DataFrame(records), lookup


def build_beam_end_envelope(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    if df.empty:
        return pd.DataFrame(), {}
    work = _detect_ends(df, "Station")
    for c in ["V2", "V3", "M2", "M3"]:
        if c not in work.columns:
            work[c] = 0.0
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)
    id_col = "ElementID" if "ElementID" in work.columns else ("Beam" if "Beam" in work.columns else None)
    if id_col is None:
        return pd.DataFrame(), {}
    group_cols = [id_col] + (["Story"] if "Story" in work.columns else [])
    records, lookup = [], {}
    for keys, grp in work.groupby(group_cols):
        if isinstance(keys, tuple):
            name = str(keys[0]).strip(); story = str(keys[1]).strip() if len(keys) > 1 else None
        else:
            name = str(keys).strip(); story = None
        if not name:
            continue
        i_rows = grp[grp["end_type"] == "i"]
        j_rows = grp[grp["end_type"] == "j"]
        rec = {
            "Beam": name,
            "V2_max": grp["V2"].abs().max(),
            "V3_max": grp["V3"].abs().max(),
            "M2_i": i_rows["M2"].abs().max() if not i_rows.empty else 0.0,
            "M3_i": i_rows["M3"].abs().max() if not i_rows.empty else 0.0,
            "M2_j": j_rows["M2"].abs().max() if not j_rows.empty else 0.0,
            "M3_j": j_rows["M3"].abs().max() if not j_rows.empty else 0.0,
        }
        if story is not None:
            rec["Story"] = story
        records.append(rec)
        lookup[name] = {k: v for k, v in rec.items() if k not in {"Beam", "Story"}}
    return pd.DataFrame(records), lookup


def build_story_shear_envelope(df: pd.DataFrame, direction: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    direction = direction.upper()
    candidates = [f"V{direction}", f"F{direction}", f"Shear{direction}"]
    force_col = next((c for c in candidates if c in df.columns), None)
    if force_col is None:
        for c in df.columns:
            if c.strip().upper() in {f"V{direction}", f"F{direction}"}:
                force_col = c; break
    if force_col is None:
        return pd.DataFrame()
    work = df.copy()
    work[force_col] = pd.to_numeric(work[force_col], errors="coerce").fillna(0.0)
    story_col = "Story" if "Story" in work.columns else ("ElementID" if "ElementID" in work.columns else None)
    if story_col is None:
        return pd.DataFrame()
    grouped = work.groupby(story_col)[force_col].apply(lambda x: x.abs().max()).reset_index()
    grouped.columns = ["Story", "V_max"]
    return grouped


def build_pier_envelope(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    if df.empty:
        return pd.DataFrame(), {}
    work = df.copy()
    val_cols = [c for c in ["P", "V2", "V3", "M2", "M3"] if c in work.columns]
    if not val_cols:
        return pd.DataFrame(), {}
    for c in val_cols:
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)
        work[c + "_abs"] = work[c].abs()
    pier_col = "ElementID" if "ElementID" in work.columns else ("Pier" if "Pier" in work.columns else ("PierName" if "PierName" in work.columns else None))
    if pier_col is None:
        return pd.DataFrame(), {}
    group_cols = [pier_col] + (["Story"] if "Story" in work.columns else [])
    grouped = work.groupby(group_cols)[[c + "_abs" for c in val_cols]].max().reset_index()
    rename = {c + "_abs": c + "_max" for c in val_cols}
    grouped = grouped.rename(columns=rename)
    lookup = {}
    for _, row in grouped.iterrows():
        key = str(row[pier_col]).strip()
        if key:
            lookup[key] = {c + "_max": row[c + "_max"] for c in val_cols}
    return grouped, lookup

def build_casewise_frame_end_forces(
    df: pd.DataFrame,
    member_col: str,
    station_col: str = "station",
    case_col: str = "output_case",
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Case-wise i/j end force map.

    Output:
    {
      "EX": {
        "C1": {"M2_i": ..., "M3_i": ..., "M2_j": ..., "M3_j": ..., "V2_max": ..., "V3_max": ...}
      }
    }
    """
    if df is None or df.empty:
        return {}

    work = df.copy()
    # duplicate column names can occur after ETABS normalize/merge
    work = work.loc[:, ~work.columns.duplicated()].copy()
    # column compatibility
    if station_col not in work.columns and "Station" in work.columns:
        station_col = "Station"
    if case_col not in work.columns and "OutputCase" in work.columns:
        case_col = "OutputCase"
    if member_col not in work.columns:
        for alt in ["unique_name", "UniqueName", "column", "Column", "beam", "Beam", "element", "ElementID"]:
            if alt in work.columns:
                member_col = alt
                break

    if station_col not in work.columns or case_col not in work.columns or member_col not in work.columns:
        return {}

    for c in ["m2_knm", "m3_knm", "M2", "M3", "v2_kn", "v3_kn", "V2", "V3"]:
        if c in work.columns:
            work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)

    m2_col = "m2_knm" if "m2_knm" in work.columns else "M2"
    m3_col = "m3_knm" if "m3_knm" in work.columns else "M3"
    v2_col = "v2_kn" if "v2_kn" in work.columns else "V2"
    v3_col = "v3_kn" if "v3_kn" in work.columns else "V3"

    for c in [m2_col, m3_col, v2_col, v3_col]:
        if c not in work.columns:
            work[c] = 0.0

    work[station_col] = pd.to_numeric(work[station_col], errors="coerce").fillna(0.0)

    out: Dict[str, Dict[str, Dict[str, float]]] = {}

    for (case, member), grp in work.groupby([case_col, member_col]):
        case = str(case).strip()
        member = str(member).strip()

        if not case or not member:
            continue

        s_min = grp[station_col].min()
        s_max = grp[station_col].max()
        tol = max((s_max - s_min) * 0.01, 1e-6)

        i_rows = grp[(grp[station_col] - s_min).abs() <= tol]
        j_rows = grp[(grp[station_col] - s_max).abs() <= tol]

        rec = {
            "M2_i": float(i_rows[m2_col].abs().max()) if not i_rows.empty else 0.0,
            "M3_i": float(i_rows[m3_col].abs().max()) if not i_rows.empty else 0.0,
            "M2_j": float(j_rows[m2_col].abs().max()) if not j_rows.empty else 0.0,
            "M3_j": float(j_rows[m3_col].abs().max()) if not j_rows.empty else 0.0,
            "V2_max": float(grp[v2_col].abs().max()),
            "V3_max": float(grp[v3_col].abs().max()),
        }

        out.setdefault(case, {})[member] = rec

    return out