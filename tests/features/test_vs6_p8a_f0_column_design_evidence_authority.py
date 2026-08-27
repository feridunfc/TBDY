from __future__ import annotations

from decimal import Decimal
import inspect
import subprocess
import sys

import pytest

from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    AnalysisBasisEligibilityEvidence,
    ColumnConcreteDesignEvidenceAuthorityError,
    ColumnConcreteDesignEligibilityStatus,
    build_actual_selected_combo_population,
    build_column_concrete_design_evidence_authority,
    neutral_combo_definition,
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
    ColumnDesignComponentBinding,
    ColumnDesignResultIdentity,
    ColumnDesignSectionEvidence,
    ColumnTopologyEvidenceEnvelope,
    ComponentBindingStatus,
    ExpectedConcreteDesignCombo,
    ExpectedConcreteDesignComboPolicy,
    ReviewedComboConstituentKind,
    ReviewedConcreteDesignComboConstituent,
    ReviewedConcreteDesignComboDefinition,
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


def test_reviewed_policy_seam_imports_without_etabs_definition_provider():
    code = (
        "import sys; "
        "import tbdy_engine.features.column_concrete_design_evidence; "
        "assert 'tbdy_engine.providers.etabs_combo_definition_provider' not in sys.modules"
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
        combo_type_code={"LINEAR_ADD": 0, "ENVELOPE": 1, "ABSOLUTE_ADD": 2, "SRSS": 3, "RANGE_ADD": 4}[combo_type],
        combo_type=combo_type,
        constituents=(EtabsComboConstituentEvidence(0, 0, "LOAD_CASE", case, factor),),
        nested_combos=(),
        raw_get_type_combo="fixture",
        raw_get_case_list="fixture",
    )


def _multi_definition(name, terms, combo_type="LINEAR_ADD", nested=()):
    constituents = tuple(
        EtabsComboConstituentEvidence(
            index,
            0 if kind == "LOAD_CASE" else 1,
            kind,
            term_name,
            factor,
        )
        for index, (kind, term_name, factor) in enumerate(terms)
    )
    return EtabsComboDefinitionEvidence(
        name=name,
        combo_type_code={"LINEAR_ADD": 0, "ENVELOPE": 1, "ABSOLUTE_ADD": 2, "SRSS": 3, "RANGE_ADD": 4}[combo_type],
        combo_type=combo_type,
        constituents=constituents,
        nested_combos=tuple(nested),
        raw_get_type_combo="fixture",
        raw_get_case_list="fixture",
    )


def _reviewed_definition(name="CMB1", case="LC1", factor=1.0, response_combo_type="LINEAR_ADD"):
    return ReviewedConcreteDesignComboDefinition(
        combo_name=name,
        response_combo_type=response_combo_type,
        constituents=(
            ReviewedConcreteDesignComboConstituent(
                ReviewedComboConstituentKind.LOAD_CASE,
                case,
                factor,
                review_provenance_refs=(f"review:term:{name}:{case}",),
            ),
        ),
        review_provenance_refs=(f"review:math:{name}",),
    )


def _reviewed_multi(name, terms, response_combo_type="LINEAR_ADD"):
    constituents = []
    for kind, term_name, factor, nested in terms:
        constituents.append(
            ReviewedConcreteDesignComboConstituent(
                kind,
                term_name,
                factor,
                nested_definition=nested,
                review_provenance_refs=(f"review:term:{name}:{term_name}",),
            )
        )
    return ReviewedConcreteDesignComboDefinition(
        combo_name=name,
        response_combo_type=response_combo_type,
        constituents=tuple(constituents),
        review_provenance_refs=(f"review:math:{name}",),
    )


def _default_reviewed(combo_name: str):
    if combo_name == "CMB2":
        return _reviewed_definition("CMB2", "LC2", Decimal("0.3"))
    return _reviewed_definition(combo_name, "LC1", Decimal("1"))


def _policy(*identities, reviewed_by_identity=None):
    reviewed_by_identity = {} if reviewed_by_identity is None else dict(reviewed_by_identity)
    return ExpectedConcreteDesignComboPolicy(
        policy_id="policy:fixture",
        combos=tuple(
            ExpectedConcreteDesignCombo(
                design_combo_type=design_combo_type,
                combo_name=combo_name,
                provenance_refs=(f"review:{design_combo_type}:{combo_name}",),
                reviewed_definition=reviewed_by_identity.get(
                    (design_combo_type, combo_name), _default_reviewed(combo_name)
                ),
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
        case_types={"LC1": "LinStatic", "LC2": "LinStatic", "G": "LinStatic", "Q": "LinStatic"}
        if case_types is None else case_types,
        analysis_basis_by_combo={identity: _basis("MATCH", identity) for identity in actual.identities}
        if basis is None else basis,
    )


def _bound_component():
    return ColumnDesignComponentBinding(
        ComponentBindingStatus.BOUND,
        "column:1",
        "C-U1",
        "Story1",
        "C1",
        "ANALYSIS_SEC",
        "DESIGN_SEC",
        "model:1",
        "e1",
        ("component-binding:fixture",),
        (),
    )


# Existing PASS-2 regression surface -------------------------------------------------

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
    assert rec.actual_definition_drift == (("Strength", "CMB1"),)
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


# Correction-B mandatory proofs ------------------------------------------------------

def test_correction_b_A_stable_wrong_factor_is_reviewed_definition_mismatch_not_drift():
    identity = ("Strength", "CMB1")
    reviewed = _reviewed_multi(
        "CMB1",
        (
            (ReviewedComboConstituentKind.LOAD_CASE, "G", Decimal("1.0"), None),
            (ReviewedComboConstituentKind.LOAD_CASE, "Q", Decimal("1.0"), None),
        ),
    )
    wrong = _multi_definition(
        "CMB1",
        (("LOAD_CASE", "G", 0.9), ("LOAD_CASE", "Q", 1.0)),
    )
    actual = _actual((wrong,), identity)
    rec = _reconcile(_policy(identity, reviewed_by_identity={identity: reviewed}), actual, (wrong,))
    authority = build_column_concrete_design_evidence_authority(
        combo_reconciliation=rec,
        component_binding=_bound_component(),
    )
    assert rec.definition_mismatch == (identity,)
    assert rec.actual_definition_drift == ()
    assert rec.matched == ()
    assert not rec.closed
    assert authority.status is ColumnConcreteDesignEligibilityStatus.BLOCKED_COMBO_DEFINITION
    assert any("reviewed expected mathematical definition" in reason for reason in authority.reasons)
    assert not any("drifted" in reason for reason in authority.reasons)


def test_correction_b_B_stable_wrong_constituent_fails_reviewed_conformance():
    identity = ("Strength", "CMB1")
    reviewed = _reviewed_definition("CMB1", "LC1", Decimal("1"))
    wrong = _definition("CMB1", "LC2", 1.0)
    rec = _reconcile(
        _policy(identity, reviewed_by_identity={identity: reviewed}),
        _actual((wrong,), identity),
        (wrong,),
    )
    assert rec.definition_mismatch == (identity,)
    assert rec.actual_definition_drift == ()
    assert not rec.closed


def test_correction_b_C_stable_wrong_response_combo_type_fails_reviewed_conformance():
    identity = ("Strength", "CMB1")
    reviewed = _reviewed_definition("CMB1", "LC1", Decimal("1"), "LINEAR_ADD")
    wrong = _definition("CMB1", "LC1", 1.0, "ENVELOPE")
    rec = _reconcile(
        _policy(identity, reviewed_by_identity={identity: reviewed}),
        _actual((wrong,), identity),
        (wrong,),
    )
    assert rec.definition_mismatch == (identity,)
    assert rec.actual_definition_drift == ()
    assert rec.unsupported_definition == ()


def test_correction_b_D_exact_reviewed_definition_closes():
    identity = ("Strength", "CMB1")
    reviewed = _reviewed_definition("CMB1", "LC1", Decimal("1"))
    actual_definition = _definition("CMB1", "LC1", 1.0)
    rec = _reconcile(
        _policy(identity, reviewed_by_identity={identity: reviewed}),
        _actual((actual_definition,), identity),
        (actual_definition,),
    )
    assert rec.definition_mismatch == ()
    assert rec.actual_definition_drift == ()
    assert rec.matched == (identity,)
    assert rec.closed


def test_correction_b_E_actual_capture_drift_blocks_separately_from_reviewed_conformance():
    identity = ("Strength", "CMB1")
    accepted_capture = _definition("CMB1", "LC1", 1.0)
    current = _definition("CMB1", "LC1", 1.1)
    reviewed_current = _reviewed_definition("CMB1", "LC1", Decimal("1.1"))
    rec = _reconcile(
        _policy(identity, reviewed_by_identity={identity: reviewed_current}),
        _actual((accepted_capture,), identity),
        (current,),
    )
    authority = build_column_concrete_design_evidence_authority(
        combo_reconciliation=rec,
        component_binding=_bound_component(),
    )
    assert rec.definition_mismatch == ()
    assert rec.actual_definition_drift == (identity,)
    assert rec.matched == ()
    assert not rec.closed
    assert authority.status is ColumnConcreteDesignEligibilityStatus.BLOCKED_COMBO_DEFINITION
    assert any("drifted from the accepted actual capture" in reason for reason in authority.reasons)


def test_correction_b_F_reviewed_source_is_independent_and_contains_no_csi_codes():
    reviewed = _reviewed_definition("CMB1", "LC1", Decimal("1"))
    expected = ExpectedConcreteDesignCombo(
        "Strength",
        "CMB1",
        ("project-review:1",),
        reviewed,
    )
    assert expected.reviewed_definition is reviewed
    assert not hasattr(reviewed, "combo_type_code")
    assert not hasattr(reviewed.constituents[0], "cname_type_code")
    assert "project-review:1" in expected.provenance_refs


def test_correction_b_G_strength_service_same_name_remain_distinct_exact_identities():
    definition = _definition()
    identities = (("Strength", "CMB1"), ("Service", "CMB1"))
    rec = _reconcile(_policy(*identities), _actual((definition,), *identities), (definition,))
    assert rec.expected == (("Service", "CMB1"), ("Strength", "CMB1"))
    assert rec.matched == rec.expected
    assert rec.closed


def test_correction_b_H_reviewed_policy_input_order_is_deterministic():
    identities_a = (("Strength", "CMB2"), ("Service", "CMB1"), ("Strength", "CMB1"))
    identities_b = tuple(reversed(identities_a))
    defs_a = (_definition("CMB1"), _definition("CMB2", "LC2", 0.3))
    defs_b = tuple(reversed(defs_a))
    rec_a = _reconcile(_policy(*identities_a), _actual(defs_a, *identities_a), defs_a)
    rec_b = _reconcile(_policy(*identities_b), _actual(defs_b, *identities_b), defs_b)
    assert rec_a == rec_b


def test_correction_b_I_fresh_interpreter_expected_seam_is_provider_independent():
    code = (
        "import sys; "
        "from tbdy_engine.features.column_concrete_design_evidence import ExpectedConcreteDesignComboPolicy; "
        "assert 'tbdy_engine.providers.etabs_combo_definition_provider' not in sys.modules"
    )
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_correction_b_J_no_name_only_governing_authorization_surface():
    definition = _definition()
    identities = (("Strength", "CMB1"), ("Service", "CMB1"))
    rec = _reconcile(_policy(*identities), _actual((definition,), *identities), (definition,))
    assert all(isinstance(identity, tuple) and len(identity) == 2 for identity in rec.matched)
    parameters = inspect.signature(build_column_concrete_design_evidence_authority).parameters
    assert "combo_name" not in parameters
    assert "eligible_combo_names" not in dir(rec)


def _nested_pair(inner_factor):
    inner = _definition("NEST", "LC1", inner_factor)
    top = _multi_definition(
        "CMB1",
        (("LOAD_COMBO", "NEST", 1.0),),
        nested=(inner,),
    )
    return inner, top


def _nested_reviewed(inner_factor):
    nested = _reviewed_definition("NEST", "LC1", Decimal(str(inner_factor)))
    return _reviewed_multi(
        "CMB1",
        ((ReviewedComboConstituentKind.LOAD_COMBO, "NEST", Decimal("1"), nested),),
    )


def test_correction_b_K_nested_reviewed_vs_actual_definition_equality():
    identity = ("Strength", "CMB1")
    _, actual_top = _nested_pair(0.3)
    reviewed = _nested_reviewed("0.3")
    assert neutral_combo_definition(reviewed).payload() == neutral_combo_definition(actual_top).payload()
    assert normalized_combo_definition_fingerprint(reviewed) == normalized_combo_definition_fingerprint(actual_top)
    rec = _reconcile(
        _policy(identity, reviewed_by_identity={identity: reviewed}),
        _actual((actual_top,), identity),
        (actual_top,),
        case_types={"LC1": "LinStatic"},
    )
    assert rec.definition_mismatch == ()
    assert rec.actual_definition_drift == ()
    assert rec.unsupported_definition == (identity,)
    assert not rec.closed


def test_correction_b_L_nested_reviewed_vs_actual_mismatch():
    identity = ("Strength", "CMB1")
    _, actual_top = _nested_pair(0.4)
    reviewed = _nested_reviewed("0.3")
    rec = _reconcile(
        _policy(identity, reviewed_by_identity={identity: reviewed}),
        _actual((actual_top,), identity),
        (actual_top,),
        case_types={"LC1": "LinStatic"},
    )
    assert rec.definition_mismatch == (identity,)
    assert rec.actual_definition_drift == ()
    assert rec.unsupported_definition == ()


def test_correction_b_M_reviewed_decimal_point_three_equals_etabs_float_point_three():
    identity = ("Strength", "CMB1")
    reviewed = _reviewed_definition("CMB1", "LC1", Decimal("0.3"))
    actual_definition = _definition("CMB1", "LC1", 0.3)
    assert normalized_combo_definition_fingerprint(reviewed) == normalized_combo_definition_fingerprint(actual_definition)
    rec = _reconcile(
        _policy(identity, reviewed_by_identity={identity: reviewed}),
        _actual((actual_definition,), identity),
        (actual_definition,),
    )
    assert rec.definition_mismatch == ()
    assert rec.actual_definition_drift == ()
    assert rec.closed


def test_correction_b_N_real_factor_difference_remains_mismatch():
    identity = ("Strength", "CMB1")
    reviewed = _reviewed_definition("CMB1", "LC1", Decimal("0.3"))
    actual_definition = _definition("CMB1", "LC1", 0.30000000000000004)
    assert normalized_combo_definition_fingerprint(reviewed) != normalized_combo_definition_fingerprint(actual_definition)
    rec = _reconcile(
        _policy(identity, reviewed_by_identity={identity: reviewed}),
        _actual((actual_definition,), identity),
        (actual_definition,),
    )
    assert rec.definition_mismatch == (identity,)
    assert rec.actual_definition_drift == ()
    assert not rec.closed


# Existing component-binding PASS-3 boundary freeze ---------------------------------

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
