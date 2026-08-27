from __future__ import annotations

import subprocess
import sys

import pytest

from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    AnalysisBasisEligibilityEvidence,
    ColumnConcreteDesignEligibilityStatus,
    build_actual_selected_combo_population,
    build_column_concrete_design_evidence_authority,
    normalized_combo_definition_fingerprint,
    reconcile_concrete_design_combos,
)
from tbdy_engine.etabs.source_units import (
    EtabsForceUnit, EtabsLengthUnit, EtabsSourceUnitError,
    convert_force, convert_length, decode_csi_force_unit, decode_csi_length_unit,
)
from tbdy_engine.features.column_concrete_design_evidence import (
    ActualConcreteDesignComboPopulation, ActualConcreteDesignComboSourceProof,
    ActualDesignComboSourceStatus, ColumnConcreteDesignEvidenceError,
    ColumnDesignComponentBinding, ColumnDesignResultIdentity, ColumnDesignSectionEvidence,
    ColumnTopologyEvidenceEnvelope, ComponentBindingStatus,
    ExpectedConcreteDesignCombo, ExpectedConcreteDesignComboPolicy,
    bind_column_design_result_identity,
)
from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence, StrictColumnTopologyBundle
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.providers.etabs_combo_definition_provider import EtabsComboConstituentEvidence, EtabsComboDefinitionEvidence


def test_unit_boundary_imports_without_regulatory_package():
    code = "import sys; import tbdy_engine.etabs.source_units; assert 'tbdy_engine.regulatory' not in sys.modules"
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_design_evidence_authority_imports_without_regulatory_package():
    code = "import sys; import tbdy_engine.design.columns.column_concrete_design_evidence_authority; assert 'tbdy_engine.regulatory' not in sys.modules"
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_unit_decoder_is_explicit_exact_and_fail_closed():
    assert decode_csi_force_unit(3) is EtabsForceUnit.N
    assert decode_csi_force_unit(4) is EtabsForceUnit.KN
    assert decode_csi_length_unit(4) is EtabsLengthUnit.MM
    assert decode_csi_length_unit(6) is EtabsLengthUnit.M
    assert convert_force("1.25", source=EtabsForceUnit.KN, target=EtabsForceUnit.N) == 1250
    assert convert_length("2.5", source=EtabsLengthUnit.M, target=EtabsLengthUnit.MM) == 2500
    with pytest.raises(EtabsSourceUnitError):
        decode_csi_length_unit(999)


def _proof(status=ActualDesignComboSourceStatus.PROVEN_READ_ONLY_SELECTED_POPULATION):
    return ActualConcreteDesignComboSourceProof(
        status=status,
        source_api_or_table="DatabaseTables.GetTableForDisplayArray",
        exact_table_key="Concrete Frame Design Load Combination Data",
        exact_field_keys=("ComboName", "ComboType"),
        combo_name_field="ComboName",
        selection_semantics_ref="review:selected-population",
        automatic_user_defined_distinction="NOT_EXPOSED",
        present_units_before_ref="units:before",
        present_units_after_ref="units:after",
        mutation_audit_ref="mutation:none",
        provenance_refs=("live-probe:fixture",),
    )


def _definition(name="CMB1", case="LC1", factor=1.0, combo_type="LINEAR_ADD"):
    return EtabsComboDefinitionEvidence(
        name=name,
        combo_type_code=0 if combo_type == "LINEAR_ADD" else 1,
        combo_type=combo_type,
        constituents=(EtabsComboConstituentEvidence(0, 0, "LOAD_CASE", case, factor),),
        nested_combos=(), raw_get_type_combo="fixture", raw_get_case_list="fixture",
    )


def _policy(*names):
    return ExpectedConcreteDesignComboPolicy(
        policy_id="policy:fixture",
        combos=tuple(ExpectedConcreteDesignCombo(name, (f"review:{name}",)) for name in names),
        review_provenance_refs=("review:approved",),
    )


def _actual(definitions, *names):
    return build_actual_selected_combo_population(
        source_proof=_proof(), model_fingerprint="model:1", evidence_epoch_id="e1",
        selected_combo_names=names, definitions=definitions,
        source_row_refs={name: f"table-row:{name}" for name in names},
    )


def _binding(status=ComponentBindingStatus.BOUND):
    return ColumnDesignComponentBinding(
        status=status, component_id="Story1:C1:C-U1", unique_name="C-U1", story="Story1", label="C1",
        assigned_section="ANALYSIS_SEC", design_section="DESIGN_SEC",
        model_fingerprint="model:1", evidence_epoch_id="e1", source_refs=("component:fixture",),
        reasons=() if status is ComponentBindingStatus.BOUND else ("blocked",),
    )


def _basis(status="MATCH", name="CMB1"):
    return AnalysisBasisEligibilityEvidence(status, f"analysis-basis:{name}", (f"analysis-basis-provenance:{name}",))


def _reconcile(policy, actual, definitions, case_types=None, basis=None):
    return reconcile_concrete_design_combos(
        expected_policy=policy, actual_population=actual, current_definitions=definitions,
        case_types={"LC1": "LinStatic", "LC2": "LinStatic"} if case_types is None else case_types,
        analysis_basis_by_combo={name: _basis("MATCH", name) for name in actual.names} if basis is None else basis,
    )


def test_unproven_source_cannot_construct_actual_selected_population():
    with pytest.raises(ColumnConcreteDesignEvidenceError):
        ActualConcreteDesignComboPopulation(
            source_proof=_proof(ActualDesignComboSourceStatus.SOURCE_NOT_PROVEN),
            model_fingerprint="model:1", evidence_epoch_id="e1", combos=(),
        )


def test_correct_population_definition_and_basis_is_eligible():
    definitions = (_definition(),)
    rec = _reconcile(_policy("CMB1"), _actual(definitions, "CMB1"), definitions)
    assert rec.closed and rec.matched == ("CMB1",)
    assert "analysis-basis:CMB1" in rec.source_refs
    authority = build_column_concrete_design_evidence_authority(combo_reconciliation=rec, component_binding=_binding())
    assert authority.status is ColumnConcreteDesignEligibilityStatus.ELIGIBLE
    assert authority.governing_combo_eligibility("CMB1") is ColumnConcreteDesignEligibilityStatus.ELIGIBLE


def test_missing_expected_and_unexpected_selected_block_population():
    definitions = (_definition("CMB1"), _definition("CMB2", "LC2"))
    rec = _reconcile(_policy("CMB1", "CMB3"), _actual(definitions, "CMB1", "CMB2"), definitions)
    assert rec.missing_expected == ("CMB3",)
    assert rec.unexpected_selected == ("CMB2",)
    authority = build_column_concrete_design_evidence_authority(combo_reconciliation=rec, component_binding=_binding())
    assert authority.status is ColumnConcreteDesignEligibilityStatus.BLOCKED_COMBO_POPULATION


def test_same_name_changed_constituent_or_factor_changes_fingerprint_and_blocks():
    captured = _definition(case="LC1", factor=1.0)
    for changed in (_definition(case="LC2", factor=1.0), _definition(case="LC1", factor=1.1)):
        assert normalized_combo_definition_fingerprint(captured) != normalized_combo_definition_fingerprint(changed)
        rec = _reconcile(_policy("CMB1"), _actual((captured,), "CMB1"), (changed,))
        assert rec.definition_mismatch == ("CMB1",)
        assert rec.matched == ()


def test_missing_or_unsupported_referenced_case_blocks_definition():
    definition = _definition()
    actual = _actual((definition,), "CMB1")
    assert _reconcile(_policy("CMB1"), actual, (definition,), case_types={}).unsupported_definition == ("CMB1",)
    assert _reconcile(_policy("CMB1"), actual, (definition,), case_types={"LC1": "Nonlinear"}).unsupported_definition == ("CMB1",)


def test_analysis_basis_and_governing_combo_are_fail_closed():
    definition = _definition()
    actual = _actual((definition,), "CMB1")
    rec = _reconcile(_policy("CMB1"), actual, (definition,), basis={"CMB1": _basis("REANALYSIS_REQUIRED")})
    assert rec.analysis_basis_blocked == ("CMB1",)
    authority = build_column_concrete_design_evidence_authority(combo_reconciliation=rec, component_binding=_binding())
    assert authority.status is ColumnConcreteDesignEligibilityStatus.BLOCKED_ANALYSIS_BASIS
    missing_basis = _reconcile(_policy("CMB1"), actual, (definition,), basis={})
    assert missing_basis.analysis_basis_blocked == ("CMB1",)
    good = _reconcile(_policy("CMB1"), actual, (definition,))
    good_authority = build_column_concrete_design_evidence_authority(combo_reconciliation=good, component_binding=_binding())
    assert good_authority.governing_combo_eligibility("OTHER") is ColumnConcreteDesignEligibilityStatus.BLOCKED_COMBO_POPULATION


def _topology():
    column = ColumnTopologyEvidence(
        unique_name="C-U1", column_label="C1", story="Story1", section="ANALYSIS_SEC",
        width_t2_m=0.4, depth_t3_m=0.5, object_length_m=3.0, coordinate_length_m=3.0,
        joint_bottom="P1", joint_top="P2", bottom_coord_m=(0.0, 0.0, 0.0), top_coord_m=(0.0, 0.0, 3.0),
        offset_bottom_m=0.0, offset_top_m=0.0, analysis_clear_length_candidate_m=3.0,
        local_axis_angle_deg=0.0, local_axis_explicit=True, beams_at_bottom=(), beams_at_top=(),
        connectivity_row={"UniqueName": "C-U1"}, assignment_row={"UniqueName": "C-U1", "Section": "ANALYSIS_SEC"},
        end_offset_row={"UniqueName": "C-U1"}, section_row={"Name": "ANALYSIS_SEC"}, local_axis_row={"UniqueName": "C-U1"},
    )
    return StrictColumnTopologyBundle((column,), 2, 0, 0, 0, "m")


def test_component_section_model_and_epoch_binding_is_exact():
    epoch = EvidenceEpoch("e1", "model:1", EvidenceEpochOrigin.FIXTURE_REPLAY)
    envelope = ColumnTopologyEvidenceEnvelope.bind(topology=_topology(), epoch=epoch, source_refs=("topology:fixture",))
    section = ColumnDesignSectionEvidence("C-U1", "DESIGN_SEC", "model:1", "e1", "DesignConcrete.GetDesignSection", "section:C-U1")
    result = ColumnDesignResultIdentity("C-U1", "Story1", "C1", "model:1", "e1", "DESIGN_SEC", ("result:C-U1",))
    bound = bind_column_design_result_identity(result=result, topology=envelope, design_section=section)
    assert bound.status is ComponentBindingStatus.BOUND
    assert bound.assigned_section == "ANALYSIS_SEC" and bound.design_section == "DESIGN_SEC"

    stale = ColumnDesignResultIdentity("C-U1", "Story1", "C1", "model:1", "e2", "DESIGN_SEC", ("result:C-U1",))
    assert bind_column_design_result_identity(result=stale, topology=envelope, design_section=section).status is ComponentBindingStatus.BLOCKED_EVIDENCE_EPOCH
    missing = ColumnDesignResultIdentity("NOPE", "Story1", "C1", "model:1", "e1", "DESIGN_SEC", ("result:NOPE",))
    assert bind_column_design_result_identity(result=missing, topology=envelope, design_section=section).status is ComponentBindingStatus.BLOCKED_COMPONENT_IDENTITY
    wrong_section = ColumnDesignResultIdentity("C-U1", "Story1", "C1", "model:1", "e1", "OTHER", ("result:C-U1",))
    assert bind_column_design_result_identity(result=wrong_section, topology=envelope, design_section=section).status is ComponentBindingStatus.BLOCKED_SECTION_IDENTITY


def test_reconciliation_is_deterministic():
    definitions = (_definition("CMB2", "LC2", 0.3), _definition("CMB1", "LC1", 1.0))
    actual = _actual(definitions, "CMB2", "CMB1")
    rec1 = _reconcile(_policy("CMB1", "CMB2"), actual, definitions)
    rec2 = _reconcile(_policy("CMB2", "CMB1"), actual, tuple(reversed(definitions)))
    assert rec1 == rec2
