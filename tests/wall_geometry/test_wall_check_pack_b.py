from __future__ import annotations

import inspect

import pytest

from tbdy_engine.assessment.wall import WallAssessment, assess_wall_results
from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.checks.wall_applicability import (
    Eq714SystemEvidence,
    ReviewedWallSystemContext,
    derive_ndm_n,
    derive_net_section_area_mm2,
    directional_eq714_quantities,
    resolve_special_branch_applicability,
)
from tbdy_engine.checks.wall_contract import (
    PACK_B_AFFECTED_CHECK_IDS,
    WALL_GEOM_SPECIAL_THICKNESS_GE_200,
    WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20,
    WALL_NET_SECTION_AXIAL_CAPACITY,
)
from tbdy_engine.checks.wall_pack_a_contract import (
    WALL_GEOM_BODY_THICKNESS_GE_250,
    WALL_GEOM_BODY_THICKNESS_GE_H16,
)
from tbdy_engine.checks.wall_pipeline import WallExecutionEvidence, run_wall_checks
from tbdy_engine.coverage.models import CoverageExecutionContextStatus, CoverageStatus
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.result_evidence import (
    PIER_FORCE_IDENTITY_FIELDS,
    PIER_FORCE_PAYLOAD_FIELDS,
    ResultRowEvidenceBundle,
    RuntimeCaptureStatus,
)
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.reporting.wall import serialize_wall_results


class _Bundle:
    def __init__(self):
        feature = lambda unit="", role="GEOMETRY": {
            "element_type": "wall",
            "unit": unit,
            "semantic_role": role,
            "source": {"table_key": None, "field_aliases": []},
            "evidence_fields": [],
        }
        self.data = {
            "check_catalog.yaml": {"checks": {}},
            "feature_catalog.yaml": {"features": {
                "wall_thickness_mm": feature("mm"),
                "wall_length_mm": feature("mm"),
                "story_height_mm": feature("mm"),
                "concrete_fck_mpa": feature("MPa", "DESIGN_BASIS"),
            }},
            "table_registry.yaml": {"tables": {}},
            "element_registry.yaml": {"element_types": {"wall": {}}},
            "high_ductility_check_scope.yaml": {"scope_items": []},
            "check_scope_alignment.yaml": {},
            "design_combo_matrix.yaml": {"design_mappings": []},
        }

    def catalog(self, name):
        return self.data[name]


def _fv(name, value, unit="", role="GEOMETRY"):
    ev = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table="pack_b_fixture",
        actual_table_name="pack_b_fixture",
        source_column=name,
        source_row={"name": name},
        raw_value=value,
        normalized_value=value,
        unit=unit,
        resolver="pack_b_fixture",
    )
    return FeatureValue(
        feature_name=name,
        value=value,
        unit=unit,
        semantic_role=role,
        status=FeatureValueStatus.RESOLVED,
        evidence=[ev],
    )


def _snapshot(component_id="W1"):
    features = {
        "wall_thickness_mm": _fv("wall_thickness_mm", 300.0, "mm"),
        "story_height_mm": _fv("story_height_mm", 3200.0, "mm"),
        "wall_body_classification": _fv(
            "wall_body_classification", "RECTANGULAR_BODY", role="GEOMETRY_CLASSIFICATION"
        ),
        "wall_is_basement": _fv("wall_is_basement", False, role="REGULATORY_LOCATION"),
        "concrete_fck_mpa": _fv("concrete_fck_mpa", 35.0, "MPa", "DESIGN_BASIS"),
    }
    return FeatureSnapshot(
        component_type="wall",
        component_id=component_id,
        identity={"story": "L1", "assigned_wall_property": "WALL-P1"},
        features=features,
    )


def _system(*, wall_only=True, c1=True, c2=True):
    return ReviewedWallSystemContext(
        system_id="SYS-1",
        wall_only_status=wall_only,
        eq714=None if wall_only is not True else Eq714SystemEvidence(
            condition_1_satisfied=c1,
            condition_2_satisfied=c2,
            directional_evidence={"X": "reviewed", "Y": "reviewed"},
        ),
        evidence_refs=("reviewed-system-record",),
    )


def _execution(*, system=None, height=None, bundle=None, topology=None, pier="P1"):
    return WallExecutionEvidence(
        wall_system_context=system,
        highest_applicable_story_height_mm_by_component={} if height is None else {"W1": height},
        result_bundles={} if bundle is None else {"pier_forces": bundle},
        wall_to_pier={} if pier is None else {"W1": pier},
        net_section_topology_by_component={} if topology is None else {"W1": topology},
    )


def _pier_bundle(*, capture=RuntimeCaptureStatus.FULL, reported=1, force_unit="N"):
    row = {field: 0 for field in PIER_FORCE_IDENTITY_FIELDS + PIER_FORCE_PAYLOAD_FIELDS}
    row.update({
        "Story": "L1",
        "Pier": "P1",
        "OutputCase": "EQX",
        "CaseType": "Combo",
        "StepType": "Max",
        "StepNumber": 1,
        "Location": "Bottom",
        "P": 100000.0,
    })
    return ResultRowEvidenceBundle(
        table_key="pier_forces",
        actual_table_name="Pier Forces",
        identity_fields=PIER_FORCE_IDENTITY_FIELDS,
        payload_fields=PIER_FORCE_PAYLOAD_FIELDS,
        rows=(row,),
        source_contract_status="VERIFIED_LIVE",
        units={"force_unit": force_unit},
        runtime_capture_status=capture,
        reported_row_count=reported,
    )


def test_pack_b_exact_five_affected_paths():
    assert PACK_B_AFFECTED_CHECK_IDS == (
        WALL_GEOM_BODY_THICKNESS_GE_H16,
        WALL_GEOM_BODY_THICKNESS_GE_250,
        WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20,
        WALL_GEOM_SPECIAL_THICKNESS_GE_200,
        WALL_NET_SECTION_AXIAL_CAPACITY,
    )


def test_engine_run_input_has_no_execution_side_channel():
    signature = inspect.signature(MinimalCheckEngine.run_input)
    assert tuple(signature.parameters) == ("self", "check_input")
    source = inspect.getsource(MinimalCheckEngine)
    assert "engineering_context" not in source


def test_missing_mandatory_execution_context_blocks_coverage_before_engine_execution():
    run = run_wall_checks(_Bundle(), [_snapshot()], [WALL_GEOM_BODY_THICKNESS_GE_H16])
    assert run.coverage_rows[0].coverage_status == CoverageStatus.BLOCKED
    readiness = {item.context_name: item for item in run.coverage_rows[0].execution_context_readiness}
    assert readiness["wall_system_context"].status == CoverageExecutionContextStatus.BLOCKED
    assert run.check_results[0].status == CheckStatus.BLOCKED


def test_general_branch_executes_when_special_is_proven_false_by_false_plus_unknown():
    system = _system(wall_only=True, c1=False, c2=None)
    special, reason = resolve_special_branch_applicability(system)
    assert special is False
    assert reason is None
    run = run_wall_checks(
        _Bundle(),
        [_snapshot()],
        [WALL_GEOM_BODY_THICKNESS_GE_H16, WALL_GEOM_BODY_THICKNESS_GE_250],
        execution_evidence=_execution(system=system),
    )
    assert all(row.coverage_status == CoverageStatus.RUNNABLE for row in run.coverage_rows)
    results = {result.check_id: result for result in run.check_results}
    assert results[WALL_GEOM_BODY_THICKNESS_GE_H16].status == CheckStatus.OK
    assert results[WALL_GEOM_BODY_THICKNESS_GE_H16].limit == pytest.approx(200.0)
    assert results[WALL_GEOM_BODY_THICKNESS_GE_250].status == CheckStatus.OK


def test_special_branch_requires_both_conditions_true_and_general_becomes_out_of_scope():
    system = _system(wall_only=True, c1=True, c2=True)
    run = run_wall_checks(
        _Bundle(),
        [_snapshot()],
        [WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20, WALL_GEOM_SPECIAL_THICKNESS_GE_200],
        execution_evidence=_execution(system=system, height=5000.0),
    )
    results = {result.check_id: result for result in run.check_results}
    assert results[WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20].status == CheckStatus.OK
    assert results[WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20].limit == pytest.approx(250.0)
    assert results[WALL_GEOM_SPECIAL_THICKNESS_GE_200].status == CheckStatus.OK
    general = run_wall_checks(
        _Bundle(), [_snapshot()], [WALL_GEOM_BODY_THICKNESS_GE_250],
        execution_evidence=_execution(system=system),
    )
    assert general.check_results[0].status == CheckStatus.OUT_OF_SCOPE


def test_unknown_system_applicability_is_blocked_not_defaulted():
    system = _system(wall_only=True, c1=None, c2=True)
    special, reason = resolve_special_branch_applicability(system)
    assert special is None
    assert "UNKNOWN" in str(reason)
    run = run_wall_checks(
        _Bundle(), [_snapshot()], [WALL_GEOM_BODY_THICKNESS_GE_250, WALL_GEOM_SPECIAL_THICKNESS_GE_200],
        execution_evidence=_execution(system=system),
    )
    assert all(row.coverage_status == CoverageStatus.BLOCKED for row in run.coverage_rows)
    assert all(result.status == CheckStatus.BLOCKED for result in run.check_results)


def test_structural_system_context_is_one_run_level_authority_not_per_wall_proof():
    system = _system(wall_only=True, c1=False, c2=None)
    snapshots = [_snapshot("W1"), _snapshot("W2")]
    execution = WallExecutionEvidence(wall_system_context=system)
    run = run_wall_checks(
        _Bundle(), snapshots, [WALL_GEOM_BODY_THICKNESS_GE_250], execution_evidence=execution
    )
    assert {item.component for item in run.check_results} == {"W1", "W2"}
    contexts = [item.execution_context.values["wall_system_context"] for item in run.check_inputs]
    assert all(context.system_id == "SYS-1" for context in contexts)
    assert not isinstance(execution.wall_system_context, dict)


def test_directional_sum_ag_and_all_floor_sum_ap_are_not_collapsed():
    q = directional_eq714_quantities(
        gross_wall_areas_mm2_by_axis={"X": [100.0, 50.0], "Y": [300.0]},
        floor_plan_areas_mm2_by_story={"L1": 1000.0, "L2": 2000.0},
    )
    assert q["sum_ag_x_mm2"] == 150.0
    assert q["sum_ag_y_mm2"] == 300.0
    assert q["sum_ap_all_floors_mm2"] == 3000.0
    assert q["sum_ag_x_over_sum_ap"] == pytest.approx(0.05)
    assert q["sum_ag_y_over_sum_ap"] == pytest.approx(0.10)


def test_ndm_policy_shaped_mapping_cannot_unlock_ndm():
    fake_policy = {
        "eligible_output_cases": ["EQX"],
        "earthquake_direction": "X",
        "envelope_rule": "MAX_COMPRESSION",
        "compression_sign": "POSITIVE",
        "governing_location": "Bottom",
        "response_spectrum_handling": "EXPLICIT_SIGNED_COMBINATION",
    }
    q = derive_ndm_n(
        component_id="W1",
        pier_name="P1",
        pier_forces=_pier_bundle(),
        selection_policy=fake_policy,
    )
    assert q.status == "BLOCKED"
    assert "not implemented" in str(q.diagnostic)


def test_result_derived_ndm_requires_runtime_full_capture():
    truncated = _pier_bundle(capture=RuntimeCaptureStatus.TRUNCATED, reported=2)
    assert truncated.is_full_capture is False
    q = derive_ndm_n(component_id="W1", pier_name="P1", pier_forces=truncated)
    assert q.status == "BLOCKED"
    assert "runtime FULL" in str(q.diagnostic)
    with pytest.raises(ValueError, match="runtime FULL"):
        truncated.require_full_capture()


def test_axial_formal_path_exists_but_coverage_is_blocked_by_missing_ndm_authority():
    topology = {
        "topology_verified": True,
        "section_semantics_verified": True,
        "gross_cross_section_area_mm2": 300000.0,
        "openings": [],
    }
    run = run_wall_checks(
        _Bundle(), [_snapshot()], [WALL_NET_SECTION_AXIAL_CAPACITY],
        execution_evidence=_execution(bundle=_pier_bundle(), topology=topology),
    )
    row = run.coverage_rows[0]
    readiness = {item.context_name: item for item in row.execution_context_readiness}
    assert readiness["pier_forces_result_bundle"].status == CoverageExecutionContextStatus.READY
    assert readiness["ndm_policy_authority"].status == CoverageExecutionContextStatus.BLOCKED
    assert row.coverage_status == CoverageStatus.BLOCKED
    assert run.check_results[0].status == CheckStatus.BLOCKED
    assert "Authoritative Ndm policy is not implemented" in run.check_results[0].messages[0]


def test_net_ac_rejects_shell_surface_area_and_does_not_subtract_unrelated_nulls():
    blocked = derive_net_section_area_mm2("W1", {"shell_surface_area": 999999.0})
    assert blocked.status == "BLOCKED"
    resolved = derive_net_section_area_mm2("W1", {
        "topology_verified": True,
        "section_semantics_verified": True,
        "gross_cross_section_area_mm2": 300000.0,
        "openings": [
            {
                "parent_wall_id": "OTHER",
                "opening_cross_section_area_mm2": 200000.0,
                "topology_verified": True,
                "section_semantics": "NET_SECTION_OPENING",
                "is_null_area": True,
            },
            {
                "parent_wall_id": "W1",
                "opening_cross_section_area_mm2": 10000.0,
                "topology_verified": True,
                "section_semantics": "NET_SECTION_OPENING",
            },
        ],
    })
    assert resolved.status == "RESOLVED"
    assert resolved.value == pytest.approx(290000.0)


def test_wall_assessment_reconciles_missing_and_duplicate_component_check_matrix():
    system = _system(wall_only=True, c1=False, c2=None)
    run = run_wall_checks(
        _Bundle(), [_snapshot("W1"), _snapshot("W2")],
        [WALL_GEOM_BODY_THICKNESS_GE_H16, WALL_GEOM_BODY_THICKNESS_GE_250],
        execution_evidence=WallExecutionEvidence(wall_system_context=system),
    )
    assert run.assessment.expected_result_count == 4
    assert run.assessment.actual_result_count == 4
    assert run.assessment.missing_result_count == 0
    assert run.assessment.duplicate_result_count == 0
    assert run.assessment.coverage_complete is True

    missing = assess_wall_results(
        run.check_results[:-1],
        check_ids=[WALL_GEOM_BODY_THICKNESS_GE_H16, WALL_GEOM_BODY_THICKNESS_GE_250],
        component_ids=["W1", "W2"],
    )
    assert missing.expected_result_count == 4
    assert missing.actual_result_count == 3
    assert missing.missing_result_count == 1
    assert missing.duplicate_result_count == 0
    assert missing.coverage_complete is False

    duplicate = assess_wall_results(
        (*run.check_results, run.check_results[0]),
        check_ids=[WALL_GEOM_BODY_THICKNESS_GE_H16, WALL_GEOM_BODY_THICKNESS_GE_250],
        component_ids=["W1", "W2"],
    )
    assert duplicate.actual_result_count == 5
    assert duplicate.duplicate_result_count == 1
    assert duplicate.coverage_complete is False


def test_out_of_scope_is_valid_evaluated_applicability_outcome():
    system = _system(wall_only=True, c1=True, c2=True)
    run = run_wall_checks(
        _Bundle(), [_snapshot()], [WALL_GEOM_BODY_THICKNESS_GE_250],
        execution_evidence=_execution(system=system),
    )
    assert run.check_results[0].status == CheckStatus.OUT_OF_SCOPE
    assert run.assessment.coverage_complete is True
    assert run.assessment.evaluated_results == 1


def test_assessment_and_reporter_remain_formula_free_and_full_compliance_not_evaluated():
    assert "0.35" not in inspect.getsource(assess_wall_results)
    assert "/ 20" not in inspect.getsource(assess_wall_results)
    assert "0.35" not in inspect.getsource(serialize_wall_results)
    system = _system(wall_only=True, c1=True, c2=True)
    run = run_wall_checks(
        _Bundle(), [_snapshot()], [WALL_GEOM_SPECIAL_THICKNESS_GE_200],
        execution_evidence=_execution(system=system),
    )
    assessment = run.assessment
    assert isinstance(assessment, WallAssessment)
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"
    payload = serialize_wall_results(run.check_results, assessment, report_contract="P2_10_WALL_CHECK_PACK_B")
    assert payload["results"][0]["limit"] == 200.0
    assert payload["assessment"]["full_tbdy_compliance_status"] == "NOT_EVALUATED"
