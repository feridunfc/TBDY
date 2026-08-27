from __future__ import annotations

import inspect
import subprocess
import sys

import pytest

from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    AnalysisBasisEligibilityEvidence,
    ColumnConcreteDesignEvidenceAuthorityError,
    build_actual_selected_combo_population,
    normalized_combo_definition_fingerprint,
    reconcile_concrete_design_combos,
)
from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.etabs.source_units import (
    EtabsForceUnit,
    EtabsLengthUnit,
    EtabsSourceUnitError,
    convert_force,
    convert_length,
    decode_csi_force_unit,
    decode_csi_length_unit,
)
from tbdy_engine.features.column_concrete_design_evidence import (
    ColumnDesignResultIdentity,
    ColumnDesignSectionEvidence,
    ColumnTopologyEvidenceEnvelope,
    ComponentBindingStatus,
    ExpectedConcreteDesignCombo,
    ExpectedConcreteDesignComboPolicy,
    bind_column_design_result_identity,
)
from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence, StrictColumnTopologyBundle
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.providers.etabs_combo_definition_provider import (
    EtabsComboConstituentEvidence,
    EtabsComboDefinitionEvidence,
)
from tbdy_engine.providers.etabs_concrete_design_combo_selection_probe import (
    EXPECTED_SELECTED_COMBO_FIELD_KEYS,
    TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
    build_actual_concrete_design_combo_selection_population,
)
from tbdy_engine.providers.etabs_display_table_fetcher import DisplayTableFetchResult
from tbdy_engine.providers.etabs_display_table_parser import ParsedDisplayTable


def test_unit_boundary_imports_without_regulatory_package():
    code = "import sys; import tbdy_engine.etabs.source_units; assert 'tbdy_engine.regulatory' not in sys.modules"
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_design_evidence_authority_imports_without_regulatory_package():
    code = (
        "import sys; "
        "import tbdy_engine.design.columns.column_concrete_design_evidence_authority; "
        "assert 'tbdy_engine.regulatory' not in sys.modules"
    )
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


def _definition(name="CMB1", case="LC1", factor=1.0, combo_type="LINEAR_ADD"):
    return EtabsComboDefinitionEvidence(
        name=name,
        combo_type_code=0 if combo_type == "LINEAR_ADD" else 1,
        combo_type=combo_type,
        constituents=(EtabsComboConstituentEvidence(0, 0, "LOAD_CASE", case, factor),),
        nested_combos=(),
        raw_get_type_combo="fixture",
        raw_get_case_list="fixture",
    )


def _policy(*identities):
    return ExpectedConcreteDesignComboPolicy(
        policy_id="policy:fixture",
        combos=tuple(
            ExpectedConcreteDesignCombo(
                design_combo_type,
                combo_name,
                (f"review:{design_combo_type}:{combo_name}",),
            )
            for design_combo_type, combo_name in identities
        ),
        review_provenance_refs=("review:approved",),
    )


def _selected_population(*identities):
    rows = tuple(
        {"ComboType": design_combo_type, "ComboName": combo_name}
        for design_combo_type, combo_name in identities
    )
    parsed = ParsedDisplayTable(
        actual_table_name=TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
        fetch_status="FETCHED",
        field_keys=EXPECTED_SELECTED_COMBO_FIELD_KEYS,
        rows=rows,
        row_count_reported=len(rows),
        return_code=0,
    )
    fetched = DisplayTableFetchResult(
        table_name=TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
        parsed=parsed,
        selected_signature={"signature_name": "sig_fixture"},
        selected_signature_reason="fixture",
        capture_status=RuntimeCaptureStatus.FULL,
    )
    return build_actual_concrete_design_combo_selection_population(
        fetched,
        model_fingerprint="model:1",
        evidence_epoch_id="e1",
        session_provenance_ref="session:fixture",
    )


def _actual(definitions, *identities, definition_model="model:1", definition_epoch="e1"):
    return build_actual_selected_combo_population(
        selected_population=_selected_population(*identities),
        definitions=definitions,
        definition_model_fingerprint=definition_model,
        definition_evidence_epoch_id=definition_epoch,
        definition_capture_refs=("combo-definitions:fixture",),
    )


def _basis(status="MATCH", identity=("Strength", "CMB1")):
    design_combo_type, combo_name = identity
    return AnalysisBasisEligibilityEvidence(
        status,
        f"analysis-basis:{design_combo_type}:{combo_name}",
        (f"analysis-basis-provenance:{design_combo_type}:{combo_name}",),
    )


def _reconcile(policy, actual, definitions, case_types=None, basis=None):
    return reconcile_concrete_design_combos(
        expected_policy=policy,
        actual_population=actual,
        current_definitions=definitions,
        current_definition_model_fingerprint="model:1",
        current_definition_evidence_epoch_id="e1",
        current_definition_capture_refs=("current-combo-definitions:fixture",),
        case_types={"LC1": "LinStatic", "LC2": "LinStatic"} if case_types is None else case_types,
        analysis_basis_by_combo={identity: _basis("MATCH", identity) for identity in actual.identities}
        if basis is None else basis,
    )


def test_A_expected_actual_exact_identity_definition_classifier_and_basis_match():
    definitions = (_definition(),)
    actual = _actual(definitions, ("Strength", "CMB1"))
    rec = _reconcile(_policy(("Strength", "CMB1")), actual, definitions)
    assert rec.closed
    assert rec.expected == (("Strength", "CMB1"),)
    assert rec.actual_selected == (("Strength", "CMB1"),)
    assert rec.matched == (("Strength", "CMB1"),)
    assert actual.combos[0].design_combo_type == "Strength"
    assert definitions[0].combo_type == "LINEAR_ADD"
    assert "analysis-basis:Strength:CMB1" in rec.source_refs


def test_B_missing_expected_is_reported_without_disappearance():
    definitions = (_definition("CMB1"),)
    actual = _actual(definitions, ("Strength", "CMB1"))
    rec = _reconcile(
        _policy(("Strength", "CMB1"), ("Strength", "CMB2")),
        actual,
        definitions,
    )
    assert rec.missing_expected == (("Strength", "CMB2"),)
    assert not rec.closed


def test_C_unexpected_actual_is_reported_without_disappearance():
    definitions = (_definition("CMB1"), _definition("CMB2", "LC2"))
    actual = _actual(definitions, ("Strength", "CMB1"), ("Strength", "CMB2"))
    rec = _reconcile(_policy(("Strength", "CMB1")), actual, definitions)
    assert rec.unexpected_selected == (("Strength", "CMB2"),)
    assert not rec.closed


def test_D_expected_strength_does_not_name_match_actual_service():
    definitions = (_definition(),)
    actual = _actual(definitions, ("Service", "CMB1"))
    rec = _reconcile(_policy(("Strength", "CMB1")), actual, definitions)
    assert rec.matched == ()
    assert rec.missing_expected == (("Strength", "CMB1"),)
    assert rec.unexpected_selected == (("Service", "CMB1"),)


def test_E_same_combo_name_across_design_types_is_preserved_end_to_end():
    definitions = (_definition(),)
    selected = _selected_population(("Strength", "CMB1"), ("Service", "CMB1"))
    actual = build_actual_selected_combo_population(
        selected_population=selected,
        definitions=definitions,
        definition_model_fingerprint="model:1",
        definition_evidence_epoch_id="e1",
        definition_capture_refs=("combo-definitions:fixture",),
    )
    policy = _policy(("Strength", "CMB1"), ("Service", "CMB1"))
    rec = _reconcile(policy, actual, definitions)
    assert actual.identities == (("Service", "CMB1"), ("Strength", "CMB1"))
    assert len({item.selected_row_id for item in actual.combos}) == 2
    assert all(item.source_row_ref in selected.source_refs for item in actual.combos)
    assert rec.matched == (("Service", "CMB1"), ("Strength", "CMB1"))
    assert rec.closed


@pytest.mark.parametrize(
    "changed",
    [
        _definition(case="LC2", factor=1.0),
        _definition(case="LC1", factor=1.1),
    ],
)
def test_F_G_same_selected_identity_changed_definition_is_mismatch(changed):
    captured = _definition(case="LC1", factor=1.0)
    assert normalized_combo_definition_fingerprint(captured) != normalized_combo_definition_fingerprint(changed)
    actual = _actual((captured,), ("Strength", "CMB1"))
    rec = _reconcile(_policy(("Strength", "CMB1")), actual, (changed,))
    assert rec.definition_mismatch == (("Strength", "CMB1"),)
    assert rec.matched == ()


def test_H_missing_or_unsupported_referenced_case_type_is_unsupported_definition():
    definition = _definition()
    actual = _actual((definition,), ("Strength", "CMB1"))
    policy = _policy(("Strength", "CMB1"))
    assert _reconcile(policy, actual, (definition,), case_types={}).unsupported_definition == (
        ("Strength", "CMB1"),
    )
    assert _reconcile(
        policy,
        actual,
        (definition,),
        case_types={"LC1": "Nonlinear"},
    ).unsupported_definition == (("Strength", "CMB1"),)


def test_I_missing_analysis_basis_is_blocked():
    definition = _definition()
    actual = _actual((definition,), ("Strength", "CMB1"))
    rec = _reconcile(_policy(("Strength", "CMB1")), actual, (definition,), basis={})
    assert rec.analysis_basis_blocked == (("Strength", "CMB1"),)
    assert rec.matched == ()


def test_J_reanalysis_required_analysis_basis_is_blocked():
    definition = _definition()
    identity = ("Strength", "CMB1")
    actual = _actual((definition,), identity)
    rec = _reconcile(
        _policy(identity),
        actual,
        (definition,),
        basis={identity: _basis("REANALYSIS_REQUIRED", identity)},
    )
    assert rec.analysis_basis_blocked == (identity,)
    assert rec.matched == ()


def test_K_reconciliation_is_deterministic_independent_of_input_order():
    definitions_a = (_definition("CMB2", "LC2", 0.3), _definition("CMB1", "LC1", 1.0))
    definitions_b = tuple(reversed(definitions_a))
    identities_a = (("Strength", "CMB2"), ("Strength", "CMB1"), ("Service", "CMB1"))
    identities_b = tuple(reversed(identities_a))
    rec1 = _reconcile(_policy(*identities_a), _actual(definitions_a, *identities_a), definitions_a)
    rec2 = _reconcile(_policy(*identities_b), _actual(definitions_b, *identities_b), definitions_b)
    assert rec1 == rec2


def test_L_pass1_typed_population_is_the_only_actual_selection_input():
    parameters = inspect.signature(build_actual_selected_combo_population).parameters
    assert "selected_population" in parameters
    assert "selected_combo_names" not in parameters
    assert "source_row_refs" not in parameters
    assert "source_proof" not in parameters


def test_definition_capture_epoch_join_is_fail_closed():
    definition = _definition()
    with pytest.raises(ColumnConcreteDesignEvidenceAuthorityError, match="model/evidence epoch"):
        _actual((definition,), ("Strength", "CMB1"), definition_epoch="e2")


def _topology():
    column = ColumnTopologyEvidence(
        unique_name="C-U1",
        column_label="C1",
        story="Story1",
        section="ANALYSIS_SEC",
        width_t2_m=0.4,
        depth_t3_m=0.5,
        object_length_m=3.0,
        coordinate_length_m=3.0,
        joint_bottom="P1",
        joint_top="P2",
        bottom_coord_m=(0.0, 0.0, 0.0),
        top_coord_m=(0.0, 0.0, 3.0),
        offset_bottom_m=0.0,
        offset_top_m=0.0,
        analysis_clear_length_candidate_m=3.0,
        local_axis_angle_deg=0.0,
        local_axis_explicit=True,
        beams_at_bottom=(),
        beams_at_top=(),
        connectivity_row={"UniqueName": "C-U1"},
        assignment_row={"UniqueName": "C-U1", "Section": "ANALYSIS_SEC"},
        end_offset_row={"UniqueName": "C-U1"},
        section_row={"Name": "ANALYSIS_SEC"},
        local_axis_row={"UniqueName": "C-U1"},
    )
    return StrictColumnTopologyBundle((column,), 2, 0, 0, 0, "m")


def test_preliminary_component_binder_contract_remains_unchanged_for_pass3():
    epoch = EvidenceEpoch("e1", "model:1", EvidenceEpochOrigin.FIXTURE_REPLAY)
    envelope = ColumnTopologyEvidenceEnvelope.bind(
        topology=_topology(), epoch=epoch, source_refs=("topology:fixture",)
    )
    section = ColumnDesignSectionEvidence(
        "C-U1",
        "DESIGN_SEC",
        "model:1",
        "e1",
        "DesignConcrete.GetDesignSection",
        "section:C-U1",
    )
    result = ColumnDesignResultIdentity(
        "C-U1", "Story1", "C1", "model:1", "e1", "DESIGN_SEC", ("result:C-U1",)
    )
    bound = bind_column_design_result_identity(result=result, topology=envelope, design_section=section)
    assert bound.status is ComponentBindingStatus.BOUND
    assert bound.assigned_section == "ANALYSIS_SEC"
    assert bound.design_section == "DESIGN_SEC"

    stale = ColumnDesignResultIdentity(
        "C-U1", "Story1", "C1", "model:1", "e2", "DESIGN_SEC", ("result:C-U1",)
    )
    assert bind_column_design_result_identity(
        result=stale, topology=envelope, design_section=section
    ).status is ComponentBindingStatus.BLOCKED_EVIDENCE_EPOCH
