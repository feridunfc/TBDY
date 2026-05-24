# app/checks/dependencies.py
"""Registry-driven dependency validation for engineering checks.

The goal of this module is deliberately narrow: decide the *engineering run
level* of a check before the check function executes, without mixing data
availability logic into the calculation code.

Check result = status (OK/FAIL/...) + run_level (DESIGN_LEVEL/APPROXIMATE/
SCREENING/NO_DATA) + missing data impact.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional



# YENİ
from tbdy_engine.checks.check_matrix import dependency_specs_from_matrix, get_check_spec
from tbdy_engine.engine.design_basis_audit import design_basis_verified   # (varsa)

class CheckLevel(str, Enum):
    DESIGN_LEVEL = "DESIGN_LEVEL"
    ETABS_DESIGN_RESULT = "ETABS_DESIGN_RESULT"   # ðŸ”¥ EKLE
    APPROXIMATE = "APPROXIMATE"
    SCREENING = "SCREENING"
    NO_DATA = "NO_DATA"


class DependencyStatus(str, Enum):
    RUN_DESIGN_LEVEL = "RUN_DESIGN_LEVEL"
    RUN_APPROXIMATE = "RUN_APPROXIMATE"
    RUN_SCREENING = "RUN_SCREENING"
    SKIP_NO_DATA = "SKIP_NO_DATA"
    FAIL_MISSING_CRITICAL = "FAIL_MISSING_CRITICAL"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass
class DependencyResult:
    check_name: str
    dependency_status: str
    run_level: str
    can_run: bool
    required_for_design_level: List[str]
    required_for_screening: List[str]
    available_data: List[str]
    missing_data: List[str]
    missing_critical: List[str]
    impact: str
    reason: str
    code_ref: str = ""
    selected_method: str = ""
    source_priority: list | None = None
    fallback_attempted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


SCREENING_NOTICE_TR = (
    "Bu kontrol SCREENING seviyesinde yapılmıştır; donatı veya ETABS design "
    "result tabloları bulunmadığı için TBDY tasarım yeterliliği kesin olarak "
    "doğrulanmamıştır."
)


def normalize_run_level(raw: Any) -> str:
    """Map descriptive registry levels to the strict reporting enum."""
    text = str(raw or "").strip().upper()
    allowed = {x.value for x in CheckLevel}

    if text in allowed:
        return text

    low = text.lower()

    if "etabs_design_result" in low or "etabs" in low:
        return CheckLevel.ETABS_DESIGN_RESULT.value

    if not low:
        return CheckLevel.APPROXIMATE.value
    if "no_data" in low:
        return CheckLevel.NO_DATA.value
    if "topology" in low or ("screening" in low and "design" not in low):
        return CheckLevel.SCREENING.value
    if low.startswith("design_level") or low == "design_level_geometry":
        return CheckLevel.DESIGN_LEVEL.value
    if "design_if" in low or "else_screening" in low or "until" in low or "if_" in low:
        return CheckLevel.APPROXIMATE.value
    if "screening" in low:
        return CheckLevel.SCREENING.value
    if "design" in low:
        return CheckLevel.DESIGN_LEVEL.value
    return CheckLevel.APPROXIMATE.value


DEPENDENCY_SPECS: Dict[str, Dict[str, Any]] = {
    "column_shear": {
        "code_ref": "TBDY 2018 §7.3.7",
        "design_required": ["column_transverse_rebar_defs"],
        "screening_required": ["column_forces", "frame_rect_sections"],
        "impact_screening": (
            "Bu kontrol SCREENING seviyesinde yapılmıştır; kolon kesme tasarım "
            "yeterliliği ETABS design result veya donatı tabloları olmadan kesin doğrulanamaz."
        ),
        "impact_no_data": (
            "Kolon kesme kontrolü için kolon kuvvet zarfı ve kesit geometrisi gerekir; "
            "bu veriler olmadan screening seviyesi bile güvenilir değildir."
        ),
    },
    "column_axial": {
        "code_ref": "TBDY 2018 §7.3.1",
        "design_table_required": ["column_design_summary"],
        "manual_design_required": ["column_forces", "frame_rect_sections", "design_basis.materials_present"],
        "design_required": ["column_forces", "frame_rect_sections", "design_basis.materials_present"],
        "screening_required": ["column_forces", "frame_rect_sections"],
        "impact_screening": (
            "Kolon eksenel yük kontrolü için kuvvet zarfı ve kesit geometrisi mevcut; "
            "malzeme kaynağı doğrulanmamışsa sonuç DESIGN_LEVEL yerine APPROXIMATE değerlendirilir."
        ),
        "impact_no_data": (
            "Kolon eksenel kontrolü için kolon kuvvet zarfı ve kesit alanı gerekir."
        ),
    },
    "column_confinement": {
        "code_ref": "TBDY 2018 §7.3.4.2",
        "design_required": ["column_rebar_defs"],
        "screening_required": ["frame_rect_sections"],
        "impact_screening": (
            "Kolon sargılama kontrolü SCREENING seviyesindedir; etriye aralığı, çiroz, "
            "kanca ve donatı detayları olmadan TBDY sargı yeterliliği kesin doğrulanamaz."
        ),
        "impact_no_data": (
            "Kolon sargılama kontrolü için en az kesit geometrisi gerekir; donatı detayı "
            "olmadan design-level kontrol yapılamaz."
        ),
    },
    "beam_shear": {
        "code_ref": "TBDY 2018 §7.4.2",
        "design_required": ["beam_transverse_rebar_defs"],
        "screening_required": ["beam_forces", "frame_rect_sections"],
        "impact_screening": (
            "Kiriş kesme kontrolü SCREENING seviyesindedir; ETABS beam design result veya "
            "kiriş donatı tabloları olmadan kesme tasarım yeterliliği kesin doğrulanamaz."
        ),
        "impact_no_data": (
            "Kiriş kesme kontrolü için kiriş kuvvet zarfı ve kesit geometrisi gerekir."
        ),
    },
    "second_order": {
        "code_ref": "TBDY 2018 §4.9.3",
        "design_required": ["story_forces", "story_drifts"],
        "screening_required": ["story_drifts"],
        "impact_screening": (
            "İkinci mertebe kontrolü SCREENING seviyesindedir; kat kesmeleri ve düşey yük "
            "toplamları doğrulanmadan θ_II tasarım seviyesi kesinliği taşımaz."
        ),
        "impact_no_data": (
            "İkinci mertebe etkileri için en az kat ötelenmeleri gerekir."
        ),
    },

    "joint_dimensions": {
        "code_ref": "TBDY 2018 §7.4.5(c)",
        "design_required": ["topology", "frame_rect_sections"],
        "screening_required": ["topology", "frame_rect_sections"],
        "impact_screening": (
            "Birleşim boyut kontrolü topology ve kesit geometrisi ile DESIGN_LEVEL geometri kontrolü olarak yapılabilir; "
            "birleşim kesme güvenliği ayrı kontroldür."
        ),
        "impact_no_data": "Birleşim boyut kontrolü için topology ve kesit geometrisi gerekir.",
    },

    "scwb": {
        "code_ref": "TBDY 2018 §7.3.5",
        "design_required": ["scwb_design"],
        "screening_required": ["scwb_capacity_inputs"],
        "fallback_level": "APPROXIMATE",
        "impact_screening": (
            "SCWB ETABS design tablosu bulunmadığı için kapasite hesabı beam/column donatı "
            "tabloları ve topology üzerinden APPROXIMATE seviyede yapılmıştır; eksenel yük-PMM "
            "etkileşimi ve kesin joint tasarım çıktısı doğrulanmadan nihai tasarım kanıtı değildir."
        ),
        "impact_no_data": (
            "SCWB kontrolü için ETABS scwb_design veya beam/column donatı + topology kapasite girdileri gerekir."
        ),
    },

    # --- FAZ 2 eklenen checkler ---

    "torsion": {
        "code_ref": "TBDY 2018 §3.6.2.1",
        "design_required": ["story_drifts"],
        "screening_required": ["story_drifts"],
    },

    "wall_shear": {
        "code_ref": "TBDY 2018 §7.6.6",
        "design_table_required": ["wall_design_summary"],
        "screening_required": ["pier_forces", "pier_sections"],
    },

    "wall_boundary_zone": {
        "title": "Perde uç bölgesi kontrolü",
        "category": "Perde Tasarımı",
        "code_ref": "TBDY 2018 §7.6.2.4",
        "design_table_required": ["wall_design_summary"],
        "required_tables": ["wall_design_summary"],
        "optional_tables": ["pier_forces", "pier_sections"],
        "requires_topology": False,
        "requires_force_envelope": False,
        "requires_reinforcement": True,
    },

    "column_dimensions": {
        "code_ref": "TBDY 2018 §7.3.2",
        "design_required": ["frame_rect_sections", "frame_assigns_section"],
        "screening_required": ["frame_rect_sections"],
    },

    "beam_dimensions": {
        "code_ref": "TBDY 2018 §7.4.1",
        "design_required": ["frame_rect_sections", "frame_assigns_section"],
        "screening_required": ["frame_rect_sections"],
    },
    "beta_x": {
        "code_ref": "TBDY 2018 §4.8.2",
        "design_required": ["auto_seismic", "base_reactions"],
    },

    "beta_y": {
        "code_ref": "TBDY 2018 §4.8.2",
        "design_required": ["auto_seismic", "base_reactions"],
    },
    "base_shear_limit": {
        "code_ref": "TBDY 2018 §4.8.2",
        "design_required": ["auto_seismic", "base_reactions"],
    },
    "soft_story": {
        "code_ref": "TBDY 2018 §3.6.1",
        "screening_required": ["story_drifts", "story_forces"],
    },
}


# Matrix-derived specs are the baseline for new checks. Hand-tuned specs above
# remain authoritative for matured checks; missing fields are backfilled from the
# matrix so dependency validation, registry and report narratives stay aligned.
for _matrix_name, _matrix_spec in dependency_specs_from_matrix().items():
    if _matrix_name not in DEPENDENCY_SPECS:
        DEPENDENCY_SPECS[_matrix_name] = _matrix_spec
    else:
        for _k, _v in _matrix_spec.items():
            DEPENDENCY_SPECS[_matrix_name].setdefault(_k, _v)


ALIASES: Dict[str, List[str]] = {
    "column_forces": ["table:column_forces", "envelope:column_forces", "attr:column_forces_df"],
    "beam_forces": ["table:beam_forces", "envelope:beam_forces", "attr:beam_forces_df"],
    "pier_forces": ["table:pier_forces", "envelope:pier_forces", "attr:pier_forces_df"],
    "story_forces": ["table:story_forces", "envelope:story_shear_x", "envelope:story_shear_y"],
    "story_drifts": ["table:story_drifts"],
    "frame_rect_sections": ["table:frame_rect_sections"],
    "frame_assigns_section": ["table:frame_assigns_section"],
    "column_design_summary": ["table:column_design_summary", "design_metadata:column_design_summary"],
    "beam_design_summary": ["table:beam_design_summary", "design_metadata:beam_design_summary"],
    "scwb_design": ["table:scwb_design", "design_metadata:scwb_design"],
    "column_rebar_defs": ["table:column_rebar_defs", "design_metadata:column_rebar_defs"],
    "beam_rebar_defs": ["table:beam_rebar_defs", "design_metadata:beam_rebar_defs"],
}


def _has_rows(value: Any) -> bool:
    if value is None:
        return False
    try:
        if hasattr(value, "empty"):
            return not bool(value.empty)
        if isinstance(value, Mapping):
            return len(value) > 0
        if isinstance(value, (list, tuple, set)):
            return len(value) > 0
        return True
    except Exception:
        return False


def _get_path(ctx: Any, token: str) -> Any:
    kind, _, key = token.partition(":")
    if kind == "table":
        return (getattr(ctx, "tables", {}) or {}).get(key)
    if kind == "envelope":
        return (getattr(ctx, "envelopes", {}) or {}).get(key)
    if kind == "design_metadata":
        return (getattr(ctx, "design_metadata", {}) or {}).get(key)
    if kind == "attr":
        return getattr(ctx, key, None)
    if kind == "topology":
        return (getattr(ctx, "topology", {}) or {}).get(key)
    if kind == "geometry":
        return (getattr(ctx, "geometry", {}) or {}).get(key)
    return None



def _df_has_any_columns(ctx: Any, data_key: str, candidates: List[str]) -> bool:
    val = None
    for token in ALIASES.get(data_key, [f"table:{data_key}"]):
        v = _get_path(ctx, token)
        if _has_rows(v):
            val = v
            break
    if val is None or not hasattr(val, "columns"):
        return False
    cols = {str(c).lower().replace(" ", "").replace("_", "") for c in val.columns}
    for cand in candidates:
        key = cand.lower().replace(" ", "").replace("_", "")
        if any(key in c for c in cols):
            return True
    return False


def _has_scwb_capacity_inputs(ctx: Any) -> bool:
    if not data_available(ctx, "frame_rect_sections"):
        return False
    if not data_available(ctx, "beam_rebar_defs") or not data_available(ctx, "column_rebar_defs"):
        return False
    topo = getattr(ctx, "topology", {}) or {}
    return _has_rows(topo.get("column_beam_map"))

def data_available(ctx: Any, data_key: str) -> bool:
    if data_key == "design_basis.materials_present":
        basis = getattr(ctx, "design_basis", {}) or {}
        return bool((basis.get("fck_mpa") or 0) and (basis.get("fyk_mpa") or 0))
    if data_key == "topology":
        topo = getattr(ctx, "topology", {}) or {}
        return bool(topo.get("analysis_joints") or topo.get("columns") or topo.get("column_beam_map"))
    if data_key == "column_transverse_rebar_defs":
        return data_available(ctx, "column_rebar_defs") and _df_has_any_columns(ctx, "column_rebar_defs", ["barsizeconf", "spacingconf", "tie_spacing", "hoop_spacing"])
    if data_key == "beam_transverse_rebar_defs":
        return data_available(ctx, "beam_rebar_defs") and _df_has_any_columns(ctx, "beam_rebar_defs", ["stirrup", "barsizeshear", "spacingshear", "tie_spacing", "hoop_spacing"])
    if data_key == "scwb_capacity_inputs":
        return _has_scwb_capacity_inputs(ctx)
    if data_key == "design_basis.materials_verified":
        basis = getattr(ctx, "design_basis", {}) or {}
        if basis.get("materials_verified") is True:
            return True
        if basis.get("material_policy") == "GLOBAL_C30_B500_FOR_ACTIVE_MODEL":
            return True
        fck_ok = (basis.get("fck_mpa") or 0) not in (None, "", 0)
        fyk_ok = (basis.get("fyk_mpa") or 0) not in (None, "", 0)
        sources = basis.get("sources", {}) or {}
        # template values are usable for screening but not trusted as verified design basis unless explicit project policy is stamped.
        src_text = " ".join(str(sources.get(k, "")).lower() for k in ("fck_mpa", "fyk_mpa"))
        return bool(fck_ok and fyk_ok and not ("template" in src_text or "default" in src_text))
    tokens = ALIASES.get(data_key, [f"table:{data_key}"])
    return any(_has_rows(_get_path(ctx, token)) for token in tokens)



def _row_count(value: Any) -> int:
    if value is None:
        return 0
    try:
        if hasattr(value, "__len__"):
            return int(len(value))
    except Exception:
        pass
    return 1 if _has_rows(value) else 0


def data_row_count(ctx: Any, data_key: str) -> int:
    tokens = ALIASES.get(data_key, [f"table:{data_key}"])
    counts = [_row_count(_get_path(ctx, token)) for token in tokens]
    return max(counts or [0])


def _topology_count(ctx: Any, key: str) -> int:
    val = (getattr(ctx, "topology", {}) or {}).get(key)
    n = _row_count(val)
    if n:
        return n
    try:
        return int(((getattr(ctx, "notes", {}) or {}).get("summary") or {}).get(key) or 0)
    except Exception:
        return 0


def _column_confinement_coverage_low(ctx: Any) -> tuple[bool, str]:
    """Detect insufficient rebar definition coverage for confinement."""
    col_count = _topology_count(ctx, "columns")
    rebar_rows = data_row_count(ctx, "column_rebar_defs")
    if col_count <= 0 or rebar_rows <= 0:
        return False, ""
    ratio = rebar_rows / max(col_count, 1)
    if rebar_rows < col_count and ratio < 0.50:
        return True, f"column_rebar_defs coverage low: {rebar_rows} rows for {col_count} columns"
    return False, ""

def _manual_design_keys_for(check_name: str, spec: Dict[str, Any]) -> List[str]:
    keys = list(spec.get("manual_design_required", []) or [])
    if keys:
        return keys
    if check_name == "beam_shear":
        return ["beam_transverse_rebar_defs", "design_basis.materials_verified"]
    if check_name == "column_shear":
        return ["column_transverse_rebar_defs", "design_basis.materials_verified"]
    if check_name == "scwb":
        return ["scwb_capacity_inputs", "design_basis.materials_verified"]
    if check_name == "column_confinement":
        return ["column_rebar_defs", "design_basis.materials_verified"]
    return list(spec.get("design_required", []) or [])


def _design_table_keys_for(check_name: str, spec: Dict[str, Any]) -> List[str]:
    keys = list(spec.get("design_table_required", []) or [])
    if keys:
        return keys
    if check_name == "beam_shear":
        return ["beam_design_summary"]
    if check_name in {"column_shear", "column_axial"}:
        return ["column_design_summary"]
    if check_name == "scwb":
        return ["scwb_design"]
    return []


def _basis_missing_for_manual(ctx: Any, keys: List[str]) -> bool:
    return "design_basis.materials_verified" in keys and not design_basis_verified(ctx)


def _mk_dep(check_name: str, dependency_status: str, run_level: str, can_run: bool,
            design_required: List[str], screening_required: List[str], available: List[str],
            missing_data: List[str], missing_critical: List[str], impact: str, reason: str,
            code_ref: str, selected_method: str, fallback_attempted: bool) -> DependencyResult:
    return DependencyResult(
        check_name=check_name, dependency_status=dependency_status, run_level=run_level, can_run=can_run,
        required_for_design_level=design_required, required_for_screening=screening_required,
        available_data=available, missing_data=missing_data, missing_critical=missing_critical,
        impact=impact, reason=reason, code_ref=code_ref, selected_method=selected_method,
        source_priority=["ETABS_DESIGN_RESULT", "MANUAL_FORMULA", "SCREENING_FALLBACK", "NO_DATA"],
        fallback_attempted=fallback_attempted,
    )


def evaluate_check_dependency(ctx: Any, check_name: str, metadata: Optional[Dict[str, Any]] = None) -> DependencyResult:
    spec = DEPENDENCY_SPECS.get(check_name)
    code_ref = (metadata or {}).get("code_ref", "")

    if spec is None:
        required = list((metadata or {}).get("required_tables", []) or [])
        available = [k for k in required if data_available(ctx, k)]
        missing = [k for k in required if k not in available]
        raw_level = (metadata or {}).get("level", "APPROXIMATE")
        return _mk_dep(check_name, DependencyStatus.NOT_EVALUATED.value, normalize_run_level(raw_level), True, required, [], available, missing, [],
                       "Bu check için ayrıntılı dependency modeli henüz tanımlı değildir; mevcut check içi veri kontrolleri kullanılmaktadır.",
                       f"metadata_only: {raw_level}", code_ref, "CHECK_INTERNAL_VALIDATION", False)

    design_table_keys = _design_table_keys_for(check_name, spec)
    manual_design_keys = _manual_design_keys_for(check_name, spec)
    screening_required = list(spec.get("screening_required", []) or [])
    design_required = list(dict.fromkeys(design_table_keys + manual_design_keys))
    all_keys = list(dict.fromkeys(design_required + screening_required))
    available = [k for k in all_keys if data_available(ctx, k)]

    design_tables_available = [k for k in design_table_keys if data_available(ctx, k)]
    if design_tables_available:
        return _mk_dep(
            check_name,
            DependencyStatus.RUN_DESIGN_LEVEL.value,
            "ETABS_DESIGN_RESULT",  # ðŸ”¥ BURASI DEĞİŞTİ
            True,
            design_required,
            screening_required,
            available,
            [k for k in design_required if k not in available],
            [],
            "ETABS design result tablosu bulundu; ETABS tasarım sonucu birincil veri kaynağıdır.",
            "design_result_available: " + ", ".join(design_tables_available),
            str(spec.get("code_ref") or code_ref),
            "ETABS_DESIGN_RESULT",
            False
        )

    missing_screening = [k for k in screening_required if k not in available]
    if missing_screening:
        return _mk_dep(check_name, DependencyStatus.SKIP_NO_DATA.value, CheckLevel.NO_DATA.value, False, design_required, screening_required, available,
                       list(dict.fromkeys([k for k in design_required if k not in available] + missing_screening)), missing_screening,
                       str(spec.get("impact_no_data") or "Minimum veri eksik; check güvenilir çalıştırılamaz."),
                       "missing minimum data " + ", ".join(missing_screening), str(spec.get("code_ref") or code_ref), "NO_DATA", True)

    manual_missing = [k for k in manual_design_keys if k not in available]
    if _basis_missing_for_manual(ctx, manual_design_keys) and "design_basis.materials_verified" not in manual_missing:
        manual_missing.append("design_basis.materials_verified")

    if not manual_missing:
        if check_name == "column_confinement":
            low_coverage, cov_reason = _column_confinement_coverage_low(ctx)
            if low_coverage:
                return _mk_dep(check_name, DependencyStatus.RUN_SCREENING.value, CheckLevel.SCREENING.value, True, design_required, screening_required, available,
                               ["column_rebar_defs_coverage"], [],
                               "Kolon sargılama kontrolü SCREENING seviyesine düşürülmüştür; eleman-bazlı donatı/sargılama detayı kapsaması doğrulanamamıştır.",
                               cov_reason, str(spec.get("code_ref") or code_ref), "SCREENING_FALLBACK_LOW_COVERAGE", True)
        return _mk_dep(check_name, DependencyStatus.RUN_DESIGN_LEVEL.value, CheckLevel.DESIGN_LEVEL.value, True, design_required, screening_required, available,
                       design_table_keys, [],
                       "ETABS design result tablosu yok; gerekli ham veri mevcut olduğu için bağımsız manuel formül hesabı DESIGN_LEVEL olarak çalıştırılır. ETABS tablosu gelirse ayrıca cross-check yapılmalıdır.",
                       "manual_design_inputs_available; missing design table " + ", ".join(design_table_keys or ["â€”"]), str(spec.get("code_ref") or code_ref), "MANUAL_FORMULA", True)

    if spec.get("allow_screening") is False:
        return _mk_dep(check_name, DependencyStatus.SKIP_NO_DATA.value, CheckLevel.NO_DATA.value, False, design_required, screening_required, available, manual_missing, manual_missing,
                       str(spec.get("impact_no_data") or "Design-level data is mandatory; this check is skipped."),
                       "missing design table and manual design inputs " + ", ".join(manual_missing), str(spec.get("code_ref") or code_ref), "NO_DATA", True)

    fallback_level = str(spec.get("fallback_level") or CheckLevel.SCREENING.value).upper()
    if fallback_level not in {x.value for x in CheckLevel}:
        fallback_level = CheckLevel.SCREENING.value
    dep_status = DependencyStatus.RUN_APPROXIMATE.value if fallback_level == CheckLevel.APPROXIMATE.value else DependencyStatus.RUN_SCREENING.value
    return _mk_dep(check_name, dep_status, fallback_level, True, design_required, screening_required, available,
                   list(dict.fromkeys(design_table_keys + manual_missing)), [],
                   str(spec.get("impact_screening") or SCREENING_NOTICE_TR),
                   "design table missing; manual design inputs missing " + ", ".join(manual_missing), str(spec.get("code_ref") or code_ref), "SCREENING_FALLBACK", True)

def build_dependency_report(dependencies: Mapping[str, DependencyResult | Dict[str, Any]]) -> Dict[str, Any]:
    items: Dict[str, Any] = {}
    counts: Dict[str, int] = {}
    for name, dep in dependencies.items():
        d = dep.to_dict() if hasattr(dep, "to_dict") else dict(dep)
        items[name] = d
        status = str(d.get("dependency_status", "UNKNOWN"))
        counts[status] = counts.get(status, 0) + 1
    return {"summary": counts, "checks": items}


def attach_dependency_to_check(check: Dict[str, Any], dep: DependencyResult) -> Dict[str, Any]:
    out = dict(check or {})
    dep_dict = dep.to_dict()
    out.setdefault("check", dep.check_name)
    out["dependency"] = dep_dict
    out["dependency_status"] = dep.dependency_status
    out["run_level"] = dep.run_level
    out["engineering_level"] = dep.run_level
    out["required_for_design_level"] = list(dep.required_for_design_level)
    out["required_for_screening"] = list(dep.required_for_screening)
    out["available_data"] = list(dep.available_data)
    out["missing_data"] = list(dep.missing_data)
    out["missing_critical"] = list(dep.missing_critical)
    out["missing_data_impact"] = dep.impact
    out["impact"] = dep.impact
    out["dependency_reason"] = dep.reason
    out["selected_method"] = dep.selected_method
    out["source_priority"] = list(dep.source_priority or [])
    out["fallback_attempted"] = bool(dep.fallback_attempted)
    if dep.code_ref and not out.get("code_ref"):
        out["code_ref"] = dep.code_ref
    matrix_spec = get_check_spec(dep.check_name)
    if matrix_spec:
        out["check_matrix"] = matrix_spec
        out.setdefault("formula", matrix_spec.get("formula"))
        out.setdefault("formula_detail", matrix_spec.get("detail", {}))
        out.setdefault("code", matrix_spec.get("code"))
        out.setdefault("clause", matrix_spec.get("clause"))
        out.setdefault("etabs_table", matrix_spec.get("etabs_table"))
        out.setdefault("cross_check_expected", bool(matrix_spec.get("cross_check")))
        out.setdefault("tolerance", matrix_spec.get("tolerance"))
    if dep.run_level == CheckLevel.SCREENING.value:
        out["confidence"] = "LOW"
    elif dep.run_level == CheckLevel.APPROXIMATE.value:
        out["confidence"] = "LOW"
    elif dep.run_level == CheckLevel.ETABS_DESIGN_RESULT.value:
        out["confidence"] = "MEDIUM"
    elif dep.run_level == CheckLevel.DESIGN_LEVEL.value:
        out["confidence"] = "HIGH"
    elif dep.run_level == CheckLevel.NO_DATA.value:
        out["confidence"] = "LOW"
    return out


def make_no_data_result(dep: DependencyResult) -> Dict[str, Any]:
    return attach_dependency_to_check(
        {
            "check": dep.check_name,
            "status": "NO_DATA",
            "message": dep.impact,
            "reason": dep.reason,
            "code_ref": dep.code_ref,
        },
        dep,
    )



