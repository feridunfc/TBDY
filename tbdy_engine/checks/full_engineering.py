# app/checks/full_engineering.py
"""
V20 full engineering checks — ModelContext-only execution.

Rules:
- Raw ETABS table access is avoided except validated design_metadata/story drift data already normalized in ModelContext.
- Main sources: ctx.capabilities, ctx.flags, ctx.envelopes, ctx.geometry, ctx.topology,
  ctx.design_basis, ctx.design_metadata.
- ETABS design summary -> ETABS_DESIGN_RESULT, never DESIGN_LEVEL.
- DESIGN_LEVEL only when independent formula inputs and verified materials/detail data exist.
- Missing data -> NO_DATA, never FAIL.
- Simplified / approximate calculations must expose assumptions and require engineer review.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from tbdy_engine.engine.context_builder import ModelContext

MAX_ITEMS = 500

def ensure_unit_layer(ctx):
    """
    Backward compatibility shim.
    Units are normalized in context_builder.
    Kept because registry.py imports it.
    """
    return ctx

# =============================================================================
# Safe access helpers
# =============================================================================

import math

def _safe_float(x, default=0.0):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _empty_df(df: Any) -> bool:
    if df is None:
        return True
    if hasattr(df, "empty"):
        return bool(df.empty)
    return False


def _dm_get(ctx: ModelContext, key: str) -> Any:
    return getattr(ctx, "design_metadata", {}).get(key)


def _cap(ctx: ModelContext, check: str) -> str:
    return getattr(ctx, "capabilities", {}).get(check, "NO_DATA")


def _flag(ctx: ModelContext, key: str, default: bool = False) -> bool:
    return bool(getattr(ctx, "flags", {}).get(key, default))


def _env_map(ctx: ModelContext, key: str) -> Dict[str, Any]:
    val = getattr(ctx, "envelopes", {}).get(key, {})
    return val if isinstance(val, dict) else {}


def _geom_sections(ctx: ModelContext, kind: str) -> Dict[str, str]:
    return getattr(ctx, "geometry", {}).get(f"{kind}_sections", {}) or {}


def _section_dims(ctx: ModelContext, section: str) -> Dict[str, float]:
    if not section:
        return {}
    return getattr(ctx, "geometry", {}).get("section_dims", {}).get(section, {}) or {}


def _topo_analysis_joints(ctx: ModelContext) -> List[Dict[str, Any]]:
    return getattr(ctx, "topology", {}).get("analysis_joints", []) or []


def _topo_column_beam_map(ctx: ModelContext) -> List[Dict[str, Any]]:
    return getattr(ctx, "topology", {}).get("column_beam_map", []) or []


def _basis_val(ctx: ModelContext, key: str, default: float = 0.0) -> float:
    return _safe_float(getattr(ctx, "design_basis", {}).get(key), default)


def _basis_verified(ctx: ModelContext, key: str) -> bool:
    return bool(getattr(ctx, "design_basis", {}).get("verified", {}).get(key, False))


def _basis_source(ctx: ModelContext, key: str) -> str:
    return _safe_str(getattr(ctx, "design_basis", {}).get("sources", {}).get(key), "")


def _materials_verified(ctx: ModelContext) -> bool:
    return bool(_flag(ctx, "materials_verified"))


def _etabs_status_kind(status_text: str = "", warnmsg: str = "", errmsg: str = "") -> str:
    s = str(status_text or "").strip().lower()
    w = str(warnmsg or "").strip().lower()
    e = str(errmsg or "").strip().lower()

    clean = {"", "no message", "none", "nan"}

    if e not in clean:
        return "FAIL"

    if w not in clean:
        return "WARNING"

    if "fail" in s or "error" in s or "see errors" in s:
        return "FAIL"

    if "warning" in s or "warn" in s or "see warnings" in s:
        return "WARNING"

    return "OK"


# =============================================================================
# Result builders
# =============================================================================

def _make_result(
    check: str,
    status: str,
    evaluation_level: str,
    code_ref: str,
    selected_method: str,
    *,
    missing_data: Optional[List[str]] = None,
    assumptions: Optional[List[str]] = None,
    data_sources: Optional[List[str]] = None,
    inputs: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    items: Optional[List[Dict[str, Any]]] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    missing_data = missing_data or []
    assumptions = assumptions or []
    data_sources = data_sources or []
    inputs = inputs or {}
    result = result or {}
    warnings = warnings or []
    items = items or []

    if evaluation_level == "DESIGN_LEVEL":
        confidence = "HIGH"
    elif evaluation_level == "ETABS_DESIGN_RESULT":
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    requires_engineer_review = (
        status in {"FAIL", "WARNING", "NO_DATA", "ERROR", "NOT_EVALUATED"}
        or evaluation_level != "DESIGN_LEVEL"
        or bool(assumptions)
        or bool(missing_data)
    )

    return {
        "check": check,
        "status": status,
        "evaluation_level": evaluation_level,
        "run_level": evaluation_level,
        "engineering_level": evaluation_level,
        "confidence": confidence,
        "requires_engineer_review": requires_engineer_review,
        "code_ref": code_ref,
        "selected_method": selected_method,
        "missing_data": missing_data,
        "assumptions": assumptions,
        "data_sources": data_sources,
        "inputs": inputs,
        "result": result,
        "items": items[:MAX_ITEMS],
        "total_items": len(items),
        "warnings": warnings,
    }


def _no_data(check: str, reason: str, missing_data: Optional[List[str]] = None, code_ref: str = "N/A") -> Dict[str, Any]:
    return _make_result(
        check=check,
        status="NO_DATA",
        evaluation_level="NO_DATA",
        code_ref=code_ref,
        selected_method="NO_DATA_AVAILABLE",
        missing_data=missing_data or [],
        assumptions=[],
        warnings=[reason],
    )


def _etabs_result(check: str, status: str, code_ref: str, selected_method: str, items: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    return _make_result(check, status, "ETABS_DESIGN_RESULT", code_ref, selected_method, items=items, **kwargs)


def _screening_result(check: str, status: str, code_ref: str, selected_method: str, items: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    return _make_result(check, status, "SCREENING", code_ref, selected_method, items=items, **kwargs)


def _approximate_result(check: str, status: str, code_ref: str, selected_method: str, items: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    return _make_result(check, status, "APPROXIMATE", code_ref, selected_method, items=items, **kwargs)


def _design_result(check: str, status: str, code_ref: str, selected_method: str, items: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    return _make_result(check, status, "DESIGN_LEVEL", code_ref, selected_method, items=items, **kwargs)


def _aggregate_status(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "NO_DATA"
    statuses = {str(i.get("status", "NO_DATA")).upper() for i in items}
    if "FAIL" in statuses:
        return "FAIL"
    if "WARNING" in statuses:
        return "WARNING"
    if "NO_DATA" in statuses:
        return "WARNING"
    if statuses == {"OK"}:
        return "OK"
    return "WARNING"


# =============================================================================
# Formula helpers — internal units: m, kN, kNm, MPa
# =============================================================================

def _fctd_mpa(fck_mpa: float, gamma_c: float = 1.5) -> float:
    return 0.35 * math.sqrt(fck_mpa) / gamma_c if fck_mpa > 0 and gamma_c > 0 else 0.0


def _concrete_shear_kN(b_m: float, d_m: float, fck_mpa: float, gamma_c: float = 1.5) -> float:
    return 0.65 * _fctd_mpa(fck_mpa, gamma_c) * b_m * d_m * 1000.0


def _effective_depth_m(h_m: float, cover_m: float, bar_centroid_m: float = 0.02) -> float:
    if h_m <= 0:
        return 0.0
    d = h_m - cover_m - bar_centroid_m
    # Safety guard: don't allow obviously impossible effective depth.
    return max(min(d, 0.95 * h_m), 0.70 * h_m)


# =============================================================================
# Design summary readers
# =============================================================================

def _read_column_design_summary(ctx: ModelContext) -> Dict[str, Dict[str, Any]]:
    df = _dm_get(ctx, "column_design_summary")
    if _empty_df(df):
        return {}

    out: Dict[str, Dict[str, Any]] = {}

    for _, row in df.iterrows():
        name = _safe_str(row.get("unique_name") or row.get("label") or row.get("column"))
        if not name:
            continue

        raw_status = _safe_str(row.get("status"))
        warnmsg = _safe_str(row.get("warnmsg"))
        errmsg = _safe_str(row.get("errmsg"))

        status_text = " ".join(
            x for x in [raw_status, warnmsg, errmsg]
            if x
        )

        out[name] = {
            "story": _safe_str(row.get("story")),
            "section": _safe_str(row.get("designsect") or row.get("section")),
            "pmm_ratio": _safe_float(row.get("pmmratio") or row.get("ratio"), 0.0),
            "status_text": status_text,
            "status_kind": _etabs_status_kind(raw_status, warnmsg, errmsg),
            "vmaj_rebar": _safe_float(row.get("vmajrebar"), 0.0),
            "vmin_rebar": _safe_float(row.get("vminrebar"), 0.0),
        }

    return out

def _read_beam_design_summary(ctx: ModelContext) -> Dict[str, Dict[str, Any]]:
    df = _dm_get(ctx, "beam_design_summary")
    if _empty_df(df):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        name = _safe_str(row.get("unique_name") or row.get("label") or row.get("beam"))
        if not name:
            continue
        status_text = " ".join([
            _safe_str(row.get("status")),
            _safe_str(row.get("warnmsg")),
            _safe_str(row.get("errmsg")),
        ])
        astop = _safe_float(row.get("astop") or row.get("tottoprebar"))
        asbot = _safe_float(row.get("asbot") or row.get("totbotrebar"))
        asmin_top = _safe_float(row.get("asmintop") or row.get("asmin"))
        asmin_bot = _safe_float(row.get("asminbot") or row.get("asmin"))
        out[name] = {
            "story": _safe_str(row.get("story")),
            "section": _safe_str(row.get("designsect") or row.get("section")),
            "status_text": status_text,
            "status_kind": _etabs_status_kind(status_text),
            "astop": astop,
            "asbot": asbot,
            "asmin_top": asmin_top,
            "asmin_bot": asmin_bot,
            "vrebar": _safe_float(row.get("vrebar") or row.get("tottrnrebar")),
        }
    return out


def _read_joint_shear_design(ctx: ModelContext) -> List[Dict[str, Any]]:
    df = _dm_get(ctx, "joint_shear_design")
    if _empty_df(df):
        return []
    ratio_cols = [c for c in df.columns if "ratio" in _safe_str(c).lower()]
    items: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        ratios = [_safe_float(row.get(c), 0.0) for c in ratio_cols]
        ratio = max(ratios) if ratios else 0.0
        status_text = " ".join([_safe_str(row.get("status")), _safe_str(row.get("warnmsg")), _safe_str(row.get("errmsg"))])
        kind = _etabs_status_kind(status_text)
        status = "FAIL" if ratio > 1.0 or kind == "FAIL" else "WARNING" if kind == "WARNING" else "OK"
        items.append({
            "element_id": _safe_str(row.get("unique_name") or row.get("label")),
            "story": _safe_str(row.get("story")),
            "ratio": round(ratio, 4),
            "limit": 1.0,
            "etabs_status": status_text,
            "status": status,
            "source": "ETABS_JOINT_DESIGN_SUMMARY",
        })
    return items


def _read_wall_design_summary(ctx: ModelContext) -> List[Dict[str, Any]]:
    df = _dm_get(ctx, "wall_design_summary")
    if _empty_df(df):
        return []
    items: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        status_text = " ".join([_safe_str(row.get("status")), _safe_str(row.get("warnmsg")), _safe_str(row.get("errmsg"))])
        kind = _etabs_status_kind(status_text)
        status = "FAIL" if kind == "FAIL" else "WARNING" if kind in {"WARNING", "UNKNOWN"} else "OK"
        items.append({
            "element_id": _safe_str(row.get("pier") or row.get("label") or row.get("unique_name")),
            "story": _safe_str(row.get("story")),
            "etabs_status": status_text,
            "status": status,
            "source": "ETABS_WALL_DESIGN_SUMMARY",
        })
    return items


def _read_scwb_design(ctx: ModelContext) -> List[Dict[str, Any]]:
    df = _dm_get(ctx, "scwb_design")
    if _empty_df(df):
        return []
    items: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        ratio = _safe_float(row.get("ratio") or row.get("SCWB") or row.get("BCRatio"), 0.0)
        status_text = " ".join([_safe_str(row.get("status")), _safe_str(row.get("warnmsg")), _safe_str(row.get("errmsg"))])
        kind = _etabs_status_kind(status_text)
        # For SCWB, ratio convention may differ by table. If unknown, ETABS status governs.
        status = "FAIL" if kind == "FAIL" else "WARNING" if kind in {"WARNING", "UNKNOWN"} else "OK"
        items.append({
            "element_id": _safe_str(row.get("unique_name") or row.get("label")),
            "story": _safe_str(row.get("story")),
            "ratio": round(ratio, 4),
            "etabs_status": status_text,
            "status": status,
            "source": "ETABS_SCWB_DESIGN",
        })
    return items


def _read_column_rebar_defs(ctx: ModelContext) -> Dict[str, Dict[str, Any]]:
    df = _dm_get(ctx, "column_rebar_defs")
    if _empty_df(df):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        name = _safe_str(row.get("name") or row.get("section"))
        if not name:
            continue
        # ETABS normalized spacingconf is expected in m if context_builder unit normalization is correct.
        out[name] = {
            "barsizeconf": _safe_float(row.get("barsizeconf")),
            "spacingconf": _safe_float(row.get("spacingconf")),
            "numcbars3": _safe_float(row.get("numcbars3"), 0.0),
            "numcbars2": _safe_float(row.get("numcbars2"), 0.0),
        }
    return out


# =============================================================================
# Checks
# =============================================================================
def _clean_etabs_msg(value: Any) -> str:
    s = _safe_str(value).strip()
    if not s:
        return ""
    if s.lower() in {"no message", "none", "nan", "-", "—"}:
        return ""
    return s


def _has_rebar_text(value: Any) -> bool:
    s = _safe_str(value).strip()
    if not s:
        return False
    return s.lower() not in {"0", "0.0", "-", "none", "nan", "no message"}


def check_wall_boundary_zone_v22(ctx: ModelContext) -> Dict[str, Any]:
    check = "wall_boundary_zone"
    code = "TBDY 2018 §7.6.2.4"

    wall_design = _dm_get(ctx, "wall_design_summary")
    if _empty_df(wall_design):
        wall_design = getattr(ctx, "tables", {}).get("wall_design_summary")

    if _empty_df(wall_design):
        return _make_result(
            check=check,
            status="NO_DATA",
            evaluation_level="NO_DATA",
            code_ref=code,
            selected_method="TBDY_WALL_BOUNDARY_ZONE_FROM_ETABS_DESIGN",
            data_sources=["wall_design_summary"],
            missing_data=["wall_design_summary"],
            items=[],
            warnings=["wall_design_summary bulunamadı; perde uç bölgesi kontrolü yapılamadı."],
        )

    items = []

    for _, row in wall_design.iterrows():
        story = _safe_str(row.get("story"))
        pier = _safe_str(row.get("pier"))
        station = _safe_str(row.get("station"))
        design_type = _safe_str(row.get("designtype"))

        edgebar = _safe_str(row.get("edgebar"))
        endbar = _safe_str(row.get("endbar"))

        warnmsg = _clean_etabs_msg(row.get("warnmsg"))
        errmsg = _clean_etabs_msg(row.get("errmsg"))

        length_m = _safe_float(row.get("length_m"), 0.0)
        thickness_m = _safe_float(row.get("thickness_m"), 0.0)
        barspacing_m = _safe_float(row.get("barspacing"), 0.0)
        required_reinf = _safe_float(row.get("reinfpcent"), 0.0)
        provided_reinf = _safe_float(row.get("currpcent"), 0.0)

        slenderness = length_m / thickness_m if thickness_m > 0 else 0.0

        # TBDY'ye yakın karar: boundary zone gerekliliğini geometri + ETABS design type + donatı talebi üzerinden oku.
        boundary_required = False
        boundary_reasons = []

        if "boundary" in design_type.lower() or "edge" in design_type.lower():
            boundary_required = True
            boundary_reasons.append("ETABS design type boundary/edge zone işaret ediyor.")

        if slenderness >= 6.0:
            boundary_required = True
            boundary_reasons.append("Perde boy/kalınlık oranı yüksek; uç bölgesi incelemesi gerekli.")

        if required_reinf > 0.8:
            boundary_required = True
            boundary_reasons.append("Gerekli donatı oranı yüksek; uç bölgesi davranışı kritik.")

        has_edgebar = _has_rebar_text(edgebar)
        has_endbar = _has_rebar_text(endbar)

        status = "OK"
        warnings = []

        # 1) ETABS mesajlarını scope'a göre ayır.
        if errmsg:
            low = errmsg.lower()
            if "boundary" in low or "edge" in low or "end zone" in low:
                status = "FAIL"
                warnings.append(f"ETABS boundary-zone error: {errmsg}")
            else:
                warnings.append(f"ETABS wall design message outside boundary-zone scope: {errmsg}")
                if status == "OK":
                    status = "WARNING"

        if warnmsg:
            warnings.append(f"ETABS wall design warning: {warnmsg}")
            if status == "OK":
                status = "WARNING"

        # 2) Uç bölgesi gerekiyorsa, uç donatısı aranır.
        if boundary_required and not (has_edgebar or has_endbar):
            status = "FAIL"
            warnings.append("Uç bölgesi gerekli görünüyor ancak edgebar/endbar raporlanmamış.")

        # 3) Donatı oranı yeterliliği.
        if required_reinf > 0 and provided_reinf > 0:
            if provided_reinf + 1e-9 < required_reinf:
                status = "FAIL"
                warnings.append(
                    f"Sağlanan perde donatı oranı yetersiz: provided={provided_reinf:.3f}% < required={required_reinf:.3f}%."
                )

        # 4) Detaylandırma kontrolleri.
        if boundary_required and barspacing_m > 0.15:
            if status != "FAIL":
                status = "WARNING"
            warnings.append(
                f"Uç bölgesi için donatı aralığı yüksek: s={barspacing_m:.3f} m > 0.150 m screening sınırı."
            )

        if thickness_m > 0 and thickness_m < 0.25:
            if status != "FAIL":
                status = "WARNING"
            warnings.append(
                f"Perde kalınlığı uç bölgesi detaylandırması için düşük: t={thickness_m:.3f} m."
            )

        items.append({
            "story": story,
            "pier": pier,
            "station": station,
            "design_type": design_type,
            "length_m": round(length_m, 3),
            "thickness_m": round(thickness_m, 3),
            "slenderness_lw_tw": round(slenderness, 3),
            "boundary_required": boundary_required,
            "boundary_reasons": boundary_reasons,
            "edgebar": edgebar,
            "endbar": endbar,
            "has_edgebar": has_edgebar,
            "has_endbar": has_endbar,
            "barspacing_m": round(barspacing_m, 4),
            "required_reinf_percent": round(required_reinf, 4),
            "provided_reinf_percent": round(provided_reinf, 4),
            "status": status,
            "warnings": warnings,
            "source": "ETABS_WALL_DESIGN_SUMMARY",
        })

    items = sorted(
        items,
        key=lambda x: (
            x["status"] != "OK",
            x["boundary_required"],
            x["required_reinf_percent"],
            x["slenderness_lw_tw"],
        ),
        reverse=True,
    )

    return _make_result(
        check=check,
        status=_aggregate_status(items),
        evaluation_level="ETABS_DESIGN_RESULT",
        code_ref=code,
        selected_method="TBDY_WALL_BOUNDARY_ZONE_FROM_ETABS_DESIGN",
        data_sources=["wall_design_summary"],
        items=items,
        warnings=[
            "Bu kontrol wall_design_summary tablosunu esas alır.",
            "Perde kesme kapasitesi mesajları wall_boundary_zone kapsamında FAIL yapılmaz; wall_shear kapsamında değerlendirilmelidir.",
        ],
    )

def check_column_axial_v20(ctx: ModelContext) -> Dict[str, Any]:
    check = "column_axial"
    code = "TBDY 2018 §7.3.1"

    if _cap(ctx, check) == "ETABS_DESIGN_RESULT":
        ds = _read_column_design_summary(ctx)
        if ds:
            items = []
            for name, d in ds.items():
                pmm = _safe_float(d.get("pmm_ratio"), 0.0)
                kind = d["status_kind"]
                status = "FAIL" if pmm > 1.0 or kind == "FAIL" else "WARNING" if kind == "WARNING" else "OK"

                items.append({
                    "element_id": name,
                    "story": d["story"],
                    "section": d["section"],
                    "pmm_ratio": round(pmm, 4),
                    "limit": 1.0,
                    "etabs_status": d["status_text"],
                    "status": status,
                    "source": "ETABS_COLUMN_DESIGN_SUMMARY",
                })
            return _etabs_result(check, _aggregate_status(items), code, "ETABS_DESIGN_SUMMARY_PMM", items, data_sources=["column_design_summary"])

    fck = _basis_val(ctx, "fck_mpa", 30.0)
    limit_ratio = _basis_val(ctx, "column_axial_limit", 0.40)
    forces = _env_map(ctx, "column_forces_map")
    sections = _geom_sections(ctx, "column")
    if not forces or not sections:
        return _no_data(check, "No column force envelope or section geometry", ["column_forces_map", "column_sections", "section_dims"], code)

    assumptions = ["Screening axial check: reinforcement and PMM interaction not considered."]
    missing = [] if _materials_verified(ctx) else ["materials_verified"]
    items = []
    for col, f in forces.items():
        sec = sections.get(col, "")
        dims = _section_dims(ctx, sec)
        Ac = _safe_float(dims.get("width_m")) * _safe_float(dims.get("depth_m"))
        Nd = abs(_safe_float(f.get("P_max")))
        if Ac <= 0:
            items.append({"element_id": col, "section": sec, "status": "NO_DATA", "reason": "Missing section dimensions"})
            continue
        denom = Ac * fck * 1000.0
        ratio = Nd / denom if denom > 0 else 0.0
        normalized = ratio / limit_ratio if limit_ratio > 0 else ratio
        if normalized > 1.0:
            status = "FAIL"
        elif normalized > 0.60:
            status = "WARNING"
        else:
            status = "OK"
        items.append({
            "element_id": col,
            "story": _safe_str(f.get("story")),
            "section": sec,
            "Nd_kN": round(Nd, 2),
            "Ac_m2": round(Ac, 5),
            "fck_mpa": fck,
            "ratio_Nd_Acfck": round(ratio, 4),
            "limit": limit_ratio,
            "utilization": round(normalized, 4),
            "governing_case": f.get("P_case"),
            "status": status,
            "source": "ENVELOPE_SCREENING",
        })
    return _screening_result(check, _aggregate_status(items), code, "SCREENING_AXIAL_ND_AC_FCK", items, missing_data=missing, assumptions=assumptions, data_sources=["column_forces_map", "section_dims"])


def check_column_shear_v20(ctx: ModelContext) -> Dict[str, Any]:
    check = "column_shear"
    code = "TBDY 2018 §7.3.7"

    if _cap(ctx, check) == "ETABS_DESIGN_RESULT":
        ds = _read_column_design_summary(ctx)
        if ds:
            items = []
            for name, d in ds.items():
                has_shear_rebar = d["vmaj_rebar"] > 0 or d["vmin_rebar"] > 0
                kind = d["status_kind"]
                status = "FAIL" if kind == "FAIL" else "WARNING" if kind == "WARNING" or not has_shear_rebar else "OK"
                items.append({
                    "element_id": name,
                    "story": d["story"],
                    "section": d["section"],
                    "vmaj_rebar": d["vmaj_rebar"],
                    "vmin_rebar": d["vmin_rebar"],
                    "has_shear_rebar": has_shear_rebar,
                    "etabs_status": d["status_text"],
                    "status": status,
                    "source": "ETABS_COLUMN_DESIGN_SUMMARY",
                })
            return _etabs_result(check, _aggregate_status(items), code, "ETABS_DESIGN_SUMMARY_SHEAR", items, data_sources=["column_design_summary"])

    fck = _basis_val(ctx, "fck_mpa", 30.0)
    gamma_c = _basis_val(ctx, "gamma_c", 1.5)
    cover = _basis_val(ctx, "column_cover_m", 0.04)
    forces = _env_map(ctx, "column_forces_map")
    sections = _geom_sections(ctx, "column")
    if not forces or not sections:
        return _no_data(check, "No column force envelope or section geometry", ["column_forces_map", "column_sections", "section_dims"], code)

    items = []
    for col, f in forces.items():
        sec = sections.get(col, "")
        dims = _section_dims(ctx, sec)
        b = min(_safe_float(dims.get("width_m")), _safe_float(dims.get("depth_m")))
        h = max(_safe_float(dims.get("width_m")), _safe_float(dims.get("depth_m")))
        if b <= 0 or h <= 0:
            items.append({"element_id": col, "section": sec, "status": "NO_DATA", "reason": "Missing section dimensions"})
            continue
        d_eff = _effective_depth_m(h, cover)
        v2 = abs(_safe_float(f.get("V2_max")))
        v3 = abs(_safe_float(f.get("V3_max")))
        Ved = max(v2, v3)
        case = f.get("V2_case") if v2 >= v3 else f.get("V3_case")
        Vc = _concrete_shear_kN(b, d_eff, fck, gamma_c)
        ratio = Ved / Vc if Vc > 0 else 0.0
        status = "FAIL" if ratio > 1.0 else "WARNING"
        items.append({
            "element_id": col,
            "story": _safe_str(f.get("story")),
            "section": sec,
            "b_m": round(b, 4),
            "d_eff_m": round(d_eff, 4),
            "V_ed_kN": round(Ved, 2),
            "Vc_kN": round(Vc, 2),
            "ratio": round(ratio, 4),
            "governing_case": case,
            "status": status,
            "source": "CONCRETE_ONLY_SCREENING",
        })
    return _screening_result(
        check, _aggregate_status(items), code, "SCREENING_CONCRETE_ONLY_SHEAR", items,
        assumptions=["Concrete-only shear screening; transverse reinforcement and capacity-design shear not included."],
        missing_data=["column transverse reinforcement", "plastic moment capacity"],
        data_sources=["column_forces_map", "section_dims"],
        warnings=["Ratio <= 1.0 remains WARNING because stirrup/capacity-design data is missing."],
    )


def check_beam_shear_v20(ctx: ModelContext) -> Dict[str, Any]:
    check = "beam_shear"
    code = "TS500 §8.1 / TBDY 2018 §7.4.2"

    if _cap(ctx, check) == "ETABS_DESIGN_RESULT":
        ds = _read_beam_design_summary(ctx)
        if ds:
            items = []
            for name, d in ds.items():
                has_rebar = d["vrebar"] > 0
                kind = d["status_kind"]
                status = "FAIL" if kind == "FAIL" else "WARNING" if kind == "WARNING" or not has_rebar else "OK"
                items.append({
                    "element_id": name,
                    "story": d["story"],
                    "section": d["section"],
                    "vrebar": d["vrebar"],
                    "has_shear_rebar": has_rebar,
                    "etabs_status": d["status_text"],
                    "status": status,
                    "source": "ETABS_BEAM_DESIGN_SUMMARY",
                })
            return _etabs_result(check, _aggregate_status(items), code, "ETABS_DESIGN_SUMMARY_SHEAR", items, data_sources=["beam_design_summary"])

    fck = _basis_val(ctx, "fck_mpa", 30.0)
    gamma_c = _basis_val(ctx, "gamma_c", 1.5)
    cover = _basis_val(ctx, "beam_cover_m", 0.04)
    forces = _env_map(ctx, "beam_forces_map")
    sections = _geom_sections(ctx, "beam")
    if not forces or not sections:
        return _no_data(check, "No beam force envelope or section geometry", ["beam_forces_map", "beam_sections", "section_dims"], code)

    items = []
    for beam, f in forces.items():
        sec = sections.get(beam, "")
        dims = _section_dims(ctx, sec)
        bw = _safe_float(dims.get("width_m"))
        h = _safe_float(dims.get("depth_m"))
        if bw <= 0 or h <= 0:
            items.append({"element_id": beam, "section": sec, "status": "NO_DATA", "reason": "Missing section dimensions"})
            continue
        d_eff = _effective_depth_m(h, cover)
        v2 = abs(_safe_float(f.get("V2_max")))
        v3 = abs(_safe_float(f.get("V3_max")))
        Ved = max(v2, v3)
        case = f.get("V2_case") if v2 >= v3 else f.get("V3_case")
        Vc = _concrete_shear_kN(bw, d_eff, fck, gamma_c)
        ratio = Ved / Vc if Vc > 0 else 0.0
        status = "FAIL" if ratio > 1.0 else "WARNING"
        items.append({
            "element_id": beam,
            "story": _safe_str(f.get("story")),
            "section": sec,
            "bw_m": round(bw, 4),
            "d_eff_m": round(d_eff, 4),
            "V_ed_kN": round(Ved, 2),
            "Vc_kN": round(Vc, 2),
            "ratio": round(ratio, 4),
            "governing_case": case,
            "status": status,
            "source": "CONCRETE_ONLY_SCREENING",
        })
    return _screening_result(
        check, _aggregate_status(items), code, "SCREENING_CONCRETE_ONLY_SHEAR", items,
        assumptions=["Concrete-only shear screening; stirrup contribution not included."],
        missing_data=["beam transverse reinforcement"],
        data_sources=["beam_forces_map", "section_dims"],
        warnings=["Ratio <= 1.0 remains WARNING because stirrup data is missing."],
    )


def check_beam_flexure_v20(ctx: ModelContext) -> Dict[str, Any]:
    check = "beam_flexure"
    code = "TS500 / TBDY 2018 §7.4"

    if _cap(ctx, check) == "ETABS_DESIGN_RESULT":
        ds = _read_beam_design_summary(ctx)
        if ds:
            items = []
            for name, d in ds.items():
                kind = d["status_kind"]
                has_rebar = d["astop"] > 0 or d["asbot"] > 0
                below_min = (d["asmin_top"] > 0 and d["astop"] < d["asmin_top"]) or (d["asmin_bot"] > 0 and d["asbot"] < d["asmin_bot"])
                status = "FAIL" if kind == "FAIL" or below_min else "WARNING" if kind == "WARNING" or not has_rebar else "OK"
                items.append({
                    "element_id": name,
                    "story": d["story"],
                    "section": d["section"],
                    "astop": d["astop"],
                    "asbot": d["asbot"],
                    "asmin_top": d["asmin_top"],
                    "asmin_bot": d["asmin_bot"],
                    "below_min_rebar": below_min,
                    "etabs_status": d["status_text"],
                    "status": status,
                    "source": "ETABS_BEAM_DESIGN_SUMMARY",
                })
            return _etabs_result(check, _aggregate_status(items), code, "ETABS_DESIGN_SUMMARY_FLEXURE", items, data_sources=["beam_design_summary"])
    return _no_data(check, "Beam design summary not available", ["beam_design_summary"], code)


def check_column_confinement_v20(ctx: ModelContext) -> Dict[str, Any]:
    check = "column_confinement"
    code = "TBDY 2018 §7.3.4.2"
    rebar_defs = _read_column_rebar_defs(ctx)
    if not rebar_defs:
        return _no_data(check, "No column rebar definitions", ["column_rebar_defs"], code)

    sections = _geom_sections(ctx, "column")
    if not sections:
        return _no_data(check, "No column-section mapping", ["column_sections"], code)

    mat_ok = _materials_verified(ctx)
    assumptions: List[str] = []
    missing: List[str] = []
    if not mat_ok:
        missing.append("materials_verified")
    if len(rebar_defs) < len(set(sections.values())):
        assumptions.append("Section-level rebar definitions do not cover every unique column section.")
    if len(rebar_defs) <= 2 and len(sections) > 2:
        assumptions.append("Section-level assumption: very few rebar definition rows are mapped to many columns.")

    items = []
    for col, sec in sections.items():
        r = rebar_defs.get(sec, {})
        dims = _section_dims(ctx, sec)
        bmin = min(_safe_float(dims.get("width_m")), _safe_float(dims.get("depth_m"))) if dims else 0.0
        dia = _safe_float(r.get("barsizeconf"))
        spacing = _safe_float(r.get("spacingconf"))
        if not r or dia <= 0 or spacing <= 0 or bmin <= 0:
            items.append({"element_id": col, "section": sec, "status": "NO_DATA", "reason": "Missing tie/spacing/section data"})
            continue
        smax = min(0.10, bmin / 3.0)
        status = "OK" if dia >= 8.0 and spacing <= smax else "FAIL"
        items.append({
            "element_id": col,
            "section": sec,
            "tie_dia_mm": round(dia, 2),
            "tie_spacing_m": round(spacing, 4),
            "s_max_m": round(smax, 4),
            "bmin_m": round(bmin, 4),
            "status": status,
            "source": "COLUMN_REBAR_DEFS",
        })

    builder = _design_result if mat_ok and not assumptions else _screening_result
    return builder(
        check, _aggregate_status(items), code, "REBAR_DEF_CONFINEMENT_CHECK", items,
        missing_data=missing,
        assumptions=assumptions,
        data_sources=["column_rebar_defs", "column_sections", "section_dims"],
        warnings=[] if mat_ok and not assumptions else ["Confinement result is not full element-level design proof."],
    )

def check_base_shear_limit_v20(ctx: ModelContext) -> Dict[str, Any]:
    check = "base_shear_limit"
    code = "TBDY 2018 §4.8.2"

    seismic = getattr(ctx, "seismic", {})

    beta_x = _safe_float(seismic.get("beta_x"), 0.0)
    beta_min = _safe_float(seismic.get("beta_min"), 0.90)

    if beta_x <= 0:
        return _no_data_result(check, code, "beta_x not available")

    status = "OK" if beta_x >= beta_min else "FAIL"

    return _make_result(
        check,
        status,
        "DESIGN_LEVEL",
        code,
        "MANUAL_FORMULA",
        inputs={
            "beta_x": beta_x,
            "beta_min": beta_min,
        },
        result={
            "ratio": beta_x / beta_min if beta_min > 0 else None,
        }
    )

def check_soft_story_v20(ctx: ModelContext) -> Dict[str, Any]:
    check = "soft_story"
    code = "TBDY 2018 §3.6.1"

    drifts = ctx.tables.get("story_drifts")

    if drifts is None or drifts.empty:
        return _no_data_result(check, code, "story_drifts missing")

    try:
        ratios = [_safe_float(r, 0.0) for r in drifts["ratio"].tolist()]
        max_ratio = max(ratios) if ratios else 0.0

        limit = 2.0

        status = "OK" if max_ratio <= limit else "FAIL"

        return _make_result(
            check,
            status,
            "APPROXIMATE",
            code,
            "SCREENING_DRIFT_RATIO",
            inputs={
                "max_ratio": max_ratio,
                "limit": limit,
            }
        )

    except Exception as e:
        return _error_result(check, code, str(e))

def check_scwb_v20(ctx: ModelContext) -> Dict[str, Any]:
    check = "scwb"
    code = "TBDY 2018 §7.3.5"

    if _cap(ctx, check) == "ETABS_DESIGN_RESULT":
        items = _read_scwb_design(ctx)
        if items:
            return _etabs_result(check, _aggregate_status(items), code, "ETABS_SCWB_DESIGN", items, data_sources=["scwb_design"])

    col_casewise = _env_map(ctx, "column_casewise_forces")
    beam_casewise = _env_map(ctx, "beam_casewise_forces")
    cb_map = _topo_column_beam_map(ctx)
    if not col_casewise or not beam_casewise or not cb_map:
        return _no_data(check, "No SCWB design or casewise topology/force data", ["scwb_design", "column_casewise_forces", "beam_casewise_forces", "column_beam_map"], code)

    items = []
    missing_ratio_count = 0
    for entry in cb_map:
        ratio = _safe_float(entry.get("scwb_ratio"), 0.0)
        if ratio <= 0:
            missing_ratio_count += 1
            items.append({
                "element_id": _safe_str(entry.get("joint") or entry.get("label") or entry.get("column")),
                "story": _safe_str(entry.get("story")),
                "status": "NO_DATA",
                "reason": "scwb_ratio not computed from capacity data",
                "source": "COLUMN_BEAM_MAP",
            })
            continue
        # Approximate force-based result is not a code-level capacity failure. Flag for review.
        status = "WARNING" if ratio < 1.20 else "OK"
        items.append({
            "element_id": _safe_str(entry.get("joint") or entry.get("label") or entry.get("column")),
            "story": _safe_str(entry.get("story")),
            "ratio": round(ratio, 4),
            "limit": 1.20,
            "status": status,
            "source": "APPROXIMATE_FORCE_BASED_SCREENING",
        })
    missing = ["scwb_ratio not computed from capacity data"] if missing_ratio_count else []
    return _approximate_result(
        check, _aggregate_status(items), code, "APPROXIMATE_FORCE_BASED_SCREENING", items,
        missing_data=missing,
        assumptions=["Approximate SCWB check uses available force/topology proxies, not plastic moment capacities."],
        data_sources=["column_casewise_forces", "beam_casewise_forces", "column_beam_map"],
        warnings=["Approximate SCWB cannot be used as DESIGN_LEVEL proof."],
    )


def check_joint_shear_v20(ctx: ModelContext) -> Dict[str, Any]:
    check = "joint_shear"
    code = "TBDY 2018 §7.4.5"

    if _cap(ctx, check) == "ETABS_DESIGN_RESULT":
        items = _read_joint_shear_design(ctx)
        if items:
            return _etabs_result(check, _aggregate_status(items), code, "ETABS_JOINT_SHEAR_DESIGN", items, data_sources=["joint_shear_design"])

    joints = _topo_analysis_joints(ctx)
    if not joints:
        return _no_data(check, "No joint shear design or analysis joint topology", ["joint_shear_design", "analysis_joints"], code)

    items = [{
        "element_id": _safe_str(j.get("joint_name") or j.get("label")),
        "story": _safe_str(j.get("story")),
        "confinement": _safe_str(j.get("confinement"), "UNKNOWN"),
        "status": "NO_DATA",
        "reason": "Joint shear capacity requires beam rebar, column geometry and joint force model.",
        "source": "TOPOLOGY_SCREENING_ONLY",
    } for j in joints]
    return _screening_result(
        check, "WARNING", code, "TOPOLOGY_SCREENING_ONLY", items,
        missing_data=["beam rebar", "joint force model"],
        assumptions=["Topology is available, but joint shear demand/capacity is not computed."],
        data_sources=["topology.analysis_joints"],
        warnings=["DESIGN_LEVEL not possible from topology only."],
    )


def check_drift_v20(ctx: ModelContext) -> Dict[str, Any]:
    check = "drift"
    code = "TBDY 2018 §4.9"
    drift_df = getattr(ctx, "tables", {}).get("story_drifts")
    if _empty_df(drift_df):
        return _no_data(check, "Story drifts not available", ["story_drifts"], code)

    R = _basis_val(ctx, "R", 7.0)
    I = _basis_val(ctx, "I", 1.5)
    drift_mult = _basis_val(ctx, "drift_multiplier", R / I)
    limit = _basis_val(ctx, "drift_limit", 0.008)
    verified = _basis_verified(ctx, "R") and _basis_verified(ctx, "I")
    assumptions = [] if verified else [f"R/I or drift multiplier not fully verified. R source={_basis_source(ctx, 'R')}, I source={_basis_source(ctx, 'I')}"]

    items = []
    for _, row in drift_df.iterrows():
        raw = abs(_safe_float(row.get("max_drift")))
        eff = raw * drift_mult
        ratio = eff / limit if limit > 0 else 0.0
        items.append({
            "story": _safe_str(row.get("story")),
            "direction": _safe_str(row.get("direction")),
            "raw_drift": round(raw, 6),
            "effective_drift": round(eff, 6),
            "limit": limit,
            "ratio": round(ratio, 4),
            "status": "FAIL" if ratio > 1.0 else "OK",
        })
    builder = _design_result if verified else _approximate_result
    return builder(check, _aggregate_status(items), code, "EFFECTIVE_DRIFT_CHECK", items, assumptions=assumptions, data_sources=["story_drifts", "design_basis.R", "design_basis.I"])


def check_torsion_v20(ctx: ModelContext) -> Dict[str, Any]:
    check = "torsion"
    code = "TBDY 2018 §3.6.2.1"
    drift_df = getattr(ctx, "tables", {}).get("story_drifts")
    if _empty_df(drift_df):
        return _no_data(check, "Story drift max/average data not available", ["story_drifts"], code)

    items = []
    for _, row in drift_df.iterrows():
        ratio = _safe_float(row.get("ratio"), 0.0)
        if ratio <= 0:
            max_drift = abs(_safe_float(row.get("max_drift")))
            avg_drift = abs(_safe_float(row.get("avg_drift") or row.get("average_drift")))
            ratio = max_drift / avg_drift if avg_drift > 0 else 0.0
        status = "OK" if ratio <= 1.2 else "WARNING" if ratio <= 2.0 else "FAIL"
        items.append({
            "story": _safe_str(row.get("story")),
            "direction": _safe_str(row.get("direction")),
            "eta_bi": round(ratio, 4),
            "warning_limit": 1.2,
            "fail_limit": 2.0,
            "status": status,
        })
    return _design_result(check, _aggregate_status(items), code, "TORSIONAL_IRREGULARITY_RATIO", items, data_sources=["story_drifts"])


def check_second_order_v20(ctx: ModelContext) -> Dict[str, Any]:
    check = "second_order"
    code = "TBDY 2018 §4.9.3"
    drift_df = getattr(ctx, "tables", {}).get("story_drifts")
    story_forces = getattr(ctx, "tables", {}).get("story_forces")
    if _empty_df(drift_df) or _empty_df(story_forces):
        return _no_data(check, "Story drifts or story forces not available", ["story_drifts", "story_forces"], code)

    D = _basis_val(ctx, "D", 2.5)
    R = _basis_val(ctx, "R", 7.0)
    limit = 0.12 * D / max(0.5 * R, 1e-9)
    heights = getattr(ctx, "story_height_map", {}) or {}
    items = []

    for _, row in drift_df.iterrows():
        story = _safe_str(row.get("story"))
        drift_ratio = abs(_safe_float(row.get("max_drift")))
        h = _safe_float(heights.get(story), 3.0)
        sf = story_forces[story_forces["story"].astype(str) == story] if "story" in story_forces else None
        if sf is None or sf.empty:
            items.append({"story": story, "status": "NO_DATA", "reason": "Story force row missing"})
            continue
        V = max(abs(_safe_float(sf["vx"].max())) if "vx" in sf else 0.0, abs(_safe_float(sf["vy"].max())) if "vy" in sf else 0.0)
        P = abs(_safe_float(sf["p_kn"].max())) if "p_kn" in sf else 0.0
        # max_drift is a drift ratio. Delta = drift_ratio*h; theta=(P*Delta)/(V*h)=P*drift_ratio/V.
        theta = (P * drift_ratio) / V if V > 0 else 0.0
        items.append({
            "story": story,
            "direction": _safe_str(row.get("direction")),
            "theta": round(theta, 6),
            "limit": round(limit, 6),
            "P_kN": round(P, 2),
            "V_kN": round(V, 2),
            "drift_ratio": round(drift_ratio, 6),
            "h_m": round(h, 2),
            "status": "FAIL" if theta > limit else "OK",
        })
    return _approximate_result(
        check, _aggregate_status(items), code, "APPROXIMATE_SECOND_ORDER_THETA", items,
        assumptions=["θ is approximated from story forces and drift ratio; not a replacement for full second-order analysis."],
        data_sources=["story_drifts", "story_forces", "story_height_map"],
        warnings=["DESIGN_LEVEL not assigned for simplified θ calculation."],
    )


def check_wall_shear_v20(ctx: ModelContext) -> Dict[str, Any]:
    check = "wall_shear"
    code = "TBDY 2018 §7.6.6"

    if _flag(ctx, "has_wall_design_summary"):
        items = _read_wall_design_summary(ctx)
        if items:
            return _etabs_result(check, _aggregate_status(items), code, "ETABS_WALL_DESIGN_SUMMARY", items, data_sources=["wall_design_summary"])

    forces = _env_map(ctx, "pier_forces_map")
    wall_sections = getattr(ctx, "geometry", {}).get("wall_sections", {}) or {}
    if not forces or not wall_sections:
        return _no_data(check, "No wall design summary or pier force/section data", ["wall_design_summary", "pier_forces_map", "wall_sections"], code)

    fcd = _basis_val(ctx, "fcd_mpa", _basis_val(ctx, "fck_mpa", 30.0) / 1.5)
    fyd = _basis_val(ctx, "fyd_mpa", 434.78)
    rho_h = _basis_val(ctx, "wall_rho_h_min", 0.0025)
    items = []
    for pier, f in forces.items():
        sec = wall_sections.get(pier, {})
        Lw = _safe_float(sec.get("length_m"))
        tw = _safe_float(sec.get("thickness_m"))
        Ach = Lw * tw
        if Ach <= 0:
            items.append({"element_id": pier, "status": "NO_DATA", "reason": "Missing wall section dimensions"})
            continue
        V2 = abs(_safe_float(f.get("V2_max")))
        V3 = abs(_safe_float(f.get("V3_max")))
        Ved = max(V2, V3)
        case = f.get("V2_case") if V2 >= V3 else f.get("V3_case")
        Vr = Ach * (0.25 * fcd + rho_h * fyd) * 1000.0
        Vrmax = 0.65 * fcd * Ach * 1000.0
        Vrd = min(Vr, Vrmax)
        ratio = Ved / Vrd if Vrd > 0 else 0.0
        status = "FAIL" if ratio > 1.0 else "WARNING"
        items.append({
            "element_id": pier,
            "Lw_m": round(Lw, 4),
            "tw_m": round(tw, 4),
            "Ach_m2": round(Ach, 4),
            "V_ed_kN": round(Ved, 2),
            "V_rd_kN": round(Vrd, 2),
            "ratio": round(ratio, 4),
            "rho_h_assumed": rho_h,
            "governing_case": case,
            "status": status,
            "source": "PIER_FORCES_SCREENING",
        })
    return _screening_result(
        check, _aggregate_status(items), code, "SCREENING_WALL_SHEAR_MIN_REBAR", items,
        assumptions=[f"Minimum wall reinforcement ratio rho_h={rho_h} assumed because actual wall rebar data is not available."],
        missing_data=["wall reinforcement details"],
        data_sources=["pier_forces_map", "wall_sections"],
        warnings=["DESIGN_LEVEL not possible without wall reinforcement details."],
    )


FULL_ENGINEERING_CHECKS = {
    "column_axial": check_column_axial_v20,
    "column_shear": check_column_shear_v20,
    "beam_shear": check_beam_shear_v20,
    "beam_flexure": check_beam_flexure_v20,
    "column_confinement": check_column_confinement_v20,
    "scwb": check_scwb_v20,
    "joint_shear": check_joint_shear_v20,
    "drift": check_drift_v20,
    "torsion": check_torsion_v20,
    "second_order": check_second_order_v20,
    "wall_shear": check_wall_shear_v20,
}
