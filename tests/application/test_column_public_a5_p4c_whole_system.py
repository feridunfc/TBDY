from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_public_a5 as a5
from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (
    AreaCategory,
    AreaEq713TargetDisposition,
    AreaFormulation,
    AreaGrossBasePropertyEvidence,
    AreaStiffnessMode,
    ContributorDisposition,
    Eq713PopulationDisposition,
    FrameModeAuditDisposition,
    FrameStiffnessMode,
    ModeDisposition,
    build_area_eq713_target,
    build_concrete_uncracked_material_basis,
)
from tbdy_engine.etabs.oapi.area_contributors import AreaDesignOrientation
from tbdy_engine.etabs.oapi.area_modifiers import AreaModifierVector
from tbdy_engine.etabs.oapi.frame_modifiers import FrameModifierVector


def _mode(mode, disposition, reason="p4c", ref="p4c:mode"):
    return ModeDisposition(mode, disposition, reason, (ref,))


def _frame_row(name: str, *, blocked: bool = False):
    if blocked:
        reason = "participation in Eq7.13 Delta_i is unresolved"
        modes = (_mode(FrameStiffnessMode.FLEXURE_2, ContributorDisposition.BLOCKED_UNSUPPORTED, reason),)
        blocked_reasons = (reason,)
    else:
        modes = (_mode(FrameStiffnessMode.FLEXURE_2, ContributorDisposition.TARGETED_UNCRACKED),)
        blocked_reasons = ()
    return FrameModeAuditDisposition(name, modes, blocked_reasons, (f"frame:{name}",))


def _area_row(
    name: str,
    *,
    formulation: AreaFormulation = AreaFormulation.SHELL_THICK,
    blocked: bool = False,
    null: bool = False,
):
    if null or formulation is AreaFormulation.MEMBRANE:
        disposition = ContributorDisposition.PROVEN_NOT_APPLICABLE
        modes = (_mode(AreaStiffnessMode.M11, disposition),)
        blocked_reasons = ()
    elif blocked:
        reason = "plate participation in Eq7.13 Delta_i is unresolved"
        modes = (_mode(AreaStiffnessMode.M11, ContributorDisposition.BLOCKED_UNSUPPORTED, reason),)
        blocked_reasons = (reason,)
    else:
        modes = (_mode(AreaStiffnessMode.M11, ContributorDisposition.TARGETED_UNCRACKED),)
        blocked_reasons = ()
    target = None if null else tuple([1.0] * 10)
    return AreaEq713TargetDisposition(name, modes, target, blocked_reasons, (f"area:{name}",))


def test_build_a3_preserves_every_factual_frame_and_area_identity_once(monkeypatch):
    frame_facts = tuple(
        SimpleNamespace(
            frame_name=name,
            base_fact=SimpleNamespace(material_name="C35"),
            property_modifiers=SimpleNamespace(modifiers=FrameModifierVector.from_sequence((1.0,) * 8)),
            object_modifiers=SimpleNamespace(modifiers=FrameModifierVector.from_sequence((1.0,) * 8)),
            source_refs=(f"frame-fact:{name}",),
        )
        for name in ("C1", "B1")
    )
    area_facts = tuple(
        SimpleNamespace(area_name=name, formulation=formulation)
        for name, formulation in (
            ("F-SHELL", AreaFormulation.SHELL_THICK),
            ("W-SHELL", AreaFormulation.SHELL_THICK),
            ("F-MEM", AreaFormulation.MEMBRANE),
            ("NULL-1", AreaFormulation.OTHER),
        )
    )
    frame_population = SimpleNamespace(expected_frame_names=("B1", "C1"), rows=frame_facts)
    area_population = SimpleNamespace(
        expected_area_names=("F-MEM", "F-SHELL", "NULL-1", "W-SHELL"),
        rows=area_facts,
    )

    monkeypatch.setattr(a5, "_material_bases", lambda _population: {"C35": object()})
    monkeypatch.setattr(
        a5,
        "_frame_mechanics_evidence",
        lambda fact, _topology: SimpleNamespace(component_uid=fact.frame_name),
    )
    monkeypatch.setattr(
        a5,
        "classify_frame_eq713_participation",
        lambda mechanics: SimpleNamespace(
            component_uid=mechanics.component_uid,
            source_refs=(f"classification:{mechanics.component_uid}",),
            as_mapping=lambda: {},
        ),
    )
    monkeypatch.setattr(
        a5,
        "audit_frame_eq713_modes",
        lambda *, component_uid, **_kwargs: _frame_row(component_uid),
    )
    monkeypatch.setattr(
        a5,
        "_area_evidence",
        lambda fact, _materials: SimpleNamespace(
            area_name=fact.area_name,
            formulation=fact.formulation,
        ),
    )
    monkeypatch.setattr(
        a5,
        "build_area_eq713_target",
        lambda evidence: _area_row(
            evidence.area_name,
            formulation=evidence.formulation,
            null=evidence.formulation is AreaFormulation.OTHER,
        ),
    )

    whole, _ = a5._build_a3(
        frame_population=frame_population,
        area_population=area_population,
        topology=object(),
    )

    assert tuple(row.component_uid for row in whole.frame_rows) == ("C1", "B1")
    assert tuple(row.area_name for row in whole.area_rows) == (
        "F-SHELL",
        "W-SHELL",
        "F-MEM",
        "NULL-1",
    )
    assert len({row.component_uid for row in whole.frame_rows}) == len(frame_population.rows)
    assert len({row.area_name for row in whole.area_rows}) == len(area_population.rows)


def test_response_probe_scope_is_only_unresolved_beam_and_shellthick():
    beam = _frame_row("B1", blocked=True)
    column = _frame_row("C1", blocked=False)
    shell = _area_row("A-SHELL", blocked=True)
    membrane = _area_row("A-MEM", formulation=AreaFormulation.MEMBRANE)
    null = _area_row("A-NULL", null=True)
    whole = Eq713PopulationDisposition(
        frame_rows=(column, beam),
        area_rows=(shell, membrane, null),
    )
    frame_population = SimpleNamespace(
        rows=(
            SimpleNamespace(frame_name="C1", member_role="COLUMN"),
            SimpleNamespace(frame_name="B1", member_role="BEAM"),
        )
    )
    area_evidence = (
        SimpleNamespace(
            area_name="A-SHELL",
            formulation=AreaFormulation.SHELL_THICK,
            homogeneous_simple_property=True,
        ),
        SimpleNamespace(
            area_name="A-MEM",
            formulation=AreaFormulation.MEMBRANE,
            homogeneous_simple_property=True,
        ),
        SimpleNamespace(
            area_name="A-NULL",
            formulation=AreaFormulation.OTHER,
            homogeneous_simple_property=True,
        ),
    )

    frame_names, area_names, unresolved_count = a5._response_probe_scope(
        whole,
        frame_population,
        area_evidence,
    )

    assert frame_names == ("B1",)
    assert area_names == ("A-SHELL",)
    assert unresolved_count == 2


def test_membrane_and_null_remain_explicit_existing_authority_rows():
    material = build_concrete_uncracked_material_basis(
        material_name="C35",
        fck_mpa=35,
        factual_ec_mpa=33000,
        factual_gc_mpa=13200,
        source_refs=("material:C35",),
    )
    membrane = AreaGrossBasePropertyEvidence.build(
        area_name="A-MEM",
        property_name="MEM",
        category=AreaCategory.FLOOR,
        formulation=AreaFormulation.MEMBRANE,
        is_concrete=True,
        gross_geometry_proven=True,
        thickness_proven=True,
        homogeneous_simple_property=True,
        material_overwrite_qualified=True,
        thickness_overwrite_qualified=True,
        property_modifiers=(0.5,) * 8 + (1.0, 1.0),
        object_modifiers=(1.0,) * 10,
        material_basis=material,
        semi_rigid_diaphragm_participation=True,
        source_refs=("area:A-MEM",),
    )
    null = AreaGrossBasePropertyEvidence.build(
        area_name="A-NULL",
        property_name="None",
        category=AreaCategory.NULL,
        formulation=AreaFormulation.OTHER,
        is_concrete=False,
        gross_geometry_proven=True,
        thickness_proven=True,
        homogeneous_simple_property=True,
        material_overwrite_qualified=True,
        thickness_overwrite_qualified=True,
        property_modifiers=(1.0,) * 10,
        object_modifiers=(1.0,) * 10,
        material_basis=None,
        source_refs=("area:A-NULL",),
    )

    membrane_row = build_area_eq713_target(membrane)
    null_row = build_area_eq713_target(null)
    membrane_by_mode = {row.mode: row.disposition for row in membrane_row.mode_dispositions}

    assert membrane_row.qualified
    assert membrane_by_mode[AreaStiffnessMode.M11] is ContributorDisposition.PROVEN_NOT_APPLICABLE
    assert membrane_by_mode[AreaStiffnessMode.V23] is ContributorDisposition.PROVEN_NOT_APPLICABLE
    assert null_row.qualified
    assert null_row.target_property_modifiers is None
    assert all(
        row.disposition is ContributorDisposition.PROVEN_NOT_APPLICABLE
        for row in null_row.mode_dispositions
    )


def test_b4b_target_builder_uses_complete_frame_and_area_population(monkeypatch):
    frame_facts = (
        SimpleNamespace(
            frame_name="C1",
            base_fact=SimpleNamespace(assigned_section_name="SEC-C"),
            property_modifiers=SimpleNamespace(modifiers=FrameModifierVector.from_sequence((1.0,) * 8)),
            object_modifiers=SimpleNamespace(modifiers=FrameModifierVector.from_sequence((1.0,) * 8)),
        ),
        SimpleNamespace(
            frame_name="B1",
            base_fact=SimpleNamespace(assigned_section_name="SEC-B"),
            property_modifiers=SimpleNamespace(modifiers=FrameModifierVector.from_sequence((1.0,) * 8)),
            object_modifiers=SimpleNamespace(modifiers=FrameModifierVector.from_sequence((1.0,) * 8)),
        ),
    )
    area_fact = SimpleNamespace(
        area_name="A1",
        property_name="SLAB",
        property_state=SimpleNamespace(),
    )
    monkeypatch.setattr(
        a5,
        "build_frame_eq713_modifier_target",
        lambda *, current_modifiers, disposition: SimpleNamespace(target_modifiers=current_modifiers),
    )

    targets = a5._b4b_targets(
        SimpleNamespace(rows=frame_facts),
        SimpleNamespace(rows=(area_fact,)),
        (_frame_row("C1"), _frame_row("B1")),
        (
            AreaEq713TargetDisposition(
                "A1",
                (_mode(AreaStiffnessMode.F11, ContributorDisposition.TARGETED_UNCRACKED),),
                tuple([1.0] * 10),
                (),
                ("area:A1",),
            ),
        ),
    )

    identities = {(target.surface.value, target.target_name) for target in targets}
    assert identities == {
        ("FRAME_OBJECT", "C1"),
        ("FRAME_OBJECT", "B1"),
        ("FRAME_SECTION_PROPERTY", "SEC-C"),
        ("FRAME_SECTION_PROPERTY", "SEC-B"),
        ("AREA_PROPERTY", "SLAB"),
    }


def _closure_context():
    return SimpleNamespace(
        verified_session=object(),
        model_fingerprint="model:p4c",
        evidence_epoch_id="epoch:p4c",
    )


def _execution(identity: str):
    return SimpleNamespace(
        analysis_result_identity=SimpleNamespace(identity_ref=identity),
        execution_proof_ref=f"proof:{identity}",
    )


def _response_for(context, execution, *, frame_names=("B1",), area_names=("A1",), cases=("EX", "EY")):
    return SimpleNamespace(
        model_fingerprint=context.model_fingerprint,
        evidence_epoch_id=context.evidence_epoch_id,
        analysis_result_ref=execution.analysis_result_identity.identity_ref,
        execution_proof_ref=execution.execution_proof_ref,
        case_names=tuple(cases),
        frame_names=tuple(frame_names),
        area_names=tuple(area_names),
    )


def test_mixed_response_population_is_bound_to_same_b5_generation(monkeypatch):
    context = _closure_context()
    execution = _execution("result:G1")
    provisional = SimpleNamespace(marker=0)
    stable = SimpleNamespace(marker=1, frame_rows=(), area_rows=(), positive=True)
    captured = []

    monkeypatch.setattr(a5, "_initial_beam_classifications", lambda *_args: {})
    monkeypatch.setattr(
        a5,
        "_run_a3_generation",
        lambda **_kwargs: (("WHOLE",), SimpleNamespace(), execution),
    )

    def capture(_session, **kwargs):
        captured.append(kwargs)
        return _response_for(
            context,
            execution,
            frame_names=kwargs["frame_names"],
            area_names=kwargs["area_names"],
            cases=kwargs["case_names"],
        )

    monkeypatch.setattr(a5, "capture_eq713_response_population_from_session", capture)
    monkeypatch.setattr(a5, "_classify_beam_generation", lambda **_kwargs: {})
    monkeypatch.setattr(a5, "_area_shell_thick_generations_from_response", lambda **_kwargs: {"A1": object()})
    monkeypatch.setattr(a5, "_build_a3", lambda **_kwargs: (stable, ()))
    monkeypatch.setattr(a5, "_b4b_targets", lambda *_args: ("WHOLE",))

    _a3, _state, final_execution = a5._legacy_area_response_closure(
        context=context,
        owned_scratch=object(),
        frame_pre=SimpleNamespace(rows=()),
        area_pre=SimpleNamespace(rows=()),
        topology_pre=object(),
        provisional_a3=provisional,
        frame_names=("B1",),
        area_names=("A1",),
        unresolved_count=2,
        requested_cases=("EX", "EY"),
        qualified_static_cases=("EX", "EY"),
        qualified_static_refs=("qualified:xy",),
    )

    assert final_execution.analysis_result_identity.identity_ref == "result:G1"
    assert len(captured) == 1
    assert captured[0]["frame_names"] == ("B1",)
    assert captured[0]["area_names"] == ("A1",)
    assert captured[0]["analysis_result_ref"] == "result:G1"
    assert captured[0]["execution_proof_ref"] == "proof:result:G1"


def test_mixed_response_binding_mismatch_fails_closed(monkeypatch):
    context = _closure_context()
    execution = _execution("result:G1")
    provisional = SimpleNamespace(marker=0)

    monkeypatch.setattr(a5, "_initial_beam_classifications", lambda *_args: {})
    monkeypatch.setattr(
        a5,
        "_run_a3_generation",
        lambda **_kwargs: (("WHOLE",), SimpleNamespace(), execution),
    )
    bad = _response_for(context, execution)
    bad = SimpleNamespace(**{**bad.__dict__, "analysis_result_ref": "result:STALE"})
    monkeypatch.setattr(a5, "capture_eq713_response_population_from_session", lambda *_args, **_kwargs: bad)

    with pytest.raises(a5.PublicA5CompositionError, match="lost exact model/epoch/B5/qualified-static binding"):
        a5._legacy_area_response_closure(
            context=context,
            owned_scratch=object(),
            frame_pre=SimpleNamespace(rows=()),
            area_pre=SimpleNamespace(rows=()),
            topology_pre=object(),
            provisional_a3=provisional,
            frame_names=("B1",),
            area_names=("A1",),
            unresolved_count=1,
            requested_cases=("EX", "EY"),
            qualified_static_cases=("EX", "EY"),
            qualified_static_refs=("qualified:xy",),
        )


def test_whole_system_fixed_point_returns_only_final_stable_b5_identity(monkeypatch):
    context = _closure_context()
    provisional = SimpleNamespace(marker=0)
    learned = SimpleNamespace(marker=1, frame_rows=(), area_rows=(), positive=False)
    stable = SimpleNamespace(marker=2, frame_rows=(), area_rows=(), positive=True)
    executions = {0: _execution("result:G0"), 1: _execution("result:G1")}
    seen_result_refs = []

    monkeypatch.setattr(a5, "_initial_beam_classifications", lambda *_args: {})

    def run_generation(**kwargs):
        marker = kwargs["a3"].marker
        return (("T0",) if marker == 0 else ("T1",), SimpleNamespace(), executions[marker])

    monkeypatch.setattr(a5, "_run_a3_generation", run_generation)

    def capture(_session, **kwargs):
        seen_result_refs.append(kwargs["analysis_result_ref"])
        execution = next(
            item for item in executions.values()
            if item.analysis_result_identity.identity_ref == kwargs["analysis_result_ref"]
        )
        return _response_for(
            context,
            execution,
            frame_names=kwargs["frame_names"],
            area_names=kwargs["area_names"],
            cases=kwargs["case_names"],
        )

    monkeypatch.setattr(a5, "capture_eq713_response_population_from_session", capture)
    monkeypatch.setattr(a5, "_classify_beam_generation", lambda **_kwargs: {})
    monkeypatch.setattr(a5, "_area_shell_thick_generations_from_response", lambda **_kwargs: {"A1": object()})

    def rebuild(**kwargs):
        return (learned if len(kwargs["response_populations"]) == 1 else stable, ())

    monkeypatch.setattr(a5, "_build_a3", rebuild)
    monkeypatch.setattr(
        a5,
        "_b4b_targets",
        lambda _frame, _area, _frows, _arows: ("T1",),
    )

    final_a3, _state, final_execution = a5._legacy_area_response_closure(
        context=context,
        owned_scratch=object(),
        frame_pre=SimpleNamespace(rows=()),
        area_pre=SimpleNamespace(rows=()),
        topology_pre=object(),
        provisional_a3=provisional,
        frame_names=("B1",),
        area_names=("A1",),
        unresolved_count=3,
        requested_cases=("EX", "EY"),
        qualified_static_cases=("EX", "EY"),
        qualified_static_refs=("qualified:xy",),
    )

    assert seen_result_refs == ["result:G0", "result:G1"]
    assert final_a3 is stable
    assert final_execution.analysis_result_identity.identity_ref == "result:G1"
    assert final_execution.analysis_result_identity.identity_ref != seen_result_refs[0]


def test_stable_but_unresolved_whole_target_fails_closed(monkeypatch):
    context = _closure_context()
    execution = _execution("result:G1")
    provisional = SimpleNamespace(marker=0)
    unresolved = SimpleNamespace(marker=1, frame_rows=(), area_rows=(), positive=False)

    monkeypatch.setattr(a5, "_initial_beam_classifications", lambda *_args: {})
    monkeypatch.setattr(
        a5,
        "_run_a3_generation",
        lambda **_kwargs: (("WHOLE",), SimpleNamespace(), execution),
    )
    monkeypatch.setattr(
        a5,
        "capture_eq713_response_population_from_session",
        lambda _session, **kwargs: _response_for(
            context,
            execution,
            frame_names=kwargs["frame_names"],
            area_names=kwargs["area_names"],
            cases=kwargs["case_names"],
        ),
    )
    monkeypatch.setattr(a5, "_classify_beam_generation", lambda **_kwargs: {})
    monkeypatch.setattr(a5, "_area_shell_thick_generations_from_response", lambda **_kwargs: {"A1": object()})
    monkeypatch.setattr(a5, "_build_a3", lambda **_kwargs: (unresolved, ()))
    monkeypatch.setattr(a5, "_b4b_targets", lambda *_args: ("WHOLE",))
    monkeypatch.setattr(
        a5,
        "_raise_unqualified_a3",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            a5.PublicA5CompositionError(a5.BLOCKER_A3_MEMBER_RESPONSE, "unresolved whole target")
        ),
    )

    with pytest.raises(a5.PublicA5CompositionError, match="unresolved whole target"):
        a5._legacy_area_response_closure(
            context=context,
            owned_scratch=object(),
            frame_pre=SimpleNamespace(rows=()),
            area_pre=SimpleNamespace(rows=()),
            topology_pre=object(),
            provisional_a3=provisional,
            frame_names=("B1",),
            area_names=("A1",),
            unresolved_count=1,
            requested_cases=("EX", "EY"),
            qualified_static_cases=("EX", "EY"),
            qualified_static_refs=("qualified:xy",),
        )
