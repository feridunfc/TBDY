from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_public_a5_second_order as second_order
import tbdy_engine.application.column_route_c_direction_binding as route_c
from tbdy_engine.application.column_design_basis import (
    BoundColumnActionFamilyApplicability,
    COLUMN_ROUTE_C_SUPPORTED_PATH,
    COLUMN_ROUTE_C_W_ACTION_FAMILY,
    COLUMN_ROUTE_C_W_APPLICABILITY_BASIS_VERSION,
    COLUMN_ROUTE_C_W_APPLICABILITY_BINDING,
    COLUMN_ROUTE_C_W_APPLICABILITY_BINDING_ID,
    ColumnDesignBasisError,
    ReviewedActionFamilyApplicability,
    ReviewedAggregateBasis,
    ReviewedColumnDesignBasis,
    ReviewedConcreteDesignStrength,
    ReviewedLongitudinalSteelDesignStrength,
    bind_reviewed_route_c_w_applicability,
)
from tbdy_engine.application.contracts import (
    ColumnExecutionRequest,
    ProjectExecutionRequest,
)
from tbdy_engine.design.columns.story_relative_translation import (
    ReviewedStoryTranslationTolerance,
)
from tbdy_engine.regulatory.contracts import ApplicabilityState


PROJECT_ID = "PROJECT:A17-W-TEST"
MODEL_ID = "MODEL:A17-W-TEST"
EPOCH_ID = "EPOCH:A17-W-TEST"


def _reviewed_basis(
    state: ApplicabilityState,
) -> ReviewedColumnDesignBasis:
    return ReviewedColumnDesignBasis(
        concrete_strengths=(
            ReviewedConcreteDesignStrength(
                material_name="C30",
                fcd_mpa=20.0,
                review_refs=("review:fcd:C30",),
            ),
        ),
        longitudinal_steel_strengths=(
            ReviewedLongitudinalSteelDesignStrength(
                material_name="B420C",
                fyd_mpa=365.2173913043478,
                review_refs=("review:fyd:B420C",),
            ),
        ),
        aggregate=ReviewedAggregateBasis(
            aggregate_max_mm=22.0,
            review_refs=("review:aggregate:22mm",),
        ),
        basis_refs=(
            "project-design-basis:a17-w-test",
        ),
        route_c_w_applicability=(
            ReviewedActionFamilyApplicability(
                state=state,
                review_refs=(
                    "review:route-c-w-applicability",
                ),
                source_refs=(
                    "source:TS500:wind-applicability",
                ),
            )
        ),
    )


def _bound(
    state: ApplicabilityState,
) -> BoundColumnActionFamilyApplicability:
    result = bind_reviewed_route_c_w_applicability(
        _reviewed_basis(state),
        project_id=PROJECT_ID,
        model_fingerprint=MODEL_ID,
        evidence_epoch_id=EPOCH_ID,
    )
    assert result is not None
    return result


def _a18_rows():
    return tuple(
        SimpleNamespace(
            disposition=second_order.A18_READY,
            source_refs=(),
            unresolved_reasons=(),
            end_tag=end,
            local_bending_axis=axis,
        )
        for end, axis in (
            ("BOTTOM", "M2"),
            ("BOTTOM", "M3"),
            ("TOP", "M2"),
            ("TOP", "M3"),
        )
    )


def _e_bindings():
    return (
        SimpleNamespace(
            case_name="LC_EQX",
            global_direction="X",
            source_refs=("direction:LC_EQX:X",),
        ),
        SimpleNamespace(
            case_name="LC_EQY",
            global_direction="Y",
            source_refs=("direction:LC_EQY:Y",),
        ),
    )


def _second_order_payload(
    monkeypatch,
    *,
    state: ApplicabilityState,
    route_blockers: tuple[str, ...],
    route_bindings=None,
):
    bindings = (
        _e_bindings()
        if route_bindings is None
        else tuple(route_bindings)
    )

    monkeypatch.setattr(
        second_order,
        "resolve_route_c_source_bound_directions",
        lambda **kwargs: SimpleNamespace(
            source_refs=("route-c:test",),
            blockers=tuple(route_blockers),
            bindings=bindings,
            ready=not route_blockers,
        ),
    )

    monkeypatch.setattr(
        second_order,
        "capture_etabs_static_linear_cases_from_session",
        lambda *args, **kwargs: (),
    )

    monkeypatch.setattr(
        second_order,
        "promote_etabs_static_cases_to_ts500_stability_actions",
        lambda *args, **kwargs: SimpleNamespace(
            promoted_sources=(),
            authority="promotion:test",
        ),
    )

    monkeypatch.setattr(
        second_order,
        "resolve_existing_ts500_stability_combos",
        lambda *args, **kwargs: SimpleNamespace(
            source_refs=("stability-combo:test",),
            both_bases_present=False,
            gqe_candidates=(),
            gqw_candidates=(),
            status="NEXT_COMBO_EDGE",
        ),
    )

    return second_order.build_public_a5_canonical_second_order_payload(
        component_id="+4.50:C10:188",
        session=object(),
        topology=None,
        target_column=None,
        frame_population=None,
        flattened_combos=(),
        constituent_case_demands=(
            SimpleNamespace(
                output_case="LC_DL",
                case_type="LinStatic",
            ),
        ),
        a18_rows=_a18_rows(),
        free_length=SimpleNamespace(
            source_refs=("free-length:test",),
            resolved=True,
        ),
        analysis_execution=None,
        route_c_w_applicability=_bound(state),
        qualified_response_static_case_names=(
            "LC_EQX",
            "LC_EQY",
        ),
        qualified_response_static_source_refs=(
            "qualified-response-static:test",
        ),
        reviewed_story_translation_tolerance=(
            ReviewedStoryTranslationTolerance(
                absolute_tolerance_mm=0.01,
                source_ref="review:translation-tolerance",
            )
        ),
    )


def _blockers(payload):
    return tuple(
        payload["canonical_second_order"]["blockers"]
    )


@pytest.mark.parametrize(
    "state",
    tuple(ApplicabilityState),
)
def test_reviewed_w_applicability_binds_deterministically(
    state,
):
    first = _bound(state)
    second = _bound(state)

    assert first.state is state
    assert first.action_family == "W"
    assert first.supported_path == "COLUMN/ROUTE_C"
    assert first.project_id == PROJECT_ID
    assert first.model_fingerprint == MODEL_ID
    assert first.evidence_epoch_id == EPOCH_ID

    assert first.binding_ref == second.binding_ref
    assert first.evidence_ref == second.evidence_ref

    assert state.value in first.evidence_ref
    assert first.evidence_ref in first.source_refs

    reviewed = _reviewed_basis(
        state
    ).route_c_w_applicability

    assert reviewed is not None

    assert (
        COLUMN_ROUTE_C_W_APPLICABILITY_BINDING
        .evaluator(reviewed)
        is state
    )


def test_reviewed_w_applicability_rejects_wrong_identity():
    with pytest.raises(ColumnDesignBasisError):
        ReviewedActionFamilyApplicability(
            state=ApplicabilityState.APPLIES,
            review_refs=("review:w",),
            source_refs=("source:w",),
            action_family="E",
        )

    with pytest.raises(ColumnDesignBasisError):
        ReviewedActionFamilyApplicability(
            state=ApplicabilityState.APPLIES,
            review_refs=("review:w",),
            source_refs=("source:w",),
            supported_path="COLUMN/OTHER",
        )

    with pytest.raises(ColumnDesignBasisError):
        ReviewedActionFamilyApplicability(
            state=ApplicabilityState.APPLIES,
            review_refs=("review:w",),
            source_refs=("source:w",),
            basis_version="UNREVIEWED_VERSION",
        )

    with pytest.raises(ColumnDesignBasisError):
        ReviewedActionFamilyApplicability(
            state=ApplicabilityState.APPLIES,
            review_refs=(),
            source_refs=("source:w",),
        )

    with pytest.raises(ColumnDesignBasisError):
        ReviewedActionFamilyApplicability(
            state=ApplicabilityState.APPLIES,
            review_refs=("review:w",),
            source_refs=(),
        )


def test_bound_w_applicability_rejects_wrong_binding_identity():
    good = _bound(
        ApplicabilityState.APPLIES
    )

    with pytest.raises(ColumnDesignBasisError):
        BoundColumnActionFamilyApplicability(
            action_family=(
                COLUMN_ROUTE_C_W_ACTION_FAMILY
            ),
            supported_path=(
                COLUMN_ROUTE_C_SUPPORTED_PATH
            ),
            state=good.state,
            project_id=good.project_id,
            model_fingerprint=good.model_fingerprint,
            evidence_epoch_id=good.evidence_epoch_id,
            basis_version=(
                COLUMN_ROUTE_C_W_APPLICABILITY_BASIS_VERSION
            ),
            applicability_binding_id="wrong-binding",
            binding_ref=good.binding_ref,
            evidence_ref=good.evidence_ref,
            review_refs=good.review_refs,
            source_refs=good.source_refs,
        )


def test_applies_without_factual_w_preserves_source_blocker(
    monkeypatch,
):
    payload = _second_order_payload(
        monkeypatch,
        state=ApplicabilityState.APPLIES,
        route_blockers=(
            "ROUTE_C_W_ACTION_SOURCE_NOT_PROVEN",
        ),
    )

    blockers = _blockers(payload)

    assert (
        "A17:ROUTE_C_W_ACTION_SOURCE_NOT_PROVEN"
        in blockers
    )

    assert (
        "A17:ROUTE_C_W_APPLICABILITY_UNRESOLVED"
        not in blockers
    )


def test_pna_without_factual_w_suppresses_w_requirements_and_retains_evidence(
    monkeypatch,
):
    bound = _bound(
        ApplicabilityState.PROVEN_NOT_APPLICABLE
    )

    payload = _second_order_payload(
        monkeypatch,
        state=ApplicabilityState.PROVEN_NOT_APPLICABLE,
        route_blockers=(
            "ROUTE_C_W_ACTION_SOURCE_NOT_PROVEN",
        ),
    )

    blockers = _blockers(payload)

    assert (
        "A17:ROUTE_C_W_ACTION_SOURCE_NOT_PROVEN"
        not in blockers
    )

    assert not any(
        "ROUTE_C_W_DIRECTION_"
        in item
        for item in blockers
    )

    # PNA passes the W requirement and reaches the
    # intentionally bounded next combo edge.
    assert "A17:NEXT_COMBO_EDGE" in blockers

    # GQW family did not disappear.  Its reviewed PNA
    # evidence remains in the canonical payload lineage.
    assert bound.evidence_ref in payload["source_refs"]

    assert any(
        "COLUMN_ROUTE_C_GQW_APPLICABILITY:"
        "PROVEN_NOT_APPLICABLE:"
        in ref
        for ref in payload["source_refs"]
    )


def test_unresolved_w_applicability_fails_closed(
    monkeypatch,
):
    payload = _second_order_payload(
        monkeypatch,
        state=ApplicabilityState.UNRESOLVED,
        route_blockers=(
            "ROUTE_C_W_ACTION_SOURCE_NOT_PROVEN",
        ),
    )

    blockers = _blockers(payload)

    assert (
        "A17:ROUTE_C_W_APPLICABILITY_UNRESOLVED"
        in blockers
    )

    assert (
        "A17:ROUTE_C_W_ACTION_SOURCE_NOT_PROVEN"
        not in blockers
    )


def test_invalid_context_w_applicability_fails_closed(
    monkeypatch,
):
    payload = _second_order_payload(
        monkeypatch,
        state=ApplicabilityState.INVALID_CONTEXT,
        route_blockers=(
            "ROUTE_C_W_ACTION_SOURCE_NOT_PROVEN",
        ),
    )

    blockers = _blockers(payload)

    assert (
        "A17:ROUTE_C_W_APPLICABILITY_INVALID_CONTEXT"
        in blockers
    )

    assert (
        "A17:ROUTE_C_W_ACTION_SOURCE_NOT_PROVEN"
        not in blockers
    )


def test_applies_with_factual_w_but_no_direction_remains_blocked(
    monkeypatch,
):
    blocker = (
        "ROUTE_C_W_DIRECTION_"
        "SOURCE_BOUND_EVIDENCE_NOT_AVAILABLE:LC_WX"
    )

    payload = _second_order_payload(
        monkeypatch,
        state=ApplicabilityState.APPLIES,
        route_blockers=(blocker,),
    )

    assert (
        f"A17:{blocker}"
        in _blockers(payload)
    )


def test_pna_conflicts_with_factual_w_presence(
    monkeypatch,
):
    blocker = (
        "ROUTE_C_W_DIRECTION_"
        "SOURCE_BOUND_EVIDENCE_NOT_AVAILABLE:LC_WX"
    )

    payload = _second_order_payload(
        monkeypatch,
        state=ApplicabilityState.PROVEN_NOT_APPLICABLE,
        route_blockers=(blocker,),
    )

    blockers = _blockers(payload)

    assert (
        "A17:"
        "ROUTE_C_W_APPLICABILITY_CONFLICT_"
        "FACTUAL_W_SOURCE_PRESENT:LC_WX"
        in blockers
    )


def test_route_c_e_direction_regression_is_unchanged(
    monkeypatch,
):
    e_sources = (
        SimpleNamespace(
            action_role=route_c.TS500_ACTION_E,
            case_name="LC_EQX",
            source_refs=("E:LC_EQX",),
        ),
        SimpleNamespace(
            action_role=route_c.TS500_ACTION_E,
            case_name="LC_EQY",
            source_refs=("E:LC_EQY",),
        ),
    )

    monkeypatch.setattr(
        route_c,
        "capture_etabs_static_linear_cases_from_session",
        lambda session, names: ("FACTS",),
    )

    monkeypatch.setattr(
        route_c,
        "promote_etabs_static_cases_to_ts500_stability_actions",
        lambda cases: SimpleNamespace(
            promoted_sources=e_sources,
            authority="promotion:test",
        ),
    )

    monkeypatch.setattr(
        route_c,
        "capture_etabs_auto_seismic_direction_evidence_from_session",
        lambda session: object(),
    )

    monkeypatch.setattr(
        route_c,
        "bind_etabs_seismic_action_directions",
        lambda sources, table: SimpleNamespace(
            complete=True,
            status="READY",
            source_refs=("seismic-direction:test",),
            bindings=(
                SimpleNamespace(
                    case_name="LC_EQX",
                    direction="X",
                    source_refs=("direction:EQX:X",),
                    authority="test:E-direction",
                ),
                SimpleNamespace(
                    case_name="LC_EQY",
                    direction="Y",
                    source_refs=("direction:EQY:Y",),
                    authority="test:E-direction",
                ),
            ),
        ),
    )

    result = (
        route_c.resolve_route_c_source_bound_directions(
            session=object(),
            static_case_names=(
                "LC_EQX",
                "LC_EQY",
            ),
        )
    )

    assert {
        item.case_name: item.global_direction
        for item in result.bindings
    } == {
        "LC_EQX": "X",
        "LC_EQY": "Y",
    }

    # W absence remains separately unresolved;
    # it does not corrupt the proven E bindings.
    assert (
        "ROUTE_C_W_ACTION_SOURCE_NOT_PROVEN"
        in result.blockers
    )


def test_request_dtos_do_not_gain_w_engineering_truth():
    forbidden = {
        "wind_applicable",
        "w_applicability",
        "wind_required",
        "route_c_w_required",
    }

    for cls in (
        ColumnExecutionRequest,
        ProjectExecutionRequest,
    ):
        assert not (
            {
                item.name
                for item in fields(cls)
            }
            & forbidden
        )


def test_canonical_w_applicability_identity_constants():
    assert COLUMN_ROUTE_C_W_ACTION_FAMILY == "W"
    assert (
        COLUMN_ROUTE_C_SUPPORTED_PATH
        == "COLUMN/ROUTE_C"
    )

    assert (
        COLUMN_ROUTE_C_W_APPLICABILITY_BINDING
        .binding_id
        == COLUMN_ROUTE_C_W_APPLICABILITY_BINDING_ID
    )

    assert (
        COLUMN_ROUTE_C_W_APPLICABILITY_BINDING
        .input_type
        is ReviewedActionFamilyApplicability
    )
