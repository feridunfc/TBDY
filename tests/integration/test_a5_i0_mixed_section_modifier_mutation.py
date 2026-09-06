from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import tbdy_engine.integration.etabs_analysis_state_mutation as subject
from tbdy_engine.etabs.oapi.area_modifiers import (
    AreaModifierReadFact,
    AreaModifierSetFact,
    AreaModifierSurface,
    AreaModifierVector,
)
from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierReadFact,
    FrameModifierSetFact,
    FrameModifierSurface,
    FrameModifierVector,
)
from tbdy_engine.integration.etabs_derived_state import DerivedStateFamily


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


def _frame_vector(value=1.0):
    return FrameModifierVector.from_sequence([value] * 8)


def _area_vector(value=1.0):
    return AreaModifierVector.from_sequence([value] * 10)


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

    source_state = {"digest": "a" * 64}

    def snapshot(_path):
        return SimpleNamespace(
            canonical_absolute_path=r"C:\tmp\source.edb",
            exists=True,
            file_size_bytes=1234,
            sha256_content_digest=source_state["digest"],
            mtime_ns=1,
        )

    monkeypatch.setattr(subject, "PhysicalFileSnapshot", SimpleNamespace)
    monkeypatch.setattr(subject, "capture_physical_file_snapshot", snapshot)

    values = {}
    calls = []
    behavior = {
        "nonzero_target": None,
        "nonzero_emitted": False,
        "ignore_target": None,
        "raise_target": None,
        "raise_emitted": False,
        "switch_active_after_target": None,
    }

    def key(surface, target_name):
        return (surface.value, target_name)

    def frame_get(_session, *, surface, target_name, timeout_seconds=30.0):
        vector = values.get(key(surface, target_name), _frame_vector())
        calls.append(("GET", surface.value, target_name, vector.as_tuple()))
        return FrameModifierReadFact(
            surface=surface,
            target_name=target_name,
            modifiers=vector,
            return_code=0,
        )

    def area_get(_session, *, surface, target_name, timeout_seconds=30.0):
        vector = values.get(key(surface, target_name), _area_vector())
        calls.append(("GET", surface.value, target_name, vector.as_tuple()))
        return AreaModifierReadFact(
            surface=surface,
            target_name=target_name,
            modifiers=vector,
            return_code=0,
        )

    def apply_behavior(surface, target_name, modifiers, fact_type):
        target_key = key(surface, target_name)
        calls.append(("SET", surface.value, target_name, modifiers.as_tuple()))
        if (
            behavior["nonzero_target"] == target_key
            and not behavior["nonzero_emitted"]
        ):
            behavior["nonzero_emitted"] = True
            return fact_type(
                surface=surface,
                target_name=target_name,
                requested_modifiers=modifiers,
                return_code=9,
            )
        if behavior["ignore_target"] != target_key:
            values[target_key] = modifiers
        if (
            behavior["raise_target"] == target_key
            and not behavior["raise_emitted"]
        ):
            behavior["raise_emitted"] = True
            raise RuntimeError("simulated setter failure after possible side effect")
        if behavior["switch_active_after_target"] == target_key:
            identity_state["path"] = r"C:\tmp\unexpected-other-model.edb"
        return fact_type(
            surface=surface,
            target_name=target_name,
            requested_modifiers=modifiers,
            return_code=0,
        )

    def frame_set(_session, *, surface, target_name, modifiers, timeout_seconds=30.0):
        return apply_behavior(surface, target_name, modifiers, FrameModifierSetFact)

    def area_set(_session, *, surface, target_name, modifiers, timeout_seconds=30.0):
        return apply_behavior(surface, target_name, modifiers, AreaModifierSetFact)

    monkeypatch.setattr(subject, "get_frame_modifiers_from_session", frame_get)
    monkeypatch.setattr(subject, "set_frame_modifiers_from_session", frame_set)
    monkeypatch.setattr(subject, "get_area_modifiers_from_session", area_get)
    monkeypatch.setattr(subject, "set_area_modifiers_from_session", area_set)

    return SimpleNamespace(
        context=context,
        owned=owned,
        identity_state=identity_state,
        source_state=source_state,
        values=values,
        calls=calls,
        behavior=behavior,
        key=key,
    )


def _mixed_manifest(harness, targets):
    return subject.build_requested_section_modifier_manifest(
        source_model_ref=harness.context.source_model_identity.source_model_ref,
        targets=targets,
        provenance_refs=("reviewed-state-plan:test",),
    )


def _targets():
    return (
        subject.FrameModifierTargetRequest(
            surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
            target_name="C40x40",
            modifiers=_frame_vector(0.25),
        ),
        subject.FrameModifierTargetRequest(
            surface=FrameModifierSurface.FRAME_OBJECT,
            target_name="F1",
            modifiers=_frame_vector(0.35),
        ),
        subject.AreaModifierTargetRequest(
            surface=AreaModifierSurface.AREA_PROPERTY,
            target_name="Slab_d=15",
            modifiers=_area_vector(0.45),
        ),
        subject.AreaModifierTargetRequest(
            surface=AreaModifierSurface.AREA_OBJECT,
            target_name="A1",
            modifiers=_area_vector(0.55),
        ),
    )


def test_mixed_plan_uses_same_section_stiffness_family(harness):
    manifest = _mixed_manifest(harness, _targets())
    assert manifest.family_set == frozenset(
        {DerivedStateFamily.SECTION_STIFFNESS_MODIFIERS}
    )
    assert (
        manifest.entries[0].canonical_value["contract"]
        == subject.SECTION_MODIFIER_PLAN_CONTRACT
    )


def test_mixed_target_order_is_canonical_and_caller_order_independent(harness):
    targets = _targets()
    left = _mixed_manifest(harness, targets)
    right = _mixed_manifest(harness, tuple(reversed(targets)))
    assert left.manifest_ref == right.manifest_ref
    assert left.entries[0].canonical_value == right.entries[0].canonical_value
    keys = [
        (item["surface"], item["target_name"])
        for item in left.entries[0].canonical_value["targets"]
    ]
    assert [surface for surface, _ in keys] == [
        "FRAME_SECTION_PROPERTY",
        "AREA_PROPERTY",
        "FRAME_OBJECT",
        "AREA_OBJECT",
    ]


def test_old_frame_v1_builder_contract_remains_unchanged(harness):
    target = subject.FrameModifierTargetRequest(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="F1",
        modifiers=_frame_vector(0.35),
    )
    manifest = subject.build_requested_frame_modifier_manifest(
        source_model_ref=harness.context.source_model_identity.source_model_ref,
        targets=(target,),
        provenance_refs=("reviewed-state-plan:test",),
    )
    assert manifest.entries[0].canonical_value == {
        "contract": subject.FRAME_MODIFIER_PLAN_CONTRACT,
        "targets": [target.semantic_dict()],
    }


def test_duplicate_area_target_is_rejected(harness):
    target = subject.AreaModifierTargetRequest(
        surface=AreaModifierSurface.AREA_OBJECT,
        target_name="A1",
        modifiers=_area_vector(0.5),
    )
    with pytest.raises(subject.AnalysisStateMutationError, match="duplicate"):
        _mixed_manifest(harness, (target, target))


def test_duplicate_frame_target_is_rejected(harness):
    target = subject.FrameModifierTargetRequest(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="F1",
        modifiers=_frame_vector(0.5),
    )
    with pytest.raises(subject.AnalysisStateMutationError, match="duplicate"):
        _mixed_manifest(harness, (target, target))


@pytest.mark.parametrize(
    "target",
    [
        subject.AreaModifierTargetRequest(
            surface=AreaModifierSurface.AREA_PROPERTY,
            target_name="Slab_d=15",
            modifiers=_area_vector(0.45),
        ),
        subject.AreaModifierTargetRequest(
            surface=AreaModifierSurface.AREA_OBJECT,
            target_name="A1",
            modifiers=_area_vector(0.55),
        ),
    ],
)
def test_area_only_pre_set_post_issues_one_analysis_state(harness, target):
    manifest = _mixed_manifest(harness, (target,))
    result = subject.establish_section_modifier_analysis_state(
        context=harness.context,
        owned_scratch=harness.owned,
        requested_manifest=manifest,
    )
    assert result.comparison.matched is True
    assert len(result.mutation_manifest.mutations) == 1
    assert isinstance(
        result.mutation_manifest.mutations[0],
        subject.AreaModifierMutationFact,
    )
    assert (
        result.analysis_state_identity.execution_state_ref
        == result.established_manifest.manifest_ref
    )


def test_successful_four_surface_mixed_plan_has_one_analysis_state(harness):
    manifest = _mixed_manifest(harness, _targets())
    result = subject.establish_section_modifier_analysis_state(
        context=harness.context,
        owned_scratch=harness.owned,
        requested_manifest=manifest,
    )
    assert result.comparison.matched is True
    assert len(result.mutation_manifest.mutations) == 4
    assert {
        item.surface.value for item in result.mutation_manifest.mutations
    } == {
        "FRAME_SECTION_PROPERTY",
        "FRAME_OBJECT",
        "AREA_PROPERTY",
        "AREA_OBJECT",
    }
    assert (
        result.mutation_manifest.contract
        == subject.SECTION_MODIFIER_MUTATION_MANIFEST_CONTRACT
    )


def test_area_setter_failure_after_frame_restores_frame(harness):
    frame = subject.FrameModifierTargetRequest(
        surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
        target_name="C40x40",
        modifiers=_frame_vector(0.25),
    )
    area = subject.AreaModifierTargetRequest(
        surface=AreaModifierSurface.AREA_PROPERTY,
        target_name="Slab_d=15",
        modifiers=_area_vector(0.45),
    )
    manifest = _mixed_manifest(harness, (area, frame))
    harness.behavior["nonzero_target"] = area.key

    with pytest.raises(subject.AnalysisStateMutationError) as exc:
        subject.establish_section_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            requested_manifest=manifest,
        )

    assert exc.value.stage == "setter_nonzero"
    assert (
        exc.value.restoration_status
        == subject.MutationRestorationStatus.RESTORED.value
    )
    assert harness.values[frame.key].as_tuple() == (1.0,) * 8


def test_frame_failure_after_area_mutation_restores_area(harness):
    area = subject.AreaModifierTargetRequest(
        surface=AreaModifierSurface.AREA_PROPERTY,
        target_name="Slab_d=15",
        modifiers=_area_vector(0.45),
    )
    frame = subject.FrameModifierTargetRequest(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="F1",
        modifiers=_frame_vector(0.35),
    )
    manifest = _mixed_manifest(harness, (frame, area))
    harness.behavior["nonzero_target"] = frame.key

    with pytest.raises(subject.AnalysisStateMutationError) as exc:
        subject.establish_section_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            requested_manifest=manifest,
        )

    assert (
        exc.value.restoration_status
        == subject.MutationRestorationStatus.RESTORED.value
    )
    assert harness.values[area.key].as_tuple() == (1.0,) * 10


def test_area_readback_mismatch_restores_exact_original(harness):
    target = subject.AreaModifierTargetRequest(
        surface=AreaModifierSurface.AREA_OBJECT,
        target_name="A1",
        modifiers=_area_vector(0.45),
    )
    manifest = _mixed_manifest(harness, (target,))
    harness.behavior["ignore_target"] = target.key

    with pytest.raises(subject.AnalysisStateMutationError) as exc:
        subject.establish_section_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            requested_manifest=manifest,
        )

    assert exc.value.stage == "requested_vs_readback_mismatch"
    assert (
        exc.value.restoration_status
        == subject.MutationRestorationStatus.RESTORED.value
    )


def test_restoration_failure_prevents_positive_result(harness, monkeypatch):
    target = subject.AreaModifierTargetRequest(
        surface=AreaModifierSurface.AREA_OBJECT,
        target_name="A1",
        modifiers=_area_vector(0.45),
    )
    manifest = _mixed_manifest(harness, (target,))
    harness.behavior["ignore_target"] = target.key
    monkeypatch.setattr(
        subject,
        "_section_restoration",
        lambda *args, **kwargs: subject.MutationRestorationStatus.FAILED,
    )

    with pytest.raises(subject.AnalysisStateMutationError) as exc:
        subject.establish_section_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            requested_manifest=manifest,
        )

    assert (
        exc.value.restoration_status
        == subject.MutationRestorationStatus.FAILED.value
    )


def test_active_model_drift_fails_closed(harness):
    target = subject.AreaModifierTargetRequest(
        surface=AreaModifierSurface.AREA_OBJECT,
        target_name="A1",
        modifiers=_area_vector(0.45),
    )
    manifest = _mixed_manifest(harness, (target,))
    harness.behavior["switch_active_after_target"] = target.key

    with pytest.raises(subject.AnalysisStateMutationError) as exc:
        subject.establish_section_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            requested_manifest=manifest,
        )

    assert exc.value.stage == "active_scratch_postcondition"
    assert (
        exc.value.restoration_status
        == subject.MutationRestorationStatus.BLOCKED_UNSAFE.value
    )


def test_source_physical_byte_drift_fails_closed(harness, monkeypatch):
    target = subject.AreaModifierTargetRequest(
        surface=AreaModifierSurface.AREA_OBJECT,
        target_name="A1",
        modifiers=_area_vector(0.45),
    )
    manifest = _mixed_manifest(harness, (target,))
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
        subject.establish_section_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            requested_manifest=manifest,
        )

    assert exc.value.stage == "source_post_mutation_integrity"
    assert (
        exc.value.restoration_status
        == subject.MutationRestorationStatus.RESTORED.value
    )


def test_locked_scratch_fails_before_any_modifier_call(harness):
    harness.identity_state["locked"] = True
    manifest = _mixed_manifest(harness, (_targets()[2],))

    with pytest.raises(subject.AnalysisStateMutationError) as exc:
        subject.establish_section_modifier_analysis_state(
            context=harness.context,
            owned_scratch=harness.owned,
            requested_manifest=manifest,
        )

    assert exc.value.stage == "scratch_locked"
    assert (
        exc.value.restoration_status
        == subject.MutationRestorationStatus.NOT_REQUIRED.value
    )
    assert harness.calls == []


def test_additional_state_basis_refs_are_committed(harness):
    manifest = _mixed_manifest(harness, (_targets()[2],))
    result = subject.establish_section_modifier_analysis_state(
        context=harness.context,
        owned_scratch=harness.owned,
        requested_manifest=manifest,
        additional_state_basis_refs=("area-base:one", "area-base:two"),
    )
    refs = result.analysis_state_identity.state_basis_refs
    assert "area-base:one" in refs
    assert "area-base:two" in refs
