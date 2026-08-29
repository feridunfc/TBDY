from __future__ import annotations

from decimal import Decimal
import inspect

import pytest

from tbdy_engine.design.columns.column_combo_eligibility_projection import (
    AUTHORITY as COMBO_ELIGIBILITY_AUTHORITY,
    ColumnComboEligibilityProjection,
    ColumnComboEligibilityState,
    ComboConstituentEligibilityFact,
)
from tbdy_engine.design.columns.column_design_rebar_promotion import (
    BLOCKED_AMBIGUOUS_PMM_COMBO,
    BLOCKED_COMBO_NOT_ELIGIBLE,
    BLOCKED_ETABS_ERROR_SUMMARY,
    BLOCKED_ETABS_WARNING_SUMMARY,
    BLOCKED_MISSING_PMM_COMBO,
    BLOCKED_UNBINDABLE_PMM_COMBO,
    promote_etabs_required_rebar,
)
from tbdy_engine.features.column_design_rebar_evidence import (
    ColumnDesignRebarEvidenceError,
    FactualColumnDesignResultPopulation,
    FactualColumnDesignResultRow,
)
import tbdy_engine.design.columns.column_design_rebar_promotion as subject

MODEL = "model:fixture"
EPOCH = "epoch:fixture"
C1 = "column:1"
C2 = "column:2"


def _projection(
    component_id: str = C1,
    *,
    design_type: str = "Strength",
    combo_name: str = "ULS",
    eligible: bool = True,
    model: str = MODEL,
    epoch: str = EPOCH,
) -> ColumnComboEligibilityProjection:
    state = ColumnComboEligibilityState.ELIGIBLE if eligible else ColumnComboEligibilityState.BLOCKED_COMBO
    blockers = () if eligible else ("FIXTURE_BLOCKER",)
    return ColumnComboEligibilityProjection(
        projection_id=f"projection:{component_id}:{design_type}:{combo_name}:{eligible}:{model}:{epoch}",
        component_id=component_id,
        design_combo_identity=(design_type, combo_name),
        normalized_definition_fingerprint=f"combo-definition:{combo_name}",
        constituent_facts=(
            ComboConstituentEligibilityFact(
                name="G",
                scale_factor="1",
                cname_type="LOAD_CASE",
                case_type="LinStatic",
            ),
        ),
        combo_pattern="SUPPORTED_STATIC_LINEAR",
        reconstruction_authority="STATIC_LINEAR_EXACT_DESIGN_STATE",
        reconstruction_behavior_refs=(),
        analysis_basis_status="MATCH",
        analysis_basis_ref=f"analysis-basis:{component_id}:{design_type}:{combo_name}",
        component_readiness_status="READY",
        component_readiness_ref=f"readiness:{component_id}",
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        eligibility_state=state,
        blockers=blockers,
        provenance_refs=(f"projection-provenance:{component_id}:{design_type}:{combo_name}",),
    )


def _row(
    source_row_id: str,
    *,
    component_id: str = C1,
    my_option: int = 2,
    pmm_combo: str | None = "ULS",
    area: str = "1200",
    error: str = "",
    warning: str = "",
    model: str = MODEL,
    epoch: str = EPOCH,
) -> FactualColumnDesignResultRow:
    suffix = component_id.split(":")[-1]
    return FactualColumnDesignResultRow(
        source_row_id=source_row_id,
        component_id=component_id,
        unique_name=f"U{suffix}",
        story="Story1",
        label=f"C{suffix}",
        assigned_section="SEC_A",
        design_section="SEC_D",
        my_option=my_option,
        pmm_combo=pmm_combo,
        location_mm=Decimal("500"),
        pmm_area_mm2=Decimal(area),
        error_summary=error,
        warning_summary=warning,
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        source_refs=(f"source:{source_row_id}",),
    )


def _population(
    rows,
    *,
    expected=(C1,),
    attempted=None,
    captured=None,
    model: str = MODEL,
    epoch: str = EPOCH,
) -> FactualColumnDesignResultPopulation:
    attempted = expected if attempted is None else attempted
    captured = expected if captured is None else captured
    rows = tuple(rows)
    return FactualColumnDesignResultPopulation(
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        expected_component_ids=tuple(expected),
        attempted_component_ids=tuple(attempted),
        captured_component_ids=tuple(captured),
        reported_result_row_count=len(rows),
        rows=rows,
        source_refs=("capture:fixture",),
    )


def test_promotes_every_exact_design_row_without_first_last_or_max_collapse():
    results = _population(
        (
            _row("row:1", area="1000"),
            _row("row:2", area="1300"),
            _row("row:3", area="1100"),
        )
    )
    promoted = promote_etabs_required_rebar(
        results,
        combo_eligibility_projections=(_projection(),),
    )
    assert promoted.promotion_complete
    assert promoted.source_result_row_count == 3
    assert promoted.source_design_row_count == 3
    assert promoted.promoted_requirement_count == 3
    assert promoted.blocked_requirement_count == 0
    assert {item.source_row_id for item in promoted.requirements} == {"row:1", "row:2", "row:3"}
    assert {item.required_as_mm2 for item in promoted.requirements} == {
        Decimal("1000"),
        Decimal("1100"),
        Decimal("1300"),
    }
    assert all(item.design_combo_identity == ("Strength", "ULS") for item in promoted.requirements)
    assert all(item.combo_eligibility_projection_id == _projection().projection_id for item in promoted.requirements)


def test_check_rows_are_preserved_in_source_count_but_not_rebar_requirements():
    results = _population((_row("row:check", my_option=1), _row("row:design", my_option=2)))
    promoted = promote_etabs_required_rebar(results, combo_eligibility_projections=(_projection(),))
    assert promoted.source_result_row_count == 2
    assert promoted.source_design_row_count == 1
    assert tuple(item.source_row_id for item in promoted.requirements) == ("row:design",)


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"error": "design error"}, BLOCKED_ETABS_ERROR_SUMMARY),
        ({"warning": "design warning"}, BLOCKED_ETABS_WARNING_SUMMARY),
        ({"pmm_combo": None}, BLOCKED_MISSING_PMM_COMBO),
        ({"pmm_combo": "UNKNOWN"}, BLOCKED_UNBINDABLE_PMM_COMBO),
    ],
)
def test_row_local_source_problems_are_explicitly_blocked(kwargs, reason):
    results = _population((_row("row:blocked", **kwargs),))
    promoted = promote_etabs_required_rebar(results, combo_eligibility_projections=(_projection(),))
    assert not promoted.promotion_complete
    assert promoted.promoted_requirement_count == 0
    assert promoted.blocked_requirement_count == 1
    assert promoted.blocked_rows[0].reason_code == reason
    assert promoted.blocked_rows[0].source_row_id == "row:blocked"


def test_exact_projection_must_be_eligible_not_merely_name_matched():
    results = _population((_row("row:1"),))
    promoted = promote_etabs_required_rebar(
        results,
        combo_eligibility_projections=(_projection(eligible=False),),
    )
    assert promoted.promoted_requirement_count == 0
    assert promoted.blocked_rows[0].reason_code == BLOCKED_COMBO_NOT_ELIGIBLE
    assert "FIXTURE_BLOCKER" in promoted.blocked_rows[0].reason_detail


def test_same_pmm_combo_name_across_design_types_is_explicitly_ambiguous():
    results = _population((_row("row:1"),))
    promoted = promote_etabs_required_rebar(
        results,
        combo_eligibility_projections=(
            _projection(design_type="Strength"),
            _projection(design_type="Service"),
        ),
    )
    assert promoted.promoted_requirement_count == 0
    assert promoted.blocked_rows[0].reason_code == BLOCKED_AMBIGUOUS_PMM_COMBO


def test_projection_for_another_component_cannot_authorize_this_row():
    results = _population(
        (_row("row:c1", component_id=C1), _row("row:c2", component_id=C2)),
        expected=(C1, C2),
    )
    promoted = promote_etabs_required_rebar(
        results,
        combo_eligibility_projections=(
            _projection(C1, combo_name="ULS"),
            _projection(C2, combo_name="OTHER"),
        ),
    )
    by_component = {item.component_id: item for item in promoted.components}
    assert by_component[C1].promoted_requirement_count == 1
    assert by_component[C2].blocked_requirement_count == 1
    assert by_component[C2].blocked_rows[0].reason_code == BLOCKED_UNBINDABLE_PMM_COMBO


def test_model_fingerprint_mismatch_fails_closed():
    results = _population((_row("row:1"),))
    with pytest.raises(ColumnDesignRebarEvidenceError, match="model/EvidenceEpoch"):
        promote_etabs_required_rebar(
            results,
            combo_eligibility_projections=(_projection(model="other-model"),),
        )


def test_evidence_epoch_mismatch_fails_closed():
    results = _population((_row("row:1"),))
    with pytest.raises(ColumnDesignRebarEvidenceError, match="model/EvidenceEpoch"):
        promote_etabs_required_rebar(
            results,
            combo_eligibility_projections=(_projection(epoch="other-epoch"),),
        )


def test_incomplete_component_capture_cannot_be_promoted():
    results = _population(
        (_row("row:c1", component_id=C1),),
        expected=(C1, C2),
        attempted=(C1,),
        captured=(C1,),
    )
    assert not results.capture_complete
    with pytest.raises(ColumnDesignRebarEvidenceError, match="not complete"):
        promote_etabs_required_rebar(
            results,
            combo_eligibility_projections=(_projection(C1), _projection(C2)),
        )


def test_projection_population_must_cover_every_expected_component():
    results = _population(
        (_row("row:c1", component_id=C1), _row("row:c2", component_id=C2)),
        expected=(C1, C2),
    )
    with pytest.raises(ColumnDesignRebarEvidenceError, match="exact expected component population"):
        promote_etabs_required_rebar(
            results,
            combo_eligibility_projections=(_projection(C1),),
        )


def test_component_without_design_rows_fails_closed():
    results = _population((_row("row:check", my_option=1),))
    with pytest.raises(ColumnDesignRebarEvidenceError, match="no MyOption=2 design rows"):
        promote_etabs_required_rebar(
            results,
            combo_eligibility_projections=(_projection(),),
        )


def test_duplicate_component_combo_projection_identity_is_rejected():
    results = _population((_row("row:1"),))
    projection = _projection()
    with pytest.raises(ColumnDesignRebarEvidenceError, match="projection identities must be unique"):
        promote_etabs_required_rebar(
            results,
            combo_eligibility_projections=(projection, projection),
        )


def test_mixed_promoted_and_blocked_rows_reconcile_exactly_once():
    results = _population(
        (
            _row("row:ok", area="1200"),
            _row("row:error", area="1300", error="x"),
            _row("row:missing", area="1400", pmm_combo=None),
        )
    )
    promoted = promote_etabs_required_rebar(results, combo_eligibility_projections=(_projection(),))
    assert promoted.source_design_row_count == 3
    assert promoted.promoted_requirement_count == 1
    assert promoted.blocked_requirement_count == 2
    assert {item.source_row_id for item in promoted.requirements} == {"row:ok"}
    assert {item.source_row_id for item in promoted.blocked_rows} == {"row:error", "row:missing"}


def test_promotion_is_deterministic_under_row_and_projection_input_order():
    rows = (
        _row("row:c1:2", component_id=C1, area="1250"),
        _row("row:c2:1", component_id=C2, area="1400"),
        _row("row:c1:1", component_id=C1, area="1100"),
    )
    expected = (C1, C2)
    first = promote_etabs_required_rebar(
        _population(rows, expected=expected),
        combo_eligibility_projections=(_projection(C2), _projection(C1)),
    )
    second = promote_etabs_required_rebar(
        _population(tuple(reversed(rows)), expected=tuple(reversed(expected))),
        combo_eligibility_projections=(_projection(C1), _projection(C2)),
    )
    assert first == second


def test_authority_boundary_has_no_etabs_access_and_never_emits_engine_selected_rebar():
    source = inspect.getsource(subject)
    for forbidden in (
        "GetSummaryResultsColumn",
        "DesignConcrete",
        "StartDesign",
        "RunAnalysis",
        "ENGINE_SELECTED_REBAR",
    ):
        assert forbidden not in source
    promoted = promote_etabs_required_rebar(
        _population((_row("row:1"),)),
        combo_eligibility_projections=(_projection(),),
    )
    assert promoted.projection_authority == COMBO_ELIGIBILITY_AUTHORITY
    assert promoted.requirements[0].authority == "ETABS_REQUIRED_REBAR"
    assert "ENGINE_SELECTED_REBAR" not in repr(promoted)
