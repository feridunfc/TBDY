import pytest

from tbdy_engine.design.columns.story_relative_translation import (
    ColumnStoryTranslationEvidence,
    ReviewedStoryTranslationTolerance,
    STATUS_NONUNIFORM,
    STATUS_PROVEN,
    StoryRelativeTranslationError,
    resolve_uniform_story_relative_translation,
)


def _row(column, value, *, analysis="analysis:1", proof="proof:1", direction="X"):
    return ColumnStoryTranslationEvidence(
        component_id=f"S1:{column}:{column}",
        story="S1",
        column_unique_name=column,
        output_name="COMB_GQE_X",
        global_direction=direction,
        signed_relative_translation_mm=value,
        analysis_result_ref=analysis,
        execution_proof_ref=proof,
        source_refs=(f"joint-displ:{column}",),
    )


def _tol(value=0.01):
    return ReviewedStoryTranslationTolerance(
        absolute_tolerance_mm=value,
        source_ref="reviewed-project-tolerance:story-translation",
    )


def test_uniform_population_promotes_unique_story_translation_without_averaging():
    result = resolve_uniform_story_relative_translation(
        (_row("C2", 12.004), _row("C1", 12.0), _row("C3", 12.006)),
        story="S1",
        output_name="COMB_GQE_X",
        global_direction="X",
        tolerance=_tol(0.01),
    )
    assert result.status == STATUS_PROVEN
    # deterministic C1 reference after full-population uniformity proof; no mean/max promotion
    assert result.signed_reference_translation_mm == pytest.approx(12.0)
    assert result.relative_story_displacement_mm == pytest.approx(12.0)
    assert result.population_spread_mm == pytest.approx(0.006)
    assert result.column_count == 3
    assert result.analysis_result_ref == "analysis:1"
    assert result.execution_proof_ref == "proof:1"


def test_uniform_negative_translation_promotes_nonnegative_delta_i_magnitude():
    result = resolve_uniform_story_relative_translation(
        (_row("C1", -8.0), _row("C2", -8.0)),
        story="S1",
        output_name="COMB_GQE_X",
        global_direction="X",
        tolerance=_tol(0.0),
    )
    assert result.status == STATUS_PROVEN
    assert result.signed_reference_translation_mm == pytest.approx(-8.0)
    assert result.relative_story_displacement_mm == pytest.approx(8.0)


def test_nonuniform_population_remains_unresolved_no_average_or_max():
    result = resolve_uniform_story_relative_translation(
        (_row("C1", 5.0), _row("C2", 8.0), _row("C3", 11.0)),
        story="S1",
        output_name="COMB_GQE_X",
        global_direction="X",
        tolerance=_tol(0.01),
    )
    assert result.status == STATUS_NONUNIFORM
    assert result.signed_reference_translation_mm is None
    assert result.relative_story_displacement_mm is None
    assert result.population_min_mm == pytest.approx(5.0)
    assert result.population_max_mm == pytest.approx(11.0)
    assert result.population_spread_mm == pytest.approx(6.0)


def test_population_must_share_b5_analysis_identity():
    with pytest.raises(StoryRelativeTranslationError, match="one B5 AnalysisResultIdentity"):
        resolve_uniform_story_relative_translation(
            (_row("C1", 5.0), _row("C2", 5.0, analysis="analysis:2")),
            story="S1",
            output_name="COMB_GQE_X",
            global_direction="X",
            tolerance=_tol(),
        )


def test_population_must_share_execution_proof():
    with pytest.raises(StoryRelativeTranslationError, match="execution proof"):
        resolve_uniform_story_relative_translation(
            (_row("C1", 5.0), _row("C2", 5.0, proof="proof:2")),
            story="S1",
            output_name="COMB_GQE_X",
            global_direction="X",
            tolerance=_tol(),
        )


def test_reviewed_tolerance_rejects_negative_value():
    with pytest.raises(StoryRelativeTranslationError, match=">= 0"):
        _tol(-0.1)
