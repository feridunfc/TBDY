"""
tbdy_engine/runner.py - DÜZELTİLMİŞ

Değişiklikler:
- _check_data_available: ctx.tables DIŞINDA ctx.geometry, ctx.design_metadata,
  ctx.topology, ctx.envelopes, ctx.design_basis altındaki verileri de tanır.
"""

from __future__ import annotations

import asyncio
import logging
import pandas as pd
from typing import Any, Dict, Iterable, List, Optional

from .checks.registry import registry
from .etabs.connection import check_etabs_connection

logger = logging.getLogger(__name__)


# =============================================================================
# STATUS / EVALUATION LEVEL SABİTLERİ
# =============================================================================

class EvaluationLevel:
    ETABS_DESIGN_RESULT = "ETABS_DESIGN_RESULT"
    DESIGN_LEVEL = "DESIGN_LEVEL"
    APPROXIMATE = "APPROXIMATE"
    SCREENING = "SCREENING"
    METADATA_ONLY = "METADATA_ONLY"
    NO_DATA = "NO_DATA"


class ExecutionStatus:
    EVALUATED = "EVALUATED"
    SKIPPED = "SKIPPED"
    NOT_EVALUATED = "NOT_EVALUATED"


ALLOWED_STATUSES = {"OK", "FAIL", "WARNING", "NO_DATA", "NOT_EVALUATED", "ERROR", "PARTIAL"}

_EVAL_LEVEL_TO_CONFIDENCE: Dict[str, str] = {
    EvaluationLevel.ETABS_DESIGN_RESULT: "HIGH",
    EvaluationLevel.DESIGN_LEVEL: "HIGH",
    EvaluationLevel.APPROXIMATE: "MEDIUM",
    EvaluationLevel.SCREENING: "MEDIUM",
    EvaluationLevel.METADATA_ONLY: "LOW",
    EvaluationLevel.NO_DATA: "LOW",
}


# =============================================================================
# DUMMY CONTEXT
# =============================================================================

class DummyContext:
    """Test/debug için minimal context."""

    _is_dummy: bool = True

    def __init__(self):
        self.design_basis = {
            "fck_mpa": 30.0, "fyk_mpa": 420.0,
            "gamma_c": 1.5, "gamma_s": 1.15,
            "fcd_mpa": 20.0, "fyd_mpa": 365.22, "fywd_mpa": 365.22,
        }

        self.geometry = {
            "section_dims": {
                "C30x50": {"width_m": 0.30, "depth_m": 0.50, "b_min_m": 0.30, "b_max_m": 0.50},
                "C40x60": {"width_m": 0.40, "depth_m": 0.60, "b_min_m": 0.40, "b_max_m": 0.60},
                "C25x25": {"width_m": 0.25, "depth_m": 0.25, "b_min_m": 0.25, "b_max_m": 0.25},
            },
            "column_sections": {"C1": "C30x50", "C2": "C40x60", "C3": "C25x25"},
        }

        self.topology = {
            "columns": [
                {"label": "C1", "story": "Story1", "section": "C30x50"},
                {"label": "C2", "story": "Story2", "section": "C40x60"},
                {"label": "C3", "story": "Story1", "section": "C25x25"},
            ],
            "column_beam_map": [
                {"column_label": "C1"}, {"column_label": "C2"},
            ],
        }

        self.story_height_map = {"Story1": 3.0, "Story2": 3.0}

        self.envelopes = {
            "column_forces_map": {
                "C1": {"P_max": -1500, "M2_max": 80, "M3_max": 160, "V2_max": 90, "V3_max": 50, "P_case": "EQX"},
                "C2": {"P_max": -2200, "M2_max": 100, "M3_max": 220, "V2_max": 130, "V3_max": 70, "P_case": "EQX"},
                "C3": {"P_max": -800, "M2_max": 30, "M3_max": 50, "V2_max": 40, "V3_max": 25, "P_case": "EQY"},
            }
        }

        self.design_metadata = {
            "column_rebar_defs": pd.DataFrame([
                {"label": "C1", "nbarstotal": 8, "bardiameter": 18.0,
                 "stirrupdiameter": 10.0, "stirrupspacing": 100.0,
                 "stirrup_legs_dir1": 2, "stirrup_legs_dir2": 2},
                {"label": "C2", "nbarstotal": 10, "bardiameter": 20.0,
                 "stirrupdiameter": 10.0, "stirrupspacing": 120.0,
                 "stirrup_legs_dir1": 3, "stirrup_legs_dir2": 2},
                {"label": "C3", "nbarstotal": 4, "bardiameter": 12.0,
                 "stirrupdiameter": 8.0, "stirrupspacing": 200.0,
                 "stirrup_legs_dir1": 2, "stirrup_legs_dir2": 2},
            ]),
            "column_design_summary": pd.DataFrame([
                {"label": "C1", "pm_ratio": 0.72},
                {"label": "C2", "pm_ratio": 1.15},
            ]),
        }

        self.tables = {}
        self.notes = {"tables_loaded": []}


def _is_dummy_context(ctx: Any) -> bool:
    if isinstance(ctx, DummyContext):
        return True
    return getattr(ctx, '_is_dummy', False)


# =============================================================================
# DEPENDENCY CHECK - DÜZELTİLDİ
# =============================================================================

# required_tables → ctx'teki karşılıkları
_TABLE_ALIASES = {
    # ETABS tablo adı → ctx'te bulunabileceği alternatif yerler
    "frame_rect_sections": ["geometry.section_dims", "tables.frame_rect_sections"],
    "frame_assigns_section": ["geometry.column_sections", "geometry.frame_sections", "tables.frame_assigns_section"],
    "column_forces": ["envelopes.column_forces_map", "tables.column_forces"],
    "beam_forces": ["envelopes.beam_forces_map", "tables.beam_forces"],
    "column_rebar_defs": ["design_metadata.column_rebar_defs", "tables.column_rebar_defs"],
    "column_design_summary": ["design_metadata.column_design_summary", "tables.column_design_summary"],
    "beam_design_summary": ["design_metadata.beam_design_summary", "tables.beam_design_summary"],
    "scwb_design": ["design_metadata.scwb_design", "tables.scwb_design"],
    "joint_shear_design": ["design_metadata.joint_shear_design", "tables.joint_shear_design"],
    "wall_design_summary": ["design_metadata.wall_design_summary", "tables.wall_design_summary"],
    "pier_forces": ["envelopes.pier_forces_map", "tables.pier_forces"],
    "pier_sections": ["geometry.wall_sections", "tables.pier_sections"],
    "story_definitions": ["story_height_map", "tables.story_definitions"],
    "story_drifts": ["tables.story_drifts"],
    "story_forces": ["envelopes.story_shear_x", "tables.story_forces"],
    "modal_mass": ["modal", "tables.modal_mass"],
    "base_reactions": ["base_reactions", "tables.base_reactions"],
    "auto_seismic": ["spectrum", "tables.auto_seismic"],
    "frame_objects": ["topology", "tables.frame_objects"],
    "joint_objects": ["topology", "tables.joint_objects"],
    "column_connectivity": ["topology", "tables.column_connectivity"],
    "beam_connectivity": ["topology", "tables.beam_connectivity"],
    "load_combos": ["combo_groups", "tables.load_combos"],
    "material_concrete": ["design_basis", "tables.material_concrete"],
    "material_general": ["design_basis", "tables.material_general"],
    "conc_design_prefs": ["design_basis", "tables.conc_design_prefs"],
}


def _resolve_ctx_path(ctx: Any, path: str) -> bool:
    """
    ctx üzerinde 'geometry.section_dims' gibi bir path'in
    var ve dolu olup olmadığını kontrol eder.
    """
    parts = path.split(".")
    obj = ctx

    for part in parts:
        if hasattr(obj, part):
            obj = getattr(obj, part)
        elif isinstance(obj, dict) and part in obj:
            obj = obj[part]
        else:
            return False

        if obj is None:
            return False

    # Boş dict/list değilse True
    if isinstance(obj, dict):
        return len(obj) > 0
    if isinstance(obj, (list, tuple)):
        return len(obj) > 0
    if hasattr(obj, 'empty'):
        return not obj.empty
    return obj is not None and obj != ""


def _check_data_available(ctx: Any, check_id: str) -> Dict[str, Any]:
    """
    Basitleştirilmiş dependency check.

    ctx.tables DIŞINDA ctx.geometry, ctx.design_metadata,
    ctx.topology, ctx.envelopes, ctx.design_basis altındaki
    verileri de tanır.
    """
    metadata = registry.metadata.get(check_id, {})
    required_tables = metadata.get("required_tables", [])
    requires_topology = metadata.get("requires_topology", False)
    requires_force_envelope = metadata.get("requires_force_envelope", False)
    requires_reinforcement = metadata.get("requires_reinforcement", False)

    missing = []

    # Tablo kontrolü - alias'larla
    for table in required_tables:
        found = False

        # Doğrudan ctx.tables'ta ara
        if hasattr(ctx, 'tables') and isinstance(ctx.tables, dict):
            if table in ctx.tables and ctx.tables[table] is not None:
                found = True

        # ctx.design_metadata'te ara
        if not found and hasattr(ctx, 'design_metadata') and isinstance(ctx.design_metadata, dict):
            if table in ctx.design_metadata and ctx.design_metadata[table] is not None:
                found = True

        # Alias'larla dene
        if not found and table in _TABLE_ALIASES:
            for alias_path in _TABLE_ALIASES[table]:
                if _resolve_ctx_path(ctx, alias_path):
                    found = True
                    break

        if not found:
            missing.append(table)

    # Topology kontrolü
    if requires_topology:
        topo = getattr(ctx, 'topology', None)
        if topo is None:
            missing.append("topology")
        elif isinstance(topo, dict) and not topo.get("columns"):
            missing.append("topology.columns")

    # Force envelope kontrolü
    if requires_force_envelope:
        env = getattr(ctx, 'envelopes', None)
        if env is None:
            missing.append("envelopes")
        elif isinstance(env, dict) and not env.get("column_forces_map"):
            missing.append("column_forces_map")

    # Malzeme kontrolü
    if requires_reinforcement:
        db = getattr(ctx, 'design_basis', None)
        if db is None:
            missing.append("design_basis")
        elif isinstance(db, dict) and not db.get("fck_mpa"):
            missing.append("design_basis.fck_mpa")

    # Can run?
    critical_missing = [m for m in missing if m in {
        "topology", "topology.columns", "frame_rect_sections",
        "frame_assigns_section", "column_forces", "column_forces_map",
        "envelopes", "design_basis",
    }]

    can_run = len(critical_missing) == 0

    if not can_run:
        return {
            "can_run": False,
            "dependency_status": "SKIP_NO_DATA",
            "run_level": "NO_DATA",
            "selected_method": "NO_DATA",
            "missing_data": missing,
            "reason": f"missing: {', '.join(critical_missing)}" if critical_missing else f"missing: {', '.join(missing)}",
        }

    # Design summary varsa ETABS_DESIGN_RESULT
    has_etabs_result = False
    if hasattr(ctx, 'design_metadata') and isinstance(ctx.design_metadata, dict):
        design_summary = ctx.design_metadata.get("column_design_summary")
        if design_summary is not None:
            if hasattr(design_summary, 'empty') and not design_summary.empty:
                has_etabs_result = True
            elif isinstance(design_summary, list) and len(design_summary) > 0:
                has_etabs_result = True

    if has_etabs_result:
        return {
            "can_run": True,
            "dependency_status": "RUN_DESIGN_LEVEL",
            "run_level": "DESIGN_LEVEL",
            "selected_method": "ETABS_DESIGN_RESULT",
            "missing_data": missing,
            "reason": "",
        }

    # Manuel formül
    has_materials = (
            hasattr(ctx, 'design_basis')
            and isinstance(ctx.design_basis, dict)
            and ctx.design_basis.get("fck_mpa")
    )

    if has_materials:
        return {
            "can_run": True,
            "dependency_status": "RUN_DESIGN_LEVEL",
            "run_level": "DESIGN_LEVEL",
            "selected_method": "MANUAL_FORMULA",
            "missing_data": missing,
            "reason": "",
        }

    return {
        "can_run": True,
        "dependency_status": "RUN_SCREENING",
        "run_level": "SCREENING",
        "selected_method": "SCREENING_FALLBACK",
        "missing_data": missing,
        "reason": "no ETABS design, no verified materials — screening only",
    }


def _try_evaluate_dependency(ctx: Any, check_id: str):
    """Dependency değerlendir (basitleştirilmiş fallback)"""
    result = _check_data_available(ctx, check_id)
    return type('DependencyResult', (), result)()


# =============================================================================
# RESOLVE HELPERS
# =============================================================================

def _resolve_execution_status(dep) -> str:
    if dep is None:
        return ExecutionStatus.NOT_EVALUATED
    dep_status = str(getattr(dep, "dependency_status", "") or "")
    if dep_status in {"SKIP_NO_DATA", "FAIL_MISSING_CRITICAL"}:
        return ExecutionStatus.SKIPPED
    if dep_status.startswith("RUN_"):
        return ExecutionStatus.EVALUATED
    if dep_status == "NOT_EVALUATED":
        return ExecutionStatus.NOT_EVALUATED
    return ExecutionStatus.EVALUATED


def _resolve_evaluation_level(dep) -> str:
    if dep is None:
        return EvaluationLevel.NO_DATA
    method = str(getattr(dep, "selected_method", "") or "").upper()
    if method == "ETABS_DESIGN_RESULT":
        return EvaluationLevel.ETABS_DESIGN_RESULT
    if method == "MANUAL_FORMULA":
        return EvaluationLevel.DESIGN_LEVEL
    if method in {"SCREENING_FALLBACK", "SCREENING_FALLBACK_LOW_COVERAGE"}:
        return EvaluationLevel.SCREENING
    if method == "NO_DATA":
        return EvaluationLevel.NO_DATA
    run_level = str(getattr(dep, "run_level", "") or "").upper()
    return {
        "DESIGN_LEVEL": EvaluationLevel.DESIGN_LEVEL,
        "APPROXIMATE": EvaluationLevel.APPROXIMATE,
        "SCREENING": EvaluationLevel.SCREENING,
        "NO_DATA": EvaluationLevel.NO_DATA,
    }.get(run_level, EvaluationLevel.NO_DATA)


# =============================================================================
# NORMALIZE
# =============================================================================

def _normalize_check_result(
        name: str,
        raw: Dict[str, Any],
        dep,
        execution_status: str,
        evaluation_level: str,
) -> Dict[str, Any]:
    """Ham check sonucunu contract'a uygun hale getirir."""
    out = dict(raw)

    if "check_id" in out and "check" not in out:
        out["check"] = out["check_id"]
    if "check" not in out:
        out["check"] = name

    details = out.get("details", [])
    if isinstance(details, list) and details:
        statuses = [str(d.get("status", "")).upper() for d in details]
        if "FAIL" in statuses:
            out["status"] = "FAIL"
        elif "WARNING" in statuses:
            out["status"] = "WARNING"
        elif all(s == "NO_DATA" for s in statuses):
            out["status"] = "NO_DATA"
        elif "OK" in statuses:
            out["status"] = "OK"
        else:
            out["status"] = "NO_DATA"
    elif "status" not in out:
        out["status"] = "NO_DATA"

    out["execution_status"] = execution_status
    out["evaluation_level"] = evaluation_level
    out["confidence"] = _EVAL_LEVEL_TO_CONFIDENCE.get(evaluation_level, "LOW")

    current_status = str(out.get("status", "ERROR")).upper()
    out["requires_engineer_review"] = not (
            out["confidence"] == "HIGH" and current_status in {"OK", "NO_DATA", "NOT_EVALUATED"}
    )

    details = out.get("details", [])
    if "total_checked" not in out:
        out["total_checked"] = len(details) if isinstance(details, list) else 0
    if "total" not in out:
        out["total"] = out["total_checked"]

    if isinstance(details, list):
        out["fail_count"] = sum(1 for d in details if str(d.get("status", "")).upper() == "FAIL")
        out["warning_count"] = sum(1 for d in details if str(d.get("status", "")).upper() == "WARNING")
        out["pass_count"] = sum(1 for d in details if str(d.get("status", "")).upper() in {"OK", "PASS"})
        out["no_data_count"] = sum(1 for d in details if str(d.get("status", "")).upper() == "NO_DATA")
    else:
        out.setdefault("fail_count", 0)
        out.setdefault("warning_count", 0)
        out.setdefault("pass_count", 0)
        out.setdefault("no_data_count", 0)

    if dep is not None:
        out["dependency_status"] = str(getattr(dep, "dependency_status", "") or "")
        out["can_run"] = getattr(dep, "can_run", False)
        out["run_level"] = str(getattr(dep, "run_level", "") or "")
        out["selected_method"] = str(getattr(dep, "selected_method", "") or "")
        out["missing_data"] = getattr(dep, "missing_data", []) or []

    if "message" not in out and "description" in out:
        out["message"] = out["description"]

    return out


# =============================================================================
# TEK CHECK ÇALIŞTIRICI
# =============================================================================

def _run_single_check(ctx: Any, name: str) -> Dict[str, Any]:
    fn = registry.get_check(name)
    dep = _try_evaluate_dependency(ctx, name)
    execution_status = _resolve_execution_status(dep)
    evaluation_level = _resolve_evaluation_level(dep)

    if not getattr(dep, "can_run", True):
        raw = {
            "check": name,
            "status": "NO_DATA",
            "message": str(getattr(dep, "reason", "Veri eksik")) or "Veri eksik",
        }
        return _normalize_check_result(name, raw, dep, execution_status, evaluation_level)

    if fn is None:
        raw = {
            "check": name,
            "status": "ERROR",
            "message": f"Check '{name}' registry'de tanımlı değil.",
        }
        return _normalize_check_result(name, raw, dep, execution_status, evaluation_level)

    try:
        raw = fn(ctx)
        if not isinstance(raw, dict):
            raw = {
                "check": name,
                "status": "ERROR",
                "message": f"Check fonksiyonu dict döndürmedi.",
            }
    except Exception as exc:
        logger.exception(f"runner: '{name}' exception")
        raw = {"check": name, "status": "ERROR", "message": str(exc)}

    return _normalize_check_result(name, raw, dep, execution_status, evaluation_level)


# =============================================================================
# SUMMARY
# =============================================================================

def _build_runner_summary(results: Dict[str, Any]) -> Dict[str, int]:
    statuses = [str(c.get("status", "ERROR")).upper() for c in results.values() if isinstance(c, dict)]
    return {
        "total": len(results),
        "ok": statuses.count("OK"),
        "fail": statuses.count("FAIL"),
        "warning": statuses.count("WARNING"),
        "no_data": statuses.count("NO_DATA"),
        "not_evaluated": statuses.count("NOT_EVALUATED"),
        "error": statuses.count("ERROR"),
        "partial": statuses.count("PARTIAL"),
        "etabs_design_result": sum(
            1 for c in results.values()
            if isinstance(c, dict) and str(c.get("evaluation_level", "")).upper() == "ETABS_DESIGN_RESULT"
        ),
        "requires_review": sum(
            1 for c in results.values()
            if isinstance(c, dict) and c.get("requires_engineer_review") is True
        ),
    }


# =============================================================================
# ANA ENTRY POINT
# =============================================================================

def run_all_checks(ctx: Any, selected: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    names: List[str] = list(selected) if selected else registry.get_all_check_ids()
    if not names:
        return {"checks": {}, "summary": _build_runner_summary({})}
    results = {name: _run_single_check(ctx, name) for name in names}
    return {"checks": results, "summary": _build_runner_summary(results)}


# =============================================================================
# ASYNC CONTEXT BUILDER
# =============================================================================
async def _build_context_async(connect_etabs: bool = True) -> Any:
    if connect_etabs:
        try:
            connected, msg = check_etabs_connection()
            if connected:
                logger.info("ETABS bağlantısı kuruldu.")
                try:
                    from .engine.context_builder import build_model_context
                    return await build_model_context()
                except ImportError as e:
                    logger.warning(f"context_builder import hatası: {e}")
                except Exception as e:
                    logger.warning(f"context_builder çalışma hatası: {e}")
            else:
                logger.warning(f"ETABS yok: {msg}")
        except Exception as e:
            logger.warning(f"ETABS kontrol hatası: {e}")

    logger.info("Dummy context oluşturuluyor...")
    return DummyContext()

# =============================================================================
# ANA RUNNER
# =============================================================================

def run(config: Optional[Dict] = None) -> Dict[str, Any]:
    config = config or {}
    logger.info("🚀 tbdy_engine başlatılıyor...")
    connect_etabs = config.get("etabs_connect", True)

    try:
        try:
            loop = asyncio.get_running_loop()
            ctx = DummyContext()
        except RuntimeError:
            ctx = asyncio.run(_build_context_async(connect_etabs=connect_etabs))
    except Exception as e:
        return {"status": "ERROR", "version": "0.4.2", "message": str(e), "checks": {}, "summary": {},
                "context_tables": 0, "context_type": "error"}

    registry.load_from_matrix()
    selected = config.get("selected_checks")
    runner_result = run_all_checks(ctx, selected=selected)
    context_type = "dummy" if _is_dummy_context(ctx) else "etabs"

    return {
        "status": "SUCCESS", "version": "0.4.2",
        "checks": runner_result["checks"],
        "summary": runner_result["summary"],
        "context_tables": len(getattr(ctx, "tables", {})),
        "context_type": context_type,
    }


def run_column_checks(ctx: Any = None) -> Dict[str, Any]:
    if ctx is None:
        ctx = DummyContext()
    from .checks.registry import get_column_check_ids
    return run_all_checks(ctx, selected=get_column_check_ids())


def run_check(ctx: Any, check_id: str) -> Dict[str, Any]:
    if ctx is None:
        ctx = DummyContext()
    return _run_single_check(ctx, check_id)