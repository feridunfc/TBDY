from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import tbdy_engine.integration.etabs_analysis_state_mutation as subject
from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierReadFact,
    FrameModifierSetFact,
    FrameModifierSurface,
    FrameModifierVector,
)
from tbdy_engine.integration.etabs_derived_state import (
    DerivedStateFamily,
    RequestedDerivedStateManifest,
    request_derived_state,
)


@dataclass(frozen=True)
class _SourceIdentity:
    source_model_ref: str = "source-model-ref:test"
    normalized_model_reference: str = r"C:\tmp\source.edb"


class _FakeContext:
    def __init__(self) -> None:
        self.source_model_identity = _SourceIdentity()
        self.verified_session = object()
        self.acquisition_context_ref = "acquisition-context:test"
        self.session_provenance_ref = "session-provenance:test"


class _FakeOwnedScratch:
    def __init__(self, source_identity: _SourceIdentity) -> None:
        self.source_model_identity = source_identity
        self.scratch_path = r"C:\tmp\source.tbdy-b4s-test.edb"
        self.active_model_path = self.scratch_path
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


@pytest.fixture
def harness(monkeypatch):
    context = _FakeContext()
    owned = _FakeOwnedScratch(context.source_model_identity)
    monkeypatch.setattr(subject, "TrustedLiveAcquisitionContext", _FakeContext)
    monkeypatch.setattr(subject, "OwnedScratchContext", _FakeOwnedScratch)

    identity_state = {"path": owned.scratch_path, "locked": False}

    def reread(_session):
        return SimpleNamespace(
            model_full_path=identity_state["path"],
            model_locked=identity_state["locked"],
        )

    monkeypatch.setattr(subject, "reread_verified_session_identity", reread)

    source_snapshot = SimpleNamespace(
        canonical_absolute_path=r"C:\tmp\source.edb",
        exists=True,
        file_size_bytes=1234,
        sha256_content_digest="a" * 64,
        mtime_ns=1,
    )
    monkeypatch.setattr(subject, "PhysicalFileSnapshot", SimpleNamespace)
    monkeypatch.setattr(subject, "capture_physical_file_snapshot", lambda _path: source_snapshot)

    values = {}
    calls = []

    def key(surface, name):
        return (surface.value, name)

    def default_vector():
        return FrameModifierVector.from_sequence([1.0] * 8)

    def get_fact(_session, *, surface, target_name, timeout_seconds=30.0):
        vector = values.get(key(surface, target_name), default_vector())
        calls.append(("GET", surface.value, target_name, vector.as_tuple()))
        return FrameModifierReadFact(
            surface=surface,
            target_name=target_name,
            modifiers=vector,
            return_code=0,
        )

    setter_behavior = {"nonzero_target": None, "ignore_target": None}

    def set_fact(_session, *, surface, target_name, modifiers, timeout_seconds=30.0):
        calls.append(("SET", surface.value, target_name, modifiers.as_tuple()))
        if setter_behavior["nonzero_target"] == key(surface, target_name):
            return FrameModifierSetFact(
                surface=surface,
                target_name=target_name,
                requested_modifiers=modifiers,
                return_code=9,
            )
        if setter_behavior["ignore_target"] != key(surface, target_name):
            values[key(surface, target_name)] = modifiers
        return FrameModifierSetFact(
            surface=surface,
            target_name=target_name,
            requested_modifiers=modifiers,
            return_code=0,
        )

    monkeypatch.setattr(subject, "get_frame_modifiers_from_session", get_fact)
    monkeypatch.setattr(subject, "set_frame_modifiers_from_session", set_fact)

    return SimpleNamespace(
        context=context,
        owned=owned,
        identity_state=identity_state,
        values=values,
        calls=calls,
        setter_behavior=setter_behavior,
        source_snapshot=source_snapshot,
    )


def _vector(i22, i33):
    return FrameModifierVector.from_sequence([1.0, 1.0, 1.0, 1.0, i22, i33, 1.0, 1.0])


def _manifest(harness, targets):
    return subject.build_requested_frame_modifier_manifest(
        source_model_ref=harness.context.source_model_identity.source_model_ref,
        targets=targets,
        provenance_refs=("reviewed-state-plan:test",),
    )


def test_request_manifest_is_exact_section_stiffness_family(harness):
    manifest = _manifest(
        harness,
        (
            subject.FrameModifierTargetRequest(
                surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
                target_name="C40x40",
                modifiers=_vector(0.25, 0.30),
            ),
        ),
    )
    assert manifest.family_set == frozenset({DerivedStateFamily.SECTION_STIFFNESS_MODIFIERS})
    assert manifest.entries[0].canonical_value["contract"] == subject.FRAME_MODIFIER_PLAN_CONTRACT


def test_successful_b4b_mutation_issues_analysis_state_identity(harness):
    targets = (
        subject.FrameModifierTargetRequest(
            surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
            target_name="C40x40",
            modifiers=_vector(0.25, 0.30),
        ),
        subject.FrameModifierTargetRequest(
            surface=FrameModifierSurface.FRAME_OBJECT,
            target_name="F1",
            modifiers=_vector(0.35, 0.40),
        ),
    )
    manifest = _manifest(harness, targets)
    result = subject.establish_frame_modifier_analysis_state(
        context=harness.context,
        owned_scratch=harness.owned,
        requested_manifest=manifest,
    )
    assert result.comparison.matched is True
    assert result.analysis_state_identity.source_model_ref == harness.context.source_model_identity.source_model_ref
    assert result.analysis_state_identity.execution_state_ref == result.established_manifest.manifest_ref
    assert result.mutation_manifest.ownership_proof_ref == harness.owned.ownership_proof_ref
    assert result.mutation_manifest.logically_invalidates_prior_analysis_results is True
    assert result.mutation_manifest.logically_invalidates_prior_design_results is True
    assert len(result.mutation_manifest.mutations) == 2


def test_wrong_source_request_rejected_before_any_etabs_call(harness):
    manifest = subject.build_requested_frame_modifier_manifest(
        source_model_ref="source-model-ref:wrong",
        targets=(
            subject.FrameModifierTargetRequest(
                surface=FrameModifierSurface.FRAME_OBJECT,
                target_name="F1",
                modifiers=_vector(0.25, 0.30),
            ),
        ),
    )
    with pytest.raises(subject.AnalysisStateMutationError) as exc:
        subject.establish_frame_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            requested_manifest=manifest,
        )
    assert exc.value.stage == "source_binding"
    assert harness.calls == []


def test_active_model_must_be_exact_owned_scratch(harness):
    harness.identity_state["path"] = r"C:\tmp\some-other.edb"
    manifest = _manifest(
        harness,
        (
            subject.FrameModifierTargetRequest(
                surface=FrameModifierSurface.FRAME_OBJECT,
                target_name="F1",
                modifiers=_vector(0.25, 0.30),
            ),
        ),
    )
    with pytest.raises(subject.AnalysisStateMutationError) as exc:
        subject.establish_frame_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            requested_manifest=manifest,
        )
    assert exc.value.stage == "active_scratch_binding"
    assert harness.calls == []


def test_nonzero_second_setter_restores_first_and_second_targets(harness):
    first = subject.FrameModifierTargetRequest(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="F1",
        modifiers=_vector(0.25, 0.30),
    )
    second = subject.FrameModifierTargetRequest(
        surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
        target_name="C40x40",
        modifiers=_vector(0.35, 0.40),
    )
    manifest = _manifest(harness, (first, second))
    harness.setter_behavior["nonzero_target"] = second.key
    with pytest.raises(subject.AnalysisStateMutationError) as exc:
        subject.establish_frame_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            requested_manifest=manifest,
        )
    assert exc.value.stage == "setter_nonzero"
    assert exc.value.restoration_status == subject.MutationRestorationStatus.RESTORED.value
    assert harness.values[first.key].as_tuple() == _vector(1.0, 1.0).as_tuple()
    assert harness.values.get(second.key, _vector(1.0, 1.0)).as_tuple() == _vector(1.0, 1.0).as_tuple()


def test_readback_mismatch_restores_and_never_issues_analysis_state(harness):
    target = subject.FrameModifierTargetRequest(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="F1",
        modifiers=_vector(0.25, 0.30),
    )
    manifest = _manifest(harness, (target,))
    harness.setter_behavior["ignore_target"] = target.key
    with pytest.raises(subject.AnalysisStateMutationError) as exc:
        subject.establish_frame_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            requested_manifest=manifest,
        )
    assert exc.value.stage == "requested_vs_readback_mismatch"
    assert exc.value.restoration_status == subject.MutationRestorationStatus.RESTORED.value


def test_source_byte_change_fails_closed_and_restores(harness, monkeypatch):
    target = subject.FrameModifierTargetRequest(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="F1",
        modifiers=_vector(0.25, 0.30),
    )
    manifest = _manifest(harness, (target,))
    calls = {"n": 0}

    def changing_snapshot(_path):
        calls["n"] += 1
        digest = "a" * 64 if calls["n"] == 1 else "b" * 64
        return SimpleNamespace(
            canonical_absolute_path=r"C:\tmp\source.edb",
            exists=True,
            file_size_bytes=1234,
            sha256_content_digest=digest,
            mtime_ns=calls["n"],
        )

    monkeypatch.setattr(subject, "capture_physical_file_snapshot", changing_snapshot)
    with pytest.raises(subject.AnalysisStateMutationError) as exc:
        subject.establish_frame_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            requested_manifest=manifest,
        )
    assert exc.value.stage == "source_post_mutation_integrity"
    assert exc.value.restoration_status == subject.MutationRestorationStatus.RESTORED.value


def test_only_section_stiffness_modifier_family_is_accepted(harness):
    other = request_derived_state(family=DerivedStateFamily.MASS_SOURCE, value={"name": "MS1"})
    manifest = RequestedDerivedStateManifest(
        source_model_ref=harness.context.source_model_identity.source_model_ref,
        entries=(other,),
    )
    with pytest.raises(subject.AnalysisStateMutationError, match="only SECTION_STIFFNESS_MODIFIERS"):
        subject.establish_frame_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            requested_manifest=manifest,
        )


def test_duplicate_targets_are_rejected_deterministically(harness):
    target = subject.FrameModifierTargetRequest(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="F1",
        modifiers=_vector(0.25, 0.30),
    )
    with pytest.raises(subject.AnalysisStateMutationError, match="duplicate"):
        _manifest(harness, (target, target))


def test_lock_state_is_observed_not_mutated(harness):
    harness.identity_state["locked"] = True
    manifest = _manifest(
        harness,
        (
            subject.FrameModifierTargetRequest(
                surface=FrameModifierSurface.FRAME_OBJECT,
                target_name="F1",
                modifiers=_vector(0.25, 0.30),
            ),
        ),
    )
    result = subject.establish_frame_modifier_analysis_state(
        context=harness.context,
        owned_scratch=harness.owned,
        requested_manifest=manifest,
    )
    assert result.mutation_manifest.model_locked_before is True
    assert result.mutation_manifest.model_locked_after is True
