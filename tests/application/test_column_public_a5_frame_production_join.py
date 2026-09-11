from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import tbdy_engine.application.column_public_a5 as a5
import tbdy_engine.application.project_execution as project_execution
from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierReadFact,
    FrameModifierSurface,
    FrameModifierVector,
)
from tbdy_engine.etabs.oapi.frame_section_mechanics import FrameSectionMechanicsFact
from tbdy_engine.etabs.oapi.material_properties import IsotropicMaterialPropertiesFact
from tests.application import test_column_public_a5_product_path as base


def _configure(monkeypatch, *, zero_v2: bool):
    harness = base.product_harness.__wrapped__(monkeypatch)
    column_fact = harness.frame_population.rows[0]

    beam_topology = SimpleNamespace(
        beam_unique_name="B1",
        is_supported_rc_beam=True,
        width_t2_m=0.30,
        depth_t3_m=0.50,
        vector_from_joint_m=(4.0, 0.0, 0.0),
    )
    column = replace(harness.column, beams_at_top=(beam_topology,))
    topology = base._Topology(column)
    monkeypatch.setattr(a5, "capture_etabs_strict_column_topology_from_session", lambda _session: topology)

    beam_base = replace(
        column_fact.base_fact,
        component_unique_name="B1",
        assigned_section_name="B30x50",
        semantic_state_ref="frame-semantic:B1",
        evidence_ref="frame-base:B1",
        capture_event_ref="frame-capture:B1",
        source_refs=("frame-base-row:B1",),
    )
    section = FrameSectionMechanicsFact(
        section_name="B30x50",
        area=0.15,
        shear_area_2=0.10,
        shear_area_3=0.11,
        torsional_constant=0.002,
        inertia_22=0.003,
        inertia_33=0.004,
        return_code=0,
    )
    material = IsotropicMaterialPropertiesFact(
        material_name="C35",
        modulus_of_elasticity=33_000.0,
        poisson_ratio=0.20,
        thermal_coefficient=1.0e-5,
        shear_modulus=13_200.0,
        temperature=0.0,
        return_code=0,
    )
    section_initial = FrameModifierVector.from_sequence((0.41, 0.52, 0.63, 0.74, 0.85, 0.96, 1.0, 1.0))
    object_initial = FrameModifierVector.from_sequence((0.31, 0.42, 0.53, 0.64, 0.75, 0.86, 1.0, 1.0))
    property_fact = FrameModifierReadFact(
        surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
        target_name="B30x50",
        modifiers=section_initial,
        return_code=0,
    )
    object_fact = FrameModifierReadFact(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="B1",
        modifiers=object_initial,
        return_code=0,
    )
    beam_fact = SimpleNamespace(
        frame_name="B1",
        member_role="BEAM",
        base_fact=beam_base,
        section_mechanics=section,
        property_modifiers=property_fact,
        object_modifiers=object_fact,
        releases=SimpleNamespace(evidence_ref="release:B1"),
        isotropic_material=material,
        factual_ec_mpa=Decimal("33000"),
        factual_gc_mpa=Decimal("13200"),
        source_refs=(
            "frame-fact:B1",
            beam_base.evidence_ref,
            section.evidence_ref,
            property_fact.evidence_ref,
            object_fact.evidence_ref,
            "release:B1",
            material.evidence_ref,
        ),
        supported_end_condition=True,
    )
    frame_population = SimpleNamespace(
        expected_frame_names=("1", "B1"),
        rows=(column_fact, beam_fact),
        source_refs=(*harness.frame_population.source_refs, "frame-population:B1"),
    )
    monkeypatch.setattr(a5, "capture_frame_eq713_factual_population", lambda *_args, **_kwargs: frame_population)

    harness.modifier_values[(FrameModifierSurface.FRAME_SECTION_PROPERTY.value, "B30x50")] = section_initial
    harness.modifier_values[(FrameModifierSurface.FRAME_OBJECT.value, "B1")] = object_initial

    cases = ("gravity-leaf", "modal-extra", "quake-alpha", "quake-beta")
    harness.runtime["run_flags"].clear()
    harness.runtime["run_flags"].update({name: False for name in cases})
    harness.runtime["statuses"].clear()
    harness.runtime["statuses"].update({name: 4 for name in cases})

    combo = SimpleNamespace(
        name="ULS",
        combo_type="LINEAR_ADD",
        constituents=tuple(
            SimpleNamespace(cname_type="LOAD_CASE", name=name, scale_factor=1.0)
            for name in cases
        ),
        nested_combos=(),
    )
    monkeypatch.setattr(a5, "capture_etabs_combo_definitions_from_session", lambda *_args, **_kwargs: (combo,))
    monkeypatch.setattr(a5, "probe_eq713_response_population_capability", lambda *_args, **_kwargs: ("FrameForce",))

    direction_map = {"PATTERN_X": (True, False), "PATTERN_Y": (False, True)}
    auto_fact = object()
    monkeypatch.setattr(a5, "capture_etabs_auto_seismic_direction_evidence_from_session", lambda _session: auto_fact)
    monkeypatch.setattr(
        a5,
        "tsc2018_horizontal_pattern_directions",
        lambda evidence: direction_map if evidence is auto_fact else (_ for _ in ()).throw(AssertionError("wrong auto fact")),
    )

    qualifier_calls = []

    def qualify(_session, *, candidate_case_names, tsc2018_pattern_directions, direction_source_refs):
        qualifier_calls.append((tuple(candidate_case_names), dict(tsc2018_pattern_directions), tuple(direction_source_refs)))
        assert set(candidate_case_names) == set(cases)
        assert dict(tsc2018_pattern_directions) == direction_map
        return SimpleNamespace(
            cases=(
                SimpleNamespace(case_name="quake-alpha", case_type="LINEAR_STATIC", direction_vectors_xy=((1.0, 0.0),), source_refs=("pattern:PATTERN_X",)),
                SimpleNamespace(case_name="modal-extra", case_type="RESPONSE_SPECTRUM", direction_vectors_xy=((1.0, 0.0),), source_refs=("modal:qualified",)),
                SimpleNamespace(case_name="quake-beta", case_type="LINEAR_STATIC", direction_vectors_xy=((0.0, 1.0),), source_refs=("pattern:PATTERN_Y",)),
            ),
            case_names=("quake-alpha", "modal-extra", "quake-beta"),
            source_refs=("qualified:broad",),
            evidence_ref="qualified:broad",
        )

    monkeypatch.setattr(a5, "qualify_eq713_horizontal_case_scope_from_session", qualify)

    response_calls = []

    def capture_response(
        _session,
        *,
        model_fingerprint,
        evidence_epoch_id,
        analysis_result_ref,
        execution_proof_ref,
        case_names,
        frame_names,
        area_names,
        case_scope_refs,
    ):
        generation = len(response_calls)
        response_calls.append((tuple(case_names), tuple(frame_names), tuple(area_names), tuple(case_scope_refs), analysis_result_ref))
        assert tuple(case_names) == ("quake-alpha", "quake-beta")
        assert tuple(frame_names) == ("B1",)
        assert tuple(area_names) == ()
        assert "gravity-leaf" not in case_names and "modal-extra" not in case_names
        if generation == 0:
            v2 = 0.0 if zero_v2 else 20.0
            values = dict(p=10.0, v2=v2, v3=30.0, t=5.0, m2=40.0, m3=50.0)
        else:
            values = dict(p=0.0, v2=0.0, v3=0.0, t=0.0, m2=0.0, m3=0.0)
        results = tuple(
            SimpleNamespace(
                frame_name="B1",
                case_name=case_name,
                rows=(SimpleNamespace(**values),),
                evidence_ref=f"frame-force:B1:{case_name}:g{generation}",
            )
            for case_name in case_names
        )
        return SimpleNamespace(
            model_fingerprint=model_fingerprint,
            evidence_epoch_id=evidence_epoch_id,
            analysis_result_ref=analysis_result_ref,
            execution_proof_ref=execution_proof_ref,
            case_names=tuple(case_names),
            frame_names=tuple(frame_names),
            area_names=(),
            frame_results=results,
            area_results=(),
            source_refs=("response:qualified-static", *case_scope_refs),
            evidence_ref=f"response:g{generation}",
        )

    monkeypatch.setattr(a5, "capture_eq713_response_population_from_session", capture_response)

    classifier_calls = []
    original_classifier = a5.classify_frame_response_participation

    def classifier_probe(**kwargs):
        result = original_classifier(**kwargs)
        classifier_calls.append((kwargs["property_modifiers"].modifiers.as_tuple(), kwargs["object_modifiers"].modifiers.as_tuple(), result))
        return result

    monkeypatch.setattr(a5, "classify_frame_response_participation", classifier_probe)

    generation_refs = []
    original_generation = a5._run_a3_generation

    def generation_probe(**kwargs):
        result = original_generation(**kwargs)
        generation_refs.append(result[2].analysis_result_identity.identity_ref)
        return result

    monkeypatch.setattr(a5, "_run_a3_generation", generation_probe)

    fnd2_result_refs = []
    original_materialize = a5._materialize_fnd2_inputs

    def materialize_probe(**kwargs):
        fnd2_result_refs.append(kwargs["execution_result"].analysis_result_identity.identity_ref)
        return original_materialize(**kwargs)

    monkeypatch.setattr(a5, "_materialize_fnd2_inputs", materialize_probe)
    return SimpleNamespace(
        harness=harness,
        qualifier_calls=qualifier_calls,
        response_calls=response_calls,
        classifier_calls=classifier_calls,
        generation_refs=generation_refs,
        fnd2_result_refs=fnd2_result_refs,
    )


def test_execute_project_joins_qualified_static_frame_response_and_uses_final_generation(monkeypatch):
    proof = _configure(monkeypatch, zero_v2=False)
    result = project_execution.execute_project(proof.harness.request, verified_session=base._FakeSession())

    assert result.column.fnd_col_2_execution is not None
    assert len(proof.qualifier_calls) == 1
    assert {"gravity-leaf", "quake-alpha", "quake-beta"}.issubset(set(proof.qualifier_calls[0][0]))
    assert len(proof.response_calls) == 2
    assert all(call[0] == ("quake-alpha", "quake-beta") for call in proof.response_calls)
    assert all("session-provenance:public-a5" in call[3] for call in proof.response_calls)
    assert proof.harness.runtime["run_calls"] == 2

    beam_section = proof.harness.modifier_values[(FrameModifierSurface.FRAME_SECTION_PROPERTY.value, "B30x50")].as_tuple()
    beam_object = proof.harness.modifier_values[(FrameModifierSurface.FRAME_OBJECT.value, "B1")].as_tuple()
    assert beam_section[1:3] == (1.0, 1.0)
    assert beam_object[1:3] == (1.0, 1.0)
    assert proof.classifier_calls[-1][0][1:3] == (1.0, 1.0)
    assert proof.classifier_calls[-1][1][1:3] == (1.0, 1.0)
    assert all(row.participates is not False for _prop, _obj, classification in proof.classifier_calls for row in classification.mode_evidence)

    assert len(proof.generation_refs) == 2
    assert proof.generation_refs[0] != proof.generation_refs[-1]
    assert proof.fnd2_result_refs == [proof.generation_refs[-1]]


def test_execute_project_zero_frame_response_remains_unresolved_and_never_becomes_false(monkeypatch):
    proof = _configure(monkeypatch, zero_v2=True)
    result = project_execution.execute_project(proof.harness.request, verified_session=base._FakeSession())

    assert result.column.fnd_col_2_execution is None
    assert result.column.blockers == (a5.BLOCKER_A3_MEMBER_RESPONSE,)
    assert len(proof.classifier_calls) >= 1
    first = proof.classifier_calls[0][2]
    by_mode = {row.mode.value: row.participates for row in first.mode_evidence}
    assert by_mode["SHEAR_2"] is None
    assert all(value is not False for value in by_mode.values())
    assert all(call[0] == ("quake-alpha", "quake-beta") for call in proof.response_calls)
