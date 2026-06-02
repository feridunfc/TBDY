"""ETABS Crosscheck boundary tests."""

import inspect
import pytest


# =============================================================================
# Test 1: No design calculator imports in crosscheck
# =============================================================================

def test_no_design_calculator_imports():
    """Crosscheck modules do not import design calculators."""
    forbidden = [
        "flexure_md_to_as",
        "flexure_limits",
        "plastic_moment",
        "capacity_design_ve",
        "shear_reinforcement_design(",
    ]

    modules_to_check = [
        "tbdy_engine.verification.beams.etabs_design_output",
        "tbdy_engine.verification.beams.comparison_result",
        "tbdy_engine.verification.beams.etabs_crosscheck",
    ]

    for mod_name in modules_to_check:
        import importlib
        mod = importlib.import_module(mod_name)
        source = inspect.getsource(mod)
        for term in forbidden:
            assert term not in source, (
                f"Forbidden design import '{term}' in {mod_name}"
            )


# =============================================================================
# Test 2: No ETABS COM or model adapter imports
# =============================================================================

def test_no_etabs_imports():
    """Crosscheck modules do not import ETABS COM/model adapters."""
    forbidden = [
        "comtypes", "SapModel", "FrameForce",
        "read_etabs_table_on_demand",
    ]

    modules_to_check = [
        "tbdy_engine.verification.beams.etabs_design_output",
        "tbdy_engine.verification.beams.comparison_result",
        "tbdy_engine.verification.beams.etabs_crosscheck",
    ]

    for mod_name in modules_to_check:
        import importlib
        mod = importlib.import_module(mod_name)
        source = inspect.getsource(mod)
        for term in forbidden:
            assert term not in source, (
                f"Forbidden ETABS import '{term}' in {mod_name}"
            )


# =============================================================================
# Test 3: No reporting or UI imports
# =============================================================================

def test_no_reporting_imports():
    """Crosscheck modules do not import reporting/UI."""
    forbidden = [
        "ReportingFacade", "CheckAdapter",
        "BeamEvaluationPackage", "streamlit",
    ]

    modules_to_check = [
        "tbdy_engine.verification.beams.etabs_design_output",
        "tbdy_engine.verification.beams.comparison_result",
        "tbdy_engine.verification.beams.etabs_crosscheck",
    ]

    for mod_name in modules_to_check:
        import importlib
        mod = importlib.import_module(mod_name)
        source = inspect.getsource(mod)
        for term in forbidden:
            assert term not in source, (
                f"Forbidden reporting import '{term}' in {mod_name}"
            )
