from __future__ import annotations

from pathlib import Path
import sys

import pytest

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from fnd_col_3_benchmarks import ANALYTIC_STATES, C25, C35, C50, MATERIALS, SECTIONS  # noqa: E402
from fnd_col_3_independent_oracle import evaluate_state  # noqa: E402
from tbdy_engine.design.columns.rebar_layout import ColumnBarPoint  # noqa: E402
from tbdy_engine.design.columns.section_capacity import (  # noqa: E402
    ColumnSectionCapacityError,
    ColumnSectionMaterial,
    evaluate_rectangular_column_capacity_state,
    ts500_k1_for_fck_mpa,
)


def _production_bars(section):
    return tuple(
        ColumnBarPoint(
            index=bar.index,
            x2_mm=bar.x2_mm,
            x3_mm=bar.x3_mm,
            diameter_mm=bar.diameter_mm,
            area_mm2=bar.area_mm2,
        )
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


def _assert_moment(actual_nmm: float, expected_nmm: float) -> None:
    if abs(expected_nmm) <= 1e-6:
        assert abs(actual_nmm) <= 1.0
        return
    absolute_ok = abs(actual_nmm - expected_nmm) <= 1_000.0  # 0.001 kN.m
    relative_ok = abs(actual_nmm - expected_nmm) / abs(expected_nmm) <= 1e-6
    assert absolute_ok or relative_ok


@pytest.mark.parametrize(
    "fixture_id,section_id,material_id,theta_deg,c_mm,expected_n,expected_m2,expected_m3",
    ANALYTIC_STATES,
)
def test_frozen_hand_reducible_states_match_production_and_independent_oracle(
    fixture_id,
    section_id,
    material_id,
    theta_deg,
    c_mm,
    expected_n,
    expected_m2,
    expected_m3,
):
    section = SECTIONS[section_id]
    material = MATERIALS[material_id].material

    oracle = evaluate_state(
        width_mm=section.width_mm,
        depth_mm=section.depth_mm,
        bars=section.bars,
        material=material,
        theta_deg=theta_deg,
        c_mm=c_mm,
    )
    production = evaluate_rectangular_column_capacity_state(
        width_mm=section.width_mm,
        depth_mm=section.depth_mm,
        bars=_production_bars(section),
        material=_production_material(material),
        neutral_axis_angle_deg=theta_deg,
        neutral_axis_depth_c_mm=c_mm,
    )

    # Frozen expected values are numerical-validation fixtures, not production-derived answers.
    assert abs(oracle.n_n - expected_n) <= 1.0, fixture_id
    assert abs(production.n_compression_n - expected_n) <= 1.0, fixture_id
    _assert_moment(oracle.m2_nmm, expected_m2)
    _assert_moment(oracle.m3_nmm, expected_m3)
    _assert_moment(production.m2_nmm, expected_m2)
    _assert_moment(production.m3_nmm, expected_m3)


@pytest.mark.parametrize("material_fixture", (C25, C35, C50))
def test_c25_c35_c50_material_states_match_independent_oracle(material_fixture):
    section = SECTIONS["SQ_800_800_8D20"]
    material = material_fixture.material
    oracle = evaluate_state(
        width_mm=section.width_mm,
        depth_mm=section.depth_mm,
        bars=section.bars,
        material=material,
        theta_deg=33.0,
        c_mm=320.0,
    )
    production = evaluate_rectangular_column_capacity_state(
        width_mm=section.width_mm,
        depth_mm=section.depth_mm,
        bars=_production_bars(section),
        material=_production_material(material),
        neutral_axis_angle_deg=33.0,
        neutral_axis_depth_c_mm=320.0,
    )
    assert ts500_k1_for_fck_mpa(material.fck_mpa) == pytest.approx(material.k1, abs=1e-12)
    assert abs(production.n_compression_n - oracle.n_n) <= 1.0
    _assert_moment(production.m2_nmm, oracle.m2_nmm)
    _assert_moment(production.m3_nmm, oracle.m3_nmm)


def test_material_validation_does_not_expand_beyond_c50():
    with pytest.raises(ColumnSectionCapacityError, match="outside the source-bound"):
        ts500_k1_for_fck_mpa(55.0)
