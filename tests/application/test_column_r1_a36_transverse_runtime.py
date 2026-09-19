from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_execution as subject
from tbdy_engine.checks.column_axial_selection import (
    ColumnDemandAvailability,
)
from tbdy_engine.regulatory.vs5_column_axial_program import (
    ReviewedVs5ColumnAxialContext,
)


COMPONENT = "Story1:C1:10"
MODEL = "model:a36"
EPOCH = "epoch:a36"


def _column():
    selected = SimpleNamespace(
        selected_rebar_ref="engine-selected-rebar:a36",
    )
    return subject.ColumnDomainArtifact(
        component_id=COMPONENT,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        status=subject.STATUS_SELECTED,
        blockers=(),
        longitudinal_selection=SimpleNamespace(
            selected_rebar=selected,
        ),
    )


def _runtime(*, pattern=1):
    target = SimpleNamespace(
        component_id=COMPONENT,
        unique_name="10",
        story="Story1",
        section="C40x60",
        width_t2_m=0.4,
        depth_t3_m=0.6,
        analysis_clear_length_candidate_m=3.0,
    )

    intent = SimpleNamespace(
        pattern=pattern,
        cover_mm=40.0,
        tie_size_name="T8",
        number_2_dir_tie_bars=3,
        number_3_dir_tie_bars=4,
    )

    basis = SimpleNamespace(
        component_id=COMPONENT,
        material_context=SimpleNamespace(
            material=SimpleNamespace(fck_mpa=30.0),
        ),
        transverse_basis_blockers=(),
        transverse_fywk_mpa=420.0,
        transverse_fywd_mpa=365.0,
        high_ductility_applies=True,
        limited_ductility_applies=False,
        source_refs=("basis:column:a36",),
        transverse_basis_refs=("basis:transverse:a36",),
    )

    selection = SimpleNamespace(
        selected=True,
        selected_rebar=SimpleNamespace(
            selected_rebar_ref="engine-selected-rebar:a36",
        ),
    )

    return SimpleNamespace(
        component_id=COMPONENT,
        target_topology=target,
        rebar_intent=intent,
        bound_design_basis=basis,
        tie_diameter_mm=8.0,
        tie_catalog_ref="rebar-catalog:T8",
        selection=selection,
    )


def test_longitudinal_runtime_contract_retains_tie_catalog_fact() -> None:
    fields = subject.ColumnLongitudinalRuntimeComposition.__dataclass_fields__
    assert "tie_diameter_mm" in fields
    assert "tie_catalog_ref" in fields


def test_a36_core_geometry_does_not_promote_design_intent_to_provided_ash(monkeypatch) -> None:
    runtime = _runtime()
    column = _column()

    reviewed = object.__new__(ReviewedVs5ColumnAxialContext)

    evidence = SimpleNamespace(
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
    )

    monkeypatch.setattr(
        subject,
        "capture_b5_bound_column_axial_evidence",
        lambda **_kwargs: evidence,
    )

    nd = SimpleNamespace(
        availability=ColumnDemandAvailability.RESOLVED,
        demand_kn=500.0,
        provenance=("vs5:ts500-nd:row",),
    )

    monkeypatch.setattr(
        subject,
        "run_vs5_column_axial",
        lambda **_kwargs: SimpleNamespace(ts500_demand=nd),
    )

    # bypass attribute lookup on the uninitialized typed context
    monkeypatch.setattr(
        ReviewedVs5ColumnAxialContext,
        "tbdy_7312_high_ductility_applies",
        None,
        raising=False,
    )

    result = subject._compose_a36_transverse_input(
        column=column,
        runtime=runtime,
        acquisition_context=SimpleNamespace(
            verified_session=object(),
            session_provenance_ref="session:a36",
        ),
        analysis_execution=object(),
        topology=object(),
        flattened_combos=(),
        controlled_design_result=SimpleNamespace(
            design_result_identity=SimpleNamespace(
                identity_ref="design-result:a36",
            ),
        ),
        reviewed_vs5_column_axial_context=reviewed,
    )

    assert result.gross_area_ac_mm2 == pytest.approx(400.0 * 600.0)

    assert result.confined_core_area_ack_mm2 == pytest.approx(
        (400.0 - 80.0) * (600.0 - 80.0)
    )

    by_dir = {item.direction: item for item in result.directions}

    assert by_dir["DIR2"].confined_core_width_bk_mm == pytest.approx(
        400.0 - 80.0 - 8.0
    )
    assert by_dir["DIR3"].confined_core_width_bk_mm == pytest.approx(
        600.0 - 80.0 - 8.0
    )

    # GetRebarColumn tie-leg counts are factual design-intent/check-input
    # evidence only. The provider explicitly does not grant final/provided
    # reinforcement authority, so production must not fabricate provided Ash.
    assert by_dir["DIR2"].provided_ash_mm2 is None
    assert by_dir["DIR3"].provided_ash_mm2 is None

    assert all(
        "Number2DirTieBars" not in ref
        and "Number3DirTieBars" not in ref
        for item in result.directions
        for ref in item.source_refs
    )

    assert result.axial_design_force_nd_n == pytest.approx(500000.0)
    assert any(
        ref.startswith("VS5:TS500_ND:")
        for ref in result.source_refs
    )
    assert "vs5:ts500-nd:row" in result.source_refs

    # GetRebarColumn TieSize remains design-intent geometry evidence only.
    # It is not promoted into final/provided transverse cage authority.
    assert result.transverse_diameter_mm is None

    # A36 must not collapse Ash into A37 shear Asw.
    assert all(
        item.provided_asw_mm2 is None
        for item in result.directions
    )

    # Unproven detailing facts remain unresolved.
    assert result.cantilever_column is None
    assert result.confinement_spacing_mm is None
    assert result.middle_spacing_mm is None
    assert result.provided_confinement_region_length_mm is None


def test_a36_rejects_non_rectangular_pattern() -> None:
    reviewed = object.__new__(ReviewedVs5ColumnAxialContext)

    with pytest.raises(
        subject.ColumnExecutionContractError,
        match="rectangular rebar pattern",
    ):
        subject._compose_a36_transverse_input(
            column=_column(),
            runtime=_runtime(pattern=2),
            acquisition_context=SimpleNamespace(
                verified_session=object(),
                session_provenance_ref="session:a36",
            ),
            analysis_execution=object(),
            topology=object(),
            flattened_combos=(),
            controlled_design_result=SimpleNamespace(
                design_result_identity=SimpleNamespace(
                    identity_ref="design-result:a36",
                )
            ),
            reviewed_vs5_column_axial_context=reviewed,
        )


def test_a36_none_reviewed_context_does_not_invent_policy(
    monkeypatch,
) -> None:
    column = _column()

    monkeypatch.setattr(
        subject,
        "_compose_a36_transverse_input",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("A36 must not execute"),
        ),
    )

    result = subject._continue_selected_column_into_a36(
        column,
        runtime=_runtime(),
        acquisition_context=object(),
        analysis_execution=object(),
        topology=object(),
        flattened_combos=(),
        controlled_design_result=object(),
        reviewed_vs5_column_axial_context=None,
    )

    assert result is not column
    assert result.status == subject.STATUS_APPLICATION_BLOCKED
    assert result.selected_rebar is column.selected_rebar
    assert result.controlled_design_result is column.controlled_design_result
    assert result.transverse_confinement is None
    assert (
        "TRANSVERSE_CONFINEMENT_PRODUCTION_NOT_CLOSED:"
        "REVIEWED_VS5_COLUMN_AXIAL_CONTEXT_NOT_AVAILABLE"
        in result.blockers
    )


def test_a36_does_not_change_request_dtos() -> None:
    from dataclasses import fields
    from tbdy_engine.application.contracts import (
        ColumnExecutionRequest,
        ProjectExecutionRequest,
    )

    forbidden = {
        "reviewed_vs5_column_axial_context",
        "transverse_input",
        "confined_core_area_ack_mm2",
        "axial_design_force_nd_n",
    }

    assert forbidden.isdisjoint(
        {x.name for x in fields(ColumnExecutionRequest)}
    )
    assert forbidden.isdisjoint(
        {x.name for x in fields(ProjectExecutionRequest)}
    )
