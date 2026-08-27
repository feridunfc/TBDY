import inspect
from pathlib import Path

from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    AnalysisBasisEligibilityEvidence,
    reconcile_concrete_design_combos,
)
from tbdy_engine.design.columns.column_design_readiness import ColumnDesignDemandReadiness
import tbdy_engine.regulatory.fnd_col_2 as fnd_col_2
import tbdy_engine.regulatory.fnd_col_2_program as fnd_col_2_program


def test_p8a_analysis_basis_eligibility_is_combo_grain_not_component_readiness():
    signature = inspect.signature(reconcile_concrete_design_combos)
    assert "analysis_basis_by_combo" in signature.parameters
    annotation = signature.parameters["analysis_basis_by_combo"].annotation
    assert "AnalysisBasisEligibilityEvidence" in str(annotation)

    assert "component_id" in ColumnDesignDemandReadiness.__dataclass_fields__
    assert "combo_ref" not in ColumnDesignDemandReadiness.__dataclass_fields__

    match_only = AnalysisBasisEligibilityEvidence(
        status_value="MATCH",
        compatibility_ref="analysis-basis:fixture",
        provenance_refs=("fixture:compatibility",),
    )
    assert match_only.acceptable is True
    # MATCH is intentionally only the existing P8A join primitive. FND-COL-2
    # must not manufacture one from a component-scoped readiness result.


def test_fnd_col_2_has_no_direct_p8a_analysis_basis_or_rebar_promotion_wiring():
    source = inspect.getsource(fnd_col_2) + inspect.getsource(fnd_col_2_program)
    assert "AnalysisBasisEligibilityEvidence" not in source
    assert "LIVE_BLOCKED_ANALYSIS_BASIS_EVIDENCE_REQUIRED" not in source
    assert "ETABS_REQUIRED_REBAR" not in source
    assert "ENGINE_SELECTED_REBAR" not in source


def test_documented_downstream_boundary_requires_separate_combo_projection():
    repo_root = Path(__file__).resolve().parents[2]
    text = (
        repo_root / "docs" / "architecture" / "FND_COL_2_DOWNSTREAM_ELIGIBILITY_BOUNDARY.md"
    ).read_text(encoding="utf-8")
    assert "Analysis-basis compatibility" in text
    assert "Full column design-demand readiness" in text
    assert "P8A reinforcement-promotion eligibility" in text
    assert "ColumnComboEligibilityProjection" in text
    assert "does **not** close `LIVE_BLOCKED_ANALYSIS_BASIS_EVIDENCE_REQUIRED`" in text
    assert "MUST NOT be converted directly into P8A `AnalysisBasisEligibilityEvidence`" in text
