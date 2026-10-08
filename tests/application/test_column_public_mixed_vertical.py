"""Offline public-root vertical; ETABS facts are mocked, engineering owners are real.

The existing acquisition/B4B/B5 boundary harness is reused. Its legacy
slenderness and stiffness overrides are explicitly replaced by production
owners. No readiness, sway, PMM, adequacy or selection result is injected.
"""
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from types import SimpleNamespace as NS
import importlib.util
import json
from pathlib import Path

import pytest

import test_column_public_population_project_root as population
import tbdy_engine.application.column_execution as column
import tbdy_engine.application.column_public_a5 as a5
import tbdy_engine.application.column_public_a5_second_order as second_order
import tbdy_engine.application.column_stability_runtime as stability
import tbdy_engine.application.column_route_c_direction_binding as direction
import tbdy_engine.application.column_longitudinal_runtime as longitudinal
import tbdy_engine.application.column_p7_runtime as p7
from tbdy_engine.application.column_final_cage import ReviewedColumnFinalCageContext
from tbdy_engine.application.column_vc_runtime import ReviewedColumnVcRuntimeContext, ReviewedHighColumnVcDirectionPlan
from tbdy_engine.features.column_shear_demand_evidence import column_shear_source_identity
from tbdy_engine.regulatory.vs6_column_shear_p7_integration import ReviewedDAmplifiedShearAuthority
import tbdy_engine.application.project_execution as project
import tbdy_engine.providers.etabs_column_end_displacement_provider as displacements
import tbdy_engine.providers.etabs_column_axial_b5_provider as axial
from tbdy_engine.checks.column_axial_selection import ReviewedColumnNdmLoadBinding, Ts498ReductionPolicyState
from tbdy_engine.regulatory.vs5_column_axial_program import ReviewedVs5ColumnAxialContext
from tbdy_engine.providers.etabs_load_pattern_catalog_provider import EtabsLoadPatternCatalogEvidence
from tbdy_engine.application.column_design_basis import (
    ReviewedColumnDesignBasis, ReviewedConcreteDesignStrength,
    ReviewedLongitudinalSteelDesignStrength, ReviewedAggregateBasis,
    ReviewedActionFamilyApplicability, ReviewedTransverseSteelDesignStrength,
)
from tbdy_engine.design.columns.free_length_basis import resolve_ts500_column_free_length
from tbdy_engine.design.columns.story_relative_translation import ReviewedStoryTranslationTolerance
from tbdy_engine.design.columns.stability_output_state import CSI_LINEAR_ADD_SINGLE_VALUE_STEP_TYPE
from tbdy_engine.design.columns.column_concrete_design_evidence_authority import normalized_combo_definition_fingerprint
from tbdy_engine.features.column_shear_topology import build_strict_column_topology
from tbdy_engine.features.column_concrete_design_evidence import (
    ExpectedConcreteDesignComboPolicy, ExpectedConcreteDesignCombo,
    ReviewedConcreteDesignComboDefinition, ReviewedConcreteDesignComboConstituent,
    ColumnTopologyEvidenceEnvelope,
)
from tbdy_engine.features.column_design_rebar_evidence import FactualColumnDesignResultPopulation, FactualColumnDesignResultRow
from tbdy_engine.features.used_rc_material_population import (
    MaterialUsageReference, MaterialUsageStatus, UsedMaterialDefinition,
    ConcreteStrengthFactStatus, MaterialPopulationReadiness,
)
from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.etabs.oapi.joint_displacement_results import JointDisplacementResultFact, JointDisplacementResultRow
from tbdy_engine.etabs.oapi.analysis_execution import DefinedAnalysisCasePopulationFact
from tbdy_engine.etabs.oapi.frame_modifiers import FrameModifierVector
from tbdy_engine.etabs.oapi.frame_releases import FrameReleaseFact
from tbdy_engine.etabs.oapi.frame_section_mechanics import FrameSectionMechanicsFact
from tbdy_engine.etabs.oapi.material_properties import IsotropicMaterialPropertiesFact
from tbdy_engine.providers.etabs_auto_seismic_direction_provider import (
    EtabsAutoSeismicDirectionEvidence, EtabsAutoSeismicDirectionRow, REQUIRED_DIRECTION_FIELDS,
)
from tbdy_engine.providers.etabs_combo_definition_provider import EtabsComboDefinitionEvidence, EtabsComboConstituentEvidence
from tbdy_engine.providers.etabs_static_linear_case_provider import (
    EtabsStaticLinearCaseEvidence, EtabsStaticLinearLoadTermEvidence, EtabsLoadPatternTypeEvidence,
)
from tbdy_engine.providers.etabs_rebar_catalog_provider import EtabsRebarCatalogEvidence, TABLE_REINFORCING_BAR_SIZES
from tbdy_engine.providers.etabs_column_rebar_intent_provider import EtabsColumnRebarIntentEvidence
from tbdy_engine.providers.etabs_concrete_design_combo_selection_probe import (
    ActualConcreteDesignComboSelectionPopulation, ActualSelectedConcreteDesignComboRow,
)
from tbdy_engine.providers.etabs_story_stability_result_provider import EtabsStoryStabilityComboFact
from tbdy_engine.providers.strict_topology_stiffness_evidence_provider import build_assigned_rc_frame_bending_modifier_evidence
from tbdy_engine.regulatory.contracts import ApplicabilityState, AvailabilityState
from unit_contract_fixtures import binding as synthetic_unit_binding


C1, C2 = population.COMPONENT_1, population.COMPONENT_2
MODEL, EPOCH = "model-fingerprint:public-a5", "evidence-epoch:public-a5"


def _topology():
    points, columns, beams, assignments, offsets, axes = [], [], [], [], [], []
    sections = [dict(Name=s, DesignType="Column", t2="0.5", t3="0.8", I2Mod=1, I3Mod=1)
                for s in ("C50x80", "C50x80B")]
    sections.append(dict(Name="B50x80", DesignType="Beam", t2="0.5", t3="0.8", I2Mod=1, I3Mod=1))
    for uid, x, section in (("1", 0, "C50x80"), ("2", 10, "C50x80B")):
        for end, z in (("BOT", 0), ("TOP", 3)):
            joint = f"J{uid}-{end}"
            points.append(dict(UniqueName=joint, Story="Story1", X=x, Y=0, Z=z))
            # C2 has no top beams: a legitimate unresolved A18 component.
            if uid == "2" and end == "TOP":
                continue
            for plane, dx, dy in (("X", 4, 0), ("Y", 0, 4)):
                name, other = f"B{uid}-{end}-{plane}", f"J{uid}-{end}-{plane}"
                points.append(dict(UniqueName=other, Story="Story1", X=x+dx, Y=dy, Z=z))
                beams.append(dict(UniqueName=name, Story="Story1", BeamBay=name, UniquePtI=joint, UniquePtJ=other, Length=4))
                assignments.append(dict(UniqueName=name, Story="Story1", Label=name, Shape="Concrete Rectangular", SectProp="B50x80"))
                axes.append(dict(UniqueName=name, Angle=0))
        columns.append(dict(UniqueName=uid, Story="Story1", ColumnBay=f"C{uid}", UniquePtI=f"J{uid}-BOT", UniquePtJ=f"J{uid}-TOP", Length=3))
        assignments.append(dict(UniqueName=uid, Story="Story1", Label=f"C{uid}", Shape="Concrete Rectangular", SectProp=section))
        offsets.append(dict(UniqueName=uid, OffsetI=0, OffsetJ=0))
        axes.append(dict(UniqueName=uid, Angle=0))
    return build_strict_column_topology(
        point_rows=points, column_rows=columns, beam_rows=beams,
        section_assignment_rows=assignments, end_offset_rows=offsets,
        local_axis_rows=axes, rectangular_section_rows=sections, reviewed_length_unit="m",
    )


def _basis():
    return ReviewedColumnDesignBasis(
        concrete_strengths=(ReviewedConcreteDesignStrength("C35", 23.3333333333, ("review:C35",)),),
        longitudinal_steel_strengths=(ReviewedLongitudinalSteelDesignStrength("B420C", 365.2173913043, ("review:B420C",)),),
        aggregate=ReviewedAggregateBasis(22.0, ("review:aggregate",)),
        basis_refs=("review:offline-vertical",),
        story_translation_tolerance=ReviewedStoryTranslationTolerance(0.01, "review:tolerance"),
        route_c_w_applicability=ReviewedActionFamilyApplicability(
            ApplicabilityState.PROVEN_NOT_APPLICABLE, ("review:wind-PNA",), ("source:wind-PNA",)),
        transverse_steel_strengths=(ReviewedTransverseSteelDesignStrength("B420C", 420.0, 365.2173913043, ("review:transverse",)),),
        high_ductility_applies=True, limited_ductility_applies=False,
        transverse_policy_refs=("review:high-ductility",),
    )


def _combos():
    return tuple(EtabsComboDefinitionEvidence(
        name=f"GQ{axis}", combo_type_code=0, combo_type="LINEAR_ADD",
        constituents=tuple(EtabsComboConstituentEvidence(i, 0, "LOAD_CASE", name, 1.0)
                           for i, name in enumerate(("G", "Q", axis))),
        nested_combos=(), raw_get_type_combo="0", raw_get_case_list=f"G,Q,{axis}",
    ) for axis in ("EX", "EY"))


def _policy(combos):
    return ExpectedConcreteDesignComboPolicy(
        policy_id="review:offline-combos", review_provenance_refs=("review:combos",),
        combos=tuple(ExpectedConcreteDesignCombo(
            "Strength", combo.name, ("review:combos",),
            ReviewedConcreteDesignComboDefinition(
                combo.name, "LINEAR_ADD", tuple(ReviewedConcreteDesignComboConstituent(
                    "LOAD_CASE", term.name, term.scale_factor, review_provenance_refs=("review:combos",),
                ) for term in combo.constituents), ("review:combos",),
            ),
        ) for combo in combos),
    )


def _axial_context():
    return ReviewedVs5ColumnAxialContext(
        ndm_binding=ReviewedColumnNdmLoadBinding(
            binding_id="review:offline-ndm", version="v1", final_combination_ids=("GQEX",),
            g_case_ids=("G",), q_case_ids=("Q",), s_case_ids=(),
            horizontal_e_case_ids=("EX",), vertical_e_case_ids=(),
            baseline_coefficients_by_combination={"GQEX": {"G": 1., "Q": 1., "EX": 1.}},
            required_fixed_coefficients_by_combination={"GQEX": {"G": 1., "EX": 1.}},
            allowed_final_step_types=(None, ""), review_refs=("review:offline-ndm",)),
        tbdy_7312_high_ductility_applies=True,
        ts498_reduction_state=Ts498ReductionPolicyState.NO_REDUCTION,
        q_target_coefficients={"Q": 1.}, s_target_coefficients={},
        linear_superposition_reviewed=True, compression_sign=-1,
        ndm_regulatory_authority_ids=("authority:TBDY2018:7.3.1.2",), ndm_review_refs=("review:ndm",),
        ts500_combination_ids=("GQEX", "GQEY"), ts500_gamma_mc=1.5, ts500_review_refs=("review:Nd",))


def _shear_contexts(module):
    eq = module._force_rows("EX")[0]
    total = {**eq, "OutputCase": "GQEX", "CaseType": "Combination", "StepType": None}
    eq_id, total_id = column_shear_source_identity(eq), column_shear_source_identity(total)
    bottom, top = (f"{C1}|GQEX|{end}|STATIC_LINEAR_EXACT|TS5006.3.10|M2=ORIGINAL|M3=ORIGINAL"
                   for end in ("I_END", "J_END"))
    return dict(
        reviewed_column_p7_context=p7.ReviewedColumnP7RuntimeContext(C1, tuple(
            p7.ReviewedColumnP7DirectionPlan(C1, axis, total_id, total_id, bottom, top, False,
                ReviewedDAmplifiedShearAuthority(C1, axis, AvailabilityState.RESOLVED, 500.,
                    "review:offline-D-amplified-candidate", ("review:offline-D",)), ("review:offline-P7",))
            for axis in ("V2", "V3")), ("review:offline-P7",)),
        reviewed_column_short_column_context=p7.ReviewedColumnShortColumnContext(
            C1, False, None, None, None, ("review:offline-not-short",)),
        reviewed_column_final_cage_context=ReviewedColumnFinalCageContext(
            C1, "C50x80", "10", 4, 4, 100., 150., 100., 800., 140., 180., 200.,
            False, None, ("review:offline-final-cage",)),
        reviewed_column_vc_context=ReviewedColumnVcRuntimeContext(C1,
            high_directions=tuple(ReviewedHighColumnVcDirectionPlan(
                C1, axis, bottom, bottom, eq_id, total_id, True, ("review:offline-Vc",))
                for axis in ("V2", "V3")), review_refs=("review:offline-Vc",)),
    )


def _install(monkeypatch):
    setup = population._install_two_column_harness(monkeypatch)
    counters, _ = population._install_real_b6_owner(monkeypatch, setup)
    lifecycle = population._install_lifecycle_counters(monkeypatch, setup)
    topology = _topology()
    monkeypatch.setattr(a5, "capture_etabs_strict_column_topology_from_session", lambda *a, **k:
                        population.EtabsStrictColumnTopologyEvidence(topology, ()))
    monkeypatch.setattr(a5, "build_public_a5_canonical_second_order_payload", second_order.build_public_a5_canonical_second_order_payload)
    monkeypatch.setattr(a5, "resolve_ts500_column_free_length", resolve_ts500_column_free_length)
    monkeypatch.setattr(a5, "build_assigned_rc_frame_bending_modifier_evidence", build_assigned_rc_frame_bending_modifier_evidence)
    monkeypatch.setattr(column, "ColumnTopologyEvidenceEnvelope", ColumnTopologyEvidenceEnvelope)
    monkeypatch.setattr(population.b6, "ColumnTopologyEvidenceEnvelope", ColumnTopologyEvidenceEnvelope)
    monkeypatch.setattr(column, "normalized_combo_definition_fingerprint", normalized_combo_definition_fingerprint)

    @dataclass(frozen=True)
    class Base(setup.module._BaseFact):
        present_length_unit: int = 6
        session_provenance_ref: str = "session-provenance:public-a5"

    facts = []
    beams = {b.beam_unique_name: b for c in topology.columns for b in (*c.beams_at_bottom, *c.beams_at_top)}
    originals = {f.frame_name: f for f in setup.frame_population.rows}
    for uid in ("1", "2", *beams):
        original = originals.get(uid, originals["1"])
        base = Base(**{**asdict(original.base_fact), "component_unique_name": uid,
                      "assigned_section_name": ("B50x80" if uid in beams else topology.column(uid).section),
                      "evidence_ref": f"frame-base-pre:{uid}", "capture_event_ref": f"frame-pre:{uid}"})
        unit_modifiers = FrameModifierVector.from_sequence((1.0,) * 8)
        prop = replace(original.property_modifiers, target_name=base.assigned_section_name, modifiers=unit_modifiers)
        obj = replace(original.object_modifiers, target_name=uid, modifiers=unit_modifiers)
        setup.harness.modifier_values[(prop.surface.value, prop.target_name)] = prop.modifiers
        setup.harness.modifier_values[(obj.surface.value, uid)] = obj.modifiers
        fact = NS(**vars(original))
        fact.frame_name, fact.base_fact = uid, base
        fact.property_modifiers, fact.object_modifiers = prop, obj
        fact.member_role = "BEAM" if uid in beams else "COLUMN"
        fact.releases = FrameReleaseFact(uid, (False,) * 6, (False,) * 6, (0.,) * 6, (0.,) * 6, 0)
        # Independent offline authority, never current native GetSectProps semantics.
        # Retain the fixture's physical values; A18 must consume each own binding.
        raw_mechanics = (0.4, 0.3, 0.3, 0.006, 0.008333333333333333,
                         0.021333333333333336, 1., 1., 1., 1., 1., 1., 0)
        mechanics = FrameSectionMechanicsFact(
            base.assigned_section_name, *raw_mechanics[:6], 0,
            raw_response=raw_mechanics, source_model_ref=base.source_model_ref,
            session_ref=base.session_provenance_ref, capture_ref=f"synthetic:mechanics:{uid}",
        )
        fact.section_mechanics = replace(mechanics, unit_provenance=tuple(
            synthetic_unit_binding(
                mechanics.source_call, mechanics.section_name, key, "L4", "m4",
                mechanics.raw_response_ref, model=mechanics.source_model_ref,
                session=mechanics.session_ref, capture=mechanics.capture_ref,
            ) for key in ("I22", "I33")
        ))
        fact.isotropic_material = IsotropicMaterialPropertiesFact("C35", 33000.0, 0.2, 1e-5, 13200.0, 0.0, 0)
        fact.source_refs = (f"factual-frame:{uid}", base.evidence_ref)
        if uid in beams:
            fact.beam_mechanics = NS(member_axis_vector=beams[uid].vector_from_joint_m,
                                    local_axis_explicit=True, local_axis_angle_degrees=0.0,
                                    source_refs=(f"beam-endpoints:{uid}",))
        facts.append(fact)
    frames = NS(expected_frame_names=tuple(f.frame_name for f in facts), rows=tuple(facts),
                out_of_slice_rows=(), source_refs=("factual:full-frame-population",))
    monkeypatch.setattr(a5, "capture_frame_eq713_factual_population", lambda *a, **k: frames)
    monkeypatch.setattr(population.continuity, "capture_frame_flexural_base_fact", lambda **k:
                        replace(next(f.base_fact for f in facts if f.frame_name == k["component_unique_name"]),
                                evidence_ref=f"frame-post:{k['component_unique_name']}",
                                capture_event_ref=f"frame-post-event:{k['component_unique_name']}"))

    combos = _combos()
    selected = ActualConcreteDesignComboSelectionPopulation(
        table_key="Concrete Frame Design Load Combination Data",
        source_api="DatabaseTables.GetTableForDisplayArray", field_keys=("ComboType", "ComboName"),
        capture_status=RuntimeCaptureStatus.FULL, row_count_reported=2,
        model_fingerprint=MODEL, evidence_epoch_id=EPOCH,
        session_provenance_ref="session-provenance:public-a5", selected_signature_name="offline:table",
        source_refs=setup.selected.source_refs,
        rows=tuple(ActualSelectedConcreteDesignComboRow(
            row_id=f"row:{c.name}", combo_type="Strength", combo_name=c.name,
            source_row_ref=f"selected-row:{c.name}") for c in combos))
    for mod, name in ((a5, "acquire_actual_concrete_design_combo_selection_from_session"),
                      (population.b6, "acquire_actual_concrete_design_combo_selection_from_context")):
        monkeypatch.setattr(mod, name, lambda *a, **k: selected)
    monkeypatch.setattr(a5, "capture_etabs_combo_definitions_from_session", lambda *a, **k: combos)
    setup.harness.runtime["run_flags"] = {name: False for name in ("G", "Q", "EX", "EY")}
    setup.harness.runtime["statuses"] = {name: 4 for name in ("G", "Q", "EX", "EY")}
    monkeypatch.setattr(a5, "get_defined_analysis_cases_from_session", lambda *a, **k:
        DefinedAnalysisCasePopulationFact(("G", "Q", "EX", "EY"), 0))
    monkeypatch.setattr(a5, "probe_eq713_response_population_capability", lambda *a, **k: ("FrameForce",))
    monkeypatch.setattr(a5, "qualify_eq713_horizontal_case_scope_from_session", lambda *a, **k:
        NS(cases=tuple(NS(case_name=n, case_type="LINEAR_STATIC", direction_vectors_xy=(v,),
                          source_refs=(f"factual:direction:{n}",)) for n, v in (("EX", (1.0, 0.0)), ("EY", (0.0, 1.0)))),
           case_names=("EX", "EY"), source_refs=("factual:horizontal-cases",), evidence_ref="factual:horizontal-cases"))

    def response(session, **k):
        return NS(**k, frame_results=tuple(NS(frame_name=f, case_name=n,
            rows=(NS(p=1., v2=1., v3=1., t=1., m2=1., m3=1.),), evidence_ref=f"response:{f}:{n}")
            for f in k["frame_names"] for n in k["case_names"]), area_results=(),
            source_refs=("factual:response", *k["case_scope_refs"]), evidence_ref="factual:response")
    monkeypatch.setattr(a5, "capture_eq713_response_population_from_session", response)

    def case_facts(session, names):
        types = {"G": (1, "DEAD"), "Q": (3, "LIVE"), "EX": (5, "QUAKE"), "EY": (5, "QUAKE")}
        return tuple(EtabsStaticLinearCaseEvidence(name, (EtabsStaticLinearLoadTermEvidence(
            0, "Load", name, 1.0, EtabsLoadPatternTypeEvidence(name, *types[name], "factual:GetLoadType")),),
            "factual:GetLoads") for name in names)
    for mod in (direction, second_order):
        monkeypatch.setattr(mod, "capture_etabs_static_linear_cases_from_session", case_facts)
    seismic = EtabsAutoSeismicDirectionEvidence(
        REQUIRED_DIRECTION_FIELDS, tuple(EtabsAutoSeismicDirectionRow(name,
            {key: key == flag for key in REQUIRED_DIRECTION_FIELDS[1:]}, {"Name": name})
            for name, flag in (("EX", "XDir"), ("EY", "YDir"))),
        RuntimeCaptureStatus.FULL, 0, 2, "offline:factual-table",
    )
    monkeypatch.setattr(direction, "capture_etabs_auto_seismic_direction_evidence_from_session", lambda *a, **k: seismic)
    monkeypatch.setattr(a5, "capture_etabs_auto_seismic_direction_evidence_from_session", lambda *a, **k: seismic)
    monkeypatch.setattr(second_order, "read_verified_unit_snapshot", lambda *a, **k:
                        NS(present_units_api="GetPresentUnits_2", present_length_unit=6, present_force_unit=4))
    for mod in (stability, displacements):
        monkeypatch.setattr(mod, "EtabsVerifiedSession", setup.module._FakeSession)

    def joint_fact(session, *, point_object, output_name, output_kind, **kwargs):
        delta = 0.00001 if point_object.endswith("TOP") else 0.0
        return JointDisplacementResultFact(point_object, output_name, output_kind, (
            JointDisplacementResultRow(point_object, point_object, output_name, CSI_LINEAR_ADD_SINGLE_VALUE_STEP_TYPE, 0.0,
                                      delta, delta, 0.0, 0.0, 0.0, 0.0),), 0)
    monkeypatch.setattr(displacements, "read_joint_displ_from_session", joint_fact)
    monkeypatch.setattr(stability, "capture_story_stability_combo_fact_from_session", lambda session, **k:
        EtabsStoryStabilityComboFact(output_name=k["output_name"], output_kind="combo", story=k["story"],
            global_direction=k["global_direction"], story_height_mm=3000.0, story_drift_rows=(),
            ts500_delta_d_mapping_status="NOT_USED_AS_TS500_DELTA_I", story_shear_n=100000.0,
            sum_column_axial_design_force_n=2000000.0, analysis_result_ref=k["analysis_result_ref"],
            execution_proof_ref=k["execution_proof_ref"], source_refs=("factual:story-force", "factual:column-axial")))

    # B6 returns the full factual model population, including the unresolved C2.
    factual = FactualColumnDesignResultPopulation(
        model_fingerprint=MODEL, evidence_epoch_id=EPOCH,
        expected_component_ids=(C1, C2), attempted_component_ids=(C1, C2), captured_component_ids=(C1, C2),
        reported_result_row_count=4,
        rows=tuple(FactualColumnDesignResultRow(
            source_row_id=f"B6:{c.unique_name}:{combo.name}", component_id=c.component_id,
            unique_name=c.unique_name, story=c.story, label=c.column_label,
            assigned_section=c.section, design_section=c.section, my_option=2,
            pmm_combo=combo.name, location_mm=Decimal("0"), pmm_area_mm2=Decimal("4000"),
            error_summary="", warning_summary="", model_fingerprint=MODEL, evidence_epoch_id=EPOCH,
            source_refs=(f"factual:B6:{c.unique_name}",),
        ) for c in topology.columns for combo in combos), source_refs=("factual:B6:full-population",),
    )
    monkeypatch.setattr(population.b6, "capture_concrete_column_design_results_from_context", lambda **k: factual)
    usages = tuple(MaterialUsageReference(f"column:{c.unique_name}", "Column", c.unique_name,
        c.story, c.column_label, c.section, "C35", 2, MaterialUsageStatus.RESOLVED_CONCRETE_USAGE,
        ({"table": "Frame Assignments", "UniqueName": c.unique_name},)) for c in topology.columns)
    material = UsedMaterialDefinition("material:C35", MODEL, "C35", 2, True, 35.0, 35.0,
        ConcreteStrengthFactStatus.RESOLVED, None, usages)
    monkeypatch.setattr(longitudinal, "build_used_rc_material_population_from_same_verified_session", lambda **k:
        NS(readiness=MaterialPopulationReadiness.COMPLETE, usages=usages, used_material_definitions=(material,)))
    monkeypatch.setattr(longitudinal, "capture_etabs_column_rebar_intent_from_session", lambda session, section, **k:
        EtabsColumnRebarIntentEvidence(section, "B420C", "B420C", 1, 1, 0.04, 0, 0, 0, "40", "10", 0.10,
                                      4, 4, True, "m", "factual:GetRebarColumn"))
    catalog = EtabsRebarCatalogEvidence(TABLE_REINFORCING_BAR_SIZES, ("Name", "Diameter"),
        tuple({"Name": str(d), "Diameter": d/1000} for d in (10, 40)), RuntimeCaptureStatus.FULL, 0, 2, "offline:table")
    monkeypatch.setattr(longitudinal, "capture_etabs_rebar_catalog_evidence_from_session", lambda *a, **k: catalog)
    monkeypatch.setattr(axial, "capture_etabs_load_pattern_catalog_from_session", lambda *a, **k:
        EtabsLoadPatternCatalogEvidence(tuple(EtabsLoadPatternTypeEvidence(n, code, kind, "factual:LoadType")
            for n, code, kind in (("G", 1, "DEAD"), ("Q", 3, "LIVE"), ("EX", 5, "QUAKE"), ("EY", 5, "QUAKE"))),
            "factual:LoadNames"))

    def combo_forces(session, *, case_name, expectation):
        # Factual combo response consistent with the three unit-factor terms.
        rows = tuple({**row, "CaseType": "Combination", "StepType": None,
                      **{key: 3 * row[key] for key in ("P", "M2", "M3")}}
                     for row in population._two_column_force_rows(setup.module, case_name))
        return population.ColumnForceResultPopulationFact(case_name=case_name, expectation_ref=expectation.evidence_ref,
            expected_unique_names=expectation.expected_unique_names, observed_unique_names=expectation.expected_unique_names,
            rows=rows)
    monkeypatch.setattr(axial, "capture_column_force_result_population_from_session", combo_forces)
    monkeypatch.setattr(p7, "TrustedLiveAcquisitionContext", setup.module._FakeContext)
    monkeypatch.setattr(p7, "read_verified_unit_snapshot", lambda *a, **k:
        NS(present_units_api="GetPresentUnits_2", present_force_unit=4, present_length_unit=6))
    return NS(setup=setup, counters=counters, lifecycle=lifecycle, topology=topology, combos=combos)


def test_public_mixed_vertical_uses_real_canonical_fnd2_and_longitudinal_owners(monkeypatch):
    harness = _install(monkeypatch)
    result = project.execute_project(population._two_column_request(),
        verified_session=harness.setup.module._FakeSession(),
        column_design_basis=_basis(), expected_combo_policy=_policy(harness.combos),
        reviewed_vs5_column_axial_context=_axial_context(), **_shear_contexts(harness.setup.module))
    ready, unresolved = result.columns
    assert ready.design_state is not None, (ready.status, ready.blockers)
    assert ready.a23_demand_states, ready.blockers
    assert ready.longitudinal_runtime is not None, ready.blockers
    assert ready.selected_rebar is not None, ready.blockers
    assert ready.longitudinal_runtime.rebar_catalog is not None
    assert ready.longitudinal_runtime.detailing.status == "FINAL_DETAILING_REQUIRED"
    assert ready.column_axial_vs5 is not None, ready.blockers
    assert ready.transverse_confinement is not None, ready.blockers
    assert ready.column_shear_p7 is not None, ready.blockers
    assert {axis for axis, _ in ready.transverse_confinement.shear_vr_by_direction_kn} == {"DIR2", "DIR3"}
    assert ready.final_transverse_cage.semantic_role == "USER_PROVIDED_REBAR"
    assert unresolved.status == "UNRESOLVED"
    assert unresolved.controlled_design_result is None
    assert unresolved.selected_rebar is None
    assert harness.counters == {"controlled_design": 1, "start_design": 1}
    assert all(c["count"] == 1 for c in harness.lifecycle)
    assert harness.setup.harness.runtime["run_calls"] == 1
    assert result.column_denominator.expected_component_ids == (C1, C2)
    assert result.column_denominator.silent_missing_count == 0
    assert result.column_denominator.duplicate_count == 0
    assert result.column_denominator.orphan_count == 0
    assert result.reconciliation.column_population_reconciled
    assert result.building_report_model is not None
    path = Path(__file__).resolve().parents[2] / "tools" / "run_column_r1_public_acceptance.py"
    spec = importlib.util.spec_from_file_location("offline_acceptance_export", path)
    export = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(export)
    assert export._is_ready(ready)
    assert not export._is_ready(unresolved)
    payload = json.loads(json.dumps(export._json(export._observations(result)), allow_nan=False))
    assert len(payload["columns"]) == 2
    assert payload["A38"] and payload["A39"] and payload["A40"]
