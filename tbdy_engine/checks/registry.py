# # app/checks/registry.py  (Faz 0 patch)
# """
# Registry — check fonksiyon tablosu ve metadata.
#
# Faz 0 degisikligi:
#   - run_all_checks() bu dosyadan KALDIRILDI.
#     Cagiranlar app.checks.runner.run_all_checks() kullanmalidir.
#   - Backward compat icin run_all_checks burada re-export edilir;
#     import yolu kirilmaz ama implementation runner'da yasar.
#
# DOKUNULMAYAN: CHECK_FUNCTIONS, CHECK_METADATA, enrich loop.
# """
# from __future__ import annotations
#
# from typing import Any, Dict, Iterable, Optional
#
# from app.checks.contracts import overall_status_from_summary, summarize_statuses
# from .checks.check_matrix import CHECK_MATRIX_VERSION, registry_metadata_from_matrix, validate_check_matrix
# from .engine.data_capability import capability_report
# from .checks.dependencies import (
#     attach_dependency_to_check,
#     build_dependency_report,
#     evaluate_check_dependency,
#     make_no_data_result,
# )
# from .checks.full_engineering import (
#     check_wall_boundary_zone_v22,
# )
# from .checks.global_checks import (
#     check_modal, check_beta_from_ctx, check_drift, check_torsion, check_soft_story,
#     check_building_height_class, check_second_order, check_b3_vertical_discontinuity,
#     check_base_shear_limit,
# )
# from .checks.column_checks import (
#     check_column_axial, check_column_dimensions, check_column_shear,
#     check_column_confinement, check_column_rebar, check_scwb,
# )
# from .checks.beam_checks import check_beam_dimensions, check_beam_shear, check_beam_flexure
# from .checks.joint_checks import check_joint_shear, check_joint_dimensions
# from .detailing.overlay_checks import check_scwb_from_overlay, check_joint_shear_from_overlay
# from .checks.wall_checks import check_wall_shear, check_wall_design_forces
# from .checks.full_engineering import (
#     ensure_unit_layer, check_beam_shear_v20, check_column_shear_v20,
#     check_column_confinement_v20, check_column_axial_v20, check_wall_shear_v20,
#     check_drift_v20, check_torsion_v20, check_second_order_v20,
#     check_joint_shear_v20, check_scwb_v20,
# )
#
#
# CHECK_FUNCTIONS = {
#     "modal": check_modal,
#     "beta_x": lambda ctx: check_beta_from_ctx(ctx, "X"),
#     "beta_y": lambda ctx: check_beta_from_ctx(ctx, "Y"),
#     "drift": check_drift_v20,
#     "torsion": check_torsion_v20,
#     "soft_story": check_soft_story,
#     "building_height_class": check_building_height_class,
#     "second_order": check_second_order_v20,
#     "b3_vertical_disc": check_b3_vertical_discontinuity,
#     "base_shear_limit": check_base_shear_limit,
#
#     "column_dimensions": check_column_dimensions,
#     "column_axial": check_column_axial_v20,
#     "column_shear": check_column_shear_v20,
#     "column_confinement": check_column_confinement_v20,
#     "column_rebar": check_column_rebar,
#     "scwb": check_scwb_v20,
#     "scwb_overlay": check_scwb_from_overlay,
#
#     "beam_dimensions": check_beam_dimensions,
#     "beam_shear": check_beam_shear_v20,
#     "beam_flexure": check_beam_flexure,
#
#     "joint_dimensions": check_joint_dimensions,
#     "joint_shear": check_joint_shear_v20,
#     "joint_shear_overlay": check_joint_shear_from_overlay,
#
#     "wall_design_forces": check_wall_design_forces,
#     "wall_shear": check_wall_shear_v20,
#     "wall_boundary_zone": check_wall_boundary_zone_v22,
# }
#
#
# CHECK_METADATA = {
#     "modal": {
#         "category": "global", "level": "design_level_if_modal_table_valid", "code_ref": "TBDY 2018 §4.8",
#         "required_tables": ["modal_mass"], "requires_topology": False, "requires_force_envelope": False, "requires_reinforcement": False,
#         "report_section": "global.modal",
#     },
#     "beta_x": {
#         "category": "global", "level": "design_level_if_base_reactions_and_cases_valid", "code_ref": "TBDY 2018 §4.7.5",
#         "required_tables": ["base_reactions", "auto_seismic"], "requires_topology": False, "requires_force_envelope": False, "requires_reinforcement": False,
#         "report_section": "global.base_shear.x",
#     },
#     "beta_y": {
#         "category": "global", "level": "design_level_if_base_reactions_and_cases_valid", "code_ref": "TBDY 2018 §4.7.5",
#         "required_tables": ["base_reactions", "auto_seismic"], "requires_topology": False, "requires_force_envelope": False, "requires_reinforcement": False,
#         "report_section": "global.base_shear.y",
#     },
#     "drift": {
#         "category": "global", "level": "design_level_if_story_drifts_valid", "code_ref": "TBDY 2018 §4.9",
#         "required_tables": ["story_definitions", "story_drifts"], "requires_topology": False, "requires_force_envelope": False, "requires_reinforcement": False,
#         "report_section": "global.drift",
#     },
#     "torsion": {
#         "category": "irregularities", "level": "design_level_if_story_drifts_include_max_avg", "code_ref": "TBDY 2018 §3.6.2.1",
#         "required_tables": ["story_drifts"], "requires_topology": False, "requires_force_envelope": False, "requires_reinforcement": False,
#         "report_section": "irregularities.a1_torsion",
#     },
#     "soft_story": {
#         "category": "irregularities", "level": "screening_or_design_if_story_stiffness_valid", "code_ref": "TBDY 2018 §3.6.2.5",
#         "required_tables": ["story_definitions", "story_drifts"], "requires_topology": False, "requires_force_envelope": False, "requires_reinforcement": False,
#         "report_section": "irregularities.b2_soft_story",
#     },
#     "building_height_class": {
#         "category": "global", "level": "screening", "code_ref": "TBDY 2018 §3.3.1",
#         "required_tables": ["story_definitions"], "requires_topology": False, "requires_force_envelope": False, "requires_reinforcement": False,
#         "report_section": "global.building_height_class",
#     },
#     "second_order": {
#         "category": "global", "level": "screening_until_story_P_delta_and_shear_valid", "code_ref": "TBDY 2018 §4.9.3",
#         "required_tables": ["story_drifts", "story_forces"], "requires_topology": False, "requires_force_envelope": True, "requires_reinforcement": False,
#         "report_section": "global.second_order",
#     },
#     "b3_vertical_disc": {
#         "category": "irregularities", "level": "topology_screening", "code_ref": "TBDY 2018 §3.6.2.6",
#         "required_tables": ["frame_objects", "joint_objects", "column_connectivity", "beam_connectivity"], "requires_topology": True, "requires_force_envelope": False, "requires_reinforcement": False,
#         "report_section": "irregularities.b3_vertical_discontinuity",
#     },
#     "base_shear_limit": {
#         "category": "global", "level": "design_level_if_beta_cases_valid", "code_ref": "TBDY 2018 §4.7.5",
#         "required_tables": ["base_reactions", "auto_seismic"], "requires_topology": False, "requires_force_envelope": False, "requires_reinforcement": False,
#         "report_section": "global.base_shear_limit",
#     },
#     "column_dimensions": {
#         "category": "columns", "level": "design_level_geometry", "code_ref": "TBDY 2018 §7.3.2",
#         "required_tables": ["frame_rect_sections", "frame_assigns_section"], "requires_topology": True, "requires_force_envelope": False, "requires_reinforcement": False,
#         "report_section": "columns.dimensions",
#     },
#     "column_axial": {
#         "category": "columns", "level": "design_level_if_design_or_envelope_forces_valid", "code_ref": "TBDY 2018 §7.3.1",
#         "required_tables": ["column_forces", "frame_rect_sections"], "requires_topology": True, "requires_force_envelope": True, "requires_reinforcement": False,
#         "report_section": "columns.axial",
#     },
#     "column_shear": {
#         "category": "columns", "level": "design_if_rebar_or_design_table_else_screening", "code_ref": "TBDY 2018 §7.3.7",
#         "required_tables": ["column_forces", "frame_rect_sections"], "requires_topology": True, "requires_force_envelope": True, "requires_reinforcement": True,
#         "report_section": "columns.shear",
#     },
#     "column_confinement": {
#         "category": "columns", "level": "design_if_rebar_defs_else_screening", "code_ref": "TBDY 2018 §7.3.4.2",
#         "required_tables": ["column_rebar_defs", "frame_rect_sections"], "requires_topology": True, "requires_force_envelope": False, "requires_reinforcement": True,
#         "report_section": "columns.confinement",
#     },
#     "scwb": {
#         "category": "columns", "level": "design_if_scwb_design_table_else_screening", "code_ref": "TBDY 2018 §7.3.5",
#         "required_tables": ["scwb_design"], "requires_topology": True, "requires_force_envelope": False, "requires_reinforcement": True,
#         "report_section": "columns.scwb",
#     },
#     "beam_dimensions": {
#         "category": "beams", "level": "design_level_geometry", "code_ref": "TBDY 2018 §7.4.1",
#         "required_tables": ["frame_rect_sections", "frame_assigns_section"], "requires_topology": True, "requires_force_envelope": False, "requires_reinforcement": False,
#         "report_section": "beams.dimensions",
#     },
#     "beam_shear": {
#         "category": "beams", "level": "design_if_rebar_or_design_table_else_screening", "code_ref": "TBDY 2018 §7.4.2",
#         "required_tables": ["beam_forces", "frame_rect_sections"], "requires_topology": True, "requires_force_envelope": True, "requires_reinforcement": True,
#         "report_section": "beams.shear",
#     },
#     "beam_flexure": {
#         "category": "beams", "level": "design_if_beam_design_summary", "code_ref": "TBDY 2018 §7.4.1 / TS500",
#         "required_tables": ["beam_design_summary"], "requires_topology": False, "requires_force_envelope": False, "requires_reinforcement": True,
#         "report_section": "beams.flexure",
#     },
#     "column_rebar": {
#         "category": "columns", "level": "design_if_column_design_summary", "code_ref": "TBDY 2018 §7.3.4",
#         "required_tables": ["column_design_summary"], "requires_topology": False, "requires_force_envelope": False, "requires_reinforcement": True,
#         "report_section": "columns.rebar",
#     },
#     "scwb_overlay": {
#         "category": "columns", "level": "precheck", "code_ref": "TBDY 2018 §7.3.5",
#         "required_tables": ["beam_design_summary"], "requires_topology": True, "requires_force_envelope": False, "requires_reinforcement": True,
#         "report_section": "columns.scwb_overlay",
#     },
#     "joint_dimensions": {
#         "category": "joints", "level": "topology_geometry_screening", "code_ref": "TBDY 2018 §7.4.5",
#         "required_tables": ["frame_rect_sections", "frame_assigns_section"], "requires_topology": True, "requires_force_envelope": False, "requires_reinforcement": False,
#         "report_section": "joints.dimensions",
#     },
#     "joint_shear": {
#         "category": "joints", "level": "design_if_joint_shear_design_table_else_screening", "code_ref": "TBDY 2018 §7.4.5",
#         "required_tables": ["joint_shear_design"], "requires_topology": True, "requires_force_envelope": False, "requires_reinforcement": True,
#         "report_section": "joints.shear",
#     },
#     "wall_design_forces": {
#         "category": "walls", "level": "screening_until_wall_design_tables_valid", "code_ref": "TBDY 2018 §7.6.2",
#         "required_tables": ["pier_forces", "pier_sections"], "requires_topology": False, "requires_force_envelope": True, "requires_reinforcement": False,
#         "report_section": "walls.design_forces",
#     },
#     "wall_shear": {
#         "category": "walls", "level": "design_if_wall_summary_else_force_section_fallback", "code_ref": "TBDY 2018 §7.6.6",
#         "required_tables": ["pier_forces", "pier_sections"], "requires_topology": False, "requires_force_envelope": True, "requires_reinforcement": True,
#         "report_section": "walls.shear",
#     },
#     "wall_boundary_zone": {
#         "title": "Perde uc bolgesi kontrolu",
#         "category": "Perde Tasarimi",
#         "code_ref": "TBDY 2018 §7.6.2.4",
#         "required_tables": ["wall_design_summary"],
#         "requires_topology": False,
#         "requires_force_envelope": False,
#         "requires_reinforcement": True,
#     },
#
# }
#
#
# # Enrich from check matrix
# for _matrix_check_name in list(CHECK_METADATA.keys()):
#     _m = registry_metadata_from_matrix(_matrix_check_name)
#     if _m:
#         for _k, _v in _m.items():
#             CHECK_METADATA[_matrix_check_name].setdefault(_k, _v)
# for _matrix_check_name in ("beam_flexure",):
#     CHECK_METADATA.setdefault(_matrix_check_name, registry_metadata_from_matrix(_matrix_check_name))
#
#
# # ---------------------------------------------------------------------------
# # Backward compat wrapper: run_all_checks lives in runner.py now.
# #
# # Eski cagiranlar bu sozlugun su alanlarini bekliyordu:
# #   ok, overall_status, summary, dependency_validation,
# #   check_matrix_validation, check_matrix_version, data_capability, checks
# #
# # runner.run_all_checks() artik sadece {"checks", "summary"} donduruyor.
# # Bu wrapper eksik alanlari buraya ekler — payload layer sorumlulugunu
# # gecici olarak burada tasir, ta ki cagiranlar runner'a dogrudan gecene dek.
# # ---------------------------------------------------------------------------
# def run_all_checks(ctx, selected=None):
#     """
#     Backward compatibility wrapper.
#
#     Yeni kod icin: app.checks.runner.run_all_checks()
#     Bu wrapper silinmeden once tum cagiranlarin runner'a gecmesi gerekir.
#     """
#     from app.checks.runner import run_all_checks as _runner
#     from app.checks.contracts import overall_status_from_summary
#     from app.checks.dependencies import build_dependency_report
#     from app.checks.check_matrix import CHECK_MATRIX_VERSION, validate_check_matrix
#     from app.engine.data_capability import capability_report
#     from app.checks.full_engineering import ensure_unit_layer
#
#     # Context setup: runner'a ait degil, context_builder isi.
#     # Eski cagiranlar bunu registry uzerinden tetikleyebilirdi;
#     # gecis tamamlanana kadar burada tutulur.
#     ensure_unit_layer(ctx)
#
#     runner_result = _runner(ctx, selected=selected)
#     checks = runner_result["checks"]
#     summary = runner_result["summary"]
#     overall = overall_status_from_summary(summary)
#
#     # dependency_validation: runner artik dep nesnelerini disari vermedigi icin
#     # dependency bilgisi check sonuclarinin icindeki "dependency" alanindan okunur.
#     dep_items = {
#         name: chk.get("dependency", {})
#         for name, chk in checks.items()
#         if isinstance(chk, dict)
#     }
#     dep_counts: Dict[str, int] = {}
#     for d in dep_items.values():
#         ds = str(d.get("dependency_status", "UNKNOWN"))
#         dep_counts[ds] = dep_counts.get(ds, 0) + 1
#
#     return {
#         "ok": overall not in {"ERROR", "FAIL"},
#         "overall_status": overall,
#         "summary": summary,
#         "dependency_validation": {"summary": dep_counts, "checks": dep_items},
#         "check_matrix_validation": validate_check_matrix(),
#         "check_matrix_version": CHECK_MATRIX_VERSION,
#         "data_capability": capability_report(ctx),
#         "checks": checks,
#     }


"""
tbdy_engine/checks/registry.py

Check Registry - Column design check'leri eklendi.
"""

from __future__ import annotations
from typing import Any, Callable, Dict

from .check_matrix import CHECK_MATRIX, public_check_matrix
from ..engine.context_builder import ModelContext


class CheckRegistry:
    """Check Registry - YAML matrix + fonksiyon mapping"""

    def __init__(self):
        self.checks: Dict[str, Callable] = {}
        self.metadata = CHECK_MATRIX

    def register(self, check_id: str, func: Callable):
        """Check fonksiyonunu kaydet"""
        self.checks[check_id] = func

    def get_check(self, check_id: str) -> Callable | None:
        return self.checks.get(check_id)

    def get_all_check_ids(self) -> list[str]:
        return list(self.checks.keys())

    def load_from_matrix(self):
        """Matrix'teki check'leri hazirla (placeholder)"""
        pass  # Sprint 3'te full_engineering fonksiyonlari buraya baglanacak


# Global registry instance
registry = CheckRegistry()


# =============================================================================
# COLUMN CHECK FONKSIYONLARI (Design Module'den registry'ye baglanmis)
# =============================================================================

def check_column_geometry(ctx):
    """
    TBDY 2018 §7.3.1 - Kolon minimum boyut kontrolu.

    Returns: dict with keys: check_id, status, description, details
    """
    from ..design.columns.module import ColumnDesignModule

    module = ColumnDesignModule(ctx)
    module.resolve_materials()
    module.resolve_columns()

    results = []
    for col in module._columns:
        check = module.check_geometry(col)
        results.append({
            "element_id": col.label,
            "story": col.story,
            "section": col.section_name,
            "status": check.status,
            "ratio": check.ratio,
            "value": check.value,
            "limit": check.limit,
            "unit": check.unit,
            "description": check.message,
            "tbdy_ref": check.tbdy_ref,
        })

    return {
        "check_id": "column_geometry",
        "status": _aggregate_column_status(results),
        "description": f"Kolon minimum boyut kontrolu ({len(results)} kolon)",
        "details": results,
    }


def check_column_axial(ctx):
    """
    TBDY 2018 §7.3.2 - Kolon eksenel yuk limiti.

    Returns: dict with keys: check_id, status, description, details
    """
    from ..design.columns.module import ColumnDesignModule

    module = ColumnDesignModule(ctx)
    module.resolve_materials()
    module.resolve_columns()
    module.resolve_forces()

    results = []
    for col in module._columns:
        forces = module._forces.get(col.label)
        if forces:
            check = module.check_axial(col, forces, module._materials)
        else:
            check = type('obj', (object,), {
                'status': 'NO_DATA',
                'ratio': 0.0,
                'value': 0.0,
                'limit': 0.0,
                'unit': 'kN',
                'message': 'Kuvvet verisi yok',
                'tbdy_ref': 'TBDY 2018 7.3.2',
            })()

        results.append({
            "element_id": col.label,
            "story": col.story,
            "section": col.section_name,
            "status": check.status,
            "ratio": check.ratio,
            "value": check.value,
            "limit": check.limit,
            "unit": check.unit,
            "description": check.message,
            "tbdy_ref": check.tbdy_ref,
        })

    return {
        "check_id": "column_axial",
        "status": _aggregate_column_status(results),
        "description": f"Kolon eksenel yuk kontrolu ({len(results)} kolon)",
        "details": results,
    }

def check_column_pmm(ctx):
    """
    Kolon PMM kontrolu.

    Oncelik:
    1. ETABS design summary varsa ETABS sonucunu kullanir.
    2. Yoksa ColumnDesignModule.check_pmm() uzerinden kuvvet + malzeme + donati ile fallback yapar.
    3. Otomatik oneri donati kullanilmissa sonuc WARNING olur.
    """
    from ..design.columns.module import ColumnDesignModule

    module = ColumnDesignModule(ctx)
    module.resolve_materials()
    module.resolve_columns()
    module.resolve_forces()
    module.resolve_rebar()

    results = []

    for col in module._columns:
        check = module.check_pmm(
            col=col,
            forces=module._forces.get(col.label),
            rebar=module._rebar.get(col.label),
            mat=module._materials,
        )

        results.append({
            "element_id": col.label,
            "story": col.story,
            "section": col.section_name,
            "status": check.status,
            "ratio": check.ratio,
            "value": check.value,
            "limit": check.limit,
            "unit": check.unit,
            "description": check.message,
            "tbdy_ref": check.tbdy_ref,
        })

    return {
        "check_id": "column_pmm",
        "status": _aggregate_column_status(results),
        "description": f"Kolon PMM kontrolu ({len(results)} kolon)",
        "details": results,
    }


def check_column_shear(ctx):
    """
    TBDY 2018 §7.3.7 - Kolon kesme guvenligi.

    Returns: dict with keys: check_id, status, description, details
    """
    from ..design.columns.module import ColumnDesignModule

    module = ColumnDesignModule(ctx)
    module.resolve_materials()
    module.resolve_columns()
    module.resolve_forces()
    module.resolve_rebar()

    results = []
    for col in module._columns:
        forces = module._forces.get(col.label)
        rebar = module._rebar.get(col.label)

        if forces and module._materials:
            check = module.check_shear(col, forces, module._materials, rebar)
        else:
            check = type('obj', (object,), {
                'status': 'NO_DATA',
                'ratio': 0.0,
                'value': 0.0,
                'limit': 0.0,
                'unit': 'kN',
                'message': 'Kuvvet/malzeme verisi yok',
                'tbdy_ref': 'TBDY 2018 7.3.7',
            })()

        results.append({
            "element_id": col.label,
            "story": col.story,
            "section": col.section_name,
            "status": check.status,
            "ratio": check.ratio,
            "value": check.value,
            "limit": check.limit,
            "unit": check.unit,
            "description": check.message,
            "tbdy_ref": check.tbdy_ref,
        })

    return {
        "check_id": "column_shear",
        "status": _aggregate_column_status(results),
        "description": f"Kolon kesme kontrolu ({len(results)} kolon)",
        "details": results,
    }


def check_column_confinement(ctx):
    """
    TBDY 2018 §7.3.4 - Kolon sargi donatisi kontrolu.

    Returns: dict with keys: check_id, status, description, details
    """
    from ..design.columns.module import ColumnDesignModule

    module = ColumnDesignModule(ctx)
    module.resolve_materials()
    module.resolve_columns()
    module.resolve_rebar()

    results = []
    for col in module._columns:
        rebar = module._rebar.get(col.label)
        check = module.check_confinement(col, module._materials, rebar)

        results.append({
            "element_id": col.label,
            "story": col.story,
            "section": col.section_name,
            "status": check.status,
            "ratio": check.ratio,
            "value": check.value,
            "limit": check.limit,
            "unit": check.unit,
            "description": check.message,
            "tbdy_ref": check.tbdy_ref,
        })

    return {
        "check_id": "column_confinement",
        "status": _aggregate_column_status(results),
        "description": f"Kolon sargi donatisi kontrolu ({len(results)} kolon)",
        "details": results,
    }


def check_column_capacity_hierarchy(ctx):
    """
    TBDY 2018 §7.3.5 - Guclu kolon kontrolu (kapasite hiyerarsisi).

    Returns: dict with keys: check_id, status, description, details
    """
    from ..design.columns.module import ColumnDesignModule

    module = ColumnDesignModule(ctx)
    module.resolve_columns()

    results = []
    for col in module._columns:
        check = module.check_capacity_hierarchy(col)
        results.append({
            "element_id": col.label,
            "story": col.story,
            "section": col.section_name,
            "status": check.status,
            "ratio": check.ratio,
            "value": check.value,
            "limit": check.limit,
            "unit": check.unit,
            "description": check.message,
            "tbdy_ref": check.tbdy_ref,
        })

    return {
        "check_id": "column_capacity_hierarchy",
        "status": _aggregate_column_status(results),
        "description": f"Guclu kolon kontrolu ({len(results)} kolon)",
        "details": results,
    }

def check_column_rebar_minimum(ctx):
    """
    Column minimum longitudinal rebar check.

    Policy:
    - source=default: WARNING because it is an automatic proposal.
    - source=real_rebar / etabs_design_summary / section_rebar_defs: OK/FAIL.
    - rho tolerance is used because ETABS As values may round to exactly 1.00%.
    """
    from ..design.columns.module import ColumnDesignModule

    module = ColumnDesignModule(ctx)
    module.resolve_columns()
    module.resolve_rebar()

    results = []
    rho_min = 1.0
    rho_tol = 0.001

    for col in module._columns:
        rebar = module._rebar.get(col.label)

        if not rebar:
            results.append({
                "element_id": col.label,
                "story": col.story,
                "section": col.section_name,
                "status": "NO_DATA",
                "ratio": 0.0,
                "value": 0.0,
                "limit": rho_min,
                "unit": "%",
                "description": "Rebar data not available and automatic proposal could not be generated",
                "tbdy_ref": "TBDY 2018 7.3.2",
            })
            continue

        rho = float(getattr(rebar, "rho", 0.0) or 0.0)
        n_bars = int(float(getattr(rebar, "n_bars_total", 0.0) or 0.0))
        bar_dia = float(getattr(rebar, "bar_diameter_mm", 0.0) or 0.0)
        source = str(getattr(rebar, "source", "unknown"))

        violations = []

        if rho + rho_tol < rho_min:
            violations.append(f"rho={rho:.3f}% < {rho_min:.3f}%")

        if n_bars < 6:
            violations.append(f"{n_bars} bars < 6")

        if bar_dia < 14:
            violations.append(f"Phi{int(round(bar_dia))} < Phi14")

        if source == "default":
            status = "WARNING"

            if violations:
                description = (
                    "Automatic proposal does not fully satisfy minimum column rebar: "
                    f"{'; '.join(violations)}. RebarSet proposal must be reviewed."
                )
                ratio = rho / rho_min if rho > 0 else 0.0
            else:
                description = (
                    f"Automatic minimum longitudinal rebar proposal: "
                    f"rho={rho:.3f}%, {n_bars}Phi{int(round(bar_dia))}. "
                    f"Real column rebar is not provided in model."
                )
                ratio = 1.0
        else:
            if violations:
                status = "FAIL"
                description = (
                    f"Provided/design column rebar does not satisfy minimum: "
                    f"{'; '.join(violations)}. source={source}"
                )
                ratio = rho / rho_min if rho > 0 else 0.0
            else:
                status = "OK"
                description = (
                    f"Provided/design column rebar OK: "
                    f"rho={rho:.3f}%, {n_bars}Phi{int(round(bar_dia))}. source={source}"
                )
                ratio = 1.0

        results.append({
            "element_id": col.label,
            "story": col.story,
            "section": col.section_name,
            "status": status,
            "ratio": ratio,
            "value": rho,
            "limit": rho_min,
            "unit": "%",
            "description": description,
            "tbdy_ref": "TBDY 2018 7.3.2",
        })

    return {
        "check_id": "column_rebar_minimum",
        "status": _aggregate_column_status(results),
        "description": f"Column minimum longitudinal rebar check ({len(results)} columns)",
        "details": results,
    }

def check_column_design_full(ctx):
    """
    Tum kolon tasarim kontrollerini tek seferde calistir.

    Returns: dict with keys: check_id, status, description, details, summary
    """
    from ..design.columns.module import ColumnDesignModule

    module = ColumnDesignModule(ctx)
    result = module.run()

    return {
        "check_id": "column_design_full",
        "status": result["package_status"],
        "description": f"Komple kolon tasarimi ({result['summary']['total_columns']} kolon)",
        "details": result["outputs"],
        "summary": result["summary"],
    }


# =============================================================================
# CHECK'LERI REGISTRY'E KAYDET
# =============================================================================

_COLUMN_CHECKS = {
    "column_geometry": check_column_geometry,
    "column_axial": check_column_axial,
    "column_pmm": check_column_pmm,
    "column_shear": check_column_shear,
    "column_confinement": check_column_confinement,
    "column_capacity_hierarchy": check_column_capacity_hierarchy,
    "column_rebar_minimum": check_column_rebar_minimum,
    "column_design_full": check_column_design_full,
}

for check_id, func in _COLUMN_CHECKS.items():
    registry.register(check_id, func)

# =============================================================================
# CHECK MATRIX METADATA (COLUMN)
# =============================================================================

COLUMN_CHECK_METADATA = {
    "column_geometry": {
        "category": "columns",
        "level": "design_level_geometry",
        "code_ref": "TBDY 2018 §7.3.1",
        "required_tables": ["frame_rect_sections", "frame_assigns_section"],
        "requires_topology": True,
        "requires_force_envelope": False,
        "requires_reinforcement": False,
        "report_section": "columns.geometry",
    },
    "column_axial": {
        "category": "columns",
        "level": "design_level_if_design_or_envelope_forces_valid",
        "code_ref": "TBDY 2018 §7.3.2",
        "required_tables": ["column_forces", "frame_rect_sections"],
        "requires_topology": True,
        "requires_force_envelope": True,
        "requires_reinforcement": False,
        "report_section": "columns.axial",
    },
    "column_pmm": {
        "category": "columns",
        "level": "design_if_column_design_summary",
        "code_ref": "TBDY 2018 §7.3.3",
        "required_tables": ["column_design_summary"],
        "requires_topology": True,
        "requires_force_envelope": False,
        "requires_reinforcement": True,
        "report_section": "columns.pmm",
    },
    "column_shear": {
        "category": "columns",
        "level": "design_if_rebar_or_design_table_else_screening",
        "code_ref": "TBDY 2018 §7.3.7",
        "required_tables": ["column_forces", "frame_rect_sections"],
        "requires_topology": True,
        "requires_force_envelope": True,
        "requires_reinforcement": True,
        "report_section": "columns.shear",
    },
    "column_confinement": {
        "category": "columns",
        "level": "design_if_rebar_defs_else_screening",
        "code_ref": "TBDY 2018 §7.3.4",
        "required_tables": ["column_rebar_defs", "frame_rect_sections"],
        "requires_topology": True,
        "requires_force_envelope": False,
        "requires_reinforcement": True,
        "report_section": "columns.confinement",
    },
    "column_capacity_hierarchy": {
        "category": "columns",
        "level": "design_if_scwb_design_table_else_screening",
        "code_ref": "TBDY 2018 §7.3.5",
        "required_tables": ["scwb_design"],
        "requires_topology": True,
        "requires_force_envelope": False,
        "requires_reinforcement": True,
        "report_section": "columns.capacity_hierarchy",
    },
    "column_rebar_minimum": {
        "category": "columns",
        "level": "design_if_rebar_defs_else_screening",
        "code_ref": "TBDY 2018 §7.3.2",
        "required_tables": ["column_rebar_defs"],
        "requires_topology": True,
        "requires_force_envelope": False,
        "requires_reinforcement": True,
        "report_section": "columns.rebar_minimum",
    },
    "column_design_full": {
        "category": "columns",
        "level": "full_design_package",
        "code_ref": "TBDY 2018 §7.3",
        "required_tables": [
            "frame_rect_sections",
            "frame_assigns_section",
            "column_forces",
            "column_rebar_defs",
            "column_design_summary",
        ],
        "requires_topology": True,
        "requires_force_envelope": True,
        "requires_reinforcement": True,
        "report_section": "columns.full_design",
    },
}

# Metadata'yi registry'ye ekle
for check_id, meta in COLUMN_CHECK_METADATA.items():
    registry.metadata[check_id] = meta


# =============================================================================
# YARDIMCILAR
# =============================================================================

def _aggregate_column_status(results: list[dict]) -> str:
    """Kolon sonuclarindan aggregate status cikar"""
    if not results:
        return "NO_DATA"

    statuses = [r["status"] for r in results]

    if "FAIL" in statuses:
        return "FAIL"
    if "WARNING" in statuses:
        return "WARNING"
    if all(s == "NO_DATA" for s in statuses):
        return "NO_DATA"
    if "OK" in statuses:
        return "OK"

    return "UNKNOWN"


def get_column_check_ids() -> list[str]:
    """Tum kolon check ID'lerini dondur"""
    return list(_COLUMN_CHECKS.keys())


# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    "registry",
    "CheckRegistry",
    "check_column_geometry",
    "check_column_axial",
    "check_column_pmm",
    "check_column_shear",
    "check_column_confinement",
    "check_column_capacity_hierarchy",
    "check_column_rebar_minimum",
    "check_column_design_full",
    "get_column_check_ids",
    "COLUMN_CHECK_METADATA",
]

# tbdy_engine/checks/registry.py

from tbdy_engine.design.beams.beam_module import BeamDesignModule

# ------------------------------
# Beam check registration
# ------------------------------

def register_beam_checks(registry, context):
    """
    Register all beam-related checks into the main registry.
    Each beam check returns a BeamCheckResult dict compatible with runner.
    """

    module = BeamDesignModule(context)

    # Beam Geometry
    registry.add_check(
        check_id="beam_geometry",
        fn=lambda ctx: module.run_geometry_checks(),
        category="geometry",
        description="Check beam geometry (width, depth, span)",
        depends_on=None,
    )

    # Flexure (Bending moment) check
    registry.add_check(
        check_id="beam_flexure",
        fn=lambda ctx: module.run_flexure_checks(),
        category="flexure",
        description="Beam bending moment capacity check (ETABS or DESIGN_LEVEL)",
        depends_on="beam_geometry",
    )

    # Shear check
    registry.add_check(
        check_id="beam_shear",
        fn=lambda ctx: module.run_shear_checks(),
        category="shear",
        description="Beam shear capacity check (Vc + Vw)",
        depends_on="beam_geometry",
    )

    # Ductility / detailing
    registry.add_check(
        check_id="beam_ductility",
        fn=lambda ctx: module.run_ductility_checks(),
        category="ductility",
        description="Beam ductility / detailing check",
        depends_on=["beam_flexure", "beam_shear"],
    )

    # Capacity hierarchy (requires topology)
    registry.add_check(
        check_id="beam_capacity_hierarchy",
        fn=lambda ctx: module.run_capacity_hierarchy_checks(),
        category="capacity_hierarchy",
        description="Beam capacity hierarchy vs connected columns",
        depends_on=["beam_geometry", "column_capacity_hierarchy"],
    )

    # Full beam design check (summary)
    registry.add_check(
        check_id="beam_design_full",
        fn=lambda ctx: module.run_full_design(),
        category="design_full",
        description="Full beam design evaluation summary",
        depends_on=[
            "beam_geometry",
            "beam_flexure",
            "beam_shear",
            "beam_ductility",
            "beam_capacity_hierarchy",
        ],
    )

    return True

# === SPRINT3_BEAM_REGISTRY_BEGIN ===
# Sprint 3 integration:
# - Activates topology using engine.topology.build_topology()
# - Registers beam checks into the existing registry object
# - Adds beam metadata after registry.load_from_matrix()
# - Overrides column_capacity_hierarchy message so it uses active topology
#
# This block is intentionally self-contained and fail-safe.
# It does not connect to ETABS directly; it only uses ModelContext tables.

def _sprint3_records(obj):
    if obj is None:
        return []
    if hasattr(obj, "empty") and obj.empty:
        return []
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict("records")
        except Exception:
            pass
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    return []


def _sprint3_frame_to_dict(frame):
    return {
        "label": getattr(frame, "label", ""),
        "story": getattr(frame, "story", ""),
        "section": getattr(frame, "section", ""),
        "unique_name": getattr(frame, "unique_name", ""),
        "design_type": getattr(frame, "design_type", ""),
        "length_m": getattr(frame, "length_m", 0.0),
        "jt_i": getattr(frame, "jt_i", ""),
        "jt_j": getattr(frame, "jt_j", ""),
        "classified_as": getattr(frame, "classified_as", ""),
        "coord_i": getattr(frame, "coord_i", None),
        "coord_j": getattr(frame, "coord_j", None),
    }


def _sprint3_joint_to_dict(joint):
    jt = getattr(joint, "joint_type", "")
    if hasattr(jt, "value"):
        jt = jt.value

    return {
        "name": getattr(joint, "name", ""),
        "story": getattr(joint, "story", ""),
        "x": getattr(joint, "x", 0.0),
        "y": getattr(joint, "y", 0.0),
        "z": getattr(joint, "z", 0.0),
        "connected_columns": list(set(getattr(joint, "connected_columns", []) or [])),
        "connected_beams": list(set(getattr(joint, "connected_beams", []) or [])),
        "joint_type": jt,
        "confinement_status": getattr(joint, "confinement_status", "UNKNOWN"),
    }


def _sprint3_ensure_topology(ctx):
    """
    Build ctx.topology as a dict expected by existing column/beam modules.

    Existing engine.topology provides build_topology(...), not TopologyResolver.
    """
    topo = getattr(ctx, "topology", None)
    if isinstance(topo, dict) and topo.get("topology_status") == "OK":
        return ctx

    try:
        from tbdy_engine.engine.topology import (
            build_topology,
            get_analysis_joints,
            get_column_beam_mapping_summary,
        )
    except Exception:
        return ctx

    tables = getattr(ctx, "tables", {}) or {}
    frame_rows = _sprint3_records(tables.get("frame_objects"))
    joint_rows = _sprint3_records(tables.get("joint_objects"))
    assign_rows = _sprint3_records(tables.get("frame_assigns_section"))

    try:
        topo_result = build_topology(
            frame_rows=frame_rows,
            joint_rows=joint_rows,
            assign_rows=assign_rows,
        )
    except Exception as exc:
        if not isinstance(topo, dict):
            topo = {}
        topo["topology_status"] = "WARNING"
        topo["topology_error"] = str(exc)
        ctx.topology = topo
        return ctx

    old_topology = getattr(ctx, "topology", {}) or {}
    if not isinstance(old_topology, dict):
        old_topology = {}

    topology = dict(old_topology)

    columns = [_sprint3_frame_to_dict(c) for c in topo_result.columns]
    beams = [_sprint3_frame_to_dict(b) for b in topo_result.beams]
    joints = {name: _sprint3_joint_to_dict(j) for name, j in topo_result.joints.items()}

    column_beam_map = {}
    beam_column_map = {}

    for key, cmap in topo_result.column_beam_map.items():
        beams_for_col = sorted(set(cmap.all_beams))
        column_beam_map[key] = beams_for_col
        column_beam_map[cmap.column_label] = beams_for_col

        for beam_label in beams_for_col:
            bkey = f"{cmap.story}|{beam_label}"
            beam_column_map.setdefault(bkey, [])
            beam_column_map.setdefault(beam_label, [])

            if key not in beam_column_map[bkey]:
                beam_column_map[bkey].append(key)
            if cmap.column_label not in beam_column_map[beam_label]:
                beam_column_map[beam_label].append(cmap.column_label)

    beam_end_joints = {}
    column_end_joints = {}

    for b in topo_result.beams:
        beam_end_joints[f"{b.story}|{b.label}"] = {"i": b.jt_i, "j": b.jt_j}
        beam_end_joints[b.label] = {"i": b.jt_i, "j": b.jt_j}

    for c in topo_result.columns:
        column_end_joints[f"{c.story}|{c.label}"] = {
            "i": c.jt_i,
            "j": c.jt_j,
            "top": c.top_joint,
            "bottom": c.bottom_joint,
        }
        column_end_joints[c.label] = {
            "i": c.jt_i,
            "j": c.jt_j,
            "top": c.top_joint,
            "bottom": c.bottom_joint,
        }

    joint_beams = {
        name: sorted(set(j.connected_beams))
        for name, j in topo_result.joints.items()
        if j.connected_beams
    }
    joint_columns = {
        name: sorted(set(j.connected_columns))
        for name, j in topo_result.joints.items()
        if j.connected_columns
    }

    topology.update({
        "topology_status": "OK" if topo_result.columns and topo_result.beams else "WARNING",
        "topology_summary": topo_result.summary,
        "topology_warnings": list(topo_result.warnings),
        "columns": columns,
        "beams": beams,
        "joints": joints,
        "joint_beams": joint_beams,
        "joint_columns": joint_columns,
        "beam_end_joints": beam_end_joints,
        "column_end_joints": column_end_joints,
        "column_beam_map": column_beam_map,
        "beam_column_map": beam_column_map,
        "analysis_joints": get_analysis_joints(topo_result),
        "column_beam_mapping_summary": get_column_beam_mapping_summary(topo_result),
        "_topology_result": topo_result,
    })

    ctx.topology = topology

    if not hasattr(ctx, "geometry") or ctx.geometry is None:
        ctx.geometry = {}

    ctx.geometry.setdefault("beam_sections", {})
    ctx.geometry.setdefault("column_sections", {})
    ctx.geometry.setdefault("beam_spans", {})

    for b in topo_result.beams:
        ctx.geometry["beam_sections"][b.label] = b.section
        ctx.geometry["beam_sections"][f"{b.story}|{b.label}"] = b.section
        if b.length_m and b.length_m > 0:
            ctx.geometry["beam_spans"][b.label] = b.length_m
            ctx.geometry["beam_spans"][f"{b.story}|{b.label}"] = b.length_m

    for c in topo_result.columns:
        ctx.geometry["column_sections"][c.label] = c.section
        ctx.geometry["column_sections"][f"{c.story}|{c.label}"] = c.section

    return ctx


def _sprint3_aggregate_status(details):
    statuses = [str(d.get("status", "")).upper() for d in details]
    if "FAIL" in statuses:
        return "FAIL"
    if "WARNING" in statuses:
        return "WARNING"
    if statuses and all(s == "NO_DATA" for s in statuses):
        return "NO_DATA"
    if "OK" in statuses:
        return "OK"
    return "NO_DATA"


def _sprint3_beam_module_result(ctx):
    _sprint3_ensure_topology(ctx)
    from tbdy_engine.design.beams.beam_module import BeamDesignModule
    return BeamDesignModule(ctx).run()


def _sprint3_beam_check(ctx, check_name):
    result = _sprint3_beam_module_result(ctx)
    outputs = result.get("outputs", []) or []
    details = []

    for out in outputs:
        checks = out.get("checks", {}) or {}
        c = checks.get(check_name)

        if not c:
            details.append({
                "element_id": out.get("label"),
                "story": out.get("story"),
                "section": out.get("section"),
                "status": "NO_DATA",
                "ratio": 0.0,
                "description": f"{check_name} result not available",
                "tbdy_ref": "",
                "evaluation_level": "NO_DATA",
            })
            continue

        details.append({
            "element_id": out.get("label"),
            "story": out.get("story"),
            "section": out.get("section"),
            "status": c.get("status", "NO_DATA"),
            "ratio": c.get("ratio", 0.0),
            "value": c.get("value"),
            "limit": c.get("limit"),
            "unit": c.get("unit", ""),
            "description": c.get("message", ""),
            "tbdy_ref": c.get("tbdy_ref", ""),
            "evaluation_level": c.get("evaluation_level", ""),
        })

    return {
        "check_id": f"beam_{check_name}",
        "status": _sprint3_aggregate_status(details),
        "description": f"Beam {check_name} check ({len(details)} beams)",
        "details": details,
    }


def check_beam_geometry(ctx):
    return _sprint3_beam_check(ctx, "geometry")


def check_beam_flexure(ctx):
    return _sprint3_beam_check(ctx, "flexure")


def check_beam_shear(ctx):
    return _sprint3_beam_check(ctx, "shear")


def check_beam_ductility(ctx):
    return _sprint3_beam_check(ctx, "ductility")


def check_beam_capacity_hierarchy(ctx):
    return _sprint3_beam_check(ctx, "capacity_hierarchy")


def check_beam_design_full(ctx):
    result = _sprint3_beam_module_result(ctx)
    details = []

    for out in result.get("outputs", []) or []:
        details.append({
            "element_id": out.get("label"),
            "story": out.get("story"),
            "section": out.get("section"),
            "status": out.get("status", "NO_DATA"),
            "ratio": out.get("governing_ratio", 0.0),
            "description": f"governing={out.get('governing_check')}",
            "tbdy_ref": "TBDY 2018 / TS500",
            "evaluation_level": "DESIGN_LEVEL",
        })

    return {
        "check_id": "beam_design_full",
        "status": result.get("package_status") or _sprint3_aggregate_status(details),
        "description": f"Full beam design package ({len(details)} beams)",
        "details": details,
    }


def check_column_capacity_hierarchy(ctx):
    """
    Topology-active column capacity hierarchy placeholder.

    This replaces the old misleading 'topology not found' behavior.
    It reports connected beams from ctx.topology["column_beam_map"].
    Full SCWB moment capacity will be added in the next capacity-design patch.
    """
    _sprint3_ensure_topology(ctx)

    try:
        from tbdy_engine.design.columns.module import ColumnDesignModule
        module = ColumnDesignModule(ctx)
        module.resolve_columns()
        columns = module._columns
    except Exception:
        columns = []

    topo = getattr(ctx, "topology", {}) or {}
    cmap = topo.get("column_beam_map", {}) if isinstance(topo, dict) else {}

    details = []

    for col in columns:
        key = f"{col.story}|{col.label}"
        beams = cmap.get(key) or cmap.get(col.label) or []

        if beams:
            details.append({
                "element_id": col.label,
                "story": col.story,
                "section": col.section_name,
                "status": "WARNING",
                "ratio": 0.0,
                "value": len(beams),
                "limit": 1.0,
                "unit": "count",
                "description": (
                    f"Topology active: {len(beams)} connected beams found. "
                    f"beams={beams[:8]}. Full SCWB moment-capacity calculation "
                    f"requires the next capacity-design patch."
                ),
                "tbdy_ref": "TBDY 2018 7.3.5",
                "evaluation_level": "TOPOLOGY_LEVEL",
            })
        else:
            details.append({
                "element_id": col.label,
                "story": col.story,
                "section": col.section_name,
                "status": "WARNING",
                "ratio": 0.0,
                "value": 0.0,
                "limit": 1.0,
                "unit": "count",
                "description": (
                    "Topology active, but no connected beam was mapped for this column. "
                    "Check joint/frame connectivity or story-label matching."
                ),
                "tbdy_ref": "TBDY 2018 7.3.5",
                "evaluation_level": "TOPOLOGY_LEVEL",
            })

    return {
        "check_id": "column_capacity_hierarchy",
        "status": _sprint3_aggregate_status(details),
        "description": f"Column capacity hierarchy topology check ({len(details)} columns)",
        "details": details,
    }


_SPRINT3_BEAM_CHECKS = {
    "beam_geometry": check_beam_geometry,
    "beam_flexure": check_beam_flexure,
    "beam_shear": check_beam_shear,
    "beam_ductility": check_beam_ductility,
    "beam_capacity_hierarchy": check_beam_capacity_hierarchy,
    "beam_design_full": check_beam_design_full,
}


_SPRINT3_BEAM_METADATA = {
    "beam_geometry": {
        "required_tables": ["frame_objects", "frame_assigns_section", "joint_objects"],
        "requires_topology": True,
        "requires_force_envelope": False,
        "requires_reinforcement": False,
    },
    "beam_flexure": {
        "required_tables": ["beam_design_summary", "frame_objects", "frame_assigns_section"],
        "requires_topology": True,
        "requires_force_envelope": True,
        "requires_reinforcement": True,
    },
    "beam_shear": {
        "required_tables": ["beam_forces", "beam_design_summary", "frame_objects"],
        "requires_topology": True,
        "requires_force_envelope": True,
        "requires_reinforcement": True,
    },
    "beam_ductility": {
        "required_tables": ["beam_design_summary", "frame_objects"],
        "requires_topology": True,
        "requires_force_envelope": False,
        "requires_reinforcement": True,
    },
    "beam_capacity_hierarchy": {
        "required_tables": ["frame_objects", "joint_objects", "frame_assigns_section"],
        "requires_topology": True,
        "requires_force_envelope": False,
        "requires_reinforcement": True,
    },
    "beam_design_full": {
        "required_tables": ["beam_design_summary", "beam_forces", "frame_objects"],
        "requires_topology": True,
        "requires_force_envelope": True,
        "requires_reinforcement": True,
    },
}


def _sprint3_register_beam_checks():
    """
    Register beam checks into every known registry storage.

    registry.load_from_matrix() may rebuild internal maps, so this function is
    called both immediately and after load_from_matrix().
    """
    funcs = dict(_SPRINT3_BEAM_CHECKS)
    funcs["column_capacity_hierarchy"] = check_column_capacity_hierarchy

    # Module-level dictionaries.
    for name in [
        "CHECKS", "_CHECKS", "CHECK_REGISTRY", "_CHECK_REGISTRY",
        "CHECK_FUNCTIONS", "_CHECK_FUNCTIONS", "_COLUMN_CHECKS",
    ]:
        d = globals().get(name)
        if isinstance(d, dict):
            d.update(funcs)

    reg = globals().get("registry")

    if reg is not None:
        # Common registry object dictionaries.
        for attr in [
            "checks", "_checks", "check_functions", "_check_functions",
            "functions", "_functions", "registry", "_registry",
        ]:
            d = getattr(reg, attr, None)
            if isinstance(d, dict):
                d.update(funcs)

        # Metadata.
        meta = getattr(reg, "metadata", None)
        if isinstance(meta, dict):
            for k, v in _SPRINT3_BEAM_METADATA.items():
                meta[k] = v

            # Improve dependencies for topology-driven column hierarchy.
            old = meta.get("column_capacity_hierarchy", {})
            if isinstance(old, dict):
                old = dict(old)
                old["requires_topology"] = True
                old.setdefault("required_tables", [])
                for t in ["frame_objects", "joint_objects", "frame_assigns_section"]:
                    if t not in old["required_tables"]:
                        old["required_tables"].append(t)
                meta["column_capacity_hierarchy"] = old

        # Try formal APIs if present.
        for check_id, fn in funcs.items():
            add_check = getattr(reg, "add_check", None)
            if callable(add_check):
                try:
                    add_check(check_id=check_id, fn=fn)
                except TypeError:
                    try:
                        add_check(check_id, fn)
                    except Exception:
                        pass
                except Exception:
                    pass

            register = getattr(reg, "register", None)
            if callable(register):
                try:
                    register(check_id, fn)
                except Exception:
                    pass

    return True


_sprint3_register_beam_checks()

try:
    _sprint3_original_load_from_matrix = registry.load_from_matrix

    def _sprint3_load_from_matrix_with_beams(*args, **kwargs):
        out = _sprint3_original_load_from_matrix(*args, **kwargs)
        _sprint3_register_beam_checks()
        return out

    registry.load_from_matrix = _sprint3_load_from_matrix_with_beams
except Exception:
    pass
# === SPRINT3_BEAM_REGISTRY_END ===

# === SPRINT32C_SCWB_REGISTRY_BEGIN ===
# Sprint 3.2c - SCWB registry integration.
#
# Replaces topology-only capacity hierarchy fallback with ScwbResolver output.
# It remains fail-safe:
# - APPROXIMATE results are WARNING, not hard FAIL.
# - DESIGN_LEVEL results may become OK/FAIL.
# - Runtime exceptions return WARNING/NO_DATA, never break the runner.

def _sprint32c_scwb_aggregate_status(details):
    statuses = [str(d.get("status", "")).upper() for d in details]

    if "FAIL" in statuses:
        return "FAIL"
    if "WARNING" in statuses:
        return "WARNING"
    if statuses and all(s == "NO_DATA" for s in statuses):
        return "NO_DATA"
    if "OK" in statuses:
        return "OK"
    return "NO_DATA"


def _sprint32c_scwb_evaluate(ctx):
    try:
        from tbdy_engine.design.joints.scwb import ScwbResolver
        return ScwbResolver(ctx).evaluate()
    except Exception as exc:
        return {
            "summary": {
                "total_joints": 0,
                "ok": 0,
                "fail": 0,
                "warning": 1,
                "no_data": 0,
                "package_status": "WARNING",
                "min_ratio": 0.0,
                "max_ratio": 0.0,
            },
            "results": [
                {
                    "joint_id": "",
                    "story": "",
                    "direction": "",
                    "columns": [],
                    "beams": [],
                    "sum_mrc_knm": 0.0,
                    "sum_mrb_knm": 0.0,
                    "required_mrc_knm": 0.0,
                    "ratio": 0.0,
                    "status": "WARNING",
                    "evaluation_level": "NO_DATA",
                    "note": f"SCWB resolver failed: {exc}",
                }
            ],
            "beam_capacity_count": 0,
            "column_capacity_count": 0,
        }


def _sprint32c_scwb_detail_from_result(r, element_id, mode):
    status = str(r.get("status") or "NO_DATA").upper()
    level = str(r.get("evaluation_level") or "NO_DATA")

    ratio = r.get("ratio", 0.0)
    try:
        ratio = float(ratio)
    except Exception:
        ratio = 0.0

    mrc = r.get("sum_mrc_knm", 0.0)
    mrb = r.get("sum_mrb_knm", 0.0)
    req = r.get("required_mrc_knm", 0.0)

    desc = (
        f"SCWB {mode}: joint={r.get('joint_id')} dir={r.get('direction')} "
        f"ratio={ratio:.3f}, Mrc={float(mrc or 0.0):.1f}kNm, "
        f"Mrb={float(mrb or 0.0):.1f}kNm, required={float(req or 0.0):.1f}kNm, "
        f"level={level}. {r.get('note') or ''}"
    )

    return {
        "element_id": element_id,
        "label": element_id,
        "story": r.get("story", ""),
        "status": status,
        "ratio": ratio,
        "value": mrc,
        "limit": req,
        "unit": "kNm",
        "description": desc,
        "message": desc,
        "tbdy_ref": "TBDY 2018 7.3.5",
        "evaluation_level": level,
        "joint_id": r.get("joint_id"),
        "direction": r.get("direction"),
        "columns": r.get("columns", []),
        "beams": r.get("beams", []),
        "sum_mrc_knm": mrc,
        "sum_mrb_knm": mrb,
        "required_mrc_knm": req,
        "source": "ScwbResolver",
    }


def check_column_capacity_hierarchy(ctx):
    result = _sprint32c_scwb_evaluate(ctx)
    rows = result.get("results", []) or []

    details = []

    for r in rows:
        cols = r.get("columns") or []

        if not cols:
            details.append(_sprint32c_scwb_detail_from_result(r, str(r.get("joint_id") or "?"), "column"))
            continue

        for col in cols:
            details.append(_sprint32c_scwb_detail_from_result(r, str(col), "column"))

    if not details:
        details.append({
            "element_id": "SCWB",
            "label": "SCWB",
            "story": "",
            "status": "NO_DATA",
            "ratio": 0.0,
            "value": 0.0,
            "limit": 0.0,
            "unit": "kNm",
            "description": "SCWB column capacity hierarchy produced no joint results",
            "message": "SCWB column capacity hierarchy produced no joint results",
            "tbdy_ref": "TBDY 2018 7.3.5",
            "evaluation_level": "NO_DATA",
            "source": "ScwbResolver",
        })

    summary = result.get("summary", {}) or {}

    return {
        "check_id": "column_capacity_hierarchy",
        "status": _sprint32c_scwb_aggregate_status(details),
        "description": (
            f"SCWB column capacity hierarchy from joint resolver "
            f"(joints={summary.get('total_joints', len(rows))}, "
            f"min_ratio={summary.get('min_ratio', 0.0)}, "
            f"max_ratio={summary.get('max_ratio', 0.0)})"
        ),
        "details": details,
    }


def check_beam_capacity_hierarchy(ctx):
    result = _sprint32c_scwb_evaluate(ctx)
    rows = result.get("results", []) or []

    details = []

    for r in rows:
        beams = r.get("beams") or []

        if not beams:
            details.append(_sprint32c_scwb_detail_from_result(r, str(r.get("joint_id") or "?"), "beam"))
            continue

        for beam in beams:
            details.append(_sprint32c_scwb_detail_from_result(r, str(beam), "beam"))

    if not details:
        details.append({
            "element_id": "SCWB",
            "label": "SCWB",
            "story": "",
            "status": "NO_DATA",
            "ratio": 0.0,
            "value": 0.0,
            "limit": 0.0,
            "unit": "kNm",
            "description": "SCWB beam capacity hierarchy produced no joint results",
            "message": "SCWB beam capacity hierarchy produced no joint results",
            "tbdy_ref": "TBDY 2018 7.3.5",
            "evaluation_level": "NO_DATA",
            "source": "ScwbResolver",
        })

    summary = result.get("summary", {}) or {}

    return {
        "check_id": "beam_capacity_hierarchy",
        "status": _sprint32c_scwb_aggregate_status(details),
        "description": (
            f"SCWB beam capacity hierarchy from joint resolver "
            f"(joints={summary.get('total_joints', len(rows))}, "
            f"min_ratio={summary.get('min_ratio', 0.0)}, "
            f"max_ratio={summary.get('max_ratio', 0.0)})"
        ),
        "details": details,
    }


def _sprint32c_register_scwb_checks():
    funcs = {
        "column_capacity_hierarchy": check_column_capacity_hierarchy,
        "beam_capacity_hierarchy": check_beam_capacity_hierarchy,
    }

    # Module-level dictionaries.
    for name in [
        "CHECKS", "_CHECKS", "CHECK_REGISTRY", "_CHECK_REGISTRY",
        "CHECK_FUNCTIONS", "_CHECK_FUNCTIONS", "_COLUMN_CHECKS",
    ]:
        d = globals().get(name)
        if isinstance(d, dict):
            d.update(funcs)

    reg = globals().get("registry")

    if reg is not None:
        for attr in [
            "checks", "_checks", "check_functions", "_check_functions",
            "functions", "_functions", "registry", "_registry",
        ]:
            d = getattr(reg, attr, None)
            if isinstance(d, dict):
                d.update(funcs)

        meta = getattr(reg, "metadata", None)
        if isinstance(meta, dict):
            for check_id in ["column_capacity_hierarchy", "beam_capacity_hierarchy"]:
                old = meta.get(check_id, {})
                if not isinstance(old, dict):
                    old = {}

                old = dict(old)
                old["requires_topology"] = True
                old["requires_reinforcement"] = True
                old["requires_force_envelope"] = False
                old.setdefault("required_tables", [])

                for t in ["frame_objects", "joint_objects", "frame_assigns_section"]:
                    if t not in old["required_tables"]:
                        old["required_tables"].append(t)

                meta[check_id] = old

        for check_id, fn in funcs.items():
            add_check = getattr(reg, "add_check", None)
            if callable(add_check):
                try:
                    add_check(check_id=check_id, fn=fn)
                except TypeError:
                    try:
                        add_check(check_id, fn)
                    except Exception:
                        pass
                except Exception:
                    pass

            register = getattr(reg, "register", None)
            if callable(register):
                try:
                    register(check_id, fn)
                except Exception:
                    pass

    return True


_sprint32c_register_scwb_checks()

try:
    _sprint32c_original_load_from_matrix = registry.load_from_matrix

    def _sprint32c_load_from_matrix_with_scwb(*args, **kwargs):
        out = _sprint32c_original_load_from_matrix(*args, **kwargs)

        try:
            _sprint32c_register_scwb_checks()
        except Exception:
            pass

        return out

    registry.load_from_matrix = _sprint32c_load_from_matrix_with_scwb
except Exception:
    pass
# === SPRINT32C_SCWB_REGISTRY_END ===

# ---------------------------------------------------------------------------
# Legacy beam registry safety patch
# ---------------------------------------------------------------------------
# Some older patch code used registry.add_check(...), but current CheckRegistry
# exposes registry.register(check_id, func). Keep beam checks explicitly bound
# to preserve legacy runner behavior.

for _beam_check_id, _beam_func in {
    "beam_geometry": check_beam_geometry,
    "beam_flexure": check_beam_flexure,
    "beam_shear": check_beam_shear,
    "beam_ductility": check_beam_ductility,
    "beam_capacity_hierarchy": check_beam_capacity_hierarchy,
    "beam_design_full": check_beam_design_full,
}.items():
    registry.register(_beam_check_id, _beam_func)

# ---------------------------------------------------------------------------
# Beam registry v2 API compatibility patch
# ---------------------------------------------------------------------------
# Current BeamDesignModule API exposes:
#   check_geometry, check_flexure, check_shear, check_ductility,
#   check_capacity_hierarchy, run
# Older registry wrappers used _sprint3_beam_check(ctx, "geometry") and
# returned NO_DATA total=0. Override beam wrappers here with current API.

def _beam_v2_as_result(check_id, module_result):
    if module_result is None:
        return {
            "check_id": check_id,
            "status": "NO_DATA",
            "description": f"{check_id}: no result returned",
            "details": [],
        }

    if isinstance(module_result, dict):
        if "check_id" not in module_result:
            module_result["check_id"] = check_id
        if "details" not in module_result and "outputs" in module_result:
            module_result["details"] = module_result.get("outputs") or []
        if "status" not in module_result:
            module_result["status"] = _sprint3_aggregate_status(module_result.get("details", []) or [])
        return module_result

    if isinstance(module_result, list):
        return {
            "check_id": check_id,
            "status": _sprint3_aggregate_status(module_result),
            "description": f"{check_id}: {len(module_result)} details",
            "details": module_result,
        }

    return {
        "check_id": check_id,
        "status": "NO_DATA",
        "description": f"{check_id}: unsupported result type {type(module_result).__name__}",
        "details": [],
    }


def check_beam_geometry(ctx):
    module = BeamDesignModule(ctx)
    return _beam_v2_as_result("beam_geometry", module.check_geometry())


def check_beam_flexure(ctx):
    module = BeamDesignModule(ctx)
    return _beam_v2_as_result("beam_flexure", module.check_flexure())


def check_beam_shear(ctx):
    module = BeamDesignModule(ctx)
    return _beam_v2_as_result("beam_shear", module.check_shear())


def check_beam_ductility(ctx):
    module = BeamDesignModule(ctx)
    return _beam_v2_as_result("beam_ductility", module.check_ductility())


def check_beam_capacity_hierarchy(ctx):
    module = BeamDesignModule(ctx)
    return _beam_v2_as_result("beam_capacity_hierarchy", module.check_capacity_hierarchy())


def check_beam_design_full(ctx):
    module = BeamDesignModule(ctx)
    result = module.run()

    if isinstance(result, dict):
        details = []
        for out in result.get("outputs", []) or []:
            if isinstance(out, dict):
                details.append({
                    "element_id": out.get("label") or out.get("element_id"),
                    "story": out.get("story"),
                    "section": out.get("section"),
                    "status": out.get("status", "NO_DATA"),
                    "ratio": out.get("governing_ratio", out.get("ratio", 0.0)),
                    "description": f"governing={out.get('governing_check', '')}",
                    "tbdy_ref": "TBDY 2018 / TS500",
                    "evaluation_level": out.get("evaluation_level", "DESIGN_LEVEL"),
                })

        if not details and "details" in result:
            details = result.get("details") or []

        return {
            "check_id": "beam_design_full",
            "status": result.get("package_status") or result.get("status") or _sprint3_aggregate_status(details),
            "description": f"Full beam design package ({len(details)} beams)",
            "details": details,
        }

    return _beam_v2_as_result("beam_design_full", result)


for _beam_check_id, _beam_func in {
    "beam_geometry": check_beam_geometry,
    "beam_flexure": check_beam_flexure,
    "beam_shear": check_beam_shear,
    "beam_ductility": check_beam_ductility,
    "beam_capacity_hierarchy": check_beam_capacity_hierarchy,
    "beam_design_full": check_beam_design_full,
}.items():
    registry.register(_beam_check_id, _beam_func)

# === Beam registry v2 API compatibility patch END ===

# ---------------------------------------------------------------------------
# Beam capacity hierarchy compatibility hotfix
# ---------------------------------------------------------------------------
# BeamDesignModule.check_capacity_hierarchy requires a single beam argument.
# For legacy runner package-level check, use the older Sprint3 wrapper path so
# the check remains non-crashing and reports ND/WARNING until SCWB package-level
# beam hierarchy is wired explicitly.

def check_beam_capacity_hierarchy(ctx):
    return _sprint3_beam_check(ctx, "capacity_hierarchy")

registry.register("beam_capacity_hierarchy", check_beam_capacity_hierarchy)

# === Beam capacity hierarchy compatibility hotfix END ===
