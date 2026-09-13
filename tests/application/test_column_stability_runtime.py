from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_stability_runtime as runtime
from tbdy_engine.design.columns.stability_action_basis import TS500_LOAD_BASIS_GQE
from tbdy_engine.design.columns.stability_combo_basis import StabilityComboCandidate
from tbdy_engine.design.columns.stability_output_state import StabilityActionDirectionBinding
from tbdy_engine.design.columns.story_relative_translation import ReviewedStoryTranslationTolerance
from tbdy_engine.providers.etabs_story_stability_result_provider import EtabsStoryStabilityComboFact


class _Session:
    pass


class _Topology:
    pass


def _candidate():
    return StabilityComboCandidate(
        combo_name="STAB_GQE_X",
        load_basis=TS500_LOAD_BASIS_GQE,
        horizontal_action_role="E",
        horizontal_case_name="EX",
        horizontal_scale_factor=1.0,
        role_coefficients=(("E", 1.0), ("G", 1.0), ("Q", 1.0)),
        constituent_case_names=("G_CASE", "Q_CASE", "EX"),
        source_refs=("combo:STAB_GQE_X",),
    )


def _direction():
    return StabilityActionDirectionBinding(
        case_name="EX",
        global_direction="X",
        source_refs=("direction:EX:X",),
    )


def _population(output_state, second_delta=5.0001):
    def row(component_id, unique_name, delta):
        return SimpleNamespace(
            component_id=component_id,
            story="S1",
            column_unique_name=unique_name,
            output_name=output_state.output_name,
            global_direction=output_state.global_direction,
            output_state_ref=output_state.binding_ref,
            story_bottom_z_mm=0.0,
            story_top_z_mm=3000.0,
            signed_directional_delta_mm=delta,
            analysis_result_ref=output_state.analysis_result_ref,
            execution_proof_ref=output_state.execution_proof_ref,
            source_refs=(
                f"strict-topology:{unique_name}:bottom=P1",
                f"strict-topology:{unique_name}:top=P2",
                f"fact:{unique_name}",
            ),
        )

    return SimpleNamespace(
        rows=(row("COL1", "U1", 5.0), row("COL2", "U2", second_delta)),
        expected_column_unique_names=("U1", "U2"),
        source_refs=("population:jointdispl",),
    )


def _install_common(monkeypatch, *, second_delta=5.0001):
    monkeypatch.setattr(runtime, "EtabsVerifiedSession", _Session)
    monkeypatch.setattr(runtime, "StrictColumnTopologyBundle", _Topology)
    monkeypatch.setattr(
        runtime,
        "_qualified_b5_refs",
        lambda analysis_execution: ("analysis-result:1", "execution-proof:1"),
    )

    def capture_displacements(session, **kwargs):
        return _population(kwargs["output_state"], second_delta=second_delta)

    monkeypatch.setattr(
        runtime,
        "capture_column_end_displacement_population_from_session",
        capture_displacements,
    )


def test_composes_exact_candidate_through_existing_a14_a15_a16_authorities(monkeypatch):
    _install_common(monkeypatch)

    def capture_story_fact(session, **kwargs):
        return EtabsStoryStabilityComboFact(
            output_name=kwargs["output_name"],
            output_kind="combo",
            story=kwargs["story"],
            global_direction=kwargs["global_direction"],
            story_height_mm=3000.0,
            story_drift_rows=(),
            ts500_delta_d_mapping_status="NOT_USED_AS_TS500_DELTA_I",
            story_shear_n=100000.0,
            sum_column_axial_design_force_n=500000.0,
            analysis_result_ref=kwargs["analysis_result_ref"],
            execution_proof_ref=kwargs["execution_proof_ref"],
            source_refs=("story-force:S1", "column-force:S1"),
        )

    monkeypatch.setattr(
        runtime,
        "capture_story_stability_combo_fact_from_session",
        capture_story_fact,
    )

    result = runtime.compose_story_stability_candidate_runtime(
        _Session(),
        topology=_Topology(),
        analysis_execution=object(),
        candidate=_candidate(),
        direction_binding=_direction(),
        story="S1",
        reference_component_id="COL1",
        translation_tolerance=ReviewedStoryTranslationTolerance(
            absolute_tolerance_mm=0.01,
            source_ref="reviewed-tolerance:column-r1",
        ),
        reviewed_displacement_unit="mm",
        reviewed_force_unit="kN",
        uncracked_basis_refs=("analysis-basis:uncracked:qualified",),
    )

    assert result.status == "READY_FOR_TS500_STORY_SWAY_RESOLUTION"
    assert result.translation.proven
    assert result.stability_result is not None
    assert result.stability_result.phi == pytest.approx(0.0125)
    assert result.stability_result.proves_sway_prevented
    assert result.output_state.analysis_result_ref == "analysis-result:1"
    assert result.output_state.execution_proof_ref == "execution-proof:1"


def test_nonuniform_story_translation_is_explicit_unresolved_and_stops_before_eq713(monkeypatch):
    _install_common(monkeypatch, second_delta=7.0)

    def should_not_capture_story_fact(*args, **kwargs):
        raise AssertionError("Eq.7.13 operands must not be captured after nonuniform A15 resolution")

    monkeypatch.setattr(
        runtime,
        "capture_story_stability_combo_fact_from_session",
        should_not_capture_story_fact,
    )

    result = runtime.compose_story_stability_candidate_runtime(
        _Session(),
        topology=_Topology(),
        analysis_execution=object(),
        candidate=_candidate(),
        direction_binding=_direction(),
        story="S1",
        reference_component_id="COL1",
        translation_tolerance=ReviewedStoryTranslationTolerance(
            absolute_tolerance_mm=0.01,
            source_ref="reviewed-tolerance:column-r1",
        ),
        reviewed_displacement_unit="mm",
        reviewed_force_unit="kN",
        uncracked_basis_refs=("analysis-basis:uncracked:qualified",),
    )

    assert result.status == "EXPLICIT_UNRESOLVED_NONUNIFORM_STORY_TRANSLATION"
    assert not result.translation.proven
    assert result.story_fact is None
    assert result.stability_evidence is None
    assert result.stability_result is None
