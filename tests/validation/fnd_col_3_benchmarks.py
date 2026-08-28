"""Deterministic numerical-validation fixtures for FND-COL-3.

All geometry/material values here are validation fixtures only. They are not cover,
tie, detailing, selection, or regulatory-default authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from fnd_col_3_independent_oracle import OracleBar, OracleMaterial, axial_limits


@dataclass(frozen=True, slots=True)
class SectionFixture:
    fixture_id: str
    width_mm: float
    depth_mm: float
    bars: tuple[OracleBar, ...]


@dataclass(frozen=True, slots=True)
class MaterialFixture:
    fixture_id: str
    material: OracleMaterial


@dataclass(frozen=True, slots=True)
class RadialCase:
    fixture_id: str
    section_id: str
    material_id: str
    target_kind: str
    target_n: float
    demand_m2_nmm: float
    demand_m3_nmm: float


def _bar(index: int, x2: float, x3: float, diameter: float = 20.0) -> OracleBar:
    return OracleBar(index=index, x2_mm=x2, x3_mm=x3, diameter_mm=diameter, area_mm2=math.pi * diameter * diameter / 4.0)


def _eight_bar_layout(x: float, y: float) -> tuple[OracleBar, ...]:
    coords = ((-x, -y), (0.0, -y), (x, -y), (-x, 0.0), (x, 0.0), (-x, y), (0.0, y), (x, y))
    return tuple(_bar(i + 1, x2, x3) for i, (x2, x3) in enumerate(coords))


SQ = SectionFixture("SQ_800_800_8D20", 800.0, 800.0, _eight_bar_layout(340.0, 340.0))
RECT = SectionFixture("RECT_600_900_8D20", 600.0, 900.0, _eight_bar_layout(240.0, 390.0))
SECTIONS = {SQ.fixture_id: SQ, RECT.fixture_id: RECT}


def _material(fck: float, k1: float) -> MaterialFixture:
    return MaterialFixture(
        fixture_id=f"C{int(fck)}_B500_VALIDATION",
        material=OracleMaterial(
            fck_mpa=fck,
            fcd_mpa=fck / 1.5,
            fyd_mpa=500.0 / 1.15,
            k1=k1,
        ),
    )


C25 = _material(25.0, 0.85)
C35 = _material(35.0, 0.79)
C50 = _material(50.0, 0.70)
MATERIALS = {m.fixture_id: m for m in (C25, C35, C50)}


def build_radial_cases() -> tuple[RadialCase, ...]:
    mat = C35.material
    sq_nmin, sq_nmax = axial_limits(width_mm=SQ.width_mm, depth_mm=SQ.depth_mm, bars=SQ.bars, material=mat)
    rect_nmin, rect_nmax = axial_limits(width_mm=RECT.width_mm, depth_mm=RECT.depth_mm, bars=RECT.bars, material=mat)
    # Demand vector magnitudes are arbitrary rays only; radial capacity is independent of their scale.
    return (
        RadialCase("COL3-R01-SQ-M2", SQ.fixture_id, C35.fixture_id, "moderate_compression", 3_000_000.0, 1.0, 0.0),
        RadialCase("COL3-R02-SQ-M3", SQ.fixture_id, C35.fixture_id, "moderate_compression", 3_000_000.0, 0.0, 1.0),
        RadialCase("COL3-R03-SQ-EQUAL", SQ.fixture_id, C35.fixture_id, "moderate_compression", 3_000_000.0, 1.0, 1.0),
        RadialCase("COL3-R04-SQ-ASYM", SQ.fixture_id, C35.fixture_id, "moderate_compression", 3_000_000.0, 2.0, 1.0),
        RadialCase("COL3-R05-RECT-M2", RECT.fixture_id, C35.fixture_id, "moderate_compression", 3_000_000.0, 1.0, 0.0),
        RadialCase("COL3-R06-RECT-M3", RECT.fixture_id, C35.fixture_id, "moderate_compression", 3_000_000.0, 0.0, 1.0),
        RadialCase("COL3-R07-SQ-NEAR-NMAX", SQ.fixture_id, C35.fixture_id, "near_compression_boundary", 0.98 * sq_nmax, 1.0, 0.7),
        RadialCase("COL3-R08-SQ-OUT-NMAX", SQ.fixture_id, C35.fixture_id, "outside_compression_boundary", 1.01 * sq_nmax, 1.0, 0.7),
        RadialCase("COL3-R09-SQ-LOW-COMP", SQ.fixture_id, C35.fixture_id, "low_compression", 0.10 * sq_nmax, 1.0, 2.0),
        RadialCase("COL3-R10-SQ-SIGN-ROT", SQ.fixture_id, C35.fixture_id, "moderate_compression", 3_000_000.0, -2.0, 1.0),
        RadialCase("COL3-R11-SQ-TENSION", SQ.fixture_id, C35.fixture_id, "moderate_tension", 0.50 * sq_nmin, 1.0, -1.5),
        RadialCase("COL3-R12-SQ-OUT-TENSION", SQ.fixture_id, C35.fixture_id, "outside_tension_boundary", 1.01 * sq_nmin, 1.0, -1.5),
    )


RADIAL_CASES = build_radial_cases()

# Accepted hand-reducible fixed-c states. Values are frozen numerical-validation fixtures,
# independently derived from the same stated physics, not by calling the production kernel.
ANALYTIC_STATES = (
    # fixture_id, section, material, theta_deg, c_mm, N_N, M2_Nmm, M3_Nmm
    ("COL3-A01-SQ-T0-C180", SQ.fixture_id, C35.fixture_id, 0.0, 180.0, 1_931_583.717448, 0.0, -1_003_221_678.966),
    ("COL3-A02-SQ-T90-C300", SQ.fixture_id, C35.fixture_id, 90.0, 300.0, 3_616_043.817568, 1_330_842_767.337, 0.0),
    ("COL3-A03-SQ-T0-C500", SQ.fixture_id, C35.fixture_id, 0.0, 500.0, 6_462_378.430277, 0.0, -1_494_389_788.491),
    ("COL3-A04-RECT-T0-C180", RECT.fixture_id, C35.fixture_id, 0.0, 180.0, 2_235_468.275039, 0.0, -765_347_186.270),
    ("COL3-A05-RECT-T90-C300", RECT.fixture_id, C35.fixture_id, 90.0, 300.0, 2_613_111.964496, 1_247_262_289.004, 0.0),
    ("COL3-A06-RECT-T0-C500", RECT.fixture_id, C35.fixture_id, 0.0, 500.0, 7_534_926.340829, 0.0, -827_418_534.057),
)
