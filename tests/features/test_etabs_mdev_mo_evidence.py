from __future__ import annotations

from types import SimpleNamespace

import pytest

from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.features import etabs_mdev_mo_evidence as ev


CASES = ("~Static+EccRSX", "~Static-EccRSX")


def _base_context(elevation=-5.15, rigid=False):
    return ev.ReviewedRegulatoryBaseContext(
        elevation_m=elevation,
        rigid_basement_above_base=rigid,
        review_refs=("review:base",),
        provenance_refs=("project:base",),
    )


def _walls():
    return ev.ReviewedDirectionalWallPopulation(
        direction="X",
        pier_refs=("P1", "P2"),
        review_refs=("review:walls:X",),
        provenance_refs=("project:walls:X",),
    )


def _result_context(*, mapping=(), sign=1):
    return ev.ReviewedResultPopulationContext(
        analysis_method=ev.ReviewedAnalysisMethod.MODAL_COMBINATION,
        scaling_state_id="reviewed:scaled-final",
        result_operator_id="reviewed:signed-same-realization",
        wall_to_total_sign_factor=sign,
        review_refs=("review:result-state",),
        provenance_refs=("project:result-state",),
        population_mapping_review_refs=tuple(mapping),
    )


def _rows(case_type="LinRespSpec", *, opposite=False, elevation=-5.15):
    sections = (
        {"Story": "B1", "Pier": "P1", "CGBotZ": elevation, "AxisAngle": 0.0},
        {"Story": "B1", "Pier": "P2", "CGBotZ": elevation, "AxisAngle": 0.0},
    )
    pier = {}
    story = {}
    base = {}
    for case in CASES:
        pier[case] = (
            {
                "Story": "B1", "Pier": "P1", "OutputCase": case,
                "CaseType": case_type, "Location": "Bottom", "M2": 0.0, "M3": 30.0,
            },
            {
                "Story": "B1", "Pier": "P2", "OutputCase": case,
                "CaseType": case_type, "Location": "Bottom", "M2": 0.0,
                "M3": -10.0 if opposite else 30.0,
            },
        )
        story[case] = (
            {
                "Story": "B1", "OutputCase": case, "CaseType": case_type,
                "Location": "Bottom", "MX": 0.0, "MY": 100.0,
            },
        )
        base[case] = (
            {
                "OutputCase": case, "CaseType": case_type,
                "MX": 0.0, "MY": 100.0, "X": 0.0, "Y": 0.0, "Z": elevation,
            },
        )
    return sections, pier, story, base


def _build(case_type="LinRespSpec", *, mapping=(), opposite=False, elevation=-5.15):
    sections, pier, story, base = _rows(case_type, opposite=opposite, elevation=elevation)
    return ev.build_directional_mdev_mo_evidence(
        direction="X",
        evidence_epoch_id="epoch:test",
        model_fingerprint="etabs:model-identity:sha256:test",
        case_names=CASES,
        base_context=_base_context(elevation),
        wall_population=_walls(),
        result_context=_result_context(mapping=mapping),
        pier_sections=sections,
        pier_force_rows_by_case=pier,
        story_force_rows_by_case=story,
        base_reaction_rows_by_case=base,
    )


def test_reviewed_base_is_explicit_not_hard_coded_to_acceptance_model_value():
    evidence = _build(elevation=123.456)
    assert evidence.reviewed_base_elevation_m == pytest.approx(123.456)
    assert all(case.base_reaction_reference_xyz[2] == pytest.approx(123.456) for case in evidence.cases)


def test_reviewed_base_requires_real_review_and_provenance_refs():
    with pytest.raises(ValueError):
        ev.ReviewedRegulatoryBaseContext(-5.15, False, (), ("project:base",))
    with pytest.raises(ValueError):
        ev.ReviewedRegulatoryBaseContext(-5.15, False, ("review:base",), ())


def test_rigid_basement_treatment_is_explicitly_out_of_scope_for_bounded_slice():
    sections, pier, story, base = _rows()
    with pytest.raises(ev.MdevMoEvidenceError) as err:
        ev.build_directional_mdev_mo_evidence(
            direction="X",
            evidence_epoch_id="epoch:test",
            model_fingerprint="etabs:model-identity:sha256:test",
            case_names=CASES,
            base_context=_base_context(rigid=True),
            wall_population=_walls(),
            result_context=_result_context(),
            pier_sections=sections,
            pier_force_rows_by_case=pier,
            story_force_rows_by_case=story,
            base_reaction_rows_by_case=base,
        )
    assert err.value.status == ev.BLOCKED_RIGID_BASEMENT_TREATMENT_OUT_OF_SCOPE


def test_exact_outputcase_isolation_never_uses_requested_selection_as_row_identity():
    rows = (
        {"OutputCase": "unrelated", "MY": 999.0},
        {"OutputCase": CASES[0], "MY": 100.0},
    )
    exact = ev.isolate_exact_output_case_rows(rows, CASES[0])
    assert exact == ({"OutputCase": CASES[0], "MY": 100.0},)


def test_missing_factual_outputcase_identity_blocks():
    with pytest.raises(ev.MdevMoEvidenceError) as err:
        ev.isolate_exact_output_case_rows(({"MY": 100.0},), CASES[0])
    assert err.value.status == ev.BLOCKED_FACTUAL_OUTPUT_CASE_IDENTITY


def test_capture_exact_output_case_requires_full_and_exact_restore(monkeypatch):
    fake = SimpleNamespace(
        capture_status=RuntimeCaptureStatus.FULL,
        display_selection={"display_selection_success": True, "fetch_after_display_selection": True},
        parsed=SimpleNamespace(
            rows=({"OutputCase": "other", "MY": 1.0}, {"OutputCase": CASES[0], "MY": 2.0}),
            actual_table_name="Base Reactions",
            return_code=0,
            row_count_reported=2,
        ),
        state_diagnostics=(
            {"phase": "snapshot", "cases": ["before"]},
            {"phase": "restore_verify", "success": True, "restored_cases": ["before"]},
        ),
    )
    monkeypatch.setattr(ev, "fetch_display_table_for_output", lambda *a, **k: fake)
    captured = ev.capture_exact_output_case_table(object(), "Base Reactions", CASES[0])
    assert captured.captured_row_count == 2
    assert captured.exact_target_row_count == 1
    assert captured.excluded_non_target_row_count == 1
    assert captured.exact_rows[0]["OutputCase"] == CASES[0]
    assert captured.restore_exact_equality_result is True


def test_axisangle_zero_and_ninety_degree_projection():
    assert ev.project_pier_moments_to_global(m2=10.0, m3=20.0, axis_angle_deg=0.0) == pytest.approx((10.0, 20.0))
    assert ev.project_pier_moments_to_global(m2=10.0, m3=20.0, axis_angle_deg=90.0) == pytest.approx((-20.0, 10.0))


def test_modal_factual_population_is_regulatory_ready_without_name_inference():
    evidence = _build("LinRespSpec")
    assert evidence.regulatory_ready is True
    assert evidence.blocking_status is None
    assert all(case.factual_result_method is ev.FactualResultPopulationMethod.MODAL_COMBINATION for case in evidence.cases)
    payload = evidence.regulatory_payload()
    assert "alpha_m" not in str(payload)
    assert [case["sum_mdev"] for case in payload["cases"]] == pytest.approx([60.0, 60.0])


def test_linstat_population_reviewed_as_modal_blocks_without_separate_mapping_review():
    evidence = _build("LinStatic")
    assert evidence.regulatory_ready is False
    assert evidence.blocking_status == ev.BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH
    with pytest.raises(ev.MdevMoEvidenceBlockedError) as err:
        evidence.regulatory_payload()
    assert err.value.status == ev.BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH
    assert all(case.factual_case_type == "LinStatic" for case in evidence.cases)


def test_linstat_population_can_only_pass_modal_gate_with_explicit_mapping_review_refs():
    evidence = _build("LinStatic", mapping=("review:linstatic-is-reviewed-modal-decomposition",))
    assert evidence.regulatory_ready is True
    assert evidence.compatibility["analysis_method_compatible"] is True


def test_opposite_signed_reviewed_wall_projection_blocks_without_abs_or_cancellation():
    evidence = _build("LinRespSpec", opposite=True)
    assert evidence.regulatory_ready is False
    assert evidence.blocking_status == ev.BLOCKED_RESULT_OPERATOR_AMBIGUITY
    values = [wall.aligned_signed_value for wall in evidence.cases[0].wall_projections]
    assert values == pytest.approx([30.0, -10.0])
