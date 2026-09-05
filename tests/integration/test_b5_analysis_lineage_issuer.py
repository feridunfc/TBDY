from __future__ import annotations

import pytest

from tbdy_engine.integration.etabs_analysis_lineage import (
    AnalysisLineageQualificationError,
    build_analysis_result_identity,
    build_analysis_state_identity,
    issue_qualified_analysis_lineage_from_controlled_execution,
)


def _state(source: str, execution: str):
    return build_analysis_state_identity(
        source_model_ref=source,
        execution_state_ref=execution,
        state_basis_refs=(f"basis:{execution}",),
    )


def test_controlled_execution_issuer_builds_qualified_lineage_without_private_factory_escape():
    state = _state("source:test", "state:test")
    result = build_analysis_result_identity(
        source_model_ref=state.source_model_ref,
        parent_analysis_state_ref=state.identity_ref,
        analysis_generation_ref="generation:test",
        result_scope_refs=("scope:b", "scope:a"),
        provenance_refs=("population:test",),
    )

    qualification = issue_qualified_analysis_lineage_from_controlled_execution(
        analysis_state=state,
        analysis_result=result,
        execution_proof_ref="execution-proof:test",
        execution_provenance_refs=("run:test", "population:test"),
        qualification_provenance_refs=("manifest:test",),
        capture_provenance_refs=("capture:test",),
    )

    assert qualification.qualified is True
    assert qualification.analysis_result == result
    assert qualification.analysis_state == state
    assert "execution-proof:test" in qualification.qualification_provenance_refs
    assert "population:test" in qualification.qualification_provenance_refs


def test_controlled_execution_issuer_rejects_result_parented_by_other_state():
    state = _state("source:test", "state:a")
    other = _state("source:test", "state:b")
    result = build_analysis_result_identity(
        source_model_ref=other.source_model_ref,
        parent_analysis_state_ref=other.identity_ref,
        analysis_generation_ref="generation:test",
        result_scope_refs=("scope:test",),
    )

    with pytest.raises(AnalysisLineageQualificationError, match="parent state mismatch"):
        issue_qualified_analysis_lineage_from_controlled_execution(
            analysis_state=state,
            analysis_result=result,
            execution_proof_ref="execution-proof:test",
            execution_provenance_refs=("run:test",),
            qualification_provenance_refs=("manifest:test",),
        )
