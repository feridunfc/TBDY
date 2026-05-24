# app/engine/report_template_basis.py
"""Design-basis defaults extracted from the structural design report template.

Source document supplied by the user:
Yapisal_Tasarim_Raporu_v2_Kapsamli(4).docx

This module intentionally contains engineering assumptions from the report
template. ETABS model tables may override seismic parameters where available;
user/project input should override both ETABS and this template when explicitly
provided by the application layer.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

TEMPLATE_SOURCE = "report_template:Yapisal_Tasarim_Raporu_v2_Kapsamli_v4"

REPORT_TEMPLATE_DESIGN_BASIS: Dict[str, Any] = {
    "code": "TBDY 2018",
    "concrete_code": "TS500-2000",
    "international_code": "ACI 318-19",
    "analysis_method": "Mod Süperpozisyonu ile Modal Analiz (CQC)",
    "earthquake_level": "DD-2 (50 yılda aşılma olasılığı %10)",
    "soil_class": "ZD",
    "structural_system": "Betonarme çerçeve + boşluksuz perde",
    "ductility_level": "Süneklik düzeyi yüksek",
    "diaphragm_type": "Semi-Rijit",
    "damping_ratio": 0.05,
    "live_load_mass_factor": 0.30,
    "accidental_eccentricity": 0.05,
    "beta_min": 0.90,
    "temperature_delta_c": 20.0,
    "vertical_seismic_rule": "EDZ = 2/3 * SDS * G",
    # Materials: report template Section 3.
    "concrete_class": "C35",
    "fck_mpa": 35.0,
    "gamma_c": 1.50,
    "fcd_mpa": 23.33,
    "fctd_mpa": 1.38,
    "ec_mpa": 33000.0,
    "rebar_class": "B500C",
    "fyk_mpa": 500.0,
    "gamma_s": 1.15,
    "fyd_mpa": 434.8,
    "fywd_mpa": 434.8,
    "es_mpa": 200000.0,
    # Minimum covers: report template Table 3.4.
    "cover_m": {
        "foundation": 0.050,
        "column": 0.035,
        "wall": 0.035,
        "beam": 0.030,
        "slab": 0.025,
        "retaining_wall": 0.050,
    },
    "column_cover_m": 0.035,
    "beam_cover_m": 0.030,
    "wall_cover_m": 0.035,
    "slab_cover_m": 0.025,
    # Engineering limits used by current checks.
    "modal_mass_target": 0.95,
    "drift_limit": 0.008,
    "drift_multiplier": 1.0,
    "column_axial_limit": 0.40,
    "column_shear_ratio_limit": 1.0,
    "beam_shear_ratio_limit": 1.0,
    "wall_shear_ratio_limit": 1.0,
    "confinement_s_max_m": 0.10,
    "confinement_bar_min_mm": 8.0,
    # Template load case / combination policy.
    "load_case_naming": {
        "rs_x": "LC_RSX",
        "rs_x_plus": "LC_RSXP",
        "rs_x_minus": "LC_RSXN",
        "rs_y": "LC_RSY",
        "rs_y_plus": "LC_RSYP",
        "rs_y_minus": "LC_RSYN",
        "eq_x": "LC_EQX",
        "eq_y": "LC_EQY",
        "vertical_seismic": "LC_EDZ",
    },
    "combo_group_counts_expected": {
        "G": 4,
        "H": 2,
        "E_UNC": 72,
        "E_CRK": 48,
        "EQ_UNC": 12,
        "EQ_CRK": 8,
        "EH_UNC": 24,
        "EH_CRK": 24,
        "ED_UNC": 24,
        "ED_CRK": 24,
        "T": 2,
        "ENV": 8,
    },
    "cracked_section_modifiers": {
        "beam_flexure": 0.35,
        "column_flexure": 0.70,
        "wall_flexure": 0.50,
        "beam_shear": 1.0,
        "column_shear": 1.0,
        "wall_shear": 1.0,
    },
}

REPORT_TEMPLATE_SPECTRUM: Dict[str, Any] = {
    # Template explicitly fixes D=2.5 in ED combinations and uses EDZ=0.351*DL,
    # which is compatible with SDS≈0.5265 via 2/3*SDS. R/I remain ETABS/user
    # overridable because the template narrative does not pin a unique value.
    "D": 2.5,
    "SDS": 0.526,
    "SD1": 0.265,
    "I": 1.5,
    "R": 7.0,
    "kappa": 0.5,
}


def template_design_basis() -> Dict[str, Any]:
    data = deepcopy(REPORT_TEMPLATE_DESIGN_BASIS)
    data["sources"] = {key: TEMPLATE_SOURCE for key in data if key != "sources"}
    return data


def template_spectrum() -> Dict[str, Any]:
    data = deepcopy(REPORT_TEMPLATE_SPECTRUM)
    data["sources"] = {key: TEMPLATE_SOURCE for key in data}
    return data
