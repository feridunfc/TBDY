from __future__ import annotations

import ast
import inspect
import math
from pathlib import Path
import sys

import pytest

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import fnd_col_3_independent_oracle as oracle_module  # noqa: E402
from fnd_col_3_benchmarks import C35, MATERIALS, RADIAL_CASES, RECT, SECTIONS, SQ  # noqa: E402
from fnd_col_3_independent_oracle import (  # noqa: E402
    audit_fixed_p_roots,
    radial_capacity_dense_convex,
)
from tbdy_engine.design.columns.rebar_layout import ColumnBarPoint  # noqa: E402
from tbdy_engine.design.columns.section_capacity import (  # noqa: E402
    ColumnSectionMaterial,
    build_interaction_envelope_at_axial_force,
    radial_moment_capacity,
    solve_capacity_state_for_axial_force,
)

# A deliberately loose smoke guard only. It is NOT the canonical PMM validation tolerance.
# Supervisor acceptance must use the measured error distribution/convergence evidence instead.
_NON_CANONICAL_GROSS_RELATIVE_ERROR_GUARD = 0.01


def _production_bars(section):
    return tuple(
        ColumnBarPoint(bar.index, bar.x2_mm, bar.x3_mm, bar.diameter_mm, bar.area_mm2)
        for bar in section.bars
    )


def _production_material(material):
    return ColumnSectionMaterial(
        fck_mpa=material.fck_mpa,
        fcd_mpa=material.fcd_mpa,
        fyd_mpa=material.fyd_mpa,
        k1=material.k1,
        es_mpa=material.es_mpa,
        epsilon_cu=material.epsilon_cu,
    )


def test_oracle_has_no_production_section_capacity_import():
    tree = ast.parse(inspect.getsource(oracle_module))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(name == "tbdy_engine.design.columns.section_capacity" for name in imported)


_ROOT_AUDIT_STATES = (
    ("SQ_MODERATE", SQ, C35.material, 3_000_000.0),
    ("RECT_MODERATE", RECT, C35.material, 3_000_000.0),
    ("SQ_NEAR_COMPRESSION", SQ, C35.material, next(c.target_n for c in RADIAL_CASES if c.fixture_id == "COL3-R07-SQ-NEAR-NMAX")),
    ("SQ_LOW_COMPRESSION", SQ, C35.material, next(c.target_n for c in RADIAL_CASES if c.fixture_id == "COL3-R09-SQ-LOW-COMP")),
    ("SQ_TENSION", SQ, C35.material, next(c.target_n for c in RADIAL_CASES if c.fixture_id == "COL3-R11-SQ-TENSION")),
)


@pytest.mark.parametrize("audit_id,section,material,target_n", _ROOT_AUDIT_STATES)
@pytest.mark.parametrize("theta_deg", (0.0, 17.0, 33.0, 45.0, 90.0, 123.0))
def test_supported_fixed_p_roots_are_unique_and_match_production(audit_id, section, material, target_n, theta_deg):
    audit = audit_fixed_p_roots(
        width_mm=section.width_mm,
        depth_mm=section.depth_mm,
        bars=section.bars,
        material=material,
        theta_deg=theta_deg,
        target_n=target_n,
        scan_count=1200,
        axial_tolerance_n=1.0,
    )
    assert audit.root_count == 1, (audit_id, theta_deg, audit.brackets, audit.roots_mm)
    assert audit.max_negative_delta_n >= -1.0, (audit_id, theta_deg, audit.max_negative_delta_n)

    production = solve_capacity_state_for_axial_force(
        width_mm=section.width_mm,
        depth_mm=section.depth_mm,
        bars=_production_bars(section),
        material=_production_material(material),
        neutral_axis_angle_deg=theta_deg,
        target_n_compression_n=target_n,
        axial_tolerance_n=1.0,
    )
    assert production is not None
    assert abs(production.n_compression_n - target_n) <= 1.0
    assert abs(production.neutral_axis_depth_c_mm - audit.roots_mm[0]) <= 0.01


@pytest.mark.parametrize("case", RADIAL_CASES, ids=lambda case: case.fixture_id)
def test_clean_twelve_case_radial_matrix(case):
    section = SECTIONS[case.section_id]
    material = MATERIALS[case.material_id].material
    production_envelope = build_interaction_envelope_at_axial_force(
        width_mm=section.width_mm,
        depth_mm=section.depth_mm,
        bars=_production_bars(section),
        material=_production_material(material),
        target_n_compression_n=case.target_n,
        angle_count=288,
        axial_tolerance_n=1.0,
    )
    production = radial_moment_capacity(
        production_envelope,
        demand_m2_nmm=case.demand_m2_nmm,
        demand_m3_nmm=case.demand_m3_nmm,
    )
    independent = radial_capacity_dense_convex(
        width_mm=section.width_mm,
        depth_mm=section.depth_mm,
        bars=section.bars,
        material=material,
        target_n=case.target_n,
        demand_m2_nmm=case.demand_m2_nmm,
        demand_m3_nmm=case.demand_m3_nmm,
        angle_count=720,
        root_scan_count=160,
        axial_tolerance_n=1.0,
    )

    outside = case.target_kind.startswith("outside_")
    if outside:
        assert production_envelope.status == "OUTSIDE_AXIAL_CAPACITY"
        assert production.status == "NO_CAPACITY_ENVELOPE"
        assert independent.status == "NO_CAPACITY_ENVELOPE"
        assert production.capacity_nmm == 0.0
        assert independent.capacity_nmm == 0.0
        return

    assert production_envelope.status == "PROVEN"
    assert production.status == "PROVEN"
    assert independent.status == "PROVEN"
    assert math.isfinite(production.capacity_nmm) and production.capacity_nmm > 0.0
    assert math.isfinite(independent.capacity_nmm) and independent.capacity_nmm > 0.0
    assert max(abs(state.n_compression_n - case.target_n) for state in production_envelope.states) <= 1.0
    assert independent.axial_residual_n is not None and independent.axial_residual_n <= 1.0
    relative_error = abs(production.capacity_nmm - independent.capacity_nmm) / independent.capacity_nmm
    assert relative_error < _NON_CANONICAL_GROSS_RELATIVE_ERROR_GUARD
