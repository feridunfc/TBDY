from __future__ import annotations

import inspect
from collections import defaultdict
import pytest

from tbdy_engine.assessment.wall_pack_a import assess_wall_pack_a
from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.checks.engine import MinimalCheckEngine, _ALLOWED_CHECKS
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.checks.wall_pack_a_contract import (
    LEGACY_NON_EXECUTABLE_CHECK_ALIASES, PACK_A_CHECK_IDS,
    WALL_GEOM_BODY_THICKNESS_GE_250, WALL_GEOM_BODY_THICKNESS_GE_H16,
    WALL_GEOM_DEFINITION_LW_BW_GE6, WALL_GEOM_RESTRAINED_LEG_THICKNESS,
    WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30,
)
from tbdy_engine.checks.wall_pack_a_pipeline import run_wall_check_pack_a
from tbdy_engine.coverage.models import CoverageStatus
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.resolver.wall_geometry import WallGeometryFactResolver
from tbdy_engine.features.unit_metadata import normalize_length_to_mm
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.features.wall_inventory import build_wall_inventory
from tbdy_engine.reporting.wall_pack_a import serialize_wall_pack_a


class _Bundle:
    def __init__(self) -> None:
        self._catalogs = {
            "check_catalog.yaml": {"checks": {}},
            "feature_catalog.yaml": {"features": {
                "wall_thickness_mm": {
                    "element_type": "wall", "unit": "mm", "semantic_role": "GEOMETRY",
                    "source": {"table_key": "wall_section_data", "field_aliases": ["ThickBot", "Thickness"]},
                    "evidence_fields": ["source_table", "source_column", "raw_value", "normalized_value", "unit"],
                },
                "wall_length_mm": {
                    "element_type": "wall", "unit": "mm", "semantic_role": "GEOMETRY",
                    "source": {"table_key": "wall_section_data", "field_aliases": ["WidthBot", "WidthTop"]},
                    "evidence_fields": ["source_table", "source_column", "raw_value", "normalized_value", "unit"],
                },
                "story_height_mm": {
                    "element_type": "story", "unit": "mm", "semantic_role": "GEOMETRY",
                    "source": {"table_key": "story_definitions", "field_aliases": ["Height", "Story Height"]},
                    "evidence_fields": ["source_table", "source_column", "raw_value", "normalized_value", "unit"],
                },
            }},
            "table_registry.yaml": {"tables": {}},
            "element_registry.yaml": {"element_types": {"wall": {}}},
            "high_ductility_check_scope.yaml": {"scope_items": []},
            "check_scope_alignment.yaml": {},
            "design_combo_matrix.yaml": {"design_mappings": []},
        }

    def catalog(self, name: str):
        return self._catalogs[name]


def _units(length_unit="m", *, resolved=True):
    return {
        "source": "fixture_etabs_unit_context", "force_unit": "kN", "length_unit": length_unit,
        "temperature_unit": "C", "unit_query_status": "RESOLVED" if resolved else "PARTIAL",
        "unit_basis_confidence": "high" if resolved else "low",
    }


def _tables(*, thickness=0.3, width=2.4, story_height=3.2, length_unit="m", resolved_units=True, property_name="WALL-P1"):
    return {
        "wall_section_properties": CanonicalTable(
            table_key="wall_section_properties", actual_table_name="Wall Property Definitions - Specified",
            columns=("Name", "Material", "Thickness", "WidthBot"),
            rows=({"Name": property_name, "Material": "C35", "Thickness": thickness, "WidthBot": width},),
            units=_units(length_unit, resolved=resolved_units), source="FAKE_PROVIDER",
        ),
        "story_definitions": CanonicalTable(
            table_key="story_definitions", actual_table_name="Story Definitions", columns=("Story", "Height"),
            rows=({"Story": "L1", "Height": story_height},),
            units=_units(length_unit, resolved=resolved_units), source="FAKE_PROVIDER",
        ),
    }


def _inventory(count=1, property_name="WALL-P1"):
    rows = [
        {"UniqueName": f"A{i}", "Label": f"W{i}", "Story": "L1", "SectionProperty": property_name, "PropertyType": "Wall"}
        for i in range(1, count + 1)
    ]
    return build_wall_inventory(
        model_fingerprint="MODEL-1", area_assignment_rows=rows,
        wall_property_rows=({"Name": property_name, "Material": "C35"},), pier_assignment_rows=(),
    )


def _provided_feature(name, value, unit="", role="APPLICABILITY"):
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL, source_table="canonical_pack_a_context",
        actual_table_name="canonical_pack_a_context", source_column=name,
        source_row={"feature": name, "value": value}, raw_value=value, normalized_value=value,
        unit=unit, resolver="test_canonical_context",
    )
    return FeatureValue(
        feature_name=name, value=value, unit=unit, semantic_role=role,
        status=FeatureValueStatus.RESOLVED, evidence=[evidence],
    )


def _provided_context(*, special=False, basement=False, restrained=True):
    return {
        "wall_is_basement": _provided_feature("wall_is_basement", basement),
        "wall_body_classification": _provided_feature("wall_body_classification", "RECTANGULAR_BODY", role="GEOMETRY_CLASSIFICATION"),
        "wall_special_branch_7_6_1_3_applies": _provided_feature("wall_special_branch_7_6_1_3_applies", special),
        "unrestrained_plan_length_mm": _provided_feature("unrestrained_plan_length_mm", 7500.0, "mm", "GEOMETRY"),
        "wall_geometry_classification": _provided_feature("wall_geometry_classification", "RECTANGULAR_WALL", role="GEOMETRY_CLASSIFICATION"),
        "wall_both_ends_laterally_restrained": _provided_feature("wall_both_ends_laterally_restrained", restrained, role="TOPOLOGY"),
    }


def _snapshots(*, count=1, tables=None, context_factory=None, property_name="WALL-P1"):
    inventory = _inventory(count, property_name)
    resolver = WallGeometryFactResolver(_Bundle(), tables or _tables())
    provided = {
        record.wall_object_id: (context_factory(record) if context_factory else _provided_context())
        for record in inventory.records if record.wall_object_id
    }
    return inventory, resolver.build_snapshots(inventory, provided_features_by_wall=provided)


def _run(**kwargs):
    inventory, snapshots = _snapshots(**kwargs)
    return inventory, snapshots, run_wall_check_pack_a(_Bundle(), snapshots)


def test_pack_a_exact_five_check_ids_and_legacy_ge7_is_non_executable():
    assert PACK_A_CHECK_IDS == (
        "WALL_GEOM_DEFINITION_LW_BW_GE6", "WALL_GEOM_BODY_THICKNESS_GE_H16",
        "WALL_GEOM_BODY_THICKNESS_GE_250", "WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30",
        "WALL_GEOM_RESTRAINED_LEG_THICKNESS",
    )
    assert "WALL11_LENGTH_TO_THICKNESS_GE7" not in PACK_A_CHECK_IDS
    assert "WALL11_LENGTH_TO_THICKNESS_GE7" not in _ALLOWED_CHECKS
    assert LEGACY_NON_EXECUTABLE_CHECK_ALIASES["WALL11_LENGTH_TO_THICKNESS_GE7"] == WALL_GEOM_DEFINITION_LW_BW_GE6


def test_wall_inventory_identity_survives_all_five_checks_for_each_wall():
    inventory, snapshots, run = _run(count=2)
    wall_ids = {r.wall_object_id for r in inventory.records if r.wall_object_id is not None}
    assert {s.component_id for s in snapshots} == wall_ids
    by_component = defaultdict(set)
    for result in run.check_results:
        by_component[result.component].add(result.check_id)
    assert set(by_component) == wall_ids
    assert all(by_component[wall_id] == set(PACK_A_CHECK_IDS) for wall_id in wall_ids)


def test_source_units_normalize_before_check_engine_and_no_magnitude_heuristic():
    _, snapshots = _snapshots(tables=_tables(thickness="0.4", width="2.4", story_height="3.2", length_unit="m"))
    snapshot = snapshots[0]
    assert snapshot.features["wall_thickness_mm"].value == pytest.approx(400.0)
    assert snapshot.features["wall_length_mm"].value == pytest.approx(2400.0)
    assert snapshot.features["story_height_mm"].value == pytest.approx(3200.0)
    _, large = _snapshots(tables=_tables(thickness="40", length_unit="m"))
    assert large[0].features["wall_thickness_mm"].value == pytest.approx(40000.0)
    _, mm = _snapshots(tables=_tables(thickness="0.4", width="2400", story_height="3200", length_unit="mm"))
    assert mm[0].features["wall_thickness_mm"].value == pytest.approx(0.4)
    assert normalize_length_to_mm("0.4", raw_unit="cm", unit_context_trusted=True).normalized_value == pytest.approx(4.0)


def test_untrusted_unit_context_fails_closed_and_coverage_is_not_runnable():
    _, snapshots = _snapshots(tables=_tables(resolved_units=False))
    assert snapshots[0].features["wall_thickness_mm"].status == FeatureValueStatus.PARTIAL
    run = run_wall_check_pack_a(_Bundle(), snapshots)
    assert all(row.coverage_status != CoverageStatus.RUNNABLE for row in run.coverage_rows)
    assert all(result.status == CheckStatus.BLOCKED for result in run.check_results)


def test_missing_global_basement_fact_blocks_all_five_checks():
    def context(_record):
        data = _provided_context(); data.pop("wall_is_basement"); return data
    _, snapshots = _snapshots(context_factory=context)
    run = run_wall_check_pack_a(_Bundle(), snapshots)
    assert all(row.coverage_status == CoverageStatus.BLOCKED for row in run.coverage_rows)
    assert all(result.status == CheckStatus.BLOCKED for result in run.check_results)


def test_unknown_special_branch_blocks_only_h16_and_250_branch_checks():
    def context(_record):
        data = _provided_context(); data.pop("wall_special_branch_7_6_1_3_applies"); return data
    _, snapshots = _snapshots(context_factory=context)
    results = {r.check_id: r for r in run_wall(snapshots)}
    assert results[WALL_GEOM_BODY_THICKNESS_GE_H16].status == CheckStatus.BLOCKED
    assert results[WALL_GEOM_BODY_THICKNESS_GE_250].status == CheckStatus.BLOCKED
    assert results[WALL_GEOM_DEFINITION_LW_BW_GE6].status == CheckStatus.OK


def run_wall(snapshots):
    return run_wall_check_pack_a(_Bundle(), snapshots).check_results


def test_special_branch_true_is_out_of_scope_for_2a_checks():
    _, snapshots = _snapshots(context_factory=lambda _: _provided_context(special=True))
    results = {r.check_id: r for r in run_wall(snapshots)}
    assert results[WALL_GEOM_BODY_THICKNESS_GE_H16].status == CheckStatus.OUT_OF_SCOPE
    assert results[WALL_GEOM_BODY_THICKNESS_GE_250].status == CheckStatus.OUT_OF_SCOPE


def test_basement_applicability_comes_from_fact_not_property_name():
    _, snapshots = _snapshots(context_factory=lambda _: _provided_context(basement=True))
    assert all(r.status == CheckStatus.OUT_OF_SCOPE for r in run_wall(snapshots))
    name = "BsmntWall_40cm"
    _, snapshots = _snapshots(tables=_tables(property_name=name), property_name=name, context_factory=lambda _: _provided_context(basement=False))
    definition = next(r for r in run_wall(snapshots) if r.check_id == WALL_GEOM_DEFINITION_LW_BW_GE6)
    assert definition.status == CheckStatus.OK


def test_property_identity_join_is_exact_and_case_sensitive():
    _, snapshots = _snapshots(tables=_tables(property_name="wall-p1"))
    assert snapshots[0].identity["assigned_wall_property"] == "WALL-P1"
    assert snapshots[0].features["wall_thickness_mm"].status == FeatureValueStatus.MISSING
    assert all(r.status == CheckStatus.BLOCKED for r in run_wall(snapshots))


def test_unknown_both_ends_restraint_blocks_restrained_leg_check():
    def context(_record):
        data = _provided_context(); data.pop("wall_both_ends_laterally_restrained"); return data
    _, snapshots = _snapshots(context_factory=context)
    result = next(r for r in run_wall(snapshots) if r.check_id == WALL_GEOM_RESTRAINED_LEG_THICKNESS)
    assert result.status == CheckStatus.BLOCKED


def test_exact_five_formulas_are_made_by_check_engine():
    _, _, run = _run()
    results = {r.check_id: r for r in run.check_results}
    assert results[WALL_GEOM_DEFINITION_LW_BW_GE6].value == pytest.approx(8.0)
    assert results[WALL_GEOM_DEFINITION_LW_BW_GE6].limit == pytest.approx(6.0)
    assert results[WALL_GEOM_BODY_THICKNESS_GE_H16].limit == pytest.approx(200.0)
    assert results[WALL_GEOM_BODY_THICKNESS_GE_250].limit == pytest.approx(250.0)
    assert results[WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30].limit == pytest.approx(250.0)
    assert results[WALL_GEOM_RESTRAINED_LEG_THICKNESS].limit == pytest.approx(250.0)
    assert all(r.evaluation_level == EvaluationLevel.DESIGN_LEVEL for r in results.values())
    _, _, run = _run(tables=_tables(story_height=6.0))
    restrained = next(r for r in run.check_results if r.check_id == WALL_GEOM_RESTRAINED_LEG_THICKNESS)
    assert restrained.limit == pytest.approx(300.0)


def test_lw_bw_failure_does_not_delete_wall_inventory_identity():
    inventory, snapshots = _snapshots(tables=_tables(thickness=0.5, width=2.0))
    wall_id = snapshots[0].component_id
    result = next(r for r in run_wall(snapshots) if r.check_id == WALL_GEOM_DEFINITION_LW_BW_GE6)
    assert result.status == CheckStatus.FAIL and result.component == wall_id
    assert any(record.wall_object_id == wall_id for record in inventory.records)


def test_unrestrained_length_is_never_substituted_from_total_wall_length():
    def context(_record):
        data = _provided_context(); data.pop("unrestrained_plan_length_mm"); return data
    _, snapshots = _snapshots(context_factory=context)
    assert snapshots[0].features["wall_length_mm"].status == FeatureValueStatus.RESOLVED
    result = next(r for r in run_wall(snapshots) if r.check_id == WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30)
    assert result.status == CheckStatus.BLOCKED


def test_restrained_leg_false_is_out_of_scope():
    _, snapshots = _snapshots(context_factory=lambda _: _provided_context(restrained=False))
    result = next(r for r in run_wall(snapshots) if r.check_id == WALL_GEOM_RESTRAINED_LEG_THICKNESS)
    assert result.status == CheckStatus.OUT_OF_SCOPE


def test_all_five_emit_canonical_checkresults_and_assessment_never_claims_full_compliance():
    _, _, run = _run()
    assert len(run.check_results) == 5 and all(isinstance(r, CheckResult) for r in run.check_results)
    assert run.assessment.status_counts[CheckStatus.OK.value] == 5
    assert run.assessment.pack_a_status == "EVALUATED_NO_FAILURES"
    assert run.assessment.full_tbdy_compliance_status == "NOT_EVALUATED"


def test_reporter_is_dumb_and_preserves_canonical_result_without_recomputing():
    synthetic = CheckResult(
        check_id=WALL_GEOM_BODY_THICKNESS_GE_250, component="wall-x", component_type="wall",
        status=CheckStatus.OK, story="L1", value=1.0, limit=9999.0, ratio=0.0001,
        ratio_type="actual_over_minimum", pass_rule="actual_over_minimum", unit="mm",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL, code_ref="test",
    )
    payload = serialize_wall_pack_a([synthetic], assess_wall_pack_a([synthetic]))
    assert payload["results"][0]["status"] == "OK" and payload["results"][0]["limit"] == 9999.0
    source = inspect.getsource(serialize_wall_pack_a)
    for forbidden in ("250", "/ 16", "/ 20", "/ 30", ">= 6"):
        assert forbidden not in source


def test_check_engine_has_no_etabs_com_or_raw_table_knowledge():
    source = inspect.getsource(MinimalCheckEngine).casefold()
    for forbidden in ("wall property definitions", "story definitions", "getpresentunits", "sapmodel", "database tables", "com.", "raw display"):
        assert forbidden not in source
