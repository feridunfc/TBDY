from dataclasses import replace
import inspect

import pytest

import tbdy_engine.design.columns.column_combo_eligibility_projection as projection_module
from tbdy_engine.design.columns.column_combo_eligibility_projection import (
    BLOCKER_AMBIGUOUS_NAME,
    BLOCKER_ANALYSIS_BASIS_NOT_MATCH,
    BLOCKER_COMPONENT_ANALYSIS_BASIS,
    BLOCKER_COMPONENT_NOT_READY,
    BLOCKER_DEMAND_RESULT_NOT_PROVEN,
    BLOCKER_MISSING_ANALYSIS_BASIS,
    BLOCKER_MISSING_DEMAND_RESULT,
    BLOCKER_RS_RECONSTRUCTION,
    ColumnComboEligibilityProjectionError,
    ColumnComboEligibilityState,
    ComboAnalysisBasisBinding,
    ComponentReadinessBinding,
    project_column_combo_eligibility,
)
from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    AnalysisBasisEligibilityEvidence,
    ConcreteDesignComboReconciliation,
)
from tbdy_engine.design.columns.column_design_demand_engine import ColumnComboDefinition
from tbdy_engine.design.columns.column_design_readiness import resolve_column_design_demand_readiness
from tbdy_engine.design.columns.combo_pattern_engine import ComboPatternConstituent
from tbdy_engine.design.columns.design_demand_states import (
    DESIGN_AUTHORITY_RESPONSE_SPECTRUM,
    DESIGN_AUTHORITY_STATIC,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessAxisBasis,
    ColumnSlendernessBasis,
    SWAY_PREVENTED,
)

COMP = "+0.00:C2:236"
MODEL = "model:1"
EPOCH = "e1"


def _state(case, end, station, n, m2, m3, *, case_type="LinStatic"):
    return ColumnDemandState(
        state_id=f"{case}:{end}",
        component_id=COMP,
        output_case=case,
        case_type=case_type,
        step_type=None,
        step_number=None,
        station_m=station,
        end_tag=end,
        nd_compression_n=n,
        m2_nmm=m2,
        m3_nmm=m3,
        source_identity=f"src:{case}:{end}",
    )


def _combo(name="ULS", case="G"):
    return (
        ColumnComboDefinition(
            name=name,
            combo_type="LINEAR_ADD",
            constituents=(ComboPatternConstituent(case, 1.0),),
        ),
    )


def _case_demands(case="G", *, case_type="LinStatic"):
    return (
        _state(case, "I_END", 0.0, 1_000_000.0, -100_000_000.0, 80_000_000.0, case_type=case_type),
        _state(case, "J_END", 3.0, 900_000.0, 70_000_000.0, -60_000_000.0, case_type=case_type),
    )


def _axis_basis(axis, *, h=800.0, ln=3000.0, ratio=0.0):
    return ColumnSlendernessAxisBasis(
        axis=axis,
        section_dimension_mm=h,
        free_length_ln_mm=ln,
        effective_length_factor_k=1.0,
        sway_classification=SWAY_PREVENTED,
        moment_ratio_m1_over_m2=ratio,
        source_refs=(f"reviewed:{axis}",),
    )


def _basis(*, m2=None, m3=None):
    return ColumnSlendernessBasis(
        component_id=COMP,
        m2=m2 or _axis_basis("M2"),
        m3=m3 or _axis_basis("M3"),
        source_refs=("reviewed:slenderness-basis",),
    )


def _resolve(*, combo_name="ULS", case="G", case_type="LinStatic", basis=None):
    return resolve_column_design_demand_readiness(
        component_id=COMP,
        combo_definitions=_combo(combo_name, case),
        constituent_case_demands=_case_demands(case, case_type=case_type),
        width_mm=500.0,
        depth_mm=800.0,
        slenderness_basis=basis or _basis(),
    )


def _blocked_readiness():
    return _resolve(
        basis=_basis(
            m2=_axis_basis("M2", h=500.0, ln=6000.0, ratio=1.0),
            m3=_axis_basis("M3"),
        )
    )


def _reanalysis_readiness():
    return _resolve(
        basis=_basis(
            m2=_axis_basis("M2", h=500.0, ln=16000.0, ratio=0.0),
            m3=_axis_basis("M3"),
        )
    )


def _fingerprint(identity):
    return f"combo-definition:fixture:{identity[0]}:{identity[1]}"


def _reconciliation(*identities):
    ids = tuple(sorted(identities))
    fingerprints = tuple((design_type, combo_name, _fingerprint((design_type, combo_name))) for design_type, combo_name in ids)
    return ConcreteDesignComboReconciliation(
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        expected=ids,
        actual_selected=ids,
        matched=ids,
        missing_expected=(),
        unexpected_selected=(),
        definition_mismatch=(),
        actual_definition_drift=(),
        unsupported_definition=(),
        analysis_basis_blocked=(),
        reviewed_definition_fingerprints=fingerprints,
        actual_capture_definition_fingerprints=fingerprints,
        definition_fingerprints=fingerprints,
        source_refs=("reconciliation:fixture",),
    )


def _readiness_binding(readiness, *, model=MODEL, epoch=EPOCH):
    return ComponentReadinessBinding(
        readiness=readiness,
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        readiness_ref=f"fnd-col-2-readiness:{readiness.component_id}",
        provenance_refs=("fnd-col-2:fixture",),
    )


def _basis_binding(identity, *, status="MATCH", model=MODEL, epoch=EPOCH):
    return ComboAnalysisBasisBinding(
        design_combo_identity=identity,
        evidence=AnalysisBasisEligibilityEvidence(
            status_value=status,
            compatibility_ref=f"analysis-basis:{identity[0]}:{identity[1]}",
            provenance_refs=(f"analysis-basis-provenance:{identity[0]}:{identity[1]}",),
        ),
        normalized_definition_fingerprint=_fingerprint(identity),
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        provenance_refs=(f"combo-analysis-binding:{identity[0]}:{identity[1]}",),
    )


def test_ready_component_and_exact_static_combo_project_eligible():
    identity = ("Strength", "ULS")
    projection = project_column_combo_eligibility(
        readiness_binding=_readiness_binding(_resolve()),
        reconciliation=_reconciliation(identity),
        analysis_basis_bindings={identity: _basis_binding(identity)},
    )[0]

    assert projection.eligible
    assert projection.eligibility_state is ColumnComboEligibilityState.ELIGIBLE
    assert projection.component_id == COMP
    assert projection.design_combo_identity == identity
    assert projection.normalized_definition_fingerprint == _fingerprint(identity)
    assert projection.model_fingerprint == MODEL
    assert projection.evidence_epoch_id == EPOCH
    assert projection.component_readiness_status == "READY"
    assert projection.analysis_basis_status == "MATCH"
    assert projection.reconstruction_authority == DESIGN_AUTHORITY_STATIC
    assert projection.reconstruction_behavior_refs == ()
    assert [(item.name, item.scale_factor, item.cname_type, item.case_type) for item in projection.constituent_facts] == [
        ("G", "1", "LOAD_CASE", "LinStatic")
    ]
    assert projection.blockers == ()


def test_component_match_does_not_broadcast_when_full_readiness_is_blocked():
    identity = ("Strength", "ULS")
    projection = project_column_combo_eligibility(
        readiness_binding=_readiness_binding(_blocked_readiness()),
        reconciliation=_reconciliation(identity),
        analysis_basis_bindings={identity: _basis_binding(identity)},
    )[0]

    assert projection.eligibility_state is ColumnComboEligibilityState.BLOCKED_COMPONENT
    assert BLOCKER_COMPONENT_NOT_READY in projection.blockers
    assert projection.component_readiness_status == "BLOCKED"
    assert projection.analysis_basis_status == "MATCH"


def test_reanalysis_required_component_is_non_authorizing():
    identity = ("Strength", "ULS")
    projection = project_column_combo_eligibility(
        readiness_binding=_readiness_binding(_reanalysis_readiness()),
        reconciliation=_reconciliation(identity),
        analysis_basis_bindings={identity: _basis_binding(identity)},
    )[0]

    assert projection.eligibility_state is ColumnComboEligibilityState.BLOCKED_COMPONENT
    assert BLOCKER_COMPONENT_NOT_READY in projection.blockers
    assert BLOCKER_COMPONENT_ANALYSIS_BASIS in projection.blockers
    assert projection.component_readiness_status == "REANALYSIS_REQUIRED"


@pytest.mark.parametrize("basis_bindings,expected_blocker", [
    ({}, BLOCKER_MISSING_ANALYSIS_BASIS),
    (None, BLOCKER_ANALYSIS_BASIS_NOT_MATCH),
])
def test_missing_or_nonmatching_combo_basis_is_blocked(basis_bindings, expected_blocker):
    identity = ("Strength", "ULS")
    if basis_bindings is None:
        basis_bindings = {identity: _basis_binding(identity, status="REANALYSIS_REQUIRED")}
    projection = project_column_combo_eligibility(
        readiness_binding=_readiness_binding(_resolve()),
        reconciliation=_reconciliation(identity),
        analysis_basis_bindings=basis_bindings,
    )[0]
    assert projection.eligibility_state is ColumnComboEligibilityState.BLOCKED_ANALYSIS_BASIS
    assert expected_blocker in projection.blockers


def test_component_identity_inconsistency_fails_closed():
    readiness = replace(_resolve(), component_id="OTHER")
    with pytest.raises(ColumnComboEligibilityProjectionError, match="component_id differs"):
        _readiness_binding(readiness)


@pytest.mark.parametrize("model,epoch", [("model:other", EPOCH), (MODEL, "e2")])
def test_component_readiness_model_or_epoch_mismatch_fails_closed(model, epoch):
    identity = ("Strength", "ULS")
    with pytest.raises(ColumnComboEligibilityProjectionError, match="model fingerprint/EvidenceEpoch"):
        project_column_combo_eligibility(
            readiness_binding=_readiness_binding(_resolve(), model=model, epoch=epoch),
            reconciliation=_reconciliation(identity),
            analysis_basis_bindings={identity: _basis_binding(identity)},
        )


@pytest.mark.parametrize("model,epoch", [("model:other", EPOCH), (MODEL, "e2")])
def test_combo_basis_model_or_epoch_mismatch_fails_closed(model, epoch):
    identity = ("Strength", "ULS")
    with pytest.raises(ColumnComboEligibilityProjectionError, match="analysis-basis binding"):
        project_column_combo_eligibility(
            readiness_binding=_readiness_binding(_resolve()),
            reconciliation=_reconciliation(identity),
            analysis_basis_bindings={identity: _basis_binding(identity, model=model, epoch=epoch)},
        )


def test_missing_component_combo_demand_result_is_blocked():
    identity = ("Strength", "DIFFERENT")
    projection = project_column_combo_eligibility(
        readiness_binding=_readiness_binding(_resolve()),
        reconciliation=_reconciliation(identity),
        analysis_basis_bindings={identity: _basis_binding(identity)},
    )[0]
    assert projection.eligibility_state is ColumnComboEligibilityState.BLOCKED_COMBO
    assert BLOCKER_MISSING_DEMAND_RESULT in projection.blockers


def test_unproven_component_combo_result_is_blocked_even_if_component_wrapper_says_ready():
    readiness = _resolve()
    original = readiness.design_demands.combo_results[0]
    blocked_result = replace(original, status="BLOCKED_OBSERVED_ROW_VERIFICATION")
    blocked_demands = replace(readiness.design_demands, combo_results=(blocked_result,))
    inconsistent_ready = replace(readiness, design_demands=blocked_demands)
    identity = ("Strength", "ULS")

    projection = project_column_combo_eligibility(
        readiness_binding=_readiness_binding(inconsistent_ready),
        reconciliation=_reconciliation(identity),
        analysis_basis_bindings={identity: _basis_binding(identity)},
    )[0]
    assert projection.eligibility_state is ColumnComboEligibilityState.BLOCKED_COMBO
    assert BLOCKER_DEMAND_RESULT_NOT_PROVEN in projection.blockers


def test_response_spectrum_combo_requires_explicit_reconstruction_behavior_ref():
    readiness = _resolve(combo_name="ULS_RS", case="RS", case_type="LinRespSpec")
    original_result = readiness.design_demands.combo_results[0]
    assert original_result.build is not None
    assert original_result.build.authority == DESIGN_AUTHORITY_RESPONSE_SPECTRUM
    assert original_result.build.behavior_refs

    bad_build = replace(original_result.build, behavior_refs=())
    bad_result = replace(original_result, build=bad_build)
    bad_demands = replace(readiness.design_demands, combo_results=(bad_result,))
    bad_readiness = replace(readiness, design_demands=bad_demands)
    identity = ("Strength", "ULS_RS")

    projection = project_column_combo_eligibility(
        readiness_binding=_readiness_binding(bad_readiness),
        reconciliation=_reconciliation(identity),
        analysis_basis_bindings={identity: _basis_binding(identity)},
    )[0]
    assert projection.eligibility_state is ColumnComboEligibilityState.BLOCKED_COMBO
    assert BLOCKER_RS_RECONSTRUCTION in projection.blockers


def test_same_combo_name_under_multiple_design_types_is_explicitly_ambiguous():
    service = ("Service", "ULS")
    strength = ("Strength", "ULS")
    reconciliation = _reconciliation(service, strength)
    bindings = {
        strength: _basis_binding(strength),
        service: _basis_binding(service),
    }
    projections = project_column_combo_eligibility(
        readiness_binding=_readiness_binding(_resolve()),
        reconciliation=reconciliation,
        analysis_basis_bindings=bindings,
    )

    assert tuple(item.design_combo_identity for item in projections) == (service, strength)
    assert all(
        item.eligibility_state is ColumnComboEligibilityState.BLOCKED_AMBIGUOUS_DESIGN_COMBO_IDENTITY
        for item in projections
    )
    assert all(BLOCKER_AMBIGUOUS_NAME in item.blockers for item in projections)


def test_projection_is_deterministic_independent_of_basis_mapping_order():
    service = ("Service", "ULS")
    strength = ("Strength", "ULS")
    reconciliation = _reconciliation(service, strength)
    readiness_binding = _readiness_binding(_resolve())
    first = project_column_combo_eligibility(
        readiness_binding=readiness_binding,
        reconciliation=reconciliation,
        analysis_basis_bindings={
            service: _basis_binding(service),
            strength: _basis_binding(strength),
        },
    )
    second = project_column_combo_eligibility(
        readiness_binding=readiness_binding,
        reconciliation=reconciliation,
        analysis_basis_bindings={
            strength: _basis_binding(strength),
            service: _basis_binding(service),
        },
    )
    assert first == second
    assert tuple(item.projection_id for item in first) == tuple(item.projection_id for item in second)


def test_projection_module_contains_no_live_etabs_access_or_rebar_authority_emission():
    source = inspect.getsource(projection_module)
    assert "GetSummaryResultsColumn" not in source
    assert "ETABS_REQUIRED_REBAR" not in source
    assert "ENGINE_SELECTED_REBAR" not in source
