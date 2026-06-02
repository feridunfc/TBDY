"""
Beam Flexure Kernel Benchmark Suite.
Golden fixture tests for Md→As kernel.
"""

import json
from pathlib import Path

import pytest

from tbdy_engine.design.beams.calculators.flexure_design import (
    FlexureMdToAsInput,
    flexure_md_to_as,
    STATUS_OK,
)

FIXTURES = Path(__file__).parent / "fixtures"


# =============================================================================
# Helpers
# =============================================================================

def _load_fixture(name: str) -> dict:
    """Load a benchmark fixture JSON file."""
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    with open(path) as f:
        return json.load(f)


def _run_case(fixture: dict):
    """Run kernel against fixture input and validate against expected ranges."""
    inp = fixture["input"]
    expected = fixture["expected"]

    flex_input = FlexureMdToAsInput(
        Md_kNm=inp["Md_kNm"],
        bw_mm=inp["bw_mm"],
        d_mm=inp["d_mm"],
        fcd_mpa=inp["fcd_mpa"],
        fyd_mpa=inp["fyd_mpa"],
        alpha=inp.get("alpha", 0.85),
        beta=inp.get("beta", 0.85),
    )

    result = flexure_md_to_as(flex_input)

    # Status
    assert result.status == expected["status"], (
        f"{fixture['case_id']}: expected status {expected['status']}, got {result.status}"
    )

    # Mu_check >= Md
    assert result.Mu_check_kNm >= inp["Md_kNm"], (
        f"{fixture['case_id']}: Mu_check={result.Mu_check_kNm} < Md={inp['Md_kNm']}"
    )

    # As_required_cm2 range
    if "As_required_cm2_min" in expected and "As_required_cm2_max" in expected:
        assert expected["As_required_cm2_min"] <= result.As_required_cm2 <= expected["As_required_cm2_max"], (
            f"{fixture['case_id']}: As_required_cm2={result.As_required_cm2:.2f} "
            f"not in [{expected['As_required_cm2_min']}, {expected['As_required_cm2_max']}]"
        )

    # a_mm range
    if "a_mm_min" in expected and "a_mm_max" in expected:
        assert expected["a_mm_min"] <= result.a_mm <= expected["a_mm_max"], (
            f"{fixture['case_id']}: a_mm={result.a_mm:.1f} "
            f"not in [{expected['a_mm_min']}, {expected['a_mm_max']}]"
        )

    # c_mm range
    if "c_mm_min" in expected and "c_mm_max" in expected:
        assert expected["c_mm_min"] <= result.c_mm <= expected["c_mm_max"], (
            f"{fixture['case_id']}: c_mm={result.c_mm:.1f} "
            f"not in [{expected['c_mm_min']}, {expected['c_mm_max']}]"
        )

    # neutral_axis_ratio range
    if "neutral_axis_ratio_min" in expected:
        assert result.neutral_axis_ratio >= expected["neutral_axis_ratio_min"], (
            f"{fixture['case_id']}: c/d={result.neutral_axis_ratio:.4f} < {expected['neutral_axis_ratio_min']}"
        )
    if "neutral_axis_ratio_max" in expected:
        assert result.neutral_axis_ratio <= expected["neutral_axis_ratio_max"], (
            f"{fixture['case_id']}: c/d={result.neutral_axis_ratio:.4f} > {expected['neutral_axis_ratio_max']}"
        )

    # lever_arm_z_mm range
    if "lever_arm_z_mm_min" in expected:
        assert result.lever_arm_z_mm >= expected["lever_arm_z_mm_min"], (
            f"{fixture['case_id']}: z={result.lever_arm_z_mm:.1f} < {expected['lever_arm_z_mm_min']}"
        )
    if "lever_arm_z_mm_max" in expected:
        assert result.lever_arm_z_mm <= expected["lever_arm_z_mm_max"], (
            f"{fixture['case_id']}: z={result.lever_arm_z_mm:.1f} > {expected['lever_arm_z_mm_max']}"
        )

    # rho_required range
    if "rho_required_min" in expected:
        assert result.rho_required >= expected["rho_required_min"], (
            f"{fixture['case_id']}: rho={result.rho_required:.6f} < {expected['rho_required_min']}"
        )
    if "rho_required_max" in expected:
        assert result.rho_required <= expected["rho_required_max"], (
            f"{fixture['case_id']}: rho={result.rho_required:.6f} > {expected['rho_required_max']}"
        )

    # iterations range
    if "iterations_min" in expected:
        assert result.iterations >= expected["iterations_min"], (
            f"{fixture['case_id']}: iterations={result.iterations} < {expected['iterations_min']}"
        )
    if "iterations_max" in expected:
        assert result.iterations <= expected["iterations_max"], (
            f"{fixture['case_id']}: iterations={result.iterations} > {expected['iterations_max']}"
        )


# =============================================================================
# Test 1: Case 01 — Typical 400 kNm
# =============================================================================

def test_benchmark_case_01():
    fixture = _load_fixture("beam_flexure_md_to_as_case_01.json")
    _run_case(fixture)


# =============================================================================
# Test 2: Case 02 — High moment 800 kNm
# =============================================================================

def test_benchmark_case_02():
    fixture = _load_fixture("beam_flexure_md_to_as_case_02.json")
    _run_case(fixture)


# =============================================================================
# Test 3: Case 03 — Edge case 50 kNm
# =============================================================================

def test_benchmark_case_03_edge():
    fixture = _load_fixture("beam_flexure_md_to_as_case_03_edge.json")
    _run_case(fixture)


# =============================================================================
# Test 4: Determinism across all fixtures
# =============================================================================

def test_benchmark_determinism():
    """All fixture cases must produce identical results on repeated runs."""
    from dataclasses import asdict

    for fixture_name in [
        "beam_flexure_md_to_as_case_01.json",
        "beam_flexure_md_to_as_case_02.json",
        "beam_flexure_md_to_as_case_03_edge.json",
    ]:
        fixture = _load_fixture(fixture_name)
        inp = fixture["input"]

        flex_input = FlexureMdToAsInput(
            Md_kNm=inp["Md_kNm"],
            bw_mm=inp["bw_mm"],
            d_mm=inp["d_mm"],
            fcd_mpa=inp["fcd_mpa"],
            fyd_mpa=inp["fyd_mpa"],
            alpha=inp.get("alpha", 0.85),
            beta=inp.get("beta", 0.85),
        )

        first = asdict(flexure_md_to_as(flex_input))
        for _ in range(50):
            again = asdict(flexure_md_to_as(flex_input))
            assert again == first, (
                f"{fixture_name}: non-deterministic result"
            )


# =============================================================================
# Test 5: Evidence completeness
# =============================================================================

def test_benchmark_evidence_completeness():
    """All fixture cases must produce complete evidence."""
    for fixture_name in [
        "beam_flexure_md_to_as_case_01.json",
        "beam_flexure_md_to_as_case_02.json",
        "beam_flexure_md_to_as_case_03_edge.json",
    ]:
        fixture = _load_fixture(fixture_name)
        inp = fixture["input"]

        flex_input = FlexureMdToAsInput(
            Md_kNm=inp["Md_kNm"],
            bw_mm=inp["bw_mm"],
            d_mm=inp["d_mm"],
            fcd_mpa=inp["fcd_mpa"],
            fyd_mpa=inp["fyd_mpa"],
            alpha=inp.get("alpha", 0.85),
            beta=inp.get("beta", 0.85),
        )

        result = flexure_md_to_as(flex_input)
        evidence = dict(result.evidence)

        required_keys = [
            "method", "formula_Mu", "formula_a", "formula_c",
            "alpha", "beta", "Md_kNm", "Mu_Nmm", "Mu_ge_Md",
            "tolerance", "max_iterations", "units",
        ]
        for key in required_keys:
            assert key in evidence, (
                f"{fixture_name}: missing evidence key '{key}'"
            )
