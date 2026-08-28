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

# VALIDATION REGRESSION CONTRACT ONLY.
# These fixtures freeze independently reproduced numerical evidence. They do NOT
# authorize a canonical PMM angle count, PMM PASS/FAIL, or any regulatory rule.
_ANGLE_COUNTS = (36, 72, 144, 288, 576, 1152)

# Dense independent reference capacities (Nmm).  Each reference was obtained
# with the committed strip-integration/all-bracket/Jarvis-march oracle, not the
# production section-capacity implementation.  Difficult cases use the final
# independently refined resolution shown in _ORACLE_REFINEMENT_EVIDENCE.
_DENSE_REFERENCE_CAPACITY_NMM = {
    "COL3-R03-SQ-EQUAL": 1_157_513_946.6468995,      # oracle 1440; 720 == 1440
    "COL3-R04-SQ-ASYM": 1_176_357_494.2922966,      # oracle 5760
    "COL3-R05-RECT-M2": 1_312_601_779.5240593,      # oracle 1440; 720 == 1440
    "COL3-R07-SQ-NEAR-NMAX": 83_410_390.56462118,   # oracle 11520
    "COL3-R09-SQ-LOW-COMP": 850_689_072.4778277,    # oracle 5760
    "COL3-R11-SQ-TENSION": 237_681_061.6352266,     # oracle 11520
}

# Measured production relative errors against the independently refined
# references above.  This table intentionally does not assert monotonicity.
# A materially different numerical response must fail this regression.
_PRODUCTION_RELATIVE_ERROR = {
    "COL3-R03-SQ-EQUAL": {
        36: 1.9714526510237794e-03,
        72: 6.927465160298695e-08,
        144: 6.927465160298695e-08,
        288: 6.927465160298695e-08,
        576: 6.927465160298695e-08,
        1152: 6.927465160298695e-08,
    },
    "COL3-R04-SQ-ASYM": {
        36: 2.2738243106748455e-03,
        72: 7.594532857062093e-04,
        144: 1.0011101766360204e-04,
        288: 4.328753295922514e-05,
        576: 1.2425829026195007e-05,
        1152: 2.2140748687654306e-06,
    },
    "COL3-R05-RECT-M2": {
        36: 2.0461094316061712e-08,
        72: 2.0461094316061712e-08,
        144: 2.0461094134423547e-08,
        288: 2.0461094316061712e-08,
        576: 2.0461094134423547e-08,
        1152: 2.0461094316061712e-08,
    },
    "COL3-R07-SQ-NEAR-NMAX": {
        36: 3.986775184166073e-03,
        72: 9.944487553906745e-04,
        144: 1.647735932771592e-04,
        288: 1.647735932771592e-04,
        576: 6.605565272257372e-05,
        1152: 1.9698396389456445e-05,
    },
    "COL3-R09-SQ-LOW-COMP": {
        36: 7.953458389831975e-04,
        72: 3.762174256059046e-04,
        144: 1.526287077342538e-04,
        288: 3.584851046596881e-05,
        576: 1.0150406929319974e-05,
        1152: 1.9252593372926586e-06,
    },
    "COL3-R11-SQ-TENSION": {
        36: 2.481835809189837e-03,
        72: 5.353764428992274e-04,
        144: 2.6254458836895216e-05,
        288: 2.6254458836895216e-05,
        576: 3.689462501190147e-06,
        1152: 1.988510916027303e-06,
    },
}

# Independent-oracle refinement evidence.  The near-Nmax case is deliberately
# refined beyond 2880 because 720/1440/2880 alias to the same sampled boundary
# while 5760 reveals a non-negligible change.  The final pair for every difficult
# case is <= 1e-7 relative; this is a validation-reference convergence criterion,
# not a production PMM tolerance or angle-count authorization.
_ORACLE_REFINEMENT_EVIDENCE = {
    "COL3-R04-SQ-ASYM": {
        720: 1_176_350_405.5337224,
        1440: 1_176_354_987.0652506,
        2880: 1_176_357_425.9525092,
        5760: 1_176_357_494.2922966,
    },
    "COL3-R07-SQ-NEAR-NMAX": {
        720: 83_409_099.75467241,
        1440: 83_409_099.75467241,
        2880: 83_409_099.75467241,
        5760: 83_410_390.56462118,
        11520: 83_410_390.56462118,
    },
    "COL3-R09-SQ-LOW-COMP": {
        720: 850_684_716.1679977,
        1440: 850_687_650.7517537,
        2880: 850_689_067.0528003,
        5760: 850_689_072.4778277,
    },
    "COL3-R11-SQ-TENSION": {
        720: 237_680_478.99254113,
        1440: 237_680_647.78352022,
        2880: 237_680_919.41873538,
        5760: 237_681_044.5590813,
        11520: 237_681_061.6352266,
    },
}
_FINAL_ORACLE_REFINEMENT_RELATIVE_BOUND = 1.0e-7


def _case(case_id):
    return next(case for case in RADIAL_CASES if case.fixture_id == case_id)


def _production_bars(section):
    return tuple(ColumnBarPoint(b.index, b.x2_mm, b.x3_mm, b.diameter_mm, b.area_mm2) for b in section.bars)


def _production_material(material):
    return ColumnSectionMaterial(material.fck_mpa, material.fcd_mpa, material.fyd_mpa, k1=material.k1)


def _oracle_capacity(case_id: str, angle_count: int) -> float:
    case = _case(case_id)
    section = SECTIONS[case.section_id]
    material = MATERIALS[case.material_id].material
    result = radial_capacity_dense_convex(
        width_mm=section.width_mm,
        depth_mm=section.depth_mm,
        bars=section.bars,
        material=material,
        target_n=case.target_n,
        demand_m2_nmm=case.demand_m2_nmm,
        demand_m3_nmm=case.demand_m3_nmm,
        angle_count=angle_count,
        root_scan_count=160,
        axial_tolerance_n=1.0,
    )
    assert result.status == "PROVEN"
    return result.capacity_nmm


@pytest.mark.parametrize("case_id", tuple(_PRODUCTION_RELATIVE_ERROR))
def test_production_angular_family_matches_frozen_independent_convergence_evidence(case_id):
    case = _case(case_id)
    section = SECTIONS[case.section_id]
    material = MATERIALS[case.material_id].material
    reference = _DENSE_REFERENCE_CAPACITY_NMM[case_id]

    measured = {}
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
        relative_error = abs(radial.capacity_nmm - reference) / reference
        assert math.isfinite(relative_error)
        measured[angle_count] = relative_error

    # Not monotonic by contract: freeze each measured value independently.
    for angle_count, expected in _PRODUCTION_RELATIVE_ERROR[case_id].items():
        assert measured[angle_count] == pytest.approx(expected, rel=0.02, abs=5.0e-8)


@pytest.mark.parametrize("case_id", tuple(_ORACLE_REFINEMENT_EVIDENCE))
def test_dense_independent_reference_is_refinement_converged_and_reproducible(case_id):
    expected = _ORACLE_REFINEMENT_EVIDENCE[case_id]
    measured = {}
    for angle_count, frozen_capacity in expected.items():
        capacity = _oracle_capacity(case_id, angle_count)
        measured[angle_count] = capacity
        assert capacity == pytest.approx(frozen_capacity, rel=5.0e-9, abs=1.0)

    counts = tuple(expected)
    assert counts[:3] == (720, 1440, 2880)

    # Freeze all measured refinement deltas for diagnostic reproducibility.
    deltas = []
    for coarse, refined in zip(counts, counts[1:]):
        delta = abs(measured[refined] - measured[coarse]) / measured[refined]
        assert math.isfinite(delta)
        deltas.append(delta)

    # Only the independently refined final pair is used to establish that the
    # stored accuracy reference itself is converged.  Earlier pairs are allowed
    # to be non-monotonic or aliased (notably near Nmax).
    assert deltas[-1] <= _FINAL_ORACLE_REFINEMENT_RELATIVE_BOUND
    assert measured[counts[-1]] == pytest.approx(
        _DENSE_REFERENCE_CAPACITY_NMM[case_id], rel=5.0e-9, abs=1.0
    )
