from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_public_a5 as a5
from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (
    AreaCategory,
    AreaEq713TargetDisposition,
    AreaFormulation,
    AreaStiffnessMode,
    ContributorDisposition,
    Eq713PopulationDisposition,
    FrameModeAuditDisposition,
    FrameStiffnessMode,
    ModeDisposition,
)


def _mode(mode, disposition, reason):
    return ModeDisposition(mode, disposition, reason, ("a39:test",))


def _frame(name, *, blocked=False, reason=None):
    if blocked:
        reason = reason or "participation in Eq7.13 Delta_i is unresolved"
        modes = (_mode(FrameStiffnessMode.FLEXURE_2, ContributorDisposition.BLOCKED_UNSUPPORTED, reason),)
        blocked_reasons = (reason,)
    else:
        modes = (_mode(FrameStiffnessMode.FLEXURE_2, ContributorDisposition.TARGETED_UNCRACKED, "already targeted"),)
        blocked_reasons = ()
    return FrameModeAuditDisposition(name, modes, blocked_reasons, (f"frame:{name}",))


def _area(
    name,
    *,
    blocked=True,
    mode=AreaStiffnessMode.M11,
    reason="plate participation in Eq7.13 displacement response is unresolved",
    target=True,
):
    disposition = ContributorDisposition.BLOCKED_UNSUPPORTED if blocked else ContributorDisposition.TARGETED_UNCRACKED
    return AreaEq713TargetDisposition(
        name,
        (_mode(mode, disposition, reason),),
        tuple([1.0] * 10) if target else None,
        (reason,) if blocked else (),
        (f"area:{name}",),
    )


def _shell_evidence(name):
    return SimpleNamespace(
        area_name=name,
        category=AreaCategory.FLOOR,
        formulation=AreaFormulation.SHELL_THICK,
        is_concrete=True,
        gross_base_qualified=True,
        homogeneous_simple_property=True,
    )


def _membrane_evidence(name):
    return SimpleNamespace(
        area_name=name,
        category=AreaCategory.FLOOR,
        formulation=AreaFormulation.MEMBRANE,
        is_concrete=True,
        gross_base_qualified=True,
        homogeneous_simple_property=True,
    )


def _context():
    return SimpleNamespace(
        verified_session=object(),
        model_fingerprint="model:a39",
        evidence_epoch_id="epoch:a39",
    )


def _execution(identity="result:G1"):
    return SimpleNamespace(
        analysis_result_identity=SimpleNamespace(identity_ref=identity),
        execution_proof_ref=f"proof:{identity}",
    )


def _response(context, execution, *, frame_names=(), area_names=("A1",), cases=("EX", "EY")):
    return SimpleNamespace(
        model_fingerprint=context.model_fingerprint,
        evidence_epoch_id=context.evidence_epoch_id,
        analysis_result_ref=execution.analysis_result_identity.identity_ref,
        execution_proof_ref=execution.execution_proof_ref,
        case_names=tuple(cases),
        frame_names=tuple(frame_names),
        area_names=tuple(area_names),
    )


def test_deck_persistent_blocker_does_not_suppress_supported_shellthick_scope():
    shell = _area("A1")
    deck_reason = (
        "Area '557' property 'Deck1' is exact DECK; DECK is not automatically "
        "not-applicable and current Eq7.13 Area applicability remains unresolved"
    )
    deck = _area("557", reason=deck_reason, target=False)
    whole = Eq713PopulationDisposition(frame_rows=(), area_rows=(shell, deck))

    scope = a5._response_probe_scope(
        whole,
        SimpleNamespace(rows=()),
        (_shell_evidence("A1"),),
    )
    partition = a5._partition_response_blockers(
        whole,
        SimpleNamespace(rows=()),
        (_shell_evidence("A1"),),
    )

    assert scope == ((), ("A1",), 1)
    assert partition.response_area_names == ("A1",)
    assert all(item[1] != "557" for item in partition.response_eligible_modes)
    assert any(item[1] == "557" for item in partition.persistent_non_response_blockers)


def test_typed_deck_never_enters_response_area_names():
    deck = _area("557", reason="DECK_APPLICABILITY_UNRESOLVED", target=False)
    whole = Eq713PopulationDisposition(frame_rows=(), area_rows=(deck,))
    assert a5._response_probe_scope(whole, SimpleNamespace(rows=()), ()) is None


def test_no_property_area_never_enters_response_area_names():
    null = AreaEq713TargetDisposition(
        "NULL-1",
        (_mode(AreaStiffnessMode.M11, ContributorDisposition.PROVEN_NOT_APPLICABLE, "Null/no-property Area has no shell-section stiffness target"),),
        None,
        (),
        ("area:NULL-1",),
    )
    whole = Eq713PopulationDisposition(frame_rows=(), area_rows=(null,))
    assert a5._response_probe_scope(whole, SimpleNamespace(rows=()), ()) is None


def test_supported_membrane_blocker_is_not_shellthick_response_target():
    membrane = _area("MEM-1")
    whole = Eq713PopulationDisposition(frame_rows=(), area_rows=(membrane,))
    assert a5._response_probe_scope(
        whole,
        SimpleNamespace(rows=()),
        (_membrane_evidence("MEM-1"),),
    ) is None


def test_supported_shellthick_non_response_prerequisite_blocker_stays_persistent():
    reason = "floor in-plane Eq7.13 participation is not positively established as semi-rigid diaphragm response"
    blocked = _area("A1", mode=AreaStiffnessMode.F11, reason=reason, target=False)
    whole = Eq713PopulationDisposition(frame_rows=(), area_rows=(blocked,))
    partition = a5._partition_response_blockers(
        whole,
        SimpleNamespace(rows=()),
        (_shell_evidence("A1"),),
    )
    assert partition.unresolved_count == 0
    assert partition.response_area_names == ()
    assert partition.persistent_non_response_blockers[0][3] == reason


def test_residual_frame_blocker_does_not_suppress_supported_beam_response_scope():
    beam = _frame("B1", blocked=True)
    residual = _frame("NULL-LINE", blocked=True, reason="NULL Frame stiffness absence is not source-proven")
    whole = Eq713PopulationDisposition(frame_rows=(beam, residual), area_rows=())
    frame_population = SimpleNamespace(rows=(SimpleNamespace(frame_name="B1", member_role="BEAM"),))
    assert a5._response_probe_scope(whole, frame_population, ()) == (("B1",), (), 1)


def test_generation_bound_count_excludes_persistent_deck_modes():
    shell = AreaEq713TargetDisposition(
        "A1",
        (
            _mode(AreaStiffnessMode.M11, ContributorDisposition.BLOCKED_UNSUPPORTED, "plate participation in Eq7.13 displacement response is unresolved"),
            _mode(AreaStiffnessMode.V13, ContributorDisposition.BLOCKED_UNSUPPORTED, "transverse-shear participation in Eq7.13 displacement response is unresolved"),
        ),
        tuple([1.0] * 10),
        (
            "plate participation in Eq7.13 displacement response is unresolved",
            "transverse-shear participation in Eq7.13 displacement response is unresolved",
        ),
        ("area:A1",),
    )
    deck = AreaEq713TargetDisposition(
        "557",
        tuple(
            _mode(mode, ContributorDisposition.BLOCKED_UNSUPPORTED, "DECK_APPLICABILITY_UNRESOLVED")
            for mode in AreaStiffnessMode
        ),
        None,
        ("DECK_APPLICABILITY_UNRESOLVED",),
        ("area:557",),
    )
    whole = Eq713PopulationDisposition(frame_rows=(), area_rows=(shell, deck))
    assert a5._response_probe_scope(
        whole,
        SimpleNamespace(rows=()),
        (_shell_evidence("A1"),),
    ) == ((), ("A1",), 2)


def test_response_scope_still_blocked_tracks_zero_response_reason_after_reason_changes():
    zero_reason = "exact local generalized-result population is identically zero; response evidence cannot prove non-participation"
    unresolved = _area("A1", reason=zero_reason)
    whole = Eq713PopulationDisposition(frame_rows=(), area_rows=(unresolved,))
    assert a5._response_scope_still_blocked(
        whole,
        frame_names=(),
        area_names=("A1",),
    ) == (("AREA", "A1", AreaStiffnessMode.M11.value, zero_reason),)


def test_persistent_deck_disposition_survives_successful_response_subset_closure(monkeypatch):
    context = _context()
    execution = _execution()
    shell_before = _area("A1")
    shell_after = _area("A1", blocked=False, reason="positive qualified response")
    deck = _area("557", reason="DECK_APPLICABILITY_UNRESOLVED", target=False)
    provisional = Eq713PopulationDisposition(frame_rows=(), area_rows=(shell_before, deck))
    resolved = Eq713PopulationDisposition(frame_rows=(), area_rows=(shell_after, deck))

    monkeypatch.setattr(a5, "_initial_beam_classifications", lambda *_args: {})
    monkeypatch.setattr(a5, "_run_a3_generation", lambda **_kwargs: (("TARGET",), SimpleNamespace(), execution))
    monkeypatch.setattr(
        a5,
        "capture_eq713_response_population_from_session",
        lambda _session, **kwargs: _response(
            context,
            execution,
            frame_names=kwargs["frame_names"],
            area_names=kwargs["area_names"],
            cases=kwargs["case_names"],
        ),
    )
    monkeypatch.setattr(a5, "_area_shell_thick_generations_from_response", lambda **_kwargs: {"A1": object()})
    monkeypatch.setattr(a5, "_build_a3", lambda **_kwargs: (resolved, ()))
    monkeypatch.setattr(a5, "_b4b_targets", lambda *_args: ("TARGET",))

    result, _state, final_execution = a5._legacy_area_response_closure(
        context=context,
        owned_scratch=object(),
        frame_pre=SimpleNamespace(rows=()),
        area_pre=SimpleNamespace(rows=()),
        topology_pre=object(),
        provisional_a3=provisional,
        frame_names=(),
        area_names=("A1",),
        unresolved_count=1,
        requested_cases=("EX", "EY"),
        qualified_static_cases=("EX", "EY"),
        qualified_static_refs=("qualified:xy",),
    )

    before_deck = next(row for row in provisional.area_rows if row.area_name == "557")
    after_deck = next(row for row in result.area_rows if row.area_name == "557")
    assert result.positive is False
    assert after_deck == before_deck
    assert final_execution is execution


def test_stable_response_subset_with_zero_response_fails_member_response(monkeypatch):
    context = _context()
    execution = _execution()
    unresolved = _area(
        "A1",
        reason="exact local generalized-result population is identically zero; response evidence cannot prove non-participation",
    )
    whole = Eq713PopulationDisposition(frame_rows=(), area_rows=(unresolved,))

    monkeypatch.setattr(a5, "_initial_beam_classifications", lambda *_args: {})
    monkeypatch.setattr(a5, "_run_a3_generation", lambda **_kwargs: (("TARGET",), SimpleNamespace(), execution))
    monkeypatch.setattr(
        a5,
        "capture_eq713_response_population_from_session",
        lambda _session, **kwargs: _response(
            context,
            execution,
            frame_names=kwargs["frame_names"],
            area_names=kwargs["area_names"],
            cases=kwargs["case_names"],
        ),
    )
    monkeypatch.setattr(a5, "_area_shell_thick_generations_from_response", lambda **_kwargs: {"A1": object()})
    monkeypatch.setattr(a5, "_build_a3", lambda **_kwargs: (whole, ()))
    monkeypatch.setattr(a5, "_b4b_targets", lambda *_args: ("TARGET",))

    with pytest.raises(a5.PublicA5CompositionError, match="response-eligible subset remains unresolved") as exc:
        a5._legacy_area_response_closure(
            context=context,
            owned_scratch=object(),
            frame_pre=SimpleNamespace(rows=()),
            area_pre=SimpleNamespace(rows=()),
            topology_pre=object(),
            provisional_a3=whole,
            frame_names=(),
            area_names=("A1",),
            unresolved_count=1,
            requested_cases=("EX", "EY"),
            qualified_static_cases=("EX", "EY"),
            qualified_static_refs=("qualified:xy",),
        )
    assert exc.value.blocker == a5.BLOCKER_A3_MEMBER_RESPONSE


def test_already_targeted_response_modes_are_not_reported_still_blocked():
    targeted = _area("A1", blocked=False, reason="already targeted")
    whole = Eq713PopulationDisposition(frame_rows=(), area_rows=(targeted,))
    assert a5._response_scope_still_blocked(
        whole,
        frame_names=(),
        area_names=("A1",),
    ) == ()
