from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VALIDATION_DIR = _REPO_ROOT / "tests" / "validation"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

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


def _production_bars(section):
    return tuple(ColumnBarPoint(b.index, b.x2_mm, b.x3_mm, b.diameter_mm, b.area_mm2) for b in section.bars)


def _production_material(material):
    return ColumnSectionMaterial(material.fck_mpa, material.fcd_mpa, material.fyd_mpa, k1=material.k1)


def _rounded(value: float) -> float:
    return round(float(value), 6)


def build_canonical_validation_payload() -> dict:
    rows = []
    for case in RADIAL_CASES:
        section = SECTIONS[case.section_id]
        material = MATERIALS[case.material_id].material
        envelope = build_interaction_envelope_at_axial_force(
            width_mm=section.width_mm,
            depth_mm=section.depth_mm,
            bars=_production_bars(section),
            material=_production_material(material),
            target_n_compression_n=case.target_n,
            angle_count=288,
            axial_tolerance_n=1.0,
        )
        production = radial_moment_capacity(
            envelope,
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
            angle_count=360,
            root_scan_count=120,
            axial_tolerance_n=1.0,
        )
        rows.append(
            {
                "fixture_id": case.fixture_id,
                "production_envelope_status": envelope.status,
                "production_radial_status": production.status,
                "production_capacity_nmm": _rounded(production.capacity_nmm),
                "oracle_status": independent.status,
                "oracle_capacity_nmm": _rounded(independent.capacity_nmm),
                "production_state_count": len(envelope.states),
            }
        )
    return {
        "schema": "FND_COL_3_NUMERICAL_VALIDATION_PAYLOAD_V1",
        "production_angle_count": 288,
        "determinism_oracle_angle_count": 360,
        "rows": rows,
    }


def _sha() -> str:
    payload = build_canonical_validation_payload()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def test_canonical_payload_is_byte_identical_across_two_fresh_interpreters():
    repo_root = Path(__file__).resolve().parents[3]
    command = [sys.executable, str(Path(__file__).resolve()), "--emit-sha"]
    run1 = subprocess.check_output(command, cwd=repo_root, text=True).strip()
    run2 = subprocess.check_output(command, cwd=repo_root, text=True).strip()
    assert len(run1) == len(run2) == 64
    assert run1 == run2


if __name__ == "__main__" and "--emit-sha" in sys.argv:
    print(_sha())
