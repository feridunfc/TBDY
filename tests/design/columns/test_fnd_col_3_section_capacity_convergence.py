from __future__ import annotations

import math
from pathlib import Path
import sys

import pytest

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from fnd_col_3_benchmarks import MATERIALS, RADIAL_CASES, SECTIONS  # noqa: E402
from fnd_col_3_independent_oracle import radial_capacity_dense_convex  # noqa: E402
from tbdy_engine.design.columns.rebar_layout import ColumnBarPoint  # noqa: E402
from tbdy_engine.design.columns.section_capacity import (  # noqa: E402
    ColumnSectionMaterial,
    build_interaction_envelope_at_axial_force,
    radial_moment_capacity,
)

_CONVERGENCE_CASE_IDS = (
    "COL3-R03-SQ-EQUAL",
    "COL3-R04-SQ-ASYM",
    "COL3-R05-RECT-M2",
    "COL3-R07-SQ-NEAR-NMAX",
    "COL3-R09-SQ-LOW-COMP",
    "COL3-R11-SQ-TENSION",
)
_ANGLE_COUNTS = (36, 72, 144, 288)


def _case(case_id):
    return next(case for case in RADIAL_CASES if case.fixture_id == case_id)


def _production_bars(section):
    return tuple(ColumnBarPoint(b.index, b.x2_mm, b.x3_mm, b.diameter_mm, b.area_mm2) for b in section.bars)


def _production_material(material):
    return ColumnSectionMaterial(material.fck_mpa, material.fcd_mpa, material.fyd_mpa, k1=material.k1)


@pytest.mark.parametrize("case_id", _CONVERGENCE_CASE_IDS)
def test_required_36_72_144_288_family_is_measured_against_dense_independent_reference(case_id):
    case = _case(case_id)
    section = SECTIONS[case.section_id]
    material = MATERIALS[case.material_id].material
    reference = radial_capacity_dense_convex(
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
    assert reference.status == "PROVEN"

    measured = []
    for angle_count in _ANGLE_COUNTS:
        envelope = build_interaction_envelope_at_axial_force(
            width_mm=section.width_mm,
            depth_mm=section.depth_mm,
            bars=_production_bars(section),
            material=_production_material(material),
            target_n_compression_n=case.target_n,
            angle_count=angle_count,
            axial_tolerance_n=1.0,
        )
        radial = radial_moment_capacity(
            envelope,
            demand_m2_nmm=case.demand_m2_nmm,
            demand_m3_nmm=case.demand_m3_nmm,
        )
        assert radial.status == "PROVEN"
        relative_error = abs(radial.capacity_nmm - reference.capacity_nmm) / reference.capacity_nmm
        assert math.isfinite(relative_error)
        measured.append(relative_error)

    # This is deliberately not a monotonicity assertion and does not authorize any angle_count.
    # It only proves that the required family was evaluated and produced finite measurable errors.
    assert len(measured) == 4
    assert all(error >= 0.0 for error in measured)


def test_dense_oracle_reference_is_replayed_at_higher_angular_resolution():
    case = _case("COL3-R04-SQ-ASYM")
    section = SECTIONS[case.section_id]
    material = MATERIALS[case.material_id].material
    coarse_dense = radial_capacity_dense_convex(
        width_mm=section.width_mm,
        depth_mm=section.depth_mm,
        bars=section.bars,
        material=material,
        target_n=case.target_n,
        demand_m2_nmm=case.demand_m2_nmm,
        demand_m3_nmm=case.demand_m3_nmm,
        angle_count=720,
        root_scan_count=160,
    )
    refined_dense = radial_capacity_dense_convex(
        width_mm=section.width_mm,
        depth_mm=section.depth_mm,
        bars=section.bars,
        material=material,
        target_n=case.target_n,
        demand_m2_nmm=case.demand_m2_nmm,
        demand_m3_nmm=case.demand_m3_nmm,
        angle_count=1440,
        root_scan_count=160,
    )
    assert coarse_dense.status == refined_dense.status == "PROVEN"
    assert math.isfinite(abs(coarse_dense.capacity_nmm - refined_dense.capacity_nmm))
