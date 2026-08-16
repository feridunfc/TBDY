from __future__ import annotations

import inspect

import pytest

from tbdy_engine.assessment.wall import WallAssessment, assess_wall_results
from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.checks.wall_applicability import (
    derive_ndm_n, derive_net_section_area_mm2, directional_eq714_quantities,
    resolve_special_branch_applicability,
)
from tbdy_engine.checks.wall_contract import (
    PACK_B_AFFECTED_CHECK_IDS, WALL_GEOM_SPECIAL_THICKNESS_GE_200,
    WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20, WALL_NET_SECTION_AXIAL_CAPACITY,
)
from tbdy_engine.checks.wall_pack_a_contract import WALL_GEOM_BODY_THICKNESS_GE_250, WALL_GEOM_BODY_THICKNESS_GE_H16
from tbdy_engine.checks.wall_pipeline import run_wall_checks
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.result_evidence import PIER_FORCE_IDENTITY_FIELDS, ResultRowEvidenceBundle
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.reporting.wall import serialize_wall_results


class _Bundle:
    def __init__(self):
        feature = lambda unit="", role="GEOMETRY": {
            "element_type": "wall", "unit": unit, "semantic_role": role,
            "source": {"table_key": None, "field_aliases": []}, "evidence_fields": [],
        }
        self.data = {
            "check_catalog.yaml": {"checks": {}},
            "feature_catalog.yaml": {"features": {
                "wall_thickness_mm": feature("mm"), "wall_length_mm": feature("mm"),
                "story_height_mm": feature("mm"), "concrete_fck_mpa": feature("MPa", "DESIGN_BASIS"),
            }},
            "table_registry.yaml": {"tables": {}},
            "element_registry.yaml": {"element_types": {"wall": {}}},
            "high_ductility_check_scope.yaml": {"scope_items": []},
            "check_scope_alignment.yaml": {}, "design_combo_matrix.yaml": {"design_mappings": []},
        }
    def catalog(self, name): return self.data[name]


def _fv(name, value, unit="", role="GEOMETRY"):
    ev = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL, source_table="pack_b_fixture",
        actual_table_name="pack_b_fixture", source_column=name, source_row={"name": name},
        raw_value=value, normalized_value=value, unit=unit, resolver="pack_b_fixture",
    )
    return FeatureValue(feature_name=name, value=value, unit=unit, semantic_role=role,
                        status=FeatureValueStatus.RESOLVED, evidence=[ev])


def _snapshot():
    features = {
        "wall_thickness_mm": _fv("wall_thickness_mm", 300.0, "mm"),
        "story_height_mm": _fv("story_height_mm", 3200.0, "mm"),
        "wall_body_classification": _fv("wall_body_classification", "RECTANGULAR_BODY", role="GEOMETRY_CLASSIFICATION"),
        "wall_is_basement": _fv("wall_is_basement", False, role="REGULATORY_LOCATION"),
        "wall_regulatory_structural_system_classification": _fv("wall_regulatory_structural_system_classification", "REVIEWED_WALL_SYSTEM", role="REGULATORY_CLASSIFICATION"),
        "concrete_fck_mpa": _fv("concrete_fck_mpa", 35.0, "MPa", "DESIGN_BASIS"),
    }
    return FeatureSnapshot(component_type="wall", component_id="W1", identity={"story": "L1", "assigned_wall_property": "WALL-P1"}, features=features)


def _special_proof(*, wall_only=True, condition_1=True, condition_2=True):
    return {"TBDY_7_6_1_3_proof": {"W1": {
        "wall_only_structural_system": wall_only,
        "eq714_condition_1_satisfied": condition_1,
        "eq714_condition_2_satisfied": condition_2,
    }}}


def test_pack_b_exact_five_affected_paths():
    assert PACK_B_AFFECTED_CHECK_IDS == (
        WALL_GEOM_BODY_THICKNESS_GE_H16, WALL_GEOM_BODY_THICKNESS_GE_250,
        WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20, WALL_GEOM_SPECIAL_THICKNESS_GE_200,
        WALL_NET_SECTION_AXIAL_CAPACITY,
    )


def test_unknown_applicability_blocks_general_and_special_without_default():
    run = run_wall_checks(_Bundle(), [_snapshot()], PACK_B_AFFECTED_CHECK_IDS)
    results = {r.check_id: r for r in run.check_results}
    assert results[WALL_GEOM_BODY_THICKNESS_GE_H16].status == CheckStatus.BLOCKED
    assert results[WALL_GEOM_BODY_THICKNESS_GE_250].status == CheckStatus.BLOCKED
    assert results[WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20].status == CheckStatus.BLOCKED
    assert results[WALL_GEOM_SPECIAL_THICKNESS_GE_200].status == CheckStatus.BLOCKED
    source = inspect.getsource(resolve_special_branch_applicability)
    assert "TBDY_7_6_1_3_applies" not in source
    assert '.get(component_id, False)' not in source
    assert 'or False' not in source


def test_wall_only_system_requires_both_eq714_condition_proofs():
    ctx = {"TBDY_7_6_1_3_proof": {"W1": {"wall_only_structural_system": True, "eq714_condition_1_satisfied": True}}}
    run = run_wall_checks(_Bundle(), [_snapshot()], [WALL_GEOM_BODY_THICKNESS_GE_250, WALL_GEOM_SPECIAL_THICKNESS_GE_200], engineering_context=ctx)
    assert all(result.status == CheckStatus.BLOCKED for result in run.check_results)


def test_general_branch_executes_only_when_special_proven_false():
    ctx = _special_proof(condition_1=True, condition_2=False)
    run = run_wall_checks(_Bundle(), [_snapshot()], [WALL_GEOM_BODY_THICKNESS_GE_H16, WALL_GEOM_BODY_THICKNESS_GE_250], engineering_context=ctx)
    results = {r.check_id: r for r in run.check_results}
    assert results[WALL_GEOM_BODY_THICKNESS_GE_H16].status == CheckStatus.OK
    assert results[WALL_GEOM_BODY_THICKNESS_GE_H16].limit == pytest.approx(200.0)
    assert results[WALL_GEOM_BODY_THICKNESS_GE_250].status == CheckStatus.OK
    assert results[WALL_GEOM_BODY_THICKNESS_GE_250].limit == pytest.approx(250.0)


def test_non_wall_only_system_proves_special_inapplicable_without_eq714_guessing():
    ctx = {"TBDY_7_6_1_3_proof": {"W1": {"wall_only_structural_system": False}}}
    run = run_wall_checks(_Bundle(), [_snapshot()], [WALL_GEOM_BODY_THICKNESS_GE_250, WALL_GEOM_SPECIAL_THICKNESS_GE_200], engineering_context=ctx)
    results = {r.check_id: r for r in run.check_results}
    assert results[WALL_GEOM_BODY_THICKNESS_GE_250].status == CheckStatus.OK
    assert results[WALL_GEOM_SPECIAL_THICKNESS_GE_200].status == CheckStatus.OUT_OF_SCOPE


def test_special_checks_execute_only_when_special_applies():
    ctx = {**_special_proof(), "highest_applicable_story_height_mm": {"W1": 5000.0}}
    run = run_wall_checks(_Bundle(), [_snapshot()], [WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20, WALL_GEOM_SPECIAL_THICKNESS_GE_200], engineering_context=ctx)
    results = {r.check_id: r for r in run.check_results}
    assert results[WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20].status == CheckStatus.OK
    assert results[WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20].limit == pytest.approx(250.0)
    assert results[WALL_GEOM_SPECIAL_THICKNESS_GE_200].status == CheckStatus.OK
    assert results[WALL_GEOM_SPECIAL_THICKNESS_GE_200].limit == pytest.approx(200.0)
    general = run_wall_checks(_Bundle(), [_snapshot()], [WALL_GEOM_BODY_THICKNESS_GE_250], engineering_context=ctx)
    assert general.check_results[0].status == CheckStatus.OUT_OF_SCOPE


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


def _pier_bundle(*, force_unit="N", axial=100000.0):
    row = {field: 0 for field in PIER_FORCE_IDENTITY_FIELDS}
    row.update({"Story": "L1", "Pier": "P1", "OutputCase": "EQX", "CaseType": "Combo", "StepType": "Max", "StepNumber": 1, "Location": "Bottom", "P": axial})
    return ResultRowEvidenceBundle(
        table_key="pier_forces", actual_table_name="Pier Forces", identity_fields=PIER_FORCE_IDENTITY_FIELDS,
        rows=(row,), source_contract_status="VERIFIED_LIVE", units={"force_unit": force_unit},
    )


def _ndm_policy():
    return {
        "eligible_output_cases": ["EQX"], "earthquake_direction": "X", "envelope_rule": "MAX_COMPRESSION",
        "compression_sign": "POSITIVE", "governing_location": "Bottom", "response_spectrum_handling": "EXPLICIT_SIGNED_COMBINATION",
    }


def test_ndm_cannot_select_merely_by_output_case_name():
    q = derive_ndm_n(component_id="W1", pier_name="P1", pier_forces=_pier_bundle(), selection_policy={"eligible_output_cases": ["EQX"]})
    assert q.status == "BLOCKED"
    assert "policy is incomplete" in str(q.diagnostic)


def test_ndm_normalizes_kn_to_n_only_from_explicit_source_unit():
    q = derive_ndm_n(component_id="W1", pier_name="P1", pier_forces=_pier_bundle(force_unit="kN", axial=100.0), selection_policy=_ndm_policy())
    assert q.status == "RESOLVED"
    assert q.value == pytest.approx(100000.0)
    blocked = derive_ndm_n(component_id="W1", pier_name="P1", pier_forces=_pier_bundle(force_unit="", axial=100.0), selection_policy=_ndm_policy())
    assert blocked.status == "BLOCKED"


def test_net_ac_rejects_shell_surface_area_and_does_not_subtract_unrelated_nulls():
    blocked = derive_net_section_area_mm2("W1", {"shell_surface_area": 999999.0})
    assert blocked.status == "BLOCKED"
    resolved = derive_net_section_area_mm2("W1", {
        "topology_verified": True, "section_semantics_verified": True,
        "gross_cross_section_area_mm2": 300000.0,
        "openings": [
            {"parent_wall_id": "OTHER", "opening_cross_section_area_mm2": 200000.0, "topology_verified": True, "section_semantics": "NET_SECTION_OPENING", "is_null_area": True},
            {"parent_wall_id": "W1", "opening_cross_section_area_mm2": 10000.0, "topology_verified": True, "section_semantics": "NET_SECTION_OPENING"},
        ],
    })
    assert resolved.status == "RESOLVED"
    assert resolved.value == pytest.approx(290000.0)


def test_axial_path_exists_but_blocks_when_authoritative_result_policy_missing():
    run = run_wall_checks(_Bundle(), [_snapshot()], [WALL_NET_SECTION_AXIAL_CAPACITY])
    assert run.check_results[0].status == CheckStatus.BLOCKED
    assert "Pier Forces" in run.check_results[0].messages[0]


def test_axial_formula_executes_only_with_complete_engineering_inputs():
    ctx = {
        "result_evidence": {"pier_forces": _pier_bundle()}, "wall_to_pier": {"W1": "P1"}, "ndm_result_policy": _ndm_policy(),
        "net_section_topology": {"W1": {"topology_verified": True, "section_semantics_verified": True, "gross_cross_section_area_mm2": 300000.0, "openings": []}},
    }
    run = run_wall_checks(_Bundle(), [_snapshot()], [WALL_NET_SECTION_AXIAL_CAPACITY], engineering_context=ctx)
    result = run.check_results[0]
    assert result.status == CheckStatus.OK
    assert result.limit == pytest.approx(100000.0 / (0.35 * 35.0))
    assert result.value == pytest.approx(300000.0)


def test_single_engine_assessment_and_reporter_authorities():
    assert "_evaluate_wall_pack_b" not in inspect.getsource(MinimalCheckEngine)
    assert "0.35" not in inspect.getsource(assess_wall_results)
    assert "/ 20" not in inspect.getsource(assess_wall_results)
    assert "0.35" not in inspect.getsource(serialize_wall_results)
    fake_run = run_wall_checks(_Bundle(), [_snapshot()], [WALL_GEOM_SPECIAL_THICKNESS_GE_200], engineering_context=_special_proof())
    assessment = fake_run.assessment
    assert isinstance(assessment, WallAssessment)
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"
    payload = serialize_wall_results(fake_run.check_results, assessment, report_contract="P2_10_WALL_CHECK_PACK_B")
    assert payload["results"][0]["limit"] == 200.0
    assert payload["assessment"]["full_tbdy_compliance_status"] == "NOT_EVALUATED"
