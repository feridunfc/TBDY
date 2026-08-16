from __future__ import annotations

import pytest

from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.input_adapter import CheckExecutionContext, GeometryCheckInput
from tbdy_engine.checks.member_geometry import (
    BEAM_7411_APPLICABILITY_CONTEXT,
    BEAM_DEPTH_WIDTH_RATIO,
    BEAM_MIN_DEPTH_300,
    BEAM_MIN_WIDTH,
    BEAM_REGISTRATIONS,
    COLUMN_MIN_DIMENSION,
    COLUMN_REGISTRATIONS,
    COLUMN_SECTION_SHAPE_CONTEXT,
    LEGACY_COLUMN_ALIASES,
    MEMBER_FORMAL_CHECK_IDS,
    MemberGeometryRegistration,
    compose_member_registrations,
    registration_check_definitions,
)
from tbdy_engine.checks.reconciliation import reconcile_check_results
from tbdy_engine.checks.result import CheckResult
from tbdy_engine.coverage.models import CoverageRow
from tbdy_engine.features.evidence import FeatureEvidence
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue


def _evidence(name: str, value: float, unit: str) -> FeatureEvidence:
    return FeatureEvidence(
        evidence_status="FULL",
        source_table="B1 fixture",
        actual_table_name="B1 fixture",
        source_column=name,
        raw_value=value,
        normalized_value=value,
        unit=unit,
    )


def _feature(name: str, value: float, unit: str = "mm") -> FeatureValue:
    return FeatureValue(
        feature_name=name,
        value=value,
        unit=unit,
        semantic_role="GEOMETRY",
        status="RESOLVED",
        evidence=[_evidence(name, value, unit)],
    )


def _snapshot(component_type: str, component_id: str, values: dict[str, tuple[float, str]]) -> FeatureSnapshot:
    return FeatureSnapshot(
        component_type=component_type,
        component_id=component_id,
        identity={"story": "S1", "section": "SEC1"},
        features={name: _feature(name, value, unit) for name, (value, unit) in values.items()},
    )


def _input(
    check_id: str,
    *,
    component_type: str,
    component_id: str = "M1",
    values: dict[str, tuple[float, str]],
    context: dict[str, object] | None = None,
) -> GeometryCheckInput:
    definition = registration_check_definitions()[check_id]
    required = tuple(definition["required_features"])
    snapshot = _snapshot(component_type, component_id, values)
    coverage = CoverageRow(
        check_id=check_id,
        component_type=component_type,
        component_id=component_id,
        required_features=required,
        resolved_features=required,
        coverage_status="RUNNABLE",
        evidence_status="FULL",
    )
    return GeometryCheckInput(
        check_id=check_id,
        component_id=component_id,
        component_type=component_type,
        story="S1",
        section="SEC1",
        required_features=required,
        snapshot=snapshot,
        coverage=coverage,
        evidence_by_feature={name: tuple(snapshot.features[name].evidence) for name in required},
        execution_context=CheckExecutionContext(values=context or {}),
    )


def _engine() -> MinimalCheckEngine:
    return MinimalCheckEngine(registration_check_definitions())


def _run(check_input: GeometryCheckInput) -> CheckResult:
    return _engine().run_input(check_input)


def test_formal_inventory_is_exact_and_aliases_are_not_formal() -> None:
    assert MEMBER_FORMAL_CHECK_IDS == {
        COLUMN_MIN_DIMENSION,
        BEAM_MIN_WIDTH,
        BEAM_MIN_DEPTH_300,
        BEAM_DEPTH_WIDTH_RATIO,
    }
    assert set(LEGACY_COLUMN_ALIASES) == {"column_geometry_min_width", "column_geometry_min_depth"}
    assert set(LEGACY_COLUMN_ALIASES).isdisjoint(MEMBER_FORMAL_CHECK_IDS)


def test_column_rectangular_exact_300_ok() -> None:
    result = _run(_input(
        COLUMN_MIN_DIMENSION,
        component_type="column",
        values={"column_width_mm": (300, "mm"), "column_depth_mm": (500, "mm")},
        context={COLUMN_SECTION_SHAPE_CONTEXT: "RECTANGULAR"},
    ))
    assert result.status == "OK"
    assert result.value == 300
    assert result.limit == 300
    assert result.ratio == 1.0


def test_column_rectangular_below_300_fails() -> None:
    result = _run(_input(
        COLUMN_MIN_DIMENSION,
        component_type="column",
        values={"column_width_mm": (299, "mm"), "column_depth_mm": (500, "mm")},
        context={COLUMN_SECTION_SHAPE_CONTEXT: "RECTANGULAR"},
    ))
    assert result.status == "FAIL"


def test_column_shape_unresolved_blocks_and_is_not_inferred_from_dimensions() -> None:
    result = _run(_input(
        COLUMN_MIN_DIMENSION,
        component_type="column",
        values={"column_width_mm": (400, "mm"), "column_depth_mm": (600, "mm")},
        context={},
    ))
    assert result.status == "BLOCKED"
    assert "applicability is unresolved" in result.messages[0]


def test_known_non_rectangular_column_is_out_of_scope() -> None:
    result = _run(_input(
        COLUMN_MIN_DIMENSION,
        component_type="column",
        values={"column_width_mm": (400, "mm"), "column_depth_mm": (400, "mm")},
        context={COLUMN_SECTION_SHAPE_CONTEXT: "CIRCULAR"},
    ))
    assert result.status == "OUT_OF_SCOPE"


def test_beam_applicability_unresolved_blocks() -> None:
    result = _run(_input(
        BEAM_MIN_WIDTH,
        component_type="beam",
        values={"beam_width_mm": (400, "mm")},
        context={},
    ))
    assert result.status == "BLOCKED"


def test_beam_proven_non_applicable_is_out_of_scope() -> None:
    result = _run(_input(
        BEAM_MIN_WIDTH,
        component_type="beam",
        values={"beam_width_mm": (400, "mm")},
        context={BEAM_7411_APPLICABILITY_CONTEXT: False},
    ))
    assert result.status == "OUT_OF_SCOPE"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(250, "OK"), (249, "FAIL")],
)
def test_beam_width_boundary(value: float, expected: str) -> None:
    result = _run(_input(
        BEAM_MIN_WIDTH,
        component_type="beam",
        values={"beam_width_mm": (value, "mm")},
        context={BEAM_7411_APPLICABILITY_CONTEXT: True},
    ))
    assert result.status == expected


def test_beam_depth_300_subcondition_boundary_ok() -> None:
    result = _run(_input(
        BEAM_MIN_DEPTH_300,
        component_type="beam",
        values={"beam_depth_mm": (300, "mm")},
        context={BEAM_7411_APPLICABILITY_CONTEXT: True},
    ))
    assert result.status == "OK"
    assert result.code_ref == "TBDY-2018-7.4.1.1(b)"
    assert result.limit == 300


@pytest.mark.parametrize(
    ("depth", "width", "expected"),
    [(700, 200, "OK"), (701, 200, "FAIL")],
)
def test_beam_depth_width_ratio_boundary(depth: float, width: float, expected: str) -> None:
    result = _run(_input(
        BEAM_DEPTH_WIDTH_RATIO,
        component_type="beam",
        values={"beam_depth_mm": (depth, "mm"), "beam_width_mm": (width, "mm")},
        context={BEAM_7411_APPLICABILITY_CONTEXT: True},
    ))
    assert result.status == expected
    assert result.ratio_type == "value_over_maximum"


@pytest.mark.parametrize("unit", ["", "m", "cm", "MM"])
def test_wrong_or_missing_member_unit_blocks(unit: str) -> None:
    result = _run(_input(
        BEAM_MIN_WIDTH,
        component_type="beam",
        values={"beam_width_mm": (250, unit)},
        context={BEAM_7411_APPLICABILITY_CONTEXT: True},
    ))
    assert result.status == "BLOCKED"


@pytest.mark.parametrize("value", [3, 30, 300, 3000])
def test_numeric_magnitude_never_changes_explicit_mm_interpretation(value: float) -> None:
    result = _run(_input(
        BEAM_MIN_WIDTH,
        component_type="beam",
        values={"beam_width_mm": (value, "mm")},
        context={BEAM_7411_APPLICABILITY_CONTEXT: True},
    ))
    assert result.status in {"OK", "FAIL"}
    assert result.value == float(value)
    assert result.unit == "mm"


def test_legacy_run_check_cannot_execute_formal_member_context_check() -> None:
    check_id = BEAM_MIN_WIDTH
    check_input = _input(
        check_id,
        component_type="beam",
        values={"beam_width_mm": (250, "mm")},
        context={BEAM_7411_APPLICABILITY_CONTEXT: True},
    )
    with pytest.raises(TypeError, match="mandatory execution context"):
        _engine().run_check(check_id, check_input.snapshot, check_input.coverage)


def test_registration_composition_is_deterministic() -> None:
    forward = compose_member_registrations(COLUMN_REGISTRATIONS, BEAM_REGISTRATIONS)
    reverse = compose_member_registrations(BEAM_REGISTRATIONS, COLUMN_REGISTRATIONS)
    assert tuple(forward) == tuple(sorted(MEMBER_FORMAL_CHECK_IDS))
    assert tuple(reverse) == tuple(forward)


def test_registration_duplicate_check_id_is_hard_failure() -> None:
    duplicate = MemberGeometryRegistration(
        check_id=BEAM_MIN_WIDTH,
        component_type="beam",
        required_features=("beam_width_mm",),
        required_execution_context=(BEAM_7411_APPLICABILITY_CONTEXT,),
        limit=999,
        comparison="minimum",
        ratio_type="actual_over_minimum",
        unit="mm",
        code_ref="fixture",
        formal_scope_note="duplicate fixture",
    )
    with pytest.raises(ValueError, match="Duplicate formal check ID"):
        compose_member_registrations(BEAM_REGISTRATIONS, (duplicate,))


def test_reconciliation_uses_canonical_formal_inventory_only() -> None:
    component_ids = ("B1", "B2")
    formal_ids = (BEAM_MIN_WIDTH, BEAM_MIN_DEPTH_300, BEAM_DEPTH_WIDTH_RATIO)
    results = []
    for component_id in component_ids:
        for check_id in formal_ids:
            result = _run(_input(
                check_id,
                component_type="beam",
                component_id=component_id,
                values=(
                    {"beam_width_mm": (250, "mm")}
                    if check_id == BEAM_MIN_WIDTH
                    else {"beam_depth_mm": (300, "mm")}
                    if check_id == BEAM_MIN_DEPTH_300
                    else {"beam_depth_mm": (700, "mm"), "beam_width_mm": (200, "mm")}
                ),
                context={BEAM_7411_APPLICABILITY_CONTEXT: True},
            ))
            results.append(result)
    reconciliation = reconcile_check_results(
        component_ids=component_ids,
        check_ids=formal_ids,
        results=results,
    )
    assert reconciliation.expected_result_count == 6
    assert reconciliation.actual_result_count == 6
    assert reconciliation.missing_result_count == 0
    assert reconciliation.duplicate_result_count == 0
    assert reconciliation.structurally_complete is True


def test_reconciliation_reports_missing_and_duplicate_without_manufacturing_results() -> None:
    first = _run(_input(
        BEAM_MIN_WIDTH,
        component_type="beam",
        component_id="B1",
        values={"beam_width_mm": (250, "mm")},
        context={BEAM_7411_APPLICABILITY_CONTEXT: True},
    ))
    reconciliation = reconcile_check_results(
        component_ids=("B1",),
        check_ids=(BEAM_MIN_WIDTH, BEAM_MIN_DEPTH_300),
        results=(first, first),
    )
    assert reconciliation.expected_result_count == 2
    assert reconciliation.actual_result_count == 2
    assert reconciliation.missing_result_count == 1
    assert reconciliation.duplicate_result_count == 1
    assert reconciliation.structurally_complete is False
