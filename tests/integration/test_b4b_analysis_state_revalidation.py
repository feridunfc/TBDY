from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.integration.etabs_analysis_state_revalidation as subject
from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierReadFact,
    FrameModifierSurface,
    FrameModifierVector,
)
from tbdy_engine.integration.etabs_analysis_state_mutation import (
    FRAME_MODIFIER_PLAN_CONTRACT,
    FrameModifierTargetRequest,
    build_requested_frame_modifier_manifest,
)
from tbdy_engine.integration.etabs_derived_state import (
    EstablishedDerivedStateManifest,
    _POSITIVE_ESTABLISHMENT_ISSUER_TOKEN,
    _establish_derived_state_from_verified_readback,
    build_analysis_state_identity_from_derived_state,
    compare_derived_state_manifests,
)


class _FakeContext:
    def __init__(self) -> None:
        self.source_model_identity = SimpleNamespace(
            source_model_ref="source-model-ref:test",
            normalized_model_reference=r"C:\tmp\source.edb",
        )
        self.verified_session = object()
        self.acquisition_context_ref = "acquisition-context:test"
        self.session_provenance_ref = "session-provenance:test"


class _FakeOwnedScratch:
    def __init__(self, source_identity) -> None:
        self.source_model_identity = source_identity
        self.scratch_path = r"C:\tmp\source.tbdy-b4s-test.edb"
        self.ownership_proof_ref = "owned-scratch:test"
        snapshot = SimpleNamespace(
            canonical_absolute_path=r"C:\tmp\source.edb",
            exists=True,
            file_size_bytes=1234,
            sha256_content_digest="a" * 64,
            mtime_ns=1,
        )
        self.source_pre = snapshot
        self.source_post = snapshot


class _FakeMutationResult:
    pass


def _vector(i22=0.35, i33=0.40):
    return FrameModifierVector.from_sequence(
        [1.0, 1.0, 1.0, 1.0, i22, i33, 1.0, 1.0]
    )


@pytest.fixture
def harness(monkeypatch):
    context = _FakeContext()
    owned = _FakeOwnedScratch(context.source_model_identity)
    target = FrameModifierTargetRequest(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="F1",
        modifiers=_vector(),
    )
    requested = build_requested_frame_modifier_manifest(
        source_model_ref=context.source_model_identity.source_model_ref,
        targets=(target,),
    )
    requested_entry = requested.entries[0]
    established_entry = _establish_derived_state_from_verified_readback(
        _issuer_token=_POSITIVE_ESTABLISHMENT_ISSUER_TOKEN,
        family=requested_entry.family,
        readback_value={
            "contract": FRAME_MODIFIER_PLAN_CONTRACT,
            "targets": [
                {
                    "surface": target.surface.value,
                    "target_name": target.target_name,
                    "modifiers": target.modifiers.as_list(),
                }
            ],
        },
        readback_evidence_refs=("initial-readback:test",),
        normalization=requested_entry.normalization,
    )
    established_manifest = EstablishedDerivedStateManifest(
        source_model_ref=context.source_model_identity.source_model_ref,
        entries=(established_entry,),
    )
    comparison = compare_derived_state_manifests(requested, established_manifest)
    mutation_manifest = SimpleNamespace(
        ownership_proof_ref=owned.ownership_proof_ref,
        manifest_ref="mutation-manifest:test",
    )
    analysis_state = build_analysis_state_identity_from_derived_state(
        comparison=comparison,
        state_basis_refs=(
            owned.ownership_proof_ref,
            requested.manifest_ref,
            mutation_manifest.manifest_ref,
        ),
    )
    result = _FakeMutationResult()
    result.requested_manifest = requested
    result.established_manifest = established_manifest
    result.comparison = comparison
    result.mutation_manifest = mutation_manifest
    result.analysis_state_identity = analysis_state

    monkeypatch.setattr(subject, "TrustedLiveAcquisitionContext", _FakeContext)
    monkeypatch.setattr(subject, "OwnedScratchContext", _FakeOwnedScratch)
    monkeypatch.setattr(subject, "AnalysisStateMutationResult", _FakeMutationResult)

    state = {
        "path": owned.scratch_path,
        "digest": "a" * 64,
        "vector": _vector(),
        "get_return": 0,
    }

    monkeypatch.setattr(
        subject,
        "reread_verified_session_identity",
        lambda _session, *, timeout_seconds=30.0: SimpleNamespace(
            model_full_path=state["path"]
        ),
    )
    monkeypatch.setattr(
        subject,
        "capture_physical_file_snapshot",
        lambda _path: SimpleNamespace(
            canonical_absolute_path=r"C:\tmp\source.edb",
            exists=True,
            file_size_bytes=1234,
            sha256_content_digest=state["digest"],
            mtime_ns=1,
        ),
    )

    def get_fact(
        _session,
        *,
        surface,
        target_name,
        timeout_seconds=30.0,
    ):
        return FrameModifierReadFact(
            surface=surface,
            target_name=target_name,
            modifiers=state["vector"],
            return_code=state["get_return"],
        )

    monkeypatch.setattr(subject, "get_frame_modifiers_from_session", get_fact)

    return SimpleNamespace(
        context=context,
        owned=owned,
        result=result,
        state=state,
    )


def test_exact_current_readback_reproduces_original_analysis_state_identity(harness):
    fact = subject.revalidate_frame_modifier_analysis_state(
        context=harness.context,
        owned_scratch=harness.owned,
        established_state=harness.result,
    )

    assert fact.matched_exact is True
    assert fact.current_analysis_state.identity_ref == harness.result.analysis_state_identity.identity_ref
    assert fact.comparison.matched is True
    assert fact.comparison.exact_causal_family_population is True
    assert len(fact.readback_evidence_refs) == 1


def test_modifier_state_drift_fails_closed(harness):
    harness.state["vector"] = _vector(i22=0.50, i33=0.40)

    with pytest.raises(subject.AnalysisStateRevalidationError) as exc:
        subject.revalidate_frame_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.result,
        )

    assert exc.value.stage == "comparison_mismatch"


def test_active_model_must_remain_exact_owned_scratch(harness):
    harness.state["path"] = r"C:\tmp\other.edb"

    with pytest.raises(subject.AnalysisStateRevalidationError) as exc:
        subject.revalidate_frame_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.result,
        )

    assert exc.value.stage == "active_scratch_binding"


def test_protected_source_byte_drift_fails_before_causal_readback(harness):
    harness.state["digest"] = "b" * 64

    with pytest.raises(subject.AnalysisStateRevalidationError) as exc:
        subject.revalidate_frame_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.result,
        )

    assert exc.value.stage == "source_integrity"


def test_nonzero_factual_readback_cannot_revalidate_state(harness):
    harness.state["get_return"] = 5

    with pytest.raises(subject.AnalysisStateRevalidationError) as exc:
        subject.revalidate_frame_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.result,
        )

    assert exc.value.stage == "readback_nonzero"


def test_wrong_source_binding_is_rejected(harness):
    harness.result.analysis_state_identity = build_analysis_state_identity_from_derived_state(
        comparison=harness.result.comparison,
        state_basis_refs=("different-basis:test",),
    )
    # Identity still names the same source; make the trusted source itself differ.
    harness.context.source_model_identity = SimpleNamespace(
        source_model_ref="source-model-ref:other",
        normalized_model_reference=r"C:\tmp\source.edb",
    )

    with pytest.raises(subject.AnalysisStateRevalidationError) as exc:
        subject.revalidate_frame_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.result,
        )

    assert exc.value.stage == "source_binding"
