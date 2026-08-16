# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from tbdy_engine.etabs.safety import read_etabs_unit_snapshot


TARGET_ETABS_EUNITS = 6  # kN_m_C

UNIT_SYSTEM_KN_M_MPA: Dict[str, Any] = {
    "policy": "PROJECT_INTERNAL_KN_M_MPA",
    "etabs_present_units_enum": TARGET_ETABS_EUNITS,
    "etabs_present_units_name": "kN_m_C",
    "force": "kN",
    "length": "m",
    "moment": "kN*m",
    "stress": "MPa",
    "temperature": "C",
    "note": "Internal convention: kN, m, kN*m, MPa.",
}


def _class_from_concrete_name(name: Any) -> Optional[float]:
    if not name:
        return None
    m = re.search(r"C\s*(\d+(?:[.,]\d+)?)", str(name), flags=re.I)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except Exception:
        return None


def normalize_stress_to_mpa(value: Any, fallback_class: Any = None) -> Optional[float]:
    """Legacy design-basis normalization helper; not an ETABS acquisition unit detector.

    This function is retained for compatibility with existing domain callers.
    Canonical ETABS acquisition uses explicit unit provenance and must not infer
    ETABS source units from numeric magnitude.
    """
    try:
        x = float(value)
    except Exception:
        x = float("nan")

    if x == x and x > 0:
        if 1.0 <= x <= 150.0:
            return x
        if x > 1000.0:
            return x / 1000.0
        if 0.0 < x < 1.0:
            return x * 1000.0

    fc = _class_from_concrete_name(fallback_class)
    if fc:
        return fc
    return None


def set_etabs_units_kn_m(sap_model: Any) -> Dict[str, Any]:
    """Compatibility-only mutating API.

    Canonical ETABS acquisition must use :func:`read_etabs_units` instead.
    """
    info = dict(UNIT_SYSTEM_KN_M_MPA)
    info["compatibility_only"] = True
    info["set_present_units_attempted"] = False
    info["set_present_units_ret"] = None
    info["actual_present_units_enum"] = None

    if sap_model is None:
        info["source"] = "NO_SAP_MODEL"
        return info

    try:
        info["set_present_units_attempted"] = True
        ret = sap_model.SetPresentUnits(TARGET_ETABS_EUNITS)
        if isinstance(ret, tuple):
            ret = ret[0] if ret else None
        info["set_present_units_ret"] = ret
    except Exception as exc:
        info["set_present_units_error"] = f"{type(exc).__name__}: {exc}"

    try:
        got = sap_model.GetPresentUnits()
        if isinstance(got, tuple):
            vals = [v for v in got if isinstance(v, int)]
            info["actual_present_units_enum"] = vals[-1] if vals else str(got)
        else:
            info["actual_present_units_enum"] = got
    except Exception as exc:
        info["get_present_units_error"] = f"{type(exc).__name__}: {exc}"

    return info


def read_etabs_units(sap_model: Any) -> Dict[str, Any]:
    """Canonical read-only ETABS unit provenance."""
    info = dict(UNIT_SYSTEM_KN_M_MPA)
    info["source"] = "ETABS_READ_ONLY"
    info["compatibility_only"] = False
    info["set_present_units_attempted"] = False
    if sap_model is None:
        info["source"] = "NO_SAP_MODEL"
        return info
    snapshot = read_etabs_unit_snapshot(sap_model)
    info["etabs_unit_provenance"] = snapshot.as_dict()
    info["actual_present_units_enum"] = snapshot.present_units
    info["actual_database_units_enum"] = snapshot.database_units
    return info


def normalize_design_basis_units(ctx: Any) -> Any:
    db = getattr(ctx, "design_basis", None)
    if not isinstance(db, dict):
        return ctx

    concrete_class = db.get("concrete_class")

    # Preserve raw values once.
    for key in ["fck_mpa", "fcd_mpa", "fctd_mpa", "fyk_mpa", "fyd_mpa", "fywd_mpa"]:
        if key in db and f"{key}_raw" not in db:
            db[f"{key}_raw"] = db.get(key)

    # Concrete values
    fck = normalize_stress_to_mpa(db.get("fck_mpa"), concrete_class)
    if fck is not None:
        db["fck_mpa"] = fck
        db["fck_mpa_unit"] = "MPa"

    # Steel values
    for key in ["fyk_mpa", "fyd_mpa", "fywd_mpa"]:
        if key in db:
            val = normalize_stress_to_mpa(db.get(key), None)
            if val is not None:
                db[key] = val
                db[f"{key}_unit"] = "MPa"

    # Derived values
    try:
        if "fck_mpa" in db and "gamma_c" in db:
            db["fcd_mpa"] = float(db["fck_mpa"]) / float(db["gamma_c"])
            db["fcd_mpa_unit"] = "MPa"
        if "fyk_mpa" in db and "gamma_s" in db:
            db["fyd_mpa"] = float(db["fyk_mpa"]) / float(db["gamma_s"])
            db["fywd_mpa"] = db["fyd_mpa"]
            db["fyd_mpa_unit"] = "MPa"
            db["fywd_mpa_unit"] = "MPa"
    except Exception:
        pass

    db["_unit_policy"] = UNIT_SYSTEM_KN_M_MPA["policy"]
    db["_etabs_units"] = getattr(ctx, "unit_system", dict(UNIT_SYSTEM_KN_M_MPA))
    db["_force_unit"] = "kN"
    db["_length_unit"] = "m"
    db["_moment_unit"] = "kN*m"
    db["_stress_unit"] = "MPa"

    return ctx


def attach_unit_context(ctx: Any, sap_model: Any = None, set_units: bool = False) -> Any:
    """Attach unit context without mutating ETABS by default.

    ``set_units=True`` is an explicit legacy compatibility opt-in only.
    """
    unit_info = set_etabs_units_kn_m(sap_model) if set_units else read_etabs_units(sap_model)
    setattr(ctx, "unit_system", unit_info)

    if not hasattr(ctx, "design_basis") or ctx.design_basis is None:
        ctx.design_basis = {}

    ctx.design_basis["_unit_policy"] = UNIT_SYSTEM_KN_M_MPA["policy"]
    ctx.design_basis["_etabs_units"] = unit_info
    ctx.design_basis["_force_unit"] = "kN"
    ctx.design_basis["_length_unit"] = "m"
    ctx.design_basis["_moment_unit"] = "kN*m"
    ctx.design_basis["_stress_unit"] = "MPa"

    normalize_design_basis_units(ctx)
    return ctx
