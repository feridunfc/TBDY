"""B4A derived/pre-analysis state contract and negative authority proofs."""
from __future__ import annotations

from dataclasses import fields
import inspect
from pathlib import Path

import pytest

import tbdy_engine.integration.etabs_derived_state as subject
from tbdy_engine.integration.etabs_analysis_lineage import AnalysisStateIdentity


ROOT = Path(__file__).resolve().parents[2]
SOURCE = "etabs-source-model-ref:sha256:" + "1" * 64


def _request(*states, provenance_refs=()):
    return subject.RequestedDerivedStateManifest(
        source_model_ref=SOURCE,
        entries=tuple(states),
        provenance_refs=provenance_refs,
    )


def _established(*states, source_model_ref=SOURCE, provenance_refs=()):
    return subject.EstablishedDerivedStateManifest(
        source_model_ref=source_model_ref,
        entries=tuple(states),
        provenance_refs=provenance_refs,
    )


def _mass(value, *, normalization=subject.NormalizationContract(), tolerance=subject.NumericTolerance()):
    return subject.request_derived_state(
        family=subject.DerivedStateFamily.MASS_SOURCE,
        value=value,
        normalization=normalization,
        tolerance=tolerance,
    )


def _mass_readback(value, *, normalization=subject.NormalizationContract(), evidence=("readback:mass-source:1",)):
    return subject.establish_derived_state_from_readback(
        family=subject.DerivedStateFamily.MASS_SOURCE,
        readback_value=value,
        readback_evidence_refs=evidence,
        normalization=normalization,
    )


def test_state_family_census_separates_causal_execution_ephemeral_context_and_design_state():
    expected = {
        subject.DerivedStateFamily.MASS_SOURCE: subject.DerivedStateFamilyClassification.CAUSAL_DERIVED_STATE,
        subject.DerivedStateFamily.MODAL_CASE_SETUP: subject.DerivedStateFamilyClassification.CAUSAL_DERIVED_STATE,
        subject.DerivedStateFamily.SECTION_STIFFNESS_MODIFIERS: subject.DerivedStateFamilyClassification.CAUSAL_DERIVED_STATE,
        subject.DerivedStateFamily.ANALYSIS_OPTIONS: subject.DerivedStateFamilyClassification.CAUSAL_DERIVED_STATE,
        subject.DerivedStateFamily.ANALYSIS_RUN_FLAGS: subject.DerivedStateFamilyClassification.ANALYSIS_EXECUTION_CONFIGURATION,
        subject.DerivedStateFamily.LOAD_CASE_PARTICIPATION: subject.DerivedStateFamilyClassification.ANALYSIS_EXECUTION_CONFIGURATION,
        subject.DerivedStateFamily.RESULTS_SETUP_SELECTION: subject.DerivedStateFamilyClassification.EPHEMERAL_ACQUISITION_CONFIGURATION,
        subject.DerivedStateFamily.DATABASE_TABLES_SELECTION: subject.DerivedStateFamilyClassification.EPHEMERAL_ACQUISITION_CONFIGURATION,
        subject.DerivedStateFamily.PRESENT_UNITS: subject.DerivedStateFamilyClassification.REPRESENTATIONAL_CONTEXT,
        subject.DerivedStateFamily.DESIGN_OVERWRITES: subject.DerivedStateFamilyClassification.DESIGN_STATE,
    }
    assert dict(subject.STATE_FAMILY_CLASSIFICATION) == expected


@pytest.mark.parametrize(
    "family",
    (
        subject.DerivedStateFamily.ANALYSIS_RUN_FLAGS,
        subject.DerivedStateFamily.LOAD_CASE_PARTICIPATION,
        subject.DerivedStateFamily.RESULTS_SETUP_SELECTION,
        subject.DerivedStateFamily.DATABASE_TABLES_SELECTION,
        subject.DerivedStateFamily.PRESENT_UNITS,
        subject.DerivedStateFamily.DESIGN_OVERWRITES,
    ),
)
def test_noncausal_state_families_cannot_enter_b4a_causal_manifest(family):
    with pytest.raises(subject.DerivedStateError, match="cannot enter a causal derived-state manifest"):
        subject.request_derived_state(family=family, value={"anything": True})


def test_requested_state_is_not_established_until_factual_readback_comparison():
    requested = _request(_mass({"name": "MS1"}))
    assert not hasattr(requested, "matched")
    empty_readback = _established()
    comparison = subject.compare_derived_state_manifests(requested, empty_readback)
    assert comparison.status is subject.DerivedStateComparisonStatus.INCOMPLETE
    assert comparison.matched is False
    with pytest.raises(subject.DerivedStateComparisonError):
        comparison.require_established_state_ref()


def test_setter_return_shaped_data_cannot_establish_state():
    for shaped in ({"ret": 0}, {"return_code": 0}, {"hresult": 0, "ret": 0}):
        with pytest.raises(subject.DerivedStateError, match="return-code-shaped data cannot establish"):
            _mass_readback(shaped)


def test_ordering_normalization_is_explicit_and_deterministic_where_irrelevant():
    unordered = subject.NormalizationContract(
        sequence_ordering=subject.SequenceOrdering.ORDER_INSENSITIVE
    )
    requested = _request(_mass(["CASE_B", "CASE_A"], normalization=unordered))
    established = _established(_mass_readback(["CASE_A", "CASE_B"], normalization=unordered))
    comparison = subject.compare_derived_state_manifests(requested, established)
    assert comparison.status is subject.DerivedStateComparisonStatus.MATCH
    assert requested.entries[0].canonical_value == ["CASE_A", "CASE_B"]
    assert established.entries[0].canonical_value == ["CASE_A", "CASE_B"]


def test_default_order_sensitive_normalization_does_not_hide_real_mismatch():
    requested = _request(_mass(["CASE_B", "CASE_A"]))
    established = _established(_mass_readback(["CASE_A", "CASE_B"]))
    comparison = subject.compare_derived_state_manifests(requested, established)
    assert comparison.status is subject.DerivedStateComparisonStatus.MISMATCH
    assert comparison.family_results[0].mismatch_reason.startswith("CANONICAL_VALUE_MISMATCH")


def test_numeric_tolerance_is_bounded_explicit_and_does_not_mask_outside_value():
    tolerance = subject.NumericTolerance(absolute=0.001, relative=0.0)
    requested = _request(_mass({"factor": 0.25}, tolerance=tolerance))
    within = _established(_mass_readback({"factor": 0.2508}))
    outside = _established(_mass_readback({"factor": 0.252}))
    assert subject.compare_derived_state_manifests(requested, within).status is subject.DerivedStateComparisonStatus.MATCH
    assert subject.compare_derived_state_manifests(requested, outside).status is subject.DerivedStateComparisonStatus.MISMATCH
    with pytest.raises(subject.DerivedStateError):
        subject.NumericTolerance(absolute=-1e-9)
    with pytest.raises(subject.DerivedStateError):
        subject.NumericTolerance(relative=float("inf"))


@pytest.mark.parametrize(
    ("readback_status", "comparison_status"),
    (
        (subject.DerivedStateEstablishmentStatus.UNAVAILABLE, subject.DerivedStateComparisonStatus.UNAVAILABLE),
        (subject.DerivedStateEstablishmentStatus.UNSUPPORTED, subject.DerivedStateComparisonStatus.UNSUPPORTED),
        (subject.DerivedStateEstablishmentStatus.INCOMPLETE, subject.DerivedStateComparisonStatus.INCOMPLETE),
    ),
)
def test_missing_or_unsupported_readback_never_becomes_match(readback_status, comparison_status):
    requested = _request(_mass({"name": "MS1"}))
    failed = subject.record_derived_state_readback_failure(
        family=subject.DerivedStateFamily.MASS_SOURCE,
        status=readback_status,
        diagnostic=f"{readback_status.value}_READBACK",
    )
    comparison = subject.compare_derived_state_manifests(requested, _established(failed))
    assert comparison.status is comparison_status
    assert comparison.matched is False
    assert comparison.family_results[0].established_canonical_value is None


def test_wrong_state_family_cannot_compare_as_equivalent_even_with_equal_value():
    requested = _mass({"value": 1})
    established = subject.establish_derived_state_from_readback(
        family=subject.DerivedStateFamily.MODAL_CASE_SETUP,
        readback_value={"value": 1},
        readback_evidence_refs=("readback:modal:1",),
    )
    result = subject.compare_derived_state_entries(requested, established)
    assert result.status is subject.DerivedStateComparisonStatus.MISMATCH
    assert result.mismatch_reason == "WRONG_STATE_FAMILY:MODAL_CASE_SETUP"


def test_caller_cannot_construct_or_flag_established_state_directly():
    assert "established" not in inspect.signature(subject.establish_derived_state_from_readback).parameters
    assert "established" not in inspect.signature(subject.RequestedDerivedStateManifest).parameters
    with pytest.raises(TypeError, match="factory-created only"):
        subject.EstablishedDerivedState(
            family=subject.DerivedStateFamily.MASS_SOURCE,
            status=subject.DerivedStateEstablishmentStatus.ESTABLISHED,
            canonical_value_json='{"name":"MS1"}',
            normalization=subject.NormalizationContract(),
            evidence_refs=("caller:asserted",),
            diagnostic=None,
            provenance_refs=(),
        )
    with pytest.raises(TypeError, match="factory-created only"):
        subject.DerivedStateComparison(
            requested_manifest=object(),
            established_manifest=object(),
            status=subject.DerivedStateComparisonStatus.MATCH,
            family_results=(),
            comparison_ref="caller:asserted-match",
            provenance_refs=(),
        )


def test_manifest_identity_is_deterministic_and_provenance_independent():
    first = subject.request_derived_state(
        family=subject.DerivedStateFamily.MASS_SOURCE,
        value={"b": 2, "a": 1},
        provenance_refs=("request-observation:1",),
    )
    second = subject.request_derived_state(
        family=subject.DerivedStateFamily.MODAL_CASE_SETUP,
        value={"modes": 20},
    )
    one = _request(first, second, provenance_refs=("manifest-provenance:1",))
    two = _request(
        subject.request_derived_state(
            family=subject.DerivedStateFamily.MODAL_CASE_SETUP,
            value={"modes": 20},
            provenance_refs=("different:entry",),
        ),
        subject.request_derived_state(
            family=subject.DerivedStateFamily.MASS_SOURCE,
            value={"a": 1, "b": 2},
        ),
        provenance_refs=("manifest-provenance:2",),
    )
    assert one.manifest_ref == two.manifest_ref

    r1 = _established(
        _mass_readback({"a": 1, "b": 2}, evidence=("readback:one",)),
        provenance_refs=("capture:1",),
    )
    r2 = _established(
        _mass_readback({"b": 2, "a": 1}, evidence=("readback:two",)),
        provenance_refs=("capture:2",),
    )
    assert r1.manifest_ref == r2.manifest_ref


def test_source_model_mismatch_fails_closed():
    requested = _request(_mass({"name": "MS1"}))
    established = _established(
        _mass_readback({"name": "MS1"}),
        source_model_ref="etabs-source-model-ref:sha256:" + "2" * 64,
    )
    comparison = subject.compare_derived_state_manifests(requested, established)
    assert comparison.status is subject.DerivedStateComparisonStatus.MISMATCH
    assert comparison.family_results[0].mismatch_reason == "SOURCE_MODEL_REF_MISMATCH"


def test_match_binds_existing_b1_analysis_state_seam_without_result_qualification():
    requested = _request(_mass({"name": "MS1"}))
    established = _established(_mass_readback({"name": "MS1"}))
    comparison = subject.compare_derived_state_manifests(requested, established)
    assert comparison.status is subject.DerivedStateComparisonStatus.MATCH
    state = subject.build_analysis_state_identity_from_derived_state(
        comparison=comparison,
        state_basis_refs=("analysis-state-basis:source-model-and-derived-state",),
        provenance_refs=("b4a-comparison:evidence",),
    )
    assert isinstance(state, AnalysisStateIdentity)
    assert state.execution_state_ref == established.manifest_ref
    assert state.source_model_ref == SOURCE
    assert comparison is not state
    assert not hasattr(comparison, "analysis_result")
    assert not hasattr(comparison, "qualified")


def test_state_match_is_not_analysis_result_qualification_and_module_has_no_mutation_capability():
    public = set(subject.__all__)
    assert "AnalysisResultIdentity" not in public
    assert "AnalysisLineageQualification" not in public
    source = (ROOT / "tbdy_engine/integration/etabs_derived_state.py").read_text(encoding="utf-8")
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        "SetRunCaseFlag(",
        "DeleteResults(",
        ".Save(",
        "OpenFile(",
        "SapModel",
        "comtypes",
        "win32com",
        "pythoncom",
    ):
        assert forbidden not in source


def test_manifest_types_are_not_b1_analysis_state_identity():
    assert subject.RequestedDerivedStateManifest is not AnalysisStateIdentity
    assert subject.EstablishedDerivedStateManifest is not AnalysisStateIdentity
    assert {field.name for field in fields(subject.EstablishedDerivedStateManifest)}.isdisjoint(
        {"identity_ref", "analysis_generation_ref", "analysis_result"}
    )
