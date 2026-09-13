import pytest

from tbdy_engine.design.columns.story_relative_translation import (
    ColumnStoryTranslationEvidence,
    ReviewedStoryTranslationTolerance,
    STATUS_NONUNIFORM,
    STATUS_PROVEN,
    StoryRelativeTranslationError,
    resolve_uniform_story_relative_translation,
)


def _row(
    column,
    value,
    *,
    component=None,
    analysis="analysis:1",
    proof="proof:1",
    state="state:1",
    direction="X",
    z0=0.0,
    z1=3000.0,
):
    return ColumnStoryTranslationEvidence(
        component_id=component or f"S1:{column}:{column}",
        story="S1",
        column_unique_name=column,
        output_name="COMB_GQE_X",
        global_direction=direction,
        output_state_ref=state,
        story_bottom_z_mm=z0,
        story_top_z_mm=z1,
        signed_relative_translation_mm=value,
        analysis_result_ref=analysis,
        execution_proof_ref=proof,
        direction_source_refs=("factual-direction:EX:X",),
        boundary_source_refs=(f"story-boundary:{column}",),
        source_refs=(f"joint-displ:{column}",),
    )


def _tol(value=0.01):
    return ReviewedStoryTranslationTolerance(
        absolute_tolerance_mm=value,
        source_ref="reviewed-project-tolerance:story-translation",
    )


def _resolve(rows, *, reference="S1:C2:C2", tolerance=0.01):
    return resolve_uniform_story_relative_translation(
        rows,
        story="S1",
        output_name="COMB_GQE_X",
        global_direction="X",
        expected_column_unique_names=("C1", "C2", "C3"),
        reference_component_id=reference,
        tolerance=_tol(tolerance),
    )


def test_uniform_population_preserves_exact_reference_value_without_averaging():
    result = _resolve(
        (
            _row("C2", 12.004),
            _row("C1", 12.0),
            _row("C3", 12.006),
        )
    )
    assert result.status == STATUS_PROVEN
    # C2 is independently identified as the reference component.  Its exact
    # factual value is retained; no mean/max/min is used after uniformity proof.
    assert result.reference_component_id == "S1:C2:C2"
    assert result.signed_reference_translation_mm == pytest.approx(12.004)
    assert result.relative_story_displacement_mm == pytest.approx(12.004)
    assert result.population_spread_mm == pytest.approx(0.006)
    assert result.expected_column_count == 3
    assert result.produced_column_count == 3
    assert result.output_state_ref == "state:1"
    assert result.analysis_result_ref == "analysis:1"
    assert result.execution_proof_ref == "proof:1"


def test_uniform_negative_translation_promotes_nonnegative_delta_i_magnitude():
    rows = (
        _row("C1", -8.0),
        _row("C2", -8.0),
        _row("C3", -8.0),
    )
    result = _resolve(rows, tolerance=0.0)
    assert result.status == STATUS_PROVEN
    assert result.signed_reference_translation_mm == pytest.approx(-8.0)
    assert result.relative_story_displacement_mm == pytest.approx(8.0)


def test_nonuniform_population_remains_unresolved_no_average_or_max():
    result = _resolve(
        (_row("C1", 5.0), _row("C2", 8.0), _row("C3", 11.0)),
        tolerance=0.01,
    )
    assert result.status == STATUS_NONUNIFORM
    assert result.signed_reference_translation_mm is None
    assert result.relative_story_displacement_mm is None
    assert result.population_min_mm == pytest.approx(5.0)
    assert result.population_max_mm == pytest.approx(11.0)
    assert result.population_spread_mm == pytest.approx(6.0)


def test_population_must_exactly_cover_expected_columns():
    with pytest.raises(StoryRelativeTranslationError, match="exactly cover"):
        _resolve((_row("C1", 5.0), _row("C2", 5.0)))


def test_population_must_share_b5_analysis_identity():
    with pytest.raises(StoryRelativeTranslationError, match="one B5 AnalysisResultIdentity"):
        _resolve(
            (
                _row("C1", 5.0),
                _row("C2", 5.0, analysis="analysis:2"),
                _row("C3", 5.0),
            )
        )


def test_population_must_share_execution_proof():
    with pytest.raises(StoryRelativeTranslationError, match="execution proof"):
        _resolve(
            (
                _row("C1", 5.0),
                _row("C2", 5.0, proof="proof:2"),
                _row("C3", 5.0),
            )
        )


def test_population_must_share_one_concurrent_output_state():
    with pytest.raises(StoryRelativeTranslationError, match="one concurrent output state"):
        _resolve(
            (
                _row("C1", 5.0),
                _row("C2", 5.0, state="state:2"),
                _row("C3", 5.0),
            )
        )


def test_population_must_share_exact_story_boundaries():
    with pytest.raises(StoryRelativeTranslationError, match="exact story boundaries"):
        _resolve(
            (
                _row("C1", 5.0),
                _row("C2", 5.0, z0=1.0),
                _row("C3", 5.0),
            )
        )


def test_reference_component_must_be_in_population():
    with pytest.raises(StoryRelativeTranslationError, match="reference_component_id"):
        _resolve(
            (_row("C1", 5.0), _row("C2", 5.0), _row("C3", 5.0)),
            reference="S1:C9:C9",
        )


def test_reviewed_tolerance_rejects_negative_value():
    with pytest.raises(StoryRelativeTranslationError, match=">= 0"):
        _tol(-0.1)
