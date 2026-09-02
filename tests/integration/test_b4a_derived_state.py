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
        source_model_ref=SOURCE, entries=tuple(states), provenance_refs=provenance_refs
    )


def _established(*states, source_model_ref=SOURCE, provenance_refs=()):
    return subject.EstablishedDerivedStateManifest(
        source_model_ref=source_model_ref, entries=tuple(states), provenance_refs=provenance_refs
    )


def _private_readback(family, value, *, normalization=subject.NormalizationContract(), evidence=("readback:verified:1",)):
    return subject._establish_derived_state_from_verified_readback(
        _issuer_token=subject._POSITIVE_ESTABLISHMENT_ISSUER_TOKEN,
        family=family,
        readback_value=value,
        readback_evidence_refs=evidence,
        normalization=normalization,
    )


def _mass(value, *, normalization=subject.NormalizationContract(), tolerance=subject.NumericTolerance()):
    return subject.request_derived_state(
        family=subject.DerivedStateFamily.MASS_SOURCE,
        value=value,
        normalization=normalization,
        tolerance=tolerance,
    )


def _mass_readback(value, *, normalization=subject.NormalizationContract(), evidence=("readback:mass-source:1",)):
    return _private_readback(
        subject.DerivedStateFamily.MASS_SOURCE,
        value,
        normalization=normalization,
        evidence=evidence,
    )


def _modal(value, *, normalization=subject.NormalizationContract()):
    return subject.request_derived_state(
        family=subject.DerivedStateFamily.MODAL_CASE_SETUP,
        value=value,
        normalization=normalization,
    )


def _modal_readback(value, *, normalization=subject.NormalizationContract()):
    return _private_readback(
        subject.DerivedStateFamily.MODAL_CASE_SETUP,
        value,
        normalization=normalization,
        evidence=("readback:modal-case:1",),
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


@pytest.mark.parametrize("family", (
    subject.DerivedStateFamily.ANALYSIS_RUN_FLAGS,
    subject.DerivedStateFamily.LOAD_CASE_PARTICIPATION,
    subject.DerivedStateFamily.RESULTS_SETUP_SELECTION,
    subject.DerivedStateFamily.DATABASE_TABLES_SELECTION,
    subject.DerivedStateFamily.PRESENT_UNITS,
    subject.DerivedStateFamily.DESIGN_OVERWRITES,
))
def test_noncausal_state_families_cannot_enter_b4a_causal_manifest(family):
    with pytest.raises(subject.DerivedStateError, match="cannot enter a causal derived-state manifest"):
        subject.request_derived_state(family=family, value={"anything": True})


def test_public_api_has_no_positive_established_state_issuer():
    public = set(subject.__all__)
    assert "establish_derived_state_from_readback" not in public
    assert "_establish_derived_state_from_verified_readback" not in public
    assert not hasattr(subject, "establish_derived_state_from_readback")
    public_callables = {name for name in public if callable(getattr(subject, name, None))}
    assert not any(name.startswith("establish") for name in public_callables)


def test_arbitrary_caller_values_and_evidence_strings_cannot_mint_positive_establishment():
    with pytest.raises(TypeError, match="factory-created only"):
        subject.EstablishedDerivedState(
            family=subject.DerivedStateFamily.MASS_SOURCE,
            status=subject.DerivedStateEstablishmentStatus.ESTABLISHED,
            canonical_value_json='{"name":"MS1"}',
            normalization=subject.NormalizationContract(),
            evidence_refs=("caller:any-string",),
            diagnostic=None,
            provenance_refs=(),
        )
    with pytest.raises(TypeError, match="issuer-created only"):
        subject._establish_derived_state_from_verified_readback(
            family=subject.DerivedStateFamily.MASS_SOURCE,
            readback_value={"name": "MS1"},
            readback_evidence_refs=("caller:any-string",),
        )


def test_setter_return_shaped_data_cannot_establish_even_through_private_test_seam():
    for shaped in ({"ret": 0}, {"return_code": 0}, {"hresult": 0, "ret": 0}):
        with pytest.raises(subject.DerivedStateError, match="return-code-shaped data cannot establish"):
            _mass_readback(shaped)


def test_requested_state_is_not_established_until_private_readback_comparison():
    requested = _request(_mass({"name": "MS1"}))
    comparison = subject.compare_derived_state_manifests(requested, _established())
    assert comparison.status is subject.DerivedStateComparisonStatus.INCOMPLETE
    assert not comparison.matched
    with pytest.raises(subject.DerivedStateComparisonError):
        comparison.require_established_state_ref()


def test_extra_established_causal_family_fails_closed():
    requested = _request(_mass({"name": "MS1"}))
    established = _established(_mass_readback({"name": "MS1"}), _modal_readback({"modes": 20}))
    comparison = subject.compare_derived_state_manifests(requested, established)
    assert comparison.status is subject.DerivedStateComparisonStatus.MISMATCH
    assert comparison.exact_causal_family_population is False
    extra = [item for item in comparison.family_results if item.family is subject.DerivedStateFamily.MODAL_CASE_SETUP]
    assert len(extra) == 1
    assert extra[0].mismatch_reason == "UNREQUESTED_CAUSAL_FAMILY"


def test_missing_established_causal_family_remains_incomplete():
    requested = _request(_mass({"name": "MS1"}), _modal({"modes": 20}))
    established = _established(_mass_readback({"name": "MS1"}))
    comparison = subject.compare_derived_state_manifests(requested, established)
    assert comparison.status is subject.DerivedStateComparisonStatus.INCOMPLETE
    assert comparison.exact_causal_family_population is False
    missing = [item for item in comparison.family_results if item.family is subject.DerivedStateFamily.MODAL_CASE_SETUP]
    assert missing[0].mismatch_reason == "REQUESTED_FAMILY_READBACK_MISSING"


def test_exact_equal_family_population_and_state_can_match_through_private_test_seam():
    requested = _request(_mass({"name": "MS1"}), _modal({"modes": 20}))
    established = _established(_mass_readback({"name": "MS1"}), _modal_readback({"modes": 20}))
    comparison = subject.compare_derived_state_manifests(requested, established)
    assert comparison.status is subject.DerivedStateComparisonStatus.MATCH
    assert comparison.exact_causal_family_population is True
    assert comparison.require_established_state_ref() == established.manifest_ref


def test_only_exact_match_can_feed_b1_bridge():
    extra = subject.compare_derived_state_manifests(
        _request(_mass({"name": "MS1"})),
        _established(_mass_readback({"name": "MS1"}), _modal_readback({"modes": 20})),
    )
    with pytest.raises(subject.DerivedStateComparisonError):
        subject.build_analysis_state_identity_from_derived_state(
            comparison=extra, state_basis_refs=("analysis-state-basis:1",)
        )
    exact_established = _established(_mass_readback({"name": "MS1"}))
    exact = subject.compare_derived_state_manifests(
        _request(_mass({"name": "MS1"})), exact_established
    )
    state = subject.build_analysis_state_identity_from_derived_state(
        comparison=exact,
        state_basis_refs=("analysis-state-basis:1",),
        provenance_refs=("b4a:comparison",),
    )
    assert isinstance(state, AnalysisStateIdentity)
    assert state.execution_state_ref == exact_established.manifest_ref
    assert state.source_model_ref == SOURCE


def test_ordering_normalization_is_explicit_and_deterministic_where_irrelevant():
    unordered = subject.NormalizationContract(sequence_ordering=subject.SequenceOrdering.ORDER_INSENSITIVE)
    requested = _request(_mass(["CASE_B", "CASE_A"], normalization=unordered))
    established = _established(_mass_readback(["CASE_A", "CASE_B"], normalization=unordered))
    comparison = subject.compare_derived_state_manifests(requested, established)
    assert comparison.status is subject.DerivedStateComparisonStatus.MATCH
    assert requested.entries[0].canonical_value == ["CASE_A", "CASE_B"]


def test_default_order_sensitive_normalization_does_not_hide_real_mismatch():
    comparison = subject.compare_derived_state_manifests(
        _request(_mass(["CASE_B", "CASE_A"])),
        _established(_mass_readback(["CASE_A", "CASE_B"])),
    )
    assert comparison.status is subject.DerivedStateComparisonStatus.MISMATCH
    assert comparison.family_results[0].mismatch_reason.startswith("CANONICAL_VALUE_MISMATCH")


def test_numeric_tolerance_is_bounded_explicit_and_does_not_mask_outside_value():
    tolerance = subject.NumericTolerance(absolute=0.001, relative=0.0)
    requested = _request(_mass({"factor": 0.25}, tolerance=tolerance))
    assert subject.compare_derived_state_manifests(
        requested, _established(_mass_readback({"factor": 0.2508}))
    ).status is subject.DerivedStateComparisonStatus.MATCH
    assert subject.compare_derived_state_manifests(
        requested, _established(_mass_readback({"factor": 0.252}))
    ).status is subject.DerivedStateComparisonStatus.MISMATCH
    with pytest.raises(subject.DerivedStateError):
        subject.NumericTolerance(absolute=-1e-9)


@pytest.mark.parametrize(("readback_status", "comparison_status"), (
    (subject.DerivedStateEstablishmentStatus.UNAVAILABLE, subject.DerivedStateComparisonStatus.UNAVAILABLE),
    (subject.DerivedStateEstablishmentStatus.UNSUPPORTED, subject.DerivedStateComparisonStatus.UNSUPPORTED),
    (subject.DerivedStateEstablishmentStatus.INCOMPLETE, subject.DerivedStateComparisonStatus.INCOMPLETE),
))
def test_missing_or_unsupported_readback_never_becomes_match(readback_status, comparison_status):
    failed = subject.record_derived_state_readback_failure(
        family=subject.DerivedStateFamily.MASS_SOURCE,
        status=readback_status,
        diagnostic=f"{readback_status.value}_READBACK",
    )
    comparison = subject.compare_derived_state_manifests(
        _request(_mass({"name": "MS1"})), _established(failed)
    )
    assert comparison.status is comparison_status
    assert not comparison.matched


def test_public_failure_factory_rejects_positive_status():
    with pytest.raises(subject.DerivedStateError, match="private to the future B4B"):
        subject.record_derived_state_readback_failure(
            family=subject.DerivedStateFamily.MASS_SOURCE,
            status=subject.DerivedStateEstablishmentStatus.ESTABLISHED,
            diagnostic="caller:tries-positive",
        )


def test_wrong_state_family_cannot_compare_as_equivalent_even_with_equal_value():
    result = subject.compare_derived_state_entries(
        _mass({"value": 1}),
        _modal_readback({"value": 1}),
    )
    assert result.status is subject.DerivedStateComparisonStatus.MISMATCH
    assert result.mismatch_reason == "WRONG_STATE_FAMILY:MODAL_CASE_SETUP"


def test_duplicate_requested_family_is_rejected():
    with pytest.raises(subject.DerivedStateError, match="duplicate requested state family"):
        _request(_mass({"name": "A"}), _mass({"name": "B"}))


def test_duplicate_established_family_is_rejected():
    with pytest.raises(subject.DerivedStateError, match="duplicate established/readback state family"):
        _established(_mass_readback({"name": "A"}), _mass_readback({"name": "B"}))


def test_normalization_contract_mismatch_fails_closed():
    unordered = subject.NormalizationContract(sequence_ordering=subject.SequenceOrdering.ORDER_INSENSITIVE)
    comparison = subject.compare_derived_state_manifests(
        _request(_mass(["A", "B"])),
        _established(_mass_readback(["A", "B"], normalization=unordered)),
    )
    assert comparison.status is subject.DerivedStateComparisonStatus.MISMATCH
    assert comparison.family_results[0].mismatch_reason == "NORMALIZATION_CONTRACT_MISMATCH"


def test_source_model_mismatch_fails_closed():
    comparison = subject.compare_derived_state_manifests(
        _request(_mass({"name": "MS1"})),
        _established(
            _mass_readback({"name": "MS1"}),
            source_model_ref="etabs-source-model-ref:sha256:" + "2" * 64,
        ),
    )
    assert comparison.status is subject.DerivedStateComparisonStatus.MISMATCH
    assert comparison.family_results[0].mismatch_reason == "SOURCE_MODEL_REF_MISMATCH"


def test_manifest_identity_is_deterministic_and_provenance_independent():
    one = _request(
        subject.request_derived_state(
            family=subject.DerivedStateFamily.MASS_SOURCE,
            value={"b": 2, "a": 1},
            provenance_refs=("request-observation:1",),
        ),
        _modal({"modes": 20}),
        provenance_refs=("manifest-provenance:1",),
    )
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
    r1 = _established(_mass_readback({"a": 1, "b": 2}, evidence=("readback:one",)))
    r2 = _established(_mass_readback({"b": 2, "a": 1}, evidence=("readback:two",)))
    assert r1.manifest_ref == r2.manifest_ref


def test_state_match_is_not_analysis_result_qualification_and_module_has_no_mutation_capability():
    public = set(subject.__all__)
    assert "AnalysisResultIdentity" not in public
    assert "AnalysisLineageQualification" not in public
    source = (ROOT / "tbdy_engine/integration/etabs_derived_state.py").read_text(encoding="utf-8")
    for forbidden in (
        "RunAnalysis(", "StartDesign(", "SetPresentUnits(", "SetRunCaseFlag(",
        "DeleteResults(", ".Save(", "OpenFile(", "SapModel", "comtypes", "win32com", "pythoncom",
    ):
        assert forbidden not in source


def test_manifest_types_are_not_b1_analysis_state_identity():
    assert subject.RequestedDerivedStateManifest is not AnalysisStateIdentity
    assert subject.EstablishedDerivedStateManifest is not AnalysisStateIdentity
    assert {field.name for field in fields(subject.EstablishedDerivedStateManifest)}.isdisjoint(
        {"identity_ref", "analysis_generation_ref", "analysis_result"}
    )


def test_private_positive_issuer_is_not_public_by_signature_or_export():
    assert "_issuer_token" in inspect.signature(subject._establish_derived_state_from_verified_readback).parameters
    assert "_POSITIVE_ESTABLISHMENT_ISSUER_TOKEN" not in subject.__all__
    assert "_establish_derived_state_from_verified_readback" not in subject.__all__
