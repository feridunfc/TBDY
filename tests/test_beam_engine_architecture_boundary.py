"""
Beam Design Engine — Architecture Boundary testleri.
"""

import inspect
import pytest


# =============================================================================
# Boundary Scan Helpers
# =============================================================================

FORBIDDEN_IN_DESIGN = [
    "comtypes", "SapModel", "FrameForce",
    "ETABS design output", "ETABSDesignOutput",
    "provided_area", "selected_area",
    "ReportingFacade", "CheckAdapter",
    "BeamEvaluationPackage", "streamlit",
    # Design calculation terms (should not be in context/demand)
]

FORBIDDEN_IN_CONTEXT = FORBIDDEN_IN_DESIGN + [
    "As_required", "Mpr", "Ve_capacity",
]

FORBIDDEN_IN_DEMAND = FORBIDDEN_IN_DESIGN + [
    "As_required", "Mpr", "Ve_capacity",
]


def _scan_module(module_name: str, forbidden: list[str]):
    """Modül kaynak kodunda yasaklı terimleri tara."""
    import importlib
    mod = importlib.import_module(module_name)
    source = inspect.getsource(mod)
    found = []
    for term in forbidden:
        if term in source:
            found.append(term)
    return found


# =============================================================================
# Test 1: context.py has no design/ETABS terms
# =============================================================================

def test_context_no_forbidden_terms():
    found = _scan_module(
        "tbdy_engine.design.beams.context",
        FORBIDDEN_IN_CONTEXT,
    )
    assert not found, f"Forbidden terms in context.py: {found}"


# =============================================================================
# Test 2: demand.py has no design calculation terms
# =============================================================================

def test_demand_no_design_calculation_terms():
    # demand.py contains RawFrameForceRow, so FrameForce is allowed there
    demand_forbidden = [
        t for t in FORBIDDEN_IN_DEMAND
        if t != "FrameForce"
    ]
    found = _scan_module(
        "tbdy_engine.design.beams.demand",
        demand_forbidden,
    )
    assert not found, f"Forbidden terms in demand.py: {found}"


# =============================================================================
# Test 3: design_result.py has no ETABS/provider terms
# =============================================================================

def test_design_result_no_etabs_terms():
    found = _scan_module(
        "tbdy_engine.design.beams.design_result",
        FORBIDDEN_IN_DESIGN,
    )
    assert not found, f"Forbidden terms in design_result.py: {found}"


# =============================================================================
# Test 4: demand_processor.py has no design calculation terms
# =============================================================================

def test_demand_processor_no_design_terms():
    # demand_processor may import RawFrameForceRow from demand.py; the boundary guard
    # forbids provider/ETABS leakage terms except that dataclass name.
    demand_processor_forbidden = [
        t for t in FORBIDDEN_IN_DEMAND
        if t != "FrameForce"
    ]
    found = _scan_module(
        "tbdy_engine.design.beams.demand_processor",
        demand_processor_forbidden,
    )
    assert not found, f"Forbidden terms in demand_processor.py: {found}"


# =============================================================================
# Test 5: provided_reinforcement is separate from design engine
# =============================================================================

def test_provided_reinforcement_not_in_design():
    """Provided reinforcement modülü design engine altında değil."""
    # verification modülü design'dan ayrı olmalı
    from tbdy_engine.verification.beams.provided_reinforcement import (
        BeamProvidedReinforcement,
    )
    from tbdy_engine.design.beams.context import BeamModelContext

    # İki sınıf farklı modüllerde
    assert BeamProvidedReinforcement.__module__ != BeamModelContext.__module__
    assert "verification" in BeamProvidedReinforcement.__module__
    assert "design" in BeamModelContext.__module__


# =============================================================================
# Test 6: verification_result does not mutate BeamDesignResult
# =============================================================================

def test_verification_result_does_not_mutate_design_result():
    """VerificationResult, BeamDesignResult'ı içermez/değiştirmez."""
    from tbdy_engine.verification.beams.verification_result import (
        BeamVerificationResult,
        ETABSComparisonResult,
    )

    vr_fields = set(BeamVerificationResult.__dataclass_fields__.keys())
    assert "design_result" not in vr_fields
    assert "BeamDesignResult" not in vr_fields

    cr_fields = set(ETABSComparisonResult.__dataclass_fields__.keys())
    assert "design_result" not in cr_fields
    assert "BeamDesignResult" not in cr_fields


# =============================================================================
# Test 7: Design Engine boundary documented
# =============================================================================

def test_boundary_documentation_exists():
    """Boundary guard dokümanı mevcut."""
    from pathlib import Path

    doc_path = Path(__file__).parent.parent / "docs" / "beam_engine_architecture_boundary.md"
    if not doc_path.exists():
        doc_path = Path(__file__).parent.parent / ".." / "docs" / "beam_engine_architecture_boundary.md"

    # En azından bir boundary dokümanı var mı kontrol et
    docs_dir = Path(__file__).parent.parent / "docs"
    if docs_dir.exists():
        md_files = list(docs_dir.glob("*boundary*.md")) + list(docs_dir.glob("*architecture*.md"))
        assert len(md_files) > 0, "No boundary/architecture documentation found in docs/"
    else:
        # docs/ henüz yoksa bu testi skip et
        pytest.skip("docs/ directory not found")


# =============================================================================
# Test 8: Status defaults are NOT_EVALUATED
# =============================================================================

def test_status_defaults_not_evaluated():
    """Tüm design/verification result'ların default status'u NOT_EVALUATED."""
    from tbdy_engine.design.beams.design_result import (
        BeamDesignResult,
        BeamFlexureDesignResult,
        BeamFlexureLimitResult,
        BeamPlasticMomentResult,
        BeamCapacityDesignResult,
        BeamShearDesignResult,
    )
    from tbdy_engine.verification.beams.verification_result import (
        BeamVerificationResult,
        ReinforcementVerificationItem,
    )

    assert BeamDesignResult(beam_id="1", label="B1").status == "NOT_EVALUATED"
    assert BeamFlexureDesignResult().status == "NOT_EVALUATED"
    assert BeamFlexureLimitResult().status == "NOT_EVALUATED"
    assert BeamPlasticMomentResult().status == "NOT_EVALUATED"
    assert BeamCapacityDesignResult().status == "NOT_EVALUATED"
    assert BeamShearDesignResult().status == "NOT_EVALUATED"
    assert BeamVerificationResult(beam_id="1", label="B1").status == "NOT_EVALUATED"
    assert ReinforcementVerificationItem().status == "UNKNOWN"
