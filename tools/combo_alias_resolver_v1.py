from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import yaml
except Exception:
    yaml = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CONTRACTS_DIR = PROJECT_ROOT / "tbdy_engine" / "contracts"
REPORTS_OUT = PROJECT_ROOT / "reports_out"

DEFAULT_FAMILIES: Dict[str, Dict[str, Any]] = {
    "G": {
        "purpose": "gravity",
        "aliases": [
            "G", "D", "DL", "DEAD", "DEADLOAD", "ÖLÜ", "OLU", "SABIT",
            "Q", "L", "LL", "LIVE", "LIVELOAD", "HAREKETLI",
            "G+Q", "D+L", "1.4G", "1.4D", "1.2G+1.6Q", "1.2D+1.6L",
            "GRAVITY", "GRAVITY_STRENGTH", "GRAVITY_SERVICE",
        ],
        "patterns": [
            r"^\s*(?:1\.4\s*)?[GD]\s*$",
            r"^\s*[GD]\s*[+]\s*[QL]\s*$",
            r"^\s*1\.2\s*[GD]\s*[+]\s*1\.6\s*[QL]\s*$",
            r"DEAD|LIVE|GRAVITY|SABIT|HAREKET",
        ],
    },
    "S_E": {
        "purpose": "seismic_strength",
        "aliases": [
            "S_E", "SE", "E", "EQ", "EQX", "EQY", "EX", "EY", "E-X", "E+X", "E-Y", "E+Y",
            "DEPREM", "EARTHQUAKE", "QUAKE", "RS", "SPEC", "RESPONSE", "RESPONSE_SPECTRUM",
            "SPECX", "SPECY", "RSX", "RSY", "SX", "SY",
            "G+0.3Q+EX", "G+0.3Q-EX", "G+0.3Q+EY", "G+0.3Q-EY",
            "G+Q+EX", "G+Q-EX", "G+Q+EY", "G+Q-EY",
            "D+0.3L+EX", "D+0.3L-EX", "D+0.3L+EY", "D+0.3L-EY",
        ],
        "patterns": [
            r"\bE\s*[+-]?\s*X\b", r"\bE\s*[+-]?\s*Y\b",
            r"\bEX\b", r"\bEY\b", r"\bEQX?\b", r"\bEQY\b",
            r"DEPREM|EARTH|QUAKE|SEISMIC",
            r"RESPONSE|SPECTRUM|SPEC|RS",
            r"[GD]\s*[+]\s*(?:0\.3\s*)?[QL]\s*[+]\s*E[XY]",
            r"[GD]\s*[+]\s*(?:0\.3\s*)?[QL]\s*[-]\s*E[XY]",
        ],
    },
    "K_E": {
        "purpose": "capacity_design_shear",
        "aliases": [
            "K_E", "KE", "KEX", "KEY", "K_E_X", "K_E_Y",
            "CAPACITY", "CAPACITY_X", "CAPACITY_Y",
            "KAPASITE", "KAPASITE_X", "KAPASITE_Y",
            "SHEAR_CAPACITY", "DESIGN_SHEAR", "KESME", "KAPASITE_KESME",
        ],
        "patterns": [
            r"\bK\s*[_\-\s]?\s*E\s*[_\-\s]?[XY]?\b",
            r"CAPACITY|KAPASITE",
            r"SHEAR\s*CAPACITY|DESIGN\s*SHEAR|KESME",
        ],
    },
    "DRIFT": {
        "purpose": "drift",
        "aliases": [
            "DRIFT", "DRIFT_X", "DRIFT_Y", "STORY_DRIFT", "STOREY_DRIFT",
            "DISP", "DISPLACEMENT", "DEPLASMAN", "UX", "UY",
        ],
        "patterns": [
            r"DRIFT", r"STORE?Y\s*DRIFT", r"DISP|DISPLACEMENT|DEPLAS", r"\bU[XY]\b",
        ],
    },
    "SOIL": {
        "purpose": "foundation_soil",
        "aliases": ["SOIL", "FOUNDATION", "BEARING", "UPLIFT", "ZEMIN", "TEMEL"],
        "patterns": [r"SOIL|FOUND|BEARING|UPLIFT|ZEMIN|TEMEL"],
    },
}

CHECK_REQUIRED_FAMILY = {
    "column_pmm": "S_E",
    "column_axial": "S_E",
    "column_shear": "K_E",
    "column_capacity_hierarchy": "S_E",
    "column_confinement": "S_E",
    "beam_flexure": "S_E",
    "beam_shear": "K_E",
    "beam_capacity_hierarchy": "S_E",
    "beam_ductility": "S_E",
}

def normalize_combo_name(name: str) -> str:
    s = str(name or "").strip().upper()

    # Turkish / Unicode normalization.
    # Important: str.translate keys must be single Unicode codepoints.
    trans = str.maketrans({
        "İ": "I",
        "ı": "I",
        "Ş": "S",
        "Ğ": "G",
        "Ü": "U",
        "Ö": "O",
        "Ç": "C",
        "ş": "S",
        "ğ": "G",
        "ü": "U",
        "ö": "O",
        "ç": "C",
    })
    s = s.translate(trans)

    # Defensive cleanup for decomposed Turkish İ: I + combining dot above.
    s = s.replace(chr(0x0307), "")

    s = s.replace("×", "X")
    s = re.sub(r"\bLOAD\s*COMBO\b", "", s)
    s = re.sub(r"\bCOMBO\b", "", s)
    s = re.sub(r"\s+", "", s)
    s = s.replace("_", "")
    return s


def _merge_unique(a: List[Any], b: List[Any]) -> List[Any]:
    out = []
    seen = set()
    for x in list(a or []) + list(b or []):
        sx = str(x)
        if sx not in seen:
            seen.add(sx)
            out.append(x)
    return out

def load_contract_families() -> Dict[str, Dict[str, Any]]:
    families = {k: dict(v) for k, v in DEFAULT_FAMILIES.items()}
    path = CONTRACTS_DIR / "combos.yaml"
    if yaml and path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
            raw = data.get("combo_families") or data.get("families") or {}
            if isinstance(raw, list):
                items = {}
                for item in raw:
                    if isinstance(item, dict):
                        fid = item.get("id") or item.get("name")
                        if fid:
                            items[str(fid)] = item
                raw = items
            if isinstance(raw, dict):
                for fid, spec in raw.items():
                    if not isinstance(spec, dict):
                        spec = {}
                    fid = str(fid)
                    base = families.get(fid, {})
                    merged = dict(base)
                    merged.update(spec)
                    merged["aliases"] = _merge_unique(base.get("aliases", []), spec.get("aliases", []) or spec.get("etabs_names", []))
                    merged["patterns"] = _merge_unique(base.get("patterns", []), spec.get("patterns", []))
                    families[fid] = merged
        except Exception:
            pass
    return families

def resolve_combo_family(raw_name: str, required_family: str = "", families: Dict[str, Dict[str, Any]] | None = None) -> Dict[str, Any]:
    families = families or load_contract_families()
    raw = str(raw_name or "").strip()

    if not raw:
        return {
            "raw_combo": raw,
            "resolved_family": "",
            "resolved_by": "empty",
            "confidence": 0.0,
            "required_family": required_family,
            "matches_required_family": not required_family,
            "is_fallback_marker": False,
        }

    if raw.startswith("UNEXPOSED_ETABS_COMBO::"):
        fam = raw.split("::", 1)[1]
        return {
            "raw_combo": raw,
            "resolved_family": fam,
            "resolved_by": "required_family_fallback",
            "confidence": 0.2,
            "required_family": required_family,
            "matches_required_family": (not required_family or fam == required_family),
            "is_fallback_marker": True,
        }

    norm = normalize_combo_name(raw)

    # Exact family id / exact alias.
    for fid, spec in families.items():
        if normalize_combo_name(fid) == norm:
            return _result(raw, fid, "family_id_exact", 1.0, required_family)
        for alias in spec.get("aliases", []) or []:
            if normalize_combo_name(alias) == norm:
                return _result(raw, fid, "alias_exact", 0.98, required_family)

    # Strong seismic/capacity/drift patterns before generic gravity.
    priority = ["S_E", "K_E", "DRIFT", "SOIL", "G"]
    for fid in priority + [x for x in families if x not in priority]:
        spec = families.get(fid, {})
        for pat in spec.get("patterns", []) or []:
            try:
                if re.search(str(pat), raw, re.I):
                    return _result(raw, fid, "pattern", 0.88, required_family)
            except re.error:
                continue

    # Alias contains, but avoid one-letter generic aliases stealing mixed combos.
    for fid in priority + [x for x in families if x not in priority]:
        spec = families.get(fid, {})
        for alias in spec.get("aliases", []) or []:
            an = normalize_combo_name(alias)
            if an and len(an) > 1 and an in norm:
                return _result(raw, fid, "alias_contains", 0.72, required_family)

    # Heuristic fallback.
    if re.search(r"E[XY]|EX|EY|EQ|RS|SPEC|DEPREM|EARTH|QUAKE", raw, re.I):
        return _result(raw, "S_E", "heuristic_seismic_token", 0.65, required_family)
    if re.search(r"K[_\-\s]?E|CAPACITY|KAPASITE|SHEAR|KESME", raw, re.I):
        return _result(raw, "K_E", "heuristic_capacity_token", 0.65, required_family)
    if re.search(r"DRIFT|DISP|DEPLAS", raw, re.I):
        return _result(raw, "DRIFT", "heuristic_drift_token", 0.65, required_family)
    if re.search(r"\b[GD]\b|\b[QL]\b|DEAD|LIVE|GRAVITY", raw, re.I):
        return _result(raw, "G", "heuristic_gravity_token", 0.55, required_family)

    return {
        "raw_combo": raw,
        "resolved_family": "",
        "resolved_by": "unmapped",
        "confidence": 0.0,
        "required_family": required_family,
        "matches_required_family": not required_family,
        "is_fallback_marker": False,
    }

def _result(raw: str, family: str, by: str, conf: float, required_family: str) -> Dict[str, Any]:
    return {
        "raw_combo": raw,
        "resolved_family": family,
        "resolved_by": by,
        "confidence": conf,
        "required_family": required_family,
        "matches_required_family": (not required_family or family == required_family),
        "is_fallback_marker": False,
    }

def resolve_report(report: Dict[str, Any]) -> Dict[str, Any]:
    families = load_contract_families()
    rows = [r for r in report.get("checks", []) if isinstance(r, dict)]
    mismatch = []
    resolved_count = 0
    fallback_count = 0

    for r in rows:
        cid = str(r.get("check_id") or "")
        required = str(r.get("combo_family") or CHECK_REQUIRED_FAMILY.get(cid, "") or "")
        raw = str(r.get("raw_combo") or r.get("governing_combo") or "")
        res = resolve_combo_family(raw, required_family=required, families=families)

        r["combo_required_family"] = required
        r["combo_resolved_family"] = res["resolved_family"]
        r["combo_resolved_by_v1"] = res["resolved_by"]
        r["combo_resolution_confidence"] = res["confidence"]
        r["combo_matches_required_family"] = res["matches_required_family"]

        # Keep existing combo_family unless empty, but expose resolved family separately.
        if not r.get("combo_family") and res["resolved_family"]:
            r["combo_family"] = res["resolved_family"]

        if res["resolved_family"]:
            resolved_count += 1
        if res["is_fallback_marker"]:
            fallback_count += 1
        if required and res["resolved_family"] and res["resolved_family"] != required:
            mismatch.append({
                "check_id": cid,
                "element_label": r.get("element_label", ""),
                "raw_combo": raw,
                "required_family": required,
                "resolved_family": res["resolved_family"],
                "resolved_by": res["resolved_by"],
            })
            r["combo_resolution_warning"] = "resolved_family_does_not_match_required_family"

    meta = dict(report.get("report_metadata") or {})
    meta["combo_alias_resolver"] = "Genesis Combo Alias Resolver v1"
    meta["combo_alias_resolver_applied_at"] = datetime.now().isoformat(timespec="seconds")
    if "schema" in meta and "combo_alias.v1" not in str(meta["schema"]):
        meta["schema"] = str(meta["schema"]) + "+combo_alias.v1"
    report["report_metadata"] = meta

    report["combo_alias_summary"] = {
        "total_rows": len(rows),
        "rows_with_required_family": sum(1 for r in rows if r.get("combo_required_family")),
        "rows_resolved": resolved_count,
        "rows_fallback_marker": fallback_count,
        "rows_mismatch": len(mismatch),
        "resolved_by": dict(Counter(str(r.get("combo_resolved_by_v1") or "<empty>") for r in rows)),
        "resolved_family": dict(Counter(str(r.get("combo_resolved_family") or "<empty>") for r in rows)),
        "mismatches": mismatch[:500],
    }
    report["checks"] = rows
    return report

def unique_raw_combo_audit(report: Dict[str, Any]) -> Dict[str, Any]:
    rows = [r for r in report.get("checks", []) if isinstance(r, dict)]
    unique = sorted(set(str(r.get("raw_combo") or r.get("governing_combo") or "") for r in rows if r.get("raw_combo") or r.get("governing_combo")))
    items = []
    for raw in unique:
        requireds = sorted(set(str(r.get("combo_family") or CHECK_REQUIRED_FAMILY.get(str(r.get("check_id") or ""), "") or "") for r in rows if str(r.get("raw_combo") or r.get("governing_combo") or "") == raw))
        res = resolve_combo_family(raw, required_family=requireds[0] if len(requireds) == 1 else "")
        items.append({
            "raw_combo": raw,
            "required_families_seen": requireds,
            "resolved_family": res["resolved_family"],
            "resolved_by": res["resolved_by"],
            "confidence": res["confidence"],
            "is_fallback_marker": res["is_fallback_marker"],
            "row_count": sum(1 for r in rows if str(r.get("raw_combo") or r.get("governing_combo") or "") == raw),
        })
    return {
        "unique_raw_combo_count": len(unique),
        "mapped_unique": sum(1 for x in items if x["resolved_family"]),
        "unmapped_unique": sum(1 for x in items if not x["resolved_family"]),
        "items": items,
    }

def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    import csv
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
