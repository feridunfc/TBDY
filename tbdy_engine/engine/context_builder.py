# # app/engine/context_builder.py
# """
# ModelContext builder.
# All ETABS/Excel table access must happen here or in endpoint table services called by this builder.
# Checks consume only ModelContext.
# Internal units: m, kN, kNm, MPa.
# """
#
# from __future__ import annotations
#
# from dataclasses import dataclass, field
# from datetime import datetime
# from typing import Any, Dict, List, Optional, Tuple
# import logging
# import pandas as pd
# from app.engine.forces import build_casewise_frame_end_forces
# from app.catalog.tables import TABLE_CATALOG, resolve_etabs_name
# from app.engine.report_template_basis import template_design_basis, template_spectrum, TEMPLATE_SOURCE
# try:
#     from app.engine.unit_context import attach_unit_context, normalize_design_basis_units
# except Exception:  # pragma: no cover
#     attach_unit_context = None
#     normalize_design_basis_units = None
#
# logger = logging.getLogger("etabs-bridge")
#
# # Import project services when available. This keeps the package drop-in friendly.
# try:
#     from app.endpoints.tables import get_table_df, get_many_case_tables
# except Exception:  # pragma: no cover
#     get_table_df = None
#     get_many_case_tables = None
#
# try:
#     from app.etabs.connection import get_available_tables, get_sap
# except Exception:  # pragma: no cover
#     get_available_tables = None
#     get_sap = None
#
# try:
#     from app.endpoints.discover import discover_cases, discover_combinations
# except Exception:  # pragma: no cover
#     discover_cases = None
#     discover_combinations = None
#
# try:
#     from app.engine.topology import (
#         build_topology,
#         get_analysis_joints,
#         get_column_beam_mapping_summary,
#         recompute_confinement_for_analysis,
#     )
# except Exception:  # pragma: no cover
#     build_topology = None
#     get_analysis_joints = None
#     get_column_beam_mapping_summary = None
#     recompute_confinement_for_analysis = None


# tbdy_engine/engine/context_builder.py
"""
ModelContext builder - All ETABS table access centralized here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging
import pandas as pd

# Relative imports
from .forces import build_casewise_frame_end_forces
from .report_template_basis import template_design_basis, template_spectrum, TEMPLATE_SOURCE
from .unit_context import attach_unit_context, normalize_design_basis_units
from .topology import (
    build_topology,
    get_analysis_joints,
    get_column_beam_mapping_summary,
    recompute_confinement_for_analysis,
)

# ETABS katmanı
from ..etabs.table_catalog import TABLE_CATALOG, resolve_etabs_name
from ..etabs.table_reader import get_table_df, get_many_case_tables
from ..etabs.connection import get_available_tables, get_sap

logger = logging.getLogger("tbdy_engine")


#     discover_cases = None        # yorum satırı - bunları açın
#     discover_combinations = None  # yorum satırı - bunları açın
discover_cases = None              # ← bu satırı ekleyin
discover_combinations = None       # ← bu satırı ekleyin

COLUMN_ALIASES = {
    # --- BASIC ---
    "Story": "story",
    "StoryName": "story",

    # --- CASE / LOAD ---
    "Output Case": "output_case",
    "OutputCase": "output_case",
    "Case": "output_case",
    "CaseType": "case_type",
    "Case Type": "case_type",
    "Step Type": "step_type",
    "StepType": "step_type",

    # --- LOAD NAME FIX (KRİTİK) ---
    "Load Name": "load_name",
    "LoadName": "load_name",
    "loadname": "load_name",

    # --- GEOMETRY ---
    "Width": "width_m",
    "Depth": "depth_m",
    "Thickness": "thickness_m",
    "Height": "height_m",
    "Elevation": "elevation_m",
    "Length": "length_m",
    "Area": "area_m2",

    # --- SECTION (KRİTİK) ---
    "Section Property": "section",
    "SectionProperty": "section",
    "Property": "section",
    "SectProp": "section",
    "sectprop": "section",

    # --- GLOBAL COORDS (KRİTİK) ---
    "Global X": "x",
    "Global Y": "y",
    "Global Z": "z",
    "globalx": "x",
    "globaly": "y",
    "globalz": "z",

    # --- FORCES ---
    "FX": "fx",
    "FY": "fy",
    "FZ": "fz",
    "VX": "vx",
    "VY": "vy",
    "P": "p_kn",
    "V2": "v2_kn",
    "V3": "v3_kn",
    "M2": "m2_knm",
    "M3": "m3_knm",

    # --- MODAL ---
    "T": "period",
    "Period": "period",
    "Mode": "mode",
    "UX": "ux",
    "UY": "uy",
    "SumUX": "sum_ux",
    "Sum Ux": "sum_ux",
    "SumUY": "sum_uy",
    "Sum Uy": "sum_uy",

    # --- IDs ---
    "Unique Name": "unique_name",
    "UniqueName": "unique_name",
    "Obj": "unique_name",

    "Object Name": "object_name",
    "ObjectName": "object_name",

    "Object Label": "label",
    "ObjectLabel": "label",
    "ObjLabel": "label",
    "objlabel": "label",

    # ETABS Objects and Elements - Joints için kritik
    "ObjName": "name",
    "objname": "name",

    "Label": "label",
    "Name": "name",

    # --- ELEMENT TYPES ---
    "Column": "column",
    "Beam": "beam",
    "Pier": "pier",
    "PierLabel": "pier",

    # --- AREA / PIER ---
    "PierName": "piername",
    "Pier Name": "piername",
    "piername": "piername",
    "Unique Name": "unique_name",
    "UniqueName": "unique_name",

    # --- JOINT CONNECTIVITY ---
    "Elm JtI": "jt_i",
    "Elm JtJ": "jt_j",
    "UniquePtI": "jt_i",
    "UniquePtJ": "jt_j",

    # --- COMBOS ---
    "Combo": "combo",
    "Combo Name": "combo_name",
    "ComboName": "combo_name",

    # --- RS / SEISMIC ---
    "Function": "function",
    "Modal Case": "modal_case",
    "Trans Accel SF": "trans_accel_sf",
    "SDS": "sds",
    "SD1": "sd1",
    "R": "r",
    "D": "d",
    "I": "i",

    # --- MISC ---
    "Multiplier": "multiplier",
    "Direction": "direction",
    "Max Drift": "max_drift",
    "Avg Drift": "avg_drift",
    "Average Drift": "avg_drift",
    "Ratio": "ratio",

    # --- NAME ---
    "Name": "name",
    "Material": "material",
    "MatProp": "material",
    "Specified Concrete Comp Strength": "fck_mpa",
    "Fc": "fck_mpa",
    "F'c": "fck_mpa",
    "Fy": "fyk_mpa",
    "Rebar Yield Stress": "fyk_mpa",
    "Rebar Shear Yield Stress": "fywd_mpa",
    "GammaC": "gamma_c",
    "GammaS": "gamma_s",
}


CRITICAL_TABLES = {
    "story_definitions",
    "modal_mass",
    "story_drifts",
}


@dataclass
class ModelContext:
    project_info: Dict[str, Any] = field(default_factory=dict)
    spectrum: Dict[str, Any] = field(default_factory=dict)
    design_basis: Dict[str, Any] = field(default_factory=dict)

    story_height_map: Dict[str, float] = field(default_factory=dict)
    story_elevation_map: Dict[str, float] = field(default_factory=dict)
    story_order: List[str] = field(default_factory=list)

    load_cases: Dict[str, Any] = field(default_factory=dict)
    combo_groups: Dict[str, List[str]] = field(default_factory=dict)
    design_envelope: Optional[str] = None

    topology: Dict[str, Any] = field(default_factory=dict)
    geometry: Dict[str, Any] = field(default_factory=dict)

    modal: Dict[str, Any] = field(default_factory=dict)
    base_reactions: Dict[str, Any] = field(default_factory=dict)

    column_forces_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    beam_forces_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    pier_forces_df: pd.DataFrame = field(default_factory=pd.DataFrame)

    envelopes: Dict[str, Any] = field(default_factory=dict)
    tables: Dict[str, pd.DataFrame] = field(default_factory=dict)
    design_metadata: Dict[str, Optional[pd.DataFrame]] = field(default_factory=dict)
    notes: Dict[str, Any] = field(default_factory=dict)

    # Faz 1: per-check execution capability (ETABS_DESIGN_RESULT / DESIGN_LEVEL /
    # SCREENING / NO_DATA) computed by build_model_context, consumed by runner.
    capabilities: Dict[str, Any] = field(default_factory=dict)

    # Faz 1: binary readiness flags for design summary tables and material trust.
    # Runner and dependencies can read these without re-inspecting design_metadata.
    flags: Dict[str, Any] = field(default_factory=dict)


class EnvKeys:
    COLUMN_FORCES = "column_forces"
    COLUMN_FORCES_MAP = "column_forces_map"
    BEAM_FORCES = "beam_forces"
    BEAM_FORCES_MAP = "beam_forces_map"
    PIER_FORCES = "pier_forces"
    PIER_FORCES_MAP = "pier_forces_map"
    STORY_SHEAR_X = "story_shear_x"
    STORY_SHEAR_Y = "story_shear_y"
    
BEAM_FLEXURE_ENVELOPE_TABLE_CANDIDATES = [
    "Concrete Beam Flexure Envelope -  TS 500-2000(R2018)",
    "Concrete Beam Flexure Envelope - TS 500-2000(R2018)",
]

BEAM_SHEAR_ENVELOPE_TABLE_CANDIDATES = [
    "Concrete Beam Shear Envelope -  TS 500-2000(R2018)",
    "Concrete Beam Shear Envelope - TS 500-2000(R2018)",
]

def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()

def _get_first_nonempty_table(
    tables: Dict[str, pd.DataFrame],
    candidates: list[str],
) -> pd.DataFrame | None:
    for name in candidates:
        df = tables.get(name)
        if df is not None and not getattr(df, "empty", True):
            return df
    return None


def _beam_label_from_row(row: pd.Series) -> str:
    return _as_str(
        row.get("Label")
        or row.get("Beam")
        or row.get("label")
        or row.get("beam")
    )


def _beam_location_from_row(row: pd.Series) -> str:
    return _as_str(row.get("Location") or row.get("location"))


def _update_abs_winner(
    target: Dict[str, Any],
    value_key: str,
    case_key: str,
    value: Any,
    case: Any,
) -> None:
    candidate = abs(_as_float(value, 0.0))
    current = abs(_as_float(target.get(value_key), 0.0))
    if candidate > current:
        target[value_key] = candidate
        target[case_key] = _as_str(case) or None


def _empty_beam_design_envelope_semantics() -> Dict[str, Any]:
    return {
        "M_pos": 0.0,
        "M_pos_case": None,
        "M_neg_left": 0.0,
        "M_neg_left_case": None,
        "M_neg_right": 0.0,
        "M_neg_right_case": None,
        "V_max": 0.0,
        "V_max_case": None,
        "V_support": 0.0,
        "V_support_case": None,
        "T_max": 0.0,
        "T_max_case": None,
        "source": "beam_design_envelope",
    }


def _build_beam_design_envelope_semantic_map(
    flexure_df: pd.DataFrame | None,
    shear_df: pd.DataFrame | None,
) -> Dict[str, Dict[str, Any]]:
    semantic_map: Dict[str, Dict[str, Any]] = {}

    if flexure_df is not None and not getattr(flexure_df, "empty", True):
        for _, row in flexure_df.iterrows():
            beam = _beam_label_from_row(row)
            if not beam:
                continue

            target = semantic_map.setdefault(
                beam,
                _empty_beam_design_envelope_semantics(),
            )
            location = _beam_location_from_row(row)

            if location == "End-I":
                _update_abs_winner(
                    target,
                    "M_neg_left",
                    "M_neg_left_case",
                    row.get("MomentTop"),
                    row.get("AsTopCombo"),
                )
            elif location == "Middle":
                _update_abs_winner(
                    target,
                    "M_pos",
                    "M_pos_case",
                    row.get("MomentBot"),
                    row.get("AsBotCombo"),
                )
            elif location == "End-J":
                _update_abs_winner(
                    target,
                    "M_neg_right",
                    "M_neg_right_case",
                    row.get("MomentTop"),
                    row.get("AsTopCombo"),
                )

    if shear_df is not None and not getattr(shear_df, "empty", True):
        for _, row in shear_df.iterrows():
            beam = _beam_label_from_row(row)
            if not beam:
                continue

            target = semantic_map.setdefault(
                beam,
                _empty_beam_design_envelope_semantics(),
            )
            location = _beam_location_from_row(row)

            _update_abs_winner(
                target,
                "V_max",
                "V_max_case",
                row.get("Shear"),
                row.get("VCombo"),
            )

            if location in {"End-I", "End-J"}:
                _update_abs_winner(
                    target,
                    "V_support",
                    "V_support_case",
                    row.get("Shear"),
                    row.get("VCombo"),
                )

    return semantic_map


def _merge_beam_design_envelope_semantics(ctx: ModelContext) -> None:
    flexure_df = _get_first_nonempty_table(
        ctx.tables,
        BEAM_FLEXURE_ENVELOPE_TABLE_CANDIDATES,
    )
    shear_df = _get_first_nonempty_table(
        ctx.tables,
        BEAM_SHEAR_ENVELOPE_TABLE_CANDIDATES,
    )

    if flexure_df is None and shear_df is None:
        ctx.notes.setdefault("data_gaps", []).append(
            "Beam design envelope tables missing or empty; semantic beam envelope forces not populated."
        )
        return

    semantic_map = _build_beam_design_envelope_semantic_map(flexure_df, shear_df)
    if not semantic_map:
        ctx.notes.setdefault("data_gaps", []).append(
            "Beam design envelope semantic map is empty."
        )
        return

    beam_forces_map = ctx.envelopes.setdefault(EnvKeys.BEAM_FORCES_MAP, {})

    for label, semantic_entry in semantic_map.items():
        target = beam_forces_map.setdefault(label, {})

        for key, value in semantic_entry.items():
            if key == "source":
                target.setdefault(key, value)
                continue

            if key.endswith("_case"):
                if value is not None:
                    target[key] = value
                else:
                    target.setdefault(key, None)
                continue

            if isinstance(value, (int, float)):
                if value != 0.0 or key not in target:
                    target[key] = value
                continue

            if value is not None:
                target[key] = value

def _snake(s: str) -> str:
    return str(s).strip().lower().replace("\n", " ").replace("-", "_").replace("/", "_").replace(" ", "_")

# app/engine/context_builder.py

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rename = {}
    for c in out.columns:
        c_clean = str(c).strip()
        rename[c] = COLUMN_ALIASES.get(c_clean, _snake(c_clean))
    out = out.rename(columns=rename)

    # --- EXISTING: t2/t3 -> width/depth ---
    if "t2" in out.columns and "width_m" not in out.columns:
        out["width_m"] = out["t2"]
    if "t3" in out.columns and "depth_m" not in out.columns:
        out["depth_m"] = out["t3"]

    # 🔥 NEW: global coords -> x,y,z
    if "x" not in out.columns and "globalx" in out.columns:
        out["x"] = out["globalx"]
    if "y" not in out.columns and "globaly" in out.columns:
        out["y"] = out["globaly"]
    if "z" not in out.columns and "globalz" in out.columns:
        out["z"] = out["globalz"]
    # --- AREA / WALL MAPPING FIX ---
    # ETABS Area Assignments - Pier Labels:
    # story, label, unique_name, piername
    if "area" not in out.columns:
        if "unique_name" in out.columns:
            out["area"] = out["unique_name"]
        elif "label" in out.columns:
            out["area"] = out["label"]

    if "pier" not in out.columns:
        if "piername" in out.columns:
            out["pier"] = out["piername"]
        elif "pier_label" in out.columns:
            out["pier"] = out["pier_label"]

    return out


def _normalize_units_by_spec(df: pd.DataFrame, canonical: str) -> pd.DataFrame:
    out = df.copy()

    # Section sizes: 300, 600 are likely mm. Wall length may be >2m, so do not convert width_m for pier_sections blindly.
    section_size_cols = ["width_m", "depth_m", "thickness_m"]
    if canonical in {"frame_rect_sections", "column_rebar_defs", "beam_rebar_defs"}:
        for col in section_size_cols:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
                med = out[col].dropna().median()
                if pd.notna(med) and med > 2.0:
                    out[col] = out[col] * 0.001

    # Wall thickness can be mm; wall width/length should normally remain m if already 3-10m.
    if canonical == "pier_sections":
        for col in ["thickness_m"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
                med = out[col].dropna().median()
                if pd.notna(med) and med > 2.0:
                    out[col] = out[col] * 0.001
        for col in ["width_m", "length_m"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
                med = out[col].dropna().median()
                if pd.notna(med) and med > 100.0:
                    out[col] = out[col] * 0.001

    for col in ["height_m", "elevation_m", "station_m", "length_m", "x", "y", "z"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
            med = out[col].dropna().median()
            if pd.notna(med) and abs(med) > 100.0:
                out[col] = out[col] * 0.001

    for col in ["fx", "fy", "fz", "vx", "vy", "p_kn", "v2_kn", "v3_kn", "m2_knm", "m3_knm"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    for col in ["max_drift", "avg_drift", "ratio", "period", "sum_ux", "sum_uy", "sds", "sd1", "r", "d", "i", "fck_mpa", "fyk_mpa", "fywd_mpa", "gamma_c", "gamma_s"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    return out


def _validate_required(ctx: ModelContext, canonical: str, df: pd.DataFrame) -> None:
    spec = TABLE_CATALOG.get(canonical)
    if spec is None:
        return
    missing = [c for c in spec.required_cols if c not in df.columns]
    if not missing:
        return
    msg = f"[{canonical}] missing normalized columns: {missing}"
    if canonical in CRITICAL_TABLES:
        raise ValueError(msg)
    ctx.notes.setdefault("warnings", []).append(msg)


def _classify_combo_name(name: str) -> str:
    n = name.upper()
    if n.startswith("COMB_G"): return "G"
    if n.startswith("COMB_H"): return "H"
    if n.startswith("COMB_EQ") and n.endswith("_U"): return "EQ_UNC"
    if n.startswith("COMB_EQ") and n.endswith("_C"): return "EQ_CRK"
    if n.startswith("COMB_EH") and n.endswith("_U"): return "EH_UNC"
    if n.startswith("COMB_EH") and n.endswith("_C"): return "EH_CRK"
    if n.startswith("COMB_ED") and n.endswith("_U"): return "ED_UNC"
    if n.startswith("COMB_ED") and n.endswith("_C"): return "ED_CRK"
    if "_U" in n and (n.startswith("COMB_EX") or n.startswith("COMB_EY")): return "E_UNC"
    if "_C" in n and (n.startswith("COMB_EX") or n.startswith("COMB_EY")): return "E_CRK"
    if n.startswith("ENV"): return "ENV"
    if n.startswith("COMB_T") or n == "T": return "T"
    return "OTHER"


async def _read_canonical(
    ctx: ModelContext,
    canonical: str,
    case: Optional[str] = None,
    combo: Optional[str] = None,
    required: bool = False,
) -> Optional[pd.DataFrame]:
    if canonical in ctx.tables and not case and not combo:
        return ctx.tables[canonical]

    spec = TABLE_CATALOG.get(canonical)
    if spec is None:
        ctx.notes.setdefault("warnings", []).append(f"[{canonical}] not in catalog")
        return None

    available = ctx.notes.get("_available_tables")
    if available is None:
        if get_sap is None or get_available_tables is None:
            ctx.notes.setdefault("warnings", []).append("ETABS table service not configured.")
            return None
        sap = get_sap()
        available = get_available_tables(sap)
        ctx.notes["_available_tables"] = available

    etabs_name = resolve_etabs_name(canonical, available)
    if etabs_name is None:
        msg = f"[{canonical}] not found. Tried: {spec.etabs_names}"
        (ctx.notes.setdefault("warnings", []) if required else ctx.notes.setdefault("data_gaps", [])).append(msg)
        return None

    if get_table_df is None:
        ctx.notes.setdefault("warnings", []).append("get_table_df service not configured.")
        return None

    try:
        tr = await get_table_df(etabs_name, case=case, combo=combo, limit=None)
        if not getattr(tr, "ok", False):
            msg = f"[{canonical}] {etabs_name}: {getattr(tr, 'error', 'Unknown error')}"
            (ctx.notes.setdefault("warnings", []) if required else ctx.notes.setdefault("data_gaps", [])).append(msg)
            return None

        df0 = getattr(tr, "df", pd.DataFrame())
        if df0 is None or df0.empty:
            msg = f"[{canonical}] {etabs_name}: 0 rows"
            ctx.notes.setdefault("data_gaps", []).append(msg)
            return None

        df = _normalize_columns(df0)
        df = _normalize_units_by_spec(df, canonical)
        _validate_required(ctx, canonical, df)
        ctx.tables[canonical] = df

        ctx.notes.setdefault("tables_loaded", []).append({
            "canonical": canonical,
            "etabs_name": etabs_name,
            "rows": int(len(df)),
            "cols": list(df.columns),
            "source": "case" if case else ("combo" if combo else "none"),
        })
        return df

    except Exception as e:
        msg = f"[{canonical}] {etabs_name}: {e}"
        (ctx.notes.setdefault("warnings", []) if required else ctx.notes.setdefault("data_gaps", [])).append(msg)
        return None


async def _read_canonical_many(ctx: ModelContext, canonical: str, cases: List[str]) -> Optional[pd.DataFrame]:
    spec = TABLE_CATALOG.get(canonical)
    if spec is None:
        ctx.notes.setdefault("warnings", []).append(f"[{canonical}] not in catalog")
        return None

    available = ctx.notes.get("_available_tables")
    if available is None:
        if get_sap is None or get_available_tables is None:
            ctx.notes.setdefault("warnings", []).append("ETABS table service not configured.")
            return None
        sap = get_sap()
        available = get_available_tables(sap)
        ctx.notes["_available_tables"] = available

    etabs_name = resolve_etabs_name(canonical, available)
    if etabs_name is None:
        ctx.notes.setdefault("data_gaps", []).append(f"[{canonical}] not found: {spec.etabs_names}")
        return None

    unique_cases = list(dict.fromkeys([c for c in cases if c]))
    if not unique_cases:
        return None

    if get_many_case_tables is None:
        ctx.notes.setdefault("warnings", []).append("get_many_case_tables service not configured.")
        return None

    try:
        tr = await get_many_case_tables(etabs_name, unique_cases, limit=None)
        if not getattr(tr, "ok", False):
            ctx.notes.setdefault("data_gaps", []).append(f"[{canonical}] {getattr(tr, 'error', 'Unknown error')}")
            return None

        df0 = getattr(tr, "df", pd.DataFrame())
        if df0 is None or df0.empty:
            return None

        df = _normalize_columns(df0)
        df = _normalize_units_by_spec(df, canonical)
        _validate_required(ctx, canonical, df)
        ctx.tables[canonical] = df

        ctx.notes.setdefault("tables_loaded", []).append({
            "canonical": canonical,
            "etabs_name": etabs_name,
            "rows": int(len(df)),
            "cols": list(df.columns),
            "source": "many_cases",
            "cases": unique_cases,
        })
        return df

    except Exception as e:
        ctx.notes.setdefault("data_gaps", []).append(f"[{canonical}] {e}")
        return None


def _build_simple_envelope(df: pd.DataFrame, element_cols: List[str]) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    """
    Per-element force envelope with governing load case tracking.

    For each force component (P, V2, V3, M2, M3) the row with the largest
    absolute value is kept, and its output_case is stored as <COMP>_case.
    End-station moments (i/j) are tracked separately with their cases.
    """
    if df is None or df.empty:
        return pd.DataFrame(), {}

    lookup: Dict[str, Dict[str, Any]] = {}

    def row_element(row: pd.Series) -> str:
        for c in element_cols + ["unique_name", "label", "name"]:
            v = _as_str(row.get(c))
            if v:
                return v
        return ""

    for _, row in df.iterrows():
        el = row_element(row)
        if not el:
            continue
        data = lookup.setdefault(el, {"element": el})
        if _as_str(row.get("story")):
            data["story"] = _as_str(row.get("story"))

        case = _as_str(row.get("output_case"))

        # --- Global envelope: max |force| per component with governing case ---
        for col, prefix in [
            ("p_kn",   "P"),
            ("v2_kn",  "V2"),
            ("v3_kn",  "V3"),
            ("m2_knm", "M2"),
            ("m3_knm", "M3"),
        ]:
            val = _as_float(row.get(col))
            key_max  = f"{prefix}_max"
            key_case = f"{prefix}_case"
            if key_max not in data or abs(val) > abs(data[key_max]):
                data[key_max]  = val
                data[key_case] = case

        # --- End-station moments and shears (i = near end, j = far end) ---
        st = _as_float(row.get("station_m"))
        if st <= 1e-6:
            # i-end
            for col, prefix in [
                ("m2_knm", "M2_i"),
                ("m3_knm", "M3_i"),
                ("v2_kn",  "V2_i"),
                ("v3_kn",  "V3_i"),
            ]:
                val = _as_float(row.get(col))
                key_val  = prefix
                key_case = f"{prefix}_case"
                if key_val not in data or abs(val) > abs(data[key_val]):
                    data[key_val]  = val
                    data[key_case] = case
        else:
            # j-end
            for col, prefix in [
                ("m2_knm", "M2_j"),
                ("m3_knm", "M3_j"),
                ("v2_kn",  "V2_j"),
                ("v3_kn",  "V3_j"),
            ]:
                val = _as_float(row.get(col))
                key_val  = prefix
                key_case = f"{prefix}_case"
                if key_val not in data or abs(val) > abs(data[key_val]):
                    data[key_val]  = val
                    data[key_case] = case

    out_rows = list(lookup.values())
    return pd.DataFrame(out_rows), lookup


def _story_shear_envelope(df: pd.DataFrame, direction: str) -> Dict[str, float]:
    if df is None or df.empty:
        return {}
    col = "vx" if direction.upper() == "X" else "vy"
    if col not in df.columns:
        return {}
    env: Dict[str, float] = {}
    for _, row in df.iterrows():
        story = _as_str(row.get("story"))
        if not story:
            continue
        val = abs(_as_float(row.get(col)))
        env[story] = max(env.get(story, 0.0), val)
    return env


async def _load_story_data(ctx: ModelContext) -> None:
    df = await _read_canonical(ctx, "story_definitions", required=True)
    if df is None or df.empty:
        return
    for _, row in df.iterrows():
        s = _as_str(row.get("story") or row.get("name"))
        if not s:
            continue
        ctx.story_height_map[s] = _as_float(row.get("height_m"))
        if "elevation_m" in row:
            ctx.story_elevation_map[s] = _as_float(row.get("elevation_m"))
    if ctx.story_elevation_map:
        ctx.story_order = sorted(ctx.story_elevation_map, key=lambda s: ctx.story_elevation_map[s])
    else:
        ctx.story_order = list(ctx.story_height_map.keys())


async def _load_modal_data(ctx: ModelContext) -> None:
    df = await _read_canonical(ctx, "modal_mass")
    if df is not None and not df.empty:
        last = df.iloc[-1]
        ctx.modal.update({
            "n_modes": int(len(df)),
            "sum_ux": _as_float(last.get("sum_ux")),
            "sum_uy": _as_float(last.get("sum_uy")),
        })
    dfp = await _read_canonical(ctx, "modal_periods")
    if dfp is not None and not dfp.empty:
        ctx.modal["T1_sec"] = _as_float(dfp.iloc[0].get("period"))


async def _load_auto_seismic(ctx: ModelContext) -> None:
    df = await _read_canonical(ctx, "auto_seismic")
    if df is None or df.empty:
        return
    row = df.iloc[0]
    updates = {
        "SDS": _as_float(row.get("sds"), ctx.spectrum.get("SDS", 0.0)),
        "SD1": _as_float(row.get("sd1"), ctx.spectrum.get("SD1", 0.0)),
        "R": _as_float(row.get("r"), ctx.spectrum.get("R", 7.0)),
        "D": _as_float(row.get("d"), ctx.spectrum.get("D", 2.5)),
        "I": _as_float(row.get("i"), ctx.spectrum.get("I", 1.5)),
    }
    ctx.spectrum.update(updates)
    src = ctx.spectrum.setdefault("sources", {})
    for key in updates:
        src[key] = "ETABS:auto_seismic"

    # Faz 1: write ETABS-sourced values into design_basis with verified=True
    dbsrc = ctx.design_basis.setdefault("sources", {})
    dbver = ctx.design_basis.setdefault("verified", {})
    for key in ("SDS", "SD1", "R", "D", "I"):
        dbsrc[key] = "ETABS:auto_seismic"
        dbver[key] = True
        ctx.design_basis[key] = ctx.spectrum.get(key)

async def _load_design_basis_from_etabs(ctx: ModelContext) -> None:
    sources = ctx.design_basis.setdefault("sources", {})
    verified = ctx.design_basis.setdefault("verified", {})
    confidence = ctx.design_basis.setdefault("confidence", {})
    notes = ctx.design_basis.setdefault("notes", {})

    def set_db(
        key: str,
        value,
        source: str,
        is_verified: bool = True,
        conf: str = "HIGH",
        note: str = "",
    ):
        val = _as_float(value, None) if isinstance(value, (int, float, str)) else value
        if val is None or val == "":
            return
        ctx.design_basis[key] = val
        sources[key] = source
        verified[key] = bool(is_verified)
        confidence[key] = conf
        notes[key] = note or f"{key} set from {source}"

    def _norm_name(x) -> str:
        return str(x or "").strip()

    def _norm_key(x) -> str:
        return str(x or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")

    def _first_existing_value(row, cols):
        for col in cols:
            if col in row.index:
                v = row.get(col)
                if str(v).strip() not in {"", "nan", "None", "NONE"}:
                    return v
        return None

    # ---------------------------------------------------------------------
    # 1) Concrete material strength
    # ---------------------------------------------------------------------
    # ESKİ HATA:
    #   material_concrete tablosundaki ilk pozitif fck alınıyordu.
    #   Bu, modelde kullanılmayan C30/default material varsa yanlış sonuç üretir.
    #
    # YENİ KURAL:
    #   Sadece gerçekten atanmış frame/pier section materialları dikkate alınır.
    # ---------------------------------------------------------------------
    dfc = await _read_canonical(ctx, "material_concrete")

    if dfc is not None and not dfc.empty:
        used_materials_raw = set()

        # Frame section materialları
        for canonical in ("frame_rect_sections", "pier_sections"):
            df_sec = ctx.tables.get(canonical)

            # Eğer ilgili section tablosu henüz okunmadıysa okumayı dene.
            if df_sec is None or getattr(df_sec, "empty", True):
                try:
                    df_sec = await _read_canonical(ctx, canonical)
                except Exception:
                    df_sec = None

            if df_sec is None or getattr(df_sec, "empty", True):
                continue

            for col in ("material", "matprop", "mat", "concrete", "conc", "material_name"):
                if col in df_sec.columns:
                    used_materials_raw.update(
                        _norm_name(x)
                        for x in df_sec[col].dropna().tolist()
                        if _norm_name(x)
                    )

        used_material_keys = {_norm_key(x) for x in used_materials_raw if _norm_key(x)}

        material_fck = []

        for _, row in dfc.iterrows():
            mat_name = _first_existing_value(
                row,
                ("name", "material", "matprop", "material_name", "mat"),
            )
            mat_name = _norm_name(mat_name)
            mat_key = _norm_key(mat_name)

            # Eğer kullanılan material listesi varsa ve bu material kullanılmıyorsa geç.
            if used_material_keys and mat_key and mat_key not in used_material_keys:
                continue

            # Eğer kullanılan material listesi var ama material_concrete satırında isim yoksa
            # güvenilir eşleşme yapılamaz; geç.
            if used_material_keys and not mat_key:
                continue

            val = _as_float(row.get("fck_mpa"), 0.0)

            # Burada MPa normalize etmiyoruz; build sonunda normalize_design_basis_units
            # ham değeri MPa'ya çevirecek.
            if val > 0.0:
                material_fck.append(
                    {
                        "material": mat_name,
                        "fck_raw": val,
                        "source": "ETABS:material_concrete",
                    }
                )

        if material_fck:
            # Kullanılan betonlar içinde minimum dayanımı governing kabul et.
            governing = min(
                material_fck,
                key=lambda x: _as_float(x.get("fck_raw"), 0.0),
            )

            ctx.design_basis["concrete_materials_used"] = material_fck
            sources["concrete_materials_used"] = (
                "ETABS:frame_rect_sections/pier_sections + material_concrete"
            )
            verified["concrete_materials_used"] = True
            confidence["concrete_materials_used"] = "HIGH"
            notes["concrete_materials_used"] = (
                "Concrete material strengths filtered by actually assigned section materials."
            )

            ctx.design_basis["concrete_materials_assigned"] = sorted(used_materials_raw)
            sources["concrete_materials_assigned"] = "ETABS:frame_rect_sections/pier_sections"
            verified["concrete_materials_assigned"] = True
            confidence["concrete_materials_assigned"] = "HIGH"
            notes["concrete_materials_assigned"] = (
                "Concrete material names collected from actually assigned sections."
            )

            set_db(
                "fck_mpa",
                governing["fck_raw"],
                f"ETABS:material_concrete:{governing.get('material', '')}",
                True,
                "HIGH",
                "Governing concrete strength from actually assigned concrete material.",
            )

        else:
            # Eşleşen kullanılan beton bulunamazsa fck'yi material_concrete ilk satırdan çekme.
            # Template/user verification bekle.
            if used_materials_raw:
                notes["fck_mpa"] = (
                    "No matching assigned concrete material found in material_concrete. "
                    f"Assigned materials: {sorted(used_materials_raw)}"
                )
            else:
                notes["fck_mpa"] = (
                    "Assigned concrete material list could not be read from section tables. "
                    "fck_mpa requires user/material verification."
                )

            verified["fck_mpa"] = False
            confidence["fck_mpa"] = "LOW"

            ctx.design_basis["concrete_materials_assigned"] = sorted(used_materials_raw)
            sources["concrete_materials_assigned"] = "ETABS:frame_rect_sections/pier_sections"
            verified["concrete_materials_assigned"] = bool(used_materials_raw)
            confidence["concrete_materials_assigned"] = "MEDIUM" if used_materials_raw else "LOW"
            notes["concrete_materials_assigned"] = (
                "Concrete material names collected from assigned sections; no matching fck found."
            )

    # ---------------------------------------------------------------------
    # 2) Rebar / steel material strength from material_general
    # ---------------------------------------------------------------------
    dfg = await _read_canonical(ctx, "material_general")

    if dfg is not None and not dfg.empty:
        for _, row in dfg.iterrows():
            mat_type = str(row.get("type") or row.get("material_type") or "").lower()

            fyk_val = _as_float(row.get("fyk_mpa"), 0.0)
            if fyk_val <= 0.0:
                fyk_val = _as_float(row.get("fy"), 0.0)

            # Burada da nihai MPa normalize işlemi build sonunda yapılacak.
            if fyk_val > 0.0 and (
                "rebar" in mat_type
                or "steel" in mat_type
                or "rein" in mat_type
            ):
                set_db(
                    "fyk_mpa",
                    fyk_val,
                    "ETABS:material_general",
                    True,
                    "HIGH",
                    "Rebar yield strength verified from ETABS.",
                )
                break

    # ---------------------------------------------------------------------
    # 3) Concrete design preferences
    # ---------------------------------------------------------------------
    # Buradan gamma_c/gamma_s alınabilir.
    # fck_mpa burada override edilmez; prefs gerçek atanmış material property
    # olmayabilir.
    # ---------------------------------------------------------------------
    prefs = await _read_canonical(ctx, "conc_design_prefs")

    if prefs is not None and not prefs.empty:
        row = prefs.iloc[0]

        for key in ("gamma_c", "gamma_s"):
            val = _as_float(row.get(key), 0.0)
            if val > 0.0:
                set_db(
                    key,
                    val,
                    "ETABS:conc_design_prefs",
                    True,
                    "HIGH",
                    f"{key} verified from ETABS concrete design preferences.",
                )

        # fck_mpa burada kesinlikle override edilmiyor.
        # fyk/fywd prefs'ten okunursa verified=False / MEDIUM olarak tutulur.
        for key in ("fyk_mpa", "fywd_mpa"):
            val = _as_float(row.get(key), 0.0)

            if val > 0.0 and not verified.get(key):
                set_db(
                    key,
                    val,
                    "ETABS:conc_design_prefs",
                    False,
                    "MEDIUM",
                    (
                        f"{key} read from ETABS concrete design preferences; "
                        "verify material grade before DESIGN_LEVEL use."
                    ),
                )

    # ---------------------------------------------------------------------
    # 4) Rebar metadata names
    # ---------------------------------------------------------------------
    for canonical, target in (
        ("column_rebar_defs", "column_rebar_materials"),
        ("beam_rebar_defs", "beam_rebar_materials"),
    ):
        df = ctx.tables.get(canonical)

        if df is not None and not df.empty:
            mats = sorted(
                {
                    str(x).strip()
                    for col in ("rebarmatl", "rebarmatc", "material")
                    if col in df.columns
                    for x in df[col].dropna().tolist()
                    if str(x).strip()
                }
            )

            if mats:
                ctx.design_basis[target] = mats
                sources[target] = f"ETABS:{canonical}"
                verified[target] = True
                confidence[target] = "HIGH"
                notes[target] = (
                    f"Rebar material names collected from {canonical}; "
                    "this does not by itself verify fyk_mpa."
                )

    # ---------------------------------------------------------------------
    # 5) Derived steel design strengths
    # ---------------------------------------------------------------------
    fyk = _as_float(ctx.design_basis.get("fyk_mpa"), 0.0)
    gamma_s = _as_float(ctx.design_basis.get("gamma_s"), 1.15)

    fyk_ok = bool(verified.get("fyk_mpa"))
    gamma_s_ok = bool(verified.get("gamma_s"))

    if fyk > 0 and gamma_s > 0:
        ctx.design_basis["fyd_mpa"] = fyk / gamma_s
        sources["fyd_mpa"] = "derived:fyk_mpa/gamma_s"
        verified["fyd_mpa"] = fyk_ok and gamma_s_ok
        confidence["fyd_mpa"] = "HIGH" if verified["fyd_mpa"] else "LOW"
        notes["fyd_mpa"] = "Derived from fyk_mpa/gamma_s."

        if not verified.get("fywd_mpa"):
            ctx.design_basis["fywd_mpa"] = ctx.design_basis["fyd_mpa"]
            sources["fywd_mpa"] = "derived:fyd_mpa"
            verified["fywd_mpa"] = verified["fyd_mpa"]
            confidence["fywd_mpa"] = confidence["fyd_mpa"]
            notes["fywd_mpa"] = (
                "Derived from fyd_mpa because ETABS verified shear rebar yield was not found."
            )

    # ---------------------------------------------------------------------
    # 6) Derived concrete design strength
    # ---------------------------------------------------------------------
    fck = _as_float(ctx.design_basis.get("fck_mpa"), 0.0)
    gamma_c = _as_float(ctx.design_basis.get("gamma_c"), 1.5)

    fck_ok = bool(verified.get("fck_mpa"))
    gamma_c_ok = bool(verified.get("gamma_c"))

    if fck > 0 and gamma_c > 0:
        ctx.design_basis["fcd_mpa"] = fck / gamma_c
        sources["fcd_mpa"] = "derived:fck_mpa/gamma_c"
        verified["fcd_mpa"] = fck_ok and gamma_c_ok
        confidence["fcd_mpa"] = "HIGH" if verified["fcd_mpa"] else "LOW"
        notes["fcd_mpa"] = "Derived from fck_mpa/gamma_c."

async def _load_discovery(ctx: ModelContext) -> None:
    if discover_cases is not None:
        try:
            data = await discover_cases()
            if data and data.get("ok"):
                ctx.load_cases = data.get("classified", {}) or {}
        except Exception as e:
            ctx.notes.setdefault("warnings", []).append(f"discover_cases: {e}")

    if discover_combinations is not None:
        try:
            data = await discover_combinations()
            if data and data.get("ok"):
                ctx.combo_groups.update(data.get("groups", {}) or {})
                ctx.design_envelope = data.get("design_recommendation") or ctx.design_envelope
        except Exception as e:
            ctx.notes.setdefault("warnings", []).append(f"discover_combinations: {e}")

    # Fallback from normalized tables
    if not ctx.load_cases:
        rs = await _read_canonical(ctx, "rs_cases")
        lin = await _read_canonical(ctx, "linear_static_cases")
        classified: Dict[str, Any] = {}
        if rs is not None and not rs.empty:
            for _, r in rs.iterrows():
                name = _as_str(r.get("name") or r.get("output_case"))
                load = _as_str(r.get("load_name")).upper()
                upper = name.upper()
                if load == "U1" or "RSX" in upper or upper.endswith("EX"):
                    key = "rs_x"
                elif load == "U2" or "RSY" in upper or upper.endswith("EY"):
                    key = "rs_y"
                else:
                    continue
                entry = classified.setdefault(key, {})
                if "P" in upper or "XP" in upper or "YP" in upper:
                    entry["plus"] = name
                elif "N" in upper or "XN" in upper or "YN" in upper:
                    entry["minus"] = name
                else:
                    entry.setdefault("primary", name)
        if lin is not None and not lin.empty:
            for _, r in lin.iterrows():
                name = _as_str(r.get("name") or r.get("output_case"))
                up = name.upper()
                if "EQX" in up:
                    classified["eq_x"] = name
                elif "EQY" in up:
                    classified["eq_y"] = name
        ctx.load_cases = classified


async def _load_combo_context(ctx: ModelContext) -> None:
    df = await _read_canonical(ctx, "load_combos")
    if df is None or df.empty:
        return
    name_col = "name" if "name" in df.columns else ("combo_name" if "combo_name" in df.columns else df.columns[0])
    groups: Dict[str, List[str]] = {}
    for name in df[name_col].dropna().unique():
        n = _as_str(name)
        if not n:
            continue
        groups.setdefault(_classify_combo_name(n), []).append(n)
    ctx.combo_groups.update(groups)
    ctx.design_envelope = (
        next((c for c in groups.get("ENV", []) if "ENV" in c.upper()), None)
        or next(iter(groups.get("E_CRK", []) or groups.get("E_UNC", []) or []), None)
        or ctx.design_envelope
    )


async def _load_base_reactions(ctx: ModelContext) -> None:
    rs_x = (ctx.load_cases.get("rs_x", {}) or {}).get("primary")
    rs_y = (ctx.load_cases.get("rs_y", {}) or {}).get("primary")
    eq_x = ctx.load_cases.get("eq_x")
    eq_y = ctx.load_cases.get("eq_y")
    for case_name, direction in [(rs_x, "X"), (rs_y, "Y"), (eq_x, "X"), (eq_y, "Y")]:
        if not case_name:
            continue
        df = await _read_canonical(ctx, "base_reactions", case=case_name)
        if df is None or df.empty:
            continue
        force_col = "fx" if direction == "X" else "fy"
        if force_col not in df.columns:
            continue
        vt = df[force_col].abs().max()
        key = f"beta_{direction.lower()}"
        ctx.base_reactions.setdefault(key, {})
        is_rs = case_name in [rs_x, rs_y]
        field = "vt_rs" if is_rs else "vt_eq"
        ctx.base_reactions[key][field] = round(float(vt), 2)
        ctx.base_reactions[key][f"{field}_case"] = case_name


async def _load_topology(ctx: ModelContext) -> None:
    df_f = await _read_canonical(ctx, "frame_objects")
    df_j = await _read_canonical(ctx, "joint_objects")
    df_cc = await _read_canonical(ctx, "column_connectivity")
    df_bc = await _read_canonical(ctx, "beam_connectivity")
    df_as = await _read_canonical(ctx, "frame_assigns_section")
    df_rs = await _read_canonical(ctx, "frame_rect_sections")
    df_prop = await _read_canonical(ctx, "frame_prop_summary")

    # Always build section dims from sections even if topology fails.
    if df_rs is not None and not df_rs.empty:
        for _, row in df_rs.iterrows():
            name = _as_str(row.get("name") or row.get("section"))
            if not name:
                continue
            w = _as_float(row.get("width_m"))
            d = _as_float(row.get("depth_m"))
            if w > 0 and d > 0:
                ctx.geometry.setdefault("section_dims", {})[name] = {
                    "width_m": w,
                    "depth_m": d,
                    "b_min_m": min(w, d),
                    "b_max_m": max(w, d),
                }

    if df_prop is not None and not df_prop.empty:
        for _, row in df_prop.iterrows():
            name = _as_str(row.get("name") or row.get("section"))
            area = _as_float(row.get("area_m2"))
            if name and area > 0:
                ctx.geometry.setdefault("section_areas", {})[name] = area

    if df_as is not None and not df_as.empty:
        for _, row in df_as.iterrows():
            label = _as_str(row.get("label") or row.get("unique_name") or row.get("name"))
            section = _as_str(row.get("section") or row.get("property"))
            if label and section:
                ctx.geometry.setdefault("frame_sections", {})[label] = section

    frame_rows = []
    for src in [df_f, df_cc, df_bc]:
        if src is not None and not src.empty:
            frame_rows.extend(src.to_dict(orient="records"))
    joint_rows = df_j.to_dict(orient="records") if df_j is not None and not df_j.empty else []
    assign_rows = df_as.to_dict(orient="records") if df_as is not None and not df_as.empty else []

    if build_topology is not None and frame_rows and joint_rows:
        try:
            topo = build_topology(frame_rows, joint_rows, assign_rows)
            aj = get_analysis_joints(topo) if get_analysis_joints else []
            cm = recompute_confinement_for_analysis(topo) if recompute_confinement_for_analysis else {}
            for a in aj:
                a["confinement"] = cm.get(a.get("joint_name"), "UNKNOWN")
            ctx.topology = {
                "columns": [{"label": c.label, "story": c.story, "section": c.section} for c in getattr(topo, "columns", [])],
                "beams": [{"label": b.label, "story": b.story, "section": b.section} for b in getattr(topo, "beams", [])],
                "joints_total": len(getattr(topo, "joints", [])),
                "analysis_joints": aj,
                "column_beam_map": get_column_beam_mapping_summary(topo) if get_column_beam_mapping_summary else [],
                "confinement_map": cm,
                "warnings": getattr(topo, "warnings", [])[:50],
                "summary": getattr(topo, "summary", {}),
            }
            ctx.geometry["column_sections"] = {c["label"]: c["section"] for c in ctx.topology.get("columns", [])}
            ctx.geometry["beam_sections"] = {b["label"]: b["section"] for b in ctx.topology.get("beams", [])}
            return
        except Exception as e:
            ctx.notes.setdefault("warnings", []).append(f"Topology: {e}")

    # Fallback topology from connectivity/section assignment.
    columns = []
    if df_cc is not None and not df_cc.empty:
        for _, row in df_cc.iterrows():
            label = _as_str(row.get("unique_name") or row.get("label") or row.get("name"))
            sec = ctx.geometry.get("frame_sections", {}).get(label, "")
            columns.append({"label": label, "story": _as_str(row.get("story")), "section": sec, "length_m": _as_float(row.get("length_m"))})
    beams = []
    if df_bc is not None and not df_bc.empty:
        for _, row in df_bc.iterrows():
            label = _as_str(row.get("unique_name") or row.get("label") or row.get("name"))
            sec = ctx.geometry.get("frame_sections", {}).get(label, "")
            beams.append({"label": label, "story": _as_str(row.get("story")), "section": sec, "length_m": _as_float(row.get("length_m"))})
    ctx.topology = {
        "columns": columns,
        "beams": beams,
        "analysis_joints": [],
        "column_beam_map": [],
        "warnings": ["Fallback topology used. Joint-level checks may be limited."],
        "summary": {"fallback": True},
    }
    ctx.geometry["column_sections"] = {c["label"]: c["section"] for c in columns if c.get("label")}
    ctx.geometry["beam_sections"] = {b["label"]: b["section"] for b in beams if b.get("label")}


def _collect_rs_cases(ctx: ModelContext) -> list[str]:
    df = ctx.tables.get("rs_cases")

    if df is None or getattr(df, "empty", True):
        return []

    cases = []

    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if not name:
            continue

        u = name.upper()

        # Response spectrum / earthquake-like cases
        if any(tag in u for tag in ["RSX", "RSY", "EQX", "EQY", "EX", "EY"]):
            cases.append(name)

    # unique, stable order
    seen = set()
    out = []
    for c in cases:
        if c not in seen:
            seen.add(c)
            out.append(c)

    return out


async def _load_force_envelopes(ctx: ModelContext) -> None:
    rs_cases = _collect_rs_cases(ctx)

    if not rs_cases:
        ctx.notes.setdefault("data_gaps", []).append("No RS cases for force envelope.")
        return

    # =========================
    # COLUMN FORCES
    # =========================
    col_df = await _read_canonical_many(ctx, "column_forces", rs_cases)

    if col_df is not None and not col_df.empty:
        df_env, lookup = _build_simple_envelope(col_df, ["column"])

        ctx.column_forces_df = df_env
        ctx.envelopes[EnvKeys.COLUMN_FORCES] = df_env
        ctx.envelopes[EnvKeys.COLUMN_FORCES_MAP] = lookup

        ctx.envelopes["column_casewise_forces"] = build_casewise_frame_end_forces(
            col_df,
            member_col="column",
        )
    else:
        ctx.notes.setdefault("data_gaps", []).append("No column force table for RS cases.")

    # =========================
    # BEAM FORCES
    # =========================
    beam_df = await _read_canonical_many(ctx, "beam_forces", rs_cases)

    if beam_df is not None and not beam_df.empty:
        df_env, lookup = _build_simple_envelope(beam_df, ["beam"])

        ctx.beam_forces_df = df_env
        ctx.envelopes[EnvKeys.BEAM_FORCES] = df_env
        ctx.envelopes[EnvKeys.BEAM_FORCES_MAP] = lookup

        ctx.envelopes["beam_casewise_forces"] = build_casewise_frame_end_forces(
            beam_df,
            member_col="beam",
        )
    else:
        ctx.notes.setdefault("data_gaps", []).append("No beam force table for RS cases.")

    # =========================
    # STORY FORCES
    # =========================
    story_df = await _read_canonical_many(ctx, "story_forces", rs_cases)

    if story_df is not None and not story_df.empty:
        ctx.envelopes[EnvKeys.STORY_SHEAR_X] = _story_shear_envelope(story_df, "X")
        ctx.envelopes[EnvKeys.STORY_SHEAR_Y] = _story_shear_envelope(story_df, "Y")

    # =========================
    # STORY DRIFTS
    # =========================
    # =========================
    # STORY DRIFTS
    # =========================
    drift_df = None

    if rs_cases:
        drift_df = await _read_canonical_many(ctx, "story_drifts", rs_cases)

    # Fallback: case-filtered okuma boş geldiyse tüm story_drifts tablosunu oku.
    if drift_df is None or getattr(drift_df, "empty", True):
        try:
            drift_df = await _read_canonical(ctx, "story_drifts")
        except Exception as e:
            ctx.notes.setdefault("warnings", []).append(
                f"story_drifts fallback read failed: {e}"
            )
            drift_df = None

    if drift_df is not None and not drift_df.empty:
        ctx.tables["story_drifts"] = drift_df
    else:
        ctx.notes.setdefault("data_gaps", []).append(
            "story_drifts could not be loaded by case-filtered or fallback read."
        )


async def _load_rebar_metadata(ctx: ModelContext) -> None:
    """
    Donatı metadata + ETABS concrete design summary tablolarını yükler.

    Kritik not:
    Bazı ETABS koşularında design summary tabloları ilk okumada boş / bulunamadı
    dönebiliyor. Bu yüzden burada:
      1. normal canonical read
      2. ctx.tables içinde varsa onu kullan
      3. eksik kalan kritik design tablolarını data_gaps'a açık yaz
    yapıyoruz.
    """

    canonical_list = [
        "column_rebar_defs",
        "beam_rebar_defs",
        "column_design_overwrites",
        "beam_design_overwrites",
        "conc_design_combos",
        "column_design_summary",
        "beam_design_summary",
        "scwb_design",
        "joint_shear_design",
    ]

    critical_design_tables = {
        "column_design_summary",
        "beam_design_summary",
        "joint_shear_design",
    }

    for c in canonical_list:
        df = None

        # 1) Önce normal canonical okuma
        try:
            df = await _read_canonical(ctx, c)
        except Exception as e:
            ctx.notes.setdefault("warnings", []).append(
                f"[{c}] design metadata read failed: {e}"
            )
            df = None

        # 2) Eğer tablo daha önce ctx.tables içine gelmişse onu kullan
        if (df is None or getattr(df, "empty", True)) and c in ctx.tables:
            df = ctx.tables.get(c)

        # 3) Başarılıysa iki yere de kaydet
        if df is not None and not getattr(df, "empty", True):
            ctx.design_metadata[c] = df
            ctx.tables[c] = df
            continue

        # 4) Kritik design summary eksikse açık data gap yaz
        if c in critical_design_tables:
            ctx.notes.setdefault("data_gaps", []).append(
                f"[{c}] ETABS design summary table missing or empty. "
                f"Related checks may fall back to NO_DATA or screening."
            )


async def _load_wall_data(ctx: ModelContext) -> None:
    df_sec = await _read_canonical(ctx, "pier_sections")
    if df_sec is not None and not df_sec.empty:
        for _, row in df_sec.iterrows():
            pier = _as_str(row.get("pier") or row.get("name"))
            if not pier:
                continue
            length = _as_float(row.get("width_m") or row.get("length_m"), 3.0)
            thk = _as_float(row.get("thickness_m"), 0.25)
            area = _as_float(row.get("area_m2"), length * thk)
            ctx.geometry.setdefault("wall_sections", {})[pier] = {
                "length_m": length,
                "thickness_m": thk,
                "area_m2": area,
            }

    rs_cases = _collect_rs_cases(ctx)
    if rs_cases:
        pier_df = await _read_canonical_many(ctx, "pier_forces", rs_cases)
        if pier_df is not None and not pier_df.empty:
            df_env, lookup = _build_simple_envelope(pier_df, ["pier"])
            ctx.pier_forces_df = df_env
            ctx.envelopes[EnvKeys.PIER_FORCES] = df_env
            ctx.envelopes[EnvKeys.PIER_FORCES_MAP] = lookup

    for c in [
        "area_pier_labels",
        "area_section_assigns",
        "area_objects",
        "wall_design_combos",
        "wall_design_prefs",
        "wall_design_summary",
    ]:
        df = None

        try:
            df = await _read_canonical(ctx, c)
        except Exception as e:
            ctx.notes.setdefault("warnings", []).append(
                f"[{c}] wall data read failed: {e}"
            )
            df = None

        if (df is None or getattr(df, "empty", True)) and c in ctx.tables:
            df = ctx.tables.get(c)

        if df is not None and not getattr(df, "empty", True):
            ctx.design_metadata[c] = df
            ctx.tables[c] = df
        elif c == "wall_design_summary":
            ctx.notes.setdefault("data_gaps", []).append(
                "[wall_design_summary] ETABS wall design summary missing or empty."
            )


def _stamp_template_sources(ctx: ModelContext) -> None:
    sources = ctx.design_basis.setdefault("sources", {})
    verified = ctx.design_basis.setdefault("verified", {})
    confidence = ctx.design_basis.setdefault("confidence", {})
    notes = ctx.design_basis.setdefault("notes", {})

    skip = {"sources", "verified", "confidence", "notes"}

    for key, val in ctx.design_basis.items():
        if key in skip:
            continue
        if isinstance(val, (dict, list)):
            continue

        sources.setdefault(key, TEMPLATE_SOURCE)
        verified.setdefault(key, False)
        confidence.setdefault(key, "LOW")
        notes.setdefault(key, "Template fallback; requires ETABS/user verification")


def _dm_has(ctx: ModelContext, key: str) -> bool:
    """design_metadata[key] var ve boş değil mi?"""
    df = ctx.design_metadata.get(key)
    return df is not None and not getattr(df, "empty", True)


def _env_has(ctx: ModelContext, key: str) -> bool:
    """envelopes[key] var ve içi dolu mu?"""
    val = ctx.envelopes.get(key)
    if val is None:
        return False
    if isinstance(val, dict):
        return len(val) > 0
    if hasattr(val, "empty"):
        return not val.empty
    return bool(val)


def _topo_has(ctx: ModelContext, key: str) -> bool:
    """topology[key] listesi var ve boş değil mi?"""
    val = ctx.topology.get(key)
    if val is None:
        return False
    if isinstance(val, (list, dict)):
        return len(val) > 0
    return bool(val)


def _geom_has(ctx: ModelContext, key: str) -> bool:
    val = ctx.geometry.get(key)
    return bool(val)


def _build_flags(ctx: ModelContext) -> Dict[str, Any]:
    verified = ctx.design_basis.get("verified", {})

    has_concrete = bool(
        verified.get("fck_mpa") and
        verified.get("gamma_c")
    )

    has_rebar = bool(
        verified.get("fyk_mpa") and
        verified.get("gamma_s")
    )

    materials_verified = has_concrete and has_rebar

    critical_material_keys = (
        "fck_mpa",
        "fyk_mpa",
        "gamma_c",
        "gamma_s",
        "fcd_mpa",
        "fyd_mpa",
        "fywd_mpa",
    )

    critical_unverified = [
        k for k in critical_material_keys
        if not verified.get(k)
    ]

    return {
        "has_column_design_summary": _dm_has(ctx, "column_design_summary"),
        "has_beam_design_summary":   _dm_has(ctx, "beam_design_summary"),
        "has_joint_shear_design":    _dm_has(ctx, "joint_shear_design"),
        "has_wall_design_summary":   _dm_has(ctx, "wall_design_summary"),
        "has_scwb_design":           _dm_has(ctx, "scwb_design"),

        "materials_verified": materials_verified,
        "concrete_verified": has_concrete,
        "rebar_verified": has_rebar,
        "critical_unverified_materials": critical_unverified,
    }

# Capability seviye sabitleri — EvaluationLevel ile hizalı
_CAP_ETABS   = "ETABS_DESIGN_RESULT"
_CAP_DESIGN  = "DESIGN_LEVEL"
_CAP_APPROX  = "APPROXIMATE"
_CAP_SCREEN  = "SCREENING"
_CAP_NO_DATA = "NO_DATA"


def _build_seismic_summary(ctx: ModelContext) -> None:
    auto = ctx.tables.get("auto_seismic")
    base = ctx.tables.get("base_reactions")

    ctx.seismic = getattr(ctx, "seismic", {}) or {}

    if auto is None or auto.empty or base is None or base.empty:
        ctx.notes.setdefault("data_gaps", []).append({
            "key": "seismic_summary",
            "reason": "auto_seismic or base_reactions missing",
        })
        return

    try:
        auto_row = auto.iloc[0]

        sds = _as_float(auto_row.get("sds"), 0.0)
        r = _as_float(auto_row.get("r"), 0.0)
        i = _as_float(auto_row.get("i"), 0.0)
        weight_used = _as_float(auto_row.get("weightused"), 0.0)
        auto_base_shear = abs(_as_float(auto_row.get("baseshear"), 0.0))

        fx_vals = []
        fy_vals = []

        if "fx" in base.columns:
            fx_vals = [abs(_as_float(v, 0.0)) for v in base["fx"].tolist()]
        if "fy" in base.columns:
            fy_vals = [abs(_as_float(v, 0.0)) for v in base["fy"].tolist()]

        vx = max(fx_vals) if fx_vals else 0.0
        vy = max(fy_vals) if fy_vals else 0.0

        denom = auto_base_shear if auto_base_shear > 0 else 0.0

        beta_x = vx / denom if denom > 0 else 0.0
        beta_y = vy / denom if denom > 0 else 0.0

        ctx.seismic.update({
            "SDS": sds,
            "R": r,
            "I": i,
            "weight_used_kn": weight_used,
            "auto_base_shear_kn": auto_base_shear,
            "base_shear_x_kn": vx,
            "base_shear_y_kn": vy,
            "beta_x": beta_x,
            "beta_y": beta_y,
            "beta_min": _as_float(ctx.design_basis.get("beta_min"), 0.90),
            "source": "ETABS:auto_seismic+base_reactions",
        })

        ctx.notes["seismic_summary"] = ctx.seismic

    except Exception as e:
        ctx.notes.setdefault("warnings", []).append(f"seismic_summary build failed: {e}")


def _build_capabilities(ctx: ModelContext) -> Dict[str, str]:
    """
    Faz 1: Her check için build time'da mevcut veri durumuna göre
    beklenen execution level hesaplanır.

    Kurallar:
      ETABS_DESIGN_RESULT : ETABS design summary tablosu mevcut.
      DESIGN_LEVEL        : Bağımsız formül + doğrulanmış malzeme/donatı verisi.
      APPROXIMATE         : Kısmi veri; fallback hesap yapılabilir.
      SCREENING           : Yalnızca geometri/kuvvet zarfı.
      NO_DATA             : Minimum veri bile yok.

    NOT: Bu capability map runner tarafından okunabilir ama runner'ı
    BAĞLAMAZ; bağımsız dependency modeli her zaman önceliklidir.
    """
    flags       = ctx.flags
    has_col_ds  = flags.get("has_column_design_summary", False)
    has_beam_ds = flags.get("has_beam_design_summary",   False)
    has_jsd     = flags.get("has_joint_shear_design",    False)
    has_scwb    = flags.get("has_scwb_design",           False)
    mat_ok      = flags.get("materials_verified",        False)

    has_col_forces   = _env_has(ctx, EnvKeys.COLUMN_FORCES_MAP)
    has_beam_forces  = _env_has(ctx, EnvKeys.BEAM_FORCES_MAP)
    has_section_dims = _geom_has(ctx, "section_dims")
    has_col_sections = _geom_has(ctx, "column_sections")
    has_beam_sections= _geom_has(ctx, "beam_sections")
    has_col_rebar    = _dm_has(ctx, "column_rebar_defs")
    has_joints       = _topo_has(ctx, "analysis_joints")
    has_col_beam_map = _topo_has(ctx, "column_beam_map")
    has_col_casewise = _env_has(ctx, "column_casewise_forces")
    has_beam_casewise= _env_has(ctx, "beam_casewise_forces")

    caps: Dict[str, str] = {}

    # column_axial
    if has_col_ds:
        caps["column_axial"] = _CAP_ETABS
    elif has_col_forces and has_section_dims:
        caps["column_axial"] = _CAP_SCREEN
    else:
        caps["column_axial"] = _CAP_NO_DATA

    # column_shear
    if has_col_ds:
        caps["column_shear"] = _CAP_ETABS
    elif has_col_forces and has_col_sections and has_section_dims:
        caps["column_shear"] = _CAP_SCREEN
    else:
        caps["column_shear"] = _CAP_NO_DATA

    # beam_shear
    if has_beam_ds:
        caps["beam_shear"] = _CAP_ETABS
    elif has_beam_forces and has_beam_sections and has_section_dims:
        caps["beam_shear"] = _CAP_SCREEN
    else:
        caps["beam_shear"] = _CAP_NO_DATA

    # beam_flexure
    if has_beam_ds:
        caps["beam_flexure"] = _CAP_ETABS
    else:
        caps["beam_flexure"] = _CAP_NO_DATA

    # joint_shear
    if has_jsd:
        caps["joint_shear"] = _CAP_ETABS
    elif has_joints and has_col_beam_map:
        caps["joint_shear"] = _CAP_SCREEN
    else:
        caps["joint_shear"] = _CAP_NO_DATA

    # scwb
    if has_scwb:
        caps["scwb"] = _CAP_ETABS
    elif has_col_beam_map and has_col_casewise and has_beam_casewise:
        caps["scwb"] = _CAP_APPROX
    else:
        caps["scwb"] = _CAP_NO_DATA

    # column_confinement
    if has_col_rebar and mat_ok:
        caps["column_confinement"] = _CAP_DESIGN
    elif has_col_rebar:
        caps["column_confinement"] = _CAP_SCREEN
    else:
        caps["column_confinement"] = _CAP_NO_DATA

    return caps


def get_available_checks(ctx: ModelContext) -> Dict[str, bool]:
    requirements = {
        "modal": ["modal_mass"],
        "beta_x": ["base_reactions", "auto_seismic"],
        "beta_y": ["base_reactions", "auto_seismic"],
        "drift": ["story_definitions", "story_drifts"],
        "torsion": ["story_drifts"],
        "soft_story": ["story_definitions", "story_drifts"],
        "building_height_class": ["story_definitions"],
        "column_dimensions": ["frame_rect_sections"],
        "beam_dimensions": ["frame_rect_sections"],
        "column_axial": ["column_forces", "frame_rect_sections"],
        "column_shear": ["column_forces", "frame_rect_sections"],
        "column_confinement": ["column_rebar_defs", "frame_rect_sections"],
        "wall_shear": ["pier_forces", "pier_sections"],
        "wall_design_forces": ["pier_forces"],
    }
    available = set(ctx.tables.keys())
    return {check: all(t in available for t in reqs) for check, reqs in requirements.items()}

async def build_model_context() -> ModelContext:
    ctx = ModelContext()

    # ETABS SAP modelini bir kere almaya çalış.
    # Bu nesne hem unit context hem metadata için kullanılabilir.
    try:
        sap_model = get_sap() if get_sap else None
    except Exception:
        sap_model = None

    ctx.notes["build_started"] = datetime.now().isoformat()
    ctx.notes.setdefault("warnings", [])
    ctx.notes.setdefault("data_gaps", [])
    ctx.notes.setdefault("tables_loaded", [])

    if sap_model is not None and get_available_tables is not None:
        try:
            sap = sap_model
            ctx.notes["_sap"] = sap
            ctx.notes["_available_tables"] = get_available_tables(sap)

            try:
                def _etabs_meta_string(ret):
                    if isinstance(ret, str):
                        return ret.strip() or "unknown"
                    if isinstance(ret, (list, tuple)):
                        for item in ret:
                            if isinstance(item, str) and item.strip():
                                return item.strip()
                        return str(ret)
                    return str(ret) if ret is not None else "unknown"

                etabs_version = _etabs_meta_string(sap.GetVersion())
                model_path = _etabs_meta_string(sap.GetModelFilename())

                ctx.notes["etabs_version"] = etabs_version
                ctx.notes["model_path"] = model_path
                ctx.project_info["etabs_version"] = etabs_version
                ctx.project_info["model_path"] = model_path

            except Exception as meta_error:
                ctx.notes["warnings"].append(f"ETABS metadata read failed: {meta_error}")

        except Exception as e:
            ctx.notes["warnings"].append(f"ETABS cache failed: {e}")

    # Design basis starts from template; all keys marked unverified.
    # ETABS loaders below will override individual keys and set verified=True.
    ctx.design_basis = template_design_basis()
    ctx.spectrum = template_spectrum()
    ctx.notes["design_basis_template_source"] = TEMPLATE_SOURCE

    # Unit policy burada bağlanmalı; çünkü design_basis artık mevcut.
    # ETABS present units hedefi: kN, m, MPa policy.
    if attach_unit_context:
        try:
            attach_unit_context(ctx, sap_model, set_units=True)
        except Exception as unit_error:
            ctx.notes["warnings"].append(f"Unit context attach failed: {unit_error}")

    # Faz 1: stamp every template-sourced key as unverified so reports can
    # distinguish template defaults from ETABS-confirmed values.
    _stamp_template_sources(ctx)

    ctx.project_info["name"] = "ETABS Model"

    await _load_story_data(ctx)
    await _load_modal_data(ctx)
    await _load_auto_seismic(ctx)
    await _load_discovery(ctx)
    await _load_combo_context(ctx)
    await _load_base_reactions(ctx)
    await _load_topology(ctx)
    await _load_force_envelopes(ctx)
    await _load_rebar_metadata(ctx)
    _merge_beam_design_envelope_semantics(ctx)
    await _load_design_basis_from_etabs(ctx)
    await _load_wall_data(ctx)
    await _read_canonical(ctx, "area_load_uniform")
    await _read_canonical(ctx, "area_load_nonuniform")

    _build_seismic_summary(ctx)

    # --- USER VERIFIED OVERRIDE (geçici) ---
    sources = ctx.design_basis.setdefault("sources", {})
    verified = ctx.design_basis.setdefault("verified", {})
    confidence = ctx.design_basis.setdefault("confidence", {})
    notes = ctx.design_basis.setdefault("notes", {})

    ctx.design_basis["fyk_mpa"] = 500.0
    sources["fyk_mpa"] = "USER_VERIFIED"
    verified["fyk_mpa"] = True
    confidence["fyk_mpa"] = "HIGH"
    notes["fyk_mpa"] = "User verified rebar yield strength (manual override)"

    # Unit policy ve MPa normalize işlemini EN SON tekrar uygula.
    # Çünkü _load_design_basis_from_etabs fck_mpa gibi değerleri 0.03 / 35000 / 35 şeklinde yazabilir.
    if attach_unit_context:
        try:
            attach_unit_context(ctx, sap_model, set_units=False)
        except Exception as unit_error:
            ctx.notes["warnings"].append(f"Final unit context attach failed: {unit_error}")

    if normalize_design_basis_units:
        try:
            normalize_design_basis_units(ctx)
        except Exception as unit_norm_error:
            ctx.notes["warnings"].append(f"Final design basis unit normalization failed: {unit_norm_error}")

    ctx.notes["available_checks"] = get_available_checks(ctx)
    ctx.notes["build_finished"] = datetime.now().isoformat()

    # --- Faz 1: flags ---
    ctx.flags = _build_flags(ctx)

    # --- Faz 1: capabilities ---
    ctx.capabilities = _build_capabilities(ctx)

    # --- Extended summary ---
    col_env = ctx.envelopes.get(EnvKeys.COLUMN_FORCES_MAP, {})
    beam_env = ctx.envelopes.get(EnvKeys.BEAM_FORCES_MAP, {})
    verified_dict = ctx.design_basis.get("verified", {})
    unverified_keys = [k for k, v in verified_dict.items() if not v]

    ctx.notes["summary"] = {
        "stories": len(ctx.story_order),
        "columns": len(ctx.topology.get("columns", [])),
        "beams": len(ctx.topology.get("beams", [])),
        "analysis_joints": len(ctx.topology.get("analysis_joints", [])),
        "walls": len(ctx.geometry.get("wall_sections", {})),
        "canonical_tables_loaded": len(ctx.tables),
        "tables_loaded_detail": ctx.notes.get("tables_loaded", []),
        "data_gaps": len(ctx.notes.get("data_gaps", [])),
        "warnings": len(ctx.notes.get("warnings", [])),
        # Faz 1 additions
        "envelope_column_count": len(col_env),
        "envelope_beam_count": len(beam_env),
        "capability_count": len(ctx.capabilities),
        "materials_verified": ctx.flags.get("materials_verified", False),
        "design_basis_unverified_keys": unverified_keys,
    }

    return ctx
