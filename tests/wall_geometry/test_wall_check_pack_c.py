from __future__ import annotations

import inspect

import pytest

from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.checks.wall_applicability import derive_wall_critical_height
from tbdy_engine.checks.wall_contract import (
    PACK_C_CHECK_IDS,
    WALL_END_REGIONS_REQUIRED_HW_LW_GT2,
    WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW,
    WALL_HCR_GE_HW_DIV6,
    WALL_HCR_GE_LW,
    WALL_HCR_LE_2LW,
)
from tbdy_engine.checks.wall_pipeline import WallExecutionEvidence, run_wall_checks
from tbdy_engine.coverage.models import CoverageStatus
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.features.wall_critical_evidence import (
    WallCriticalHeightFactualEvidence,
    WallEndRegionStoryEvidence,
    WallRegulatoryReferenceFacts,
    WallStoryGeometryEvidence,
)


class _Bundle:
    def __init__(self):
        feature = lambda unit="", role="GEOMETRY": {
            "element_type": "wall", "unit": unit, "semantic_role": role,
            "source": {"table_key": None, "field_aliases": []}, "evidence_fields": [],
        }
        self.data = {
            "check_catalog.yaml": {"checks": {}},
            "feature_catalog.yaml": {"features": {
                "wall_thickness_mm": feature("mm"),
                "wall_length_mm": feature("mm"),
                "story_height_mm": feature("mm"),
            }},
            "table_registry.yaml": {"tables": {}},
            "element_registry.yaml": {"element_types": {"wall": {}}},
            "high_ductility_check_scope.yaml": {"scope_items": []},
            "check_scope_alignment.yaml": {},
            "design_combo_matrix.yaml": {"design_mappings": []},
        }

    def catalog(self, name):
        return self.data[name]


def _fv(name: str, value: float, unit: str = "mm") -> FeatureValue:
    ev = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table="verified_pack_c_fixture",
        actual_table_name="verified_pack_c_fixture",
        source_column=name,
        source_row={"feature": name},
        raw_value=value,
        normalized_value=value,
        unit=unit,
        resolver="pack_c_fixture",
    )
    return FeatureValue(
        feature_name=name, value=value, unit=unit, semantic_role="GEOMETRY",
        status=FeatureValueStatus.RESOLVED, evidence=[ev],
    )


def _snapshot(component_id: str = "W1", *, lw: float = 3000.0, bw: float = 300.0) -> FeatureSnapshot:
    return FeatureSnapshot(
        component_type="wall",
        component_id=component_id,
        identity={"story": "L1", "assigned_wall_property": "OPAQUE-WALL-PROP"},
        features={
            "wall_length_mm": _fv("wall_length_mm", lw),
            "wall_thickness_mm": _fv("wall_thickness_mm", bw),
            "story_height_mm": _fv("story_height_mm", 3000.0),
        },
    )


def _facts(
    component_id: str = "W1",
    *,
    lengths=(3000.0, 3000.0, 3000.0, 3000.0),
    thicknesses=(300.0, 300.0, 300.0, 300.0),
    heights=(3000.0, 3000.0, 3000.0, 3000.0),
    continuity=True,
    reductions_complete=True,
    topology=True,
    end_length=700.0,
    end_exists=True,
    rigid_perimeter=False,
    rigid_diaphragm=None,
    foundation=0.0,
    ground=None,
    first_basement_height=None,
):
    base = 0.0
    geometry = []
    end_rows = []
    for index, (lw, bw, height) in enumerate(zip(lengths, thicknesses, heights), start=1):
        story = f"L{index}"
        geometry.append(WallStoryGeometryEvidence(
            story=story,
            base_elevation_mm=base,
            story_height_mm=height,
            wall_length_mm=lw,
            wall_thickness_mm=bw,
            source_refs=("Pier Section Properties", "Story Definitions"),
        ))
        end_rows.append(WallEndRegionStoryEvidence(
            story=story,
            left_exists=end_exists,
            right_exists=end_exists,
            left_plan_length_mm=end_length if end_exists else None,
            right_plan_length_mm=end_length if end_exists else None,
            source_refs=("reviewed end-region topology",),
        ))
        base += height
    return WallCriticalHeightFactualEvidence(
        component_id=component_id,
        story_geometry=tuple(geometry),
        vertical_continuity_proven=continuity,
        section_reduction_evidence_complete=reductions_complete,
        reference_facts=WallRegulatoryReferenceFacts(
            foundation_top_elevation_mm=foundation,
            ground_floor_elevation_mm=ground,
            rigid_basement_perimeter_walls=rigid_perimeter,
            rigid_basement_diaphragm=rigid_diaphragm,
            first_basement_story_height_mm=first_basement_height,
            source_refs=("Story Definitions", "reviewed basement facts"),
        ),
        end_region_geometry=tuple(end_rows),
        end_region_topology_proven=topology,
        source_refs=("VERIFIED_LIVE geometry", "reviewed topology proof"),
    )


def _run(facts, *, snapshots=None, check_ids=PACK_C_CHECK_IDS):
    snaps = snapshots or [_snapshot(facts.component_id)]
    return run_wall_checks(
        _Bundle(), snaps, check_ids,
        execution_evidence=WallExecutionEvidence(
            critical_height_facts_by_component={facts.component_id: facts}
        ),
    )


def test_pack_c_exact_five_ids_and_no_new_engine_boundary():
    assert PACK_C_CHECK_IDS == (
        WALL_END_REGIONS_REQUIRED_HW_LW_GT2,
        WALL_HCR_GE_LW,
        WALL_HCR_GE_HW_DIV6,
        WALL_HCR_LE_2LW,
        WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW,
    )
    assert tuple(inspect.signature(MinimalCheckEngine.run_input).parameters) == ("self", "check_input")
    assert "engineering_context" not in inspect.getsource(MinimalCheckEngine)


def test_complete_pack_c_bundle_produces_five_canonical_results_and_complete_assessment():
    run = _run(_facts())
    assert len(run.check_results) == 5
    assert {result.check_id for result in run.check_results} == set(PACK_C_CHECK_IDS)
    assert all(result.status == CheckStatus.OK for result in run.check_results)
    assert run.assessment.expected_result_count == 5
    assert run.assessment.actual_result_count == 5
    assert run.assessment.missing_result_count == 0
    assert run.assessment.duplicate_result_count == 0
    assert run.assessment.coverage_complete is True
    assert run.assessment.full_tbdy_compliance_status == "NOT_EVALUATED"


def test_hw_over_lw_is_strictly_greater_than_two_not_greater_or_equal():
    facts = _facts(lengths=(3000.0, 3000.0), thicknesses=(300.0, 300.0), heights=(3000.0, 3000.0))
    derivation = derive_wall_critical_height(facts)
    assert derivation.status == "RESOLVED"
    assert derivation.segments[0].hw_over_lw == pytest.approx(2.0)
    assert derivation.end_regions_required is False
    run = _run(facts)
    assert all(result.status == CheckStatus.OUT_OF_SCOPE for result in run.check_results)


def test_eq715_lower_bound_can_fail_when_hw_div6_exceeds_2lw_cap():
    facts = _facts(lengths=(3000.0,), thicknesses=(300.0,), heights=(45000.0,), end_length=700.0)
    run = _run(facts, check_ids=(WALL_HCR_GE_LW, WALL_HCR_GE_HW_DIV6, WALL_HCR_LE_2LW))
    results = {result.check_id: result for result in run.check_results}
    assert results[WALL_HCR_GE_LW].status == CheckStatus.OK
    assert results[WALL_HCR_GE_HW_DIV6].status == CheckStatus.FAIL
    assert results[WALL_HCR_LE_2LW].status == CheckStatus.OK
    assert results[WALL_HCR_GE_HW_DIV6].value == pytest.approx(6000.0)
    assert results[WALL_HCR_GE_HW_DIV6].limit == pytest.approx(7500.0)


def test_plan_length_reduction_is_strictly_more_than_20_percent_and_derived_not_raw():
    at_20 = derive_wall_critical_height(_facts(lengths=(4000.0, 3200.0, 3200.0, 3200.0)))
    assert len(at_20.segments) == 1
    over_20 = derive_wall_critical_height(_facts(lengths=(4000.0, 3199.0, 3199.0, 3199.0)))
    assert len(over_20.segments) == 2
    assert over_20.segments[1].reference_reason == "PLAN_LENGTH_REDUCTION_GT20"
    snapshot = _snapshot()
    forbidden = {"Hw", "Hcr", "wall_hw_mm", "wall_hcr_mm", "wall_hw_lw_gt2", "critical_region_membership"}
    assert forbidden.isdisjoint(snapshot.features)


def test_section_width_reduction_over_50_percent_creates_engineering_reference_segment():
    derivation = derive_wall_critical_height(_facts(thicknesses=(400.0, 199.0, 199.0, 199.0)))
    assert derivation.status == "RESOLVED"
    assert len(derivation.segments) == 2
    assert derivation.segments[1].reference_reason == "SECTION_WIDTH_REDUCTION_GT50"


def test_missing_vertical_continuity_blocks_all_five_with_explicit_reason():
    run = _run(_facts(continuity=None))
    assert all(row.coverage_status == CoverageStatus.BLOCKED for row in run.coverage_rows)
    assert all(result.status == CheckStatus.BLOCKED for result in run.check_results)
    assert all("vertical continuity" in " ".join(result.messages).lower() for result in run.check_results)


def test_missing_reference_and_reduction_proof_fail_closed():
    no_reference = _facts(foundation=None)
    run = _run(no_reference, check_ids=(WALL_HCR_GE_LW,))
    assert run.coverage_rows[0].coverage_status == CoverageStatus.BLOCKED
    assert "reference" in (run.coverage_rows[0].reason or "").lower()
    no_reduction = _facts(reductions_complete=None)
    run2 = _run(no_reduction, check_ids=(WALL_HCR_GE_LW,))
    assert run2.coverage_rows[0].coverage_status == CoverageStatus.BLOCKED
    assert "reduction" in (run2.coverage_rows[0].reason or "").lower()


def test_end_region_topology_only_blocks_checks_that_need_it():
    run = _run(_facts(topology=None))
    results = {result.check_id: result for result in run.check_results}
    assert results[WALL_END_REGIONS_REQUIRED_HW_LW_GT2].status == CheckStatus.BLOCKED
    assert results[WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW].status == CheckStatus.BLOCKED
    assert results[WALL_HCR_GE_LW].status == CheckStatus.OK
    assert results[WALL_HCR_GE_HW_DIV6].status == CheckStatus.OK
    assert results[WALL_HCR_LE_2LW].status == CheckStatus.OK


def test_end_region_length_uses_max_of_0_2lw_and_2bw_and_can_fail():
    run = _run(_facts(end_length=500.0), check_ids=(WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW,))
    result = run.check_results[0]
    assert result.status == CheckStatus.FAIL
    assert result.value == pytest.approx(500.0)
    assert result.limit == pytest.approx(600.0)


def test_rigid_basement_reference_uses_ground_floor_and_extends_critical_interval_down_one_basement():
    facts = _facts(
        rigid_perimeter=True,
        rigid_diaphragm=True,
        foundation=-3000.0,
        ground=0.0,
        first_basement_height=3000.0,
    )
    derivation = derive_wall_critical_height(facts)
    assert derivation.status == "RESOLVED"
    segment = derivation.segments[0]
    assert segment.reference_reason == "RIGID_BASEMENT_GROUND_FLOOR"
    assert segment.reference_elevation_mm == pytest.approx(0.0)
    assert segment.critical_start_elevation_mm == pytest.approx(-3000.0)


def test_two_candidates_receive_full_2x5_matrix_without_missing_or_duplicates():
    facts1 = _facts("W1")
    facts2 = _facts("W2")
    execution = WallExecutionEvidence(critical_height_facts_by_component={"W1": facts1, "W2": facts2})
    run = run_wall_checks(_Bundle(), [_snapshot("W1"), _snapshot("W2")], PACK_C_CHECK_IDS, execution_evidence=execution)
    assert len(run.check_results) == 10
    keys = [(result.component, result.check_id) for result in run.check_results]
    assert len(keys) == len(set(keys)) == 10
    assert run.assessment.expected_result_count == 10
    assert run.assessment.actual_result_count == 10
    assert run.assessment.missing_result_count == 0
    assert run.assessment.duplicate_result_count == 0


def test_engineering_derived_pack_c_state_never_enters_feature_snapshot_or_side_channel():
    source = inspect.getsource(MinimalCheckEngine)
    assert "engineering_context" not in source
    facts_source = inspect.getsource(WallCriticalHeightFactualEvidence)
    assert "hw_over_lw" not in facts_source
    assert "hcr_governing" not in facts_source
