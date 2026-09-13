"""Source-bound TS500 storey relative-translation promotion.

This module deliberately does not average, maximize, minimize or otherwise
aggregate a torsionally nonuniform column-end displacement population.  The
bounded fast path promotes TS500 ``Delta_i`` only when the complete expected
strict-topology column population proves one common signed storey translation
within an explicitly reviewed numerical equality tolerance.

The numerical tolerance proves only uniformity.  It never modifies the
engineering value: after uniformity is proven, the exact factual translation of
an independently identified reference component is retained as ``Delta_i``.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


STORY_TRANSLATION_AUTHORITY = "TS500_7.6.2.1_UNIFORM_STORY_TRANSLATION"
STATUS_PROVEN = "PROVEN_UNIFORM_STORY_RELATIVE_TRANSLATION"
STATUS_NONUNIFORM = "UNRESOLVED_NONUNIFORM_STORY_TRANSLATION"


class StoryRelativeTranslationError(ValueError):
    """Raised when a source-bound storey-translation contract is malformed."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise StoryRelativeTranslationError(f"{label} must be a nonblank canonical string")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StoryRelativeTranslationError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise StoryRelativeTranslationError(f"{label} must be finite numeric")
    return result


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    refs = tuple(_text(ref, label) for ref in values)
    if not refs or len(refs) != len(set(refs)):
        raise StoryRelativeTranslationError(f"{label} must be nonempty and unique")
    return refs


@dataclass(frozen=True, slots=True)
class ReviewedStoryTranslationTolerance:
    absolute_tolerance_mm: float
    source_ref: str

    def __post_init__(self) -> None:
        tolerance = _finite(self.absolute_tolerance_mm, "absolute_tolerance_mm")
        if tolerance < 0.0:
            raise StoryRelativeTranslationError("absolute_tolerance_mm must be >= 0")
        object.__setattr__(self, "absolute_tolerance_mm", tolerance)
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))


@dataclass(frozen=True, slots=True)
class ColumnStoryTranslationEvidence:
    component_id: str
    story: str
    column_unique_name: str
    output_name: str
    global_direction: str
    output_state_ref: str
    story_bottom_z_mm: float
    story_top_z_mm: float
    signed_relative_translation_mm: float
    analysis_result_ref: str
    execution_proof_ref: str
    direction_source_refs: tuple[str, ...]
    boundary_source_refs: tuple[str, ...]
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "component_id",
            "story",
            "column_unique_name",
            "output_name",
            "output_state_ref",
            "analysis_result_ref",
            "execution_proof_ref",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        direction = _text(self.global_direction, "global_direction")
        if direction not in {"X", "Y"}:
            raise StoryRelativeTranslationError("global_direction must be X or Y")
        object.__setattr__(self, "global_direction", direction)
        for name in (
            "story_bottom_z_mm",
            "story_top_z_mm",
            "signed_relative_translation_mm",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.story_top_z_mm <= self.story_bottom_z_mm:
            raise StoryRelativeTranslationError("story boundary elevations are invalid")
        object.__setattr__(
            self,
            "direction_source_refs",
            _refs(self.direction_source_refs, "direction_source_ref"),
        )
        object.__setattr__(
            self,
            "boundary_source_refs",
            _refs(self.boundary_source_refs, "boundary_source_ref"),
        )
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))


@dataclass(frozen=True, slots=True)
class StoryRelativeTranslationResolution:
    story: str
    output_name: str
    global_direction: str
    status: str
    reference_component_id: str
    signed_reference_translation_mm: float | None
    relative_story_displacement_mm: float | None
    population_min_mm: float
    population_max_mm: float
    population_spread_mm: float
    expected_column_count: int
    produced_column_count: int
    output_state_ref: str
    analysis_result_ref: str
    execution_proof_ref: str
    story_bottom_z_mm: float
    story_top_z_mm: float
    source_refs: tuple[str, ...]
    authority: str = STORY_TRANSLATION_AUTHORITY

    @property
    def proven(self) -> bool:
        return self.status == STATUS_PROVEN


def resolve_uniform_story_relative_translation(
    evidences: Sequence[ColumnStoryTranslationEvidence],
    *,
    story: str,
    output_name: str,
    global_direction: str,
    expected_column_unique_names: Sequence[str],
    reference_component_id: str,
    tolerance: ReviewedStoryTranslationTolerance,
) -> StoryRelativeTranslationResolution:
    """Promote one exact factual reference translation after population uniformity proof."""
    story_name = _text(story, "story")
    output = _text(output_name, "output_name")
    direction = _text(global_direction, "global_direction")
    if direction not in {"X", "Y"}:
        raise StoryRelativeTranslationError("global_direction must be X or Y")
    reference_component = _text(reference_component_id, "reference_component_id")
    if not isinstance(tolerance, ReviewedStoryTranslationTolerance):
        raise TypeError("tolerance must be ReviewedStoryTranslationTolerance")
    expected = tuple(sorted(_text(value, "expected_column_unique_name") for value in expected_column_unique_names))
    if not expected or len(expected) != len(set(expected)):
        raise StoryRelativeTranslationError("expected column identities must be nonempty and unique")

    rows = tuple(
        sorted(
            (
                item
                for item in evidences
                if item.story == story_name
                and item.output_name == output
                and item.global_direction == direction
            ),
            key=lambda item: item.column_unique_name,
        )
    )
    if not rows:
        raise StoryRelativeTranslationError("no exact column translations for requested story/output/direction")
    produced_names = tuple(row.column_unique_name for row in rows)
    if len(set(produced_names)) != len(produced_names):
        raise StoryRelativeTranslationError("duplicate column identity in translation evidence")
    if produced_names != expected:
        raise StoryRelativeTranslationError(
            "translation evidence does not exactly cover the expected strict-topology story population"
        )

    analysis_refs = {row.analysis_result_ref for row in rows}
    proof_refs = {row.execution_proof_ref for row in rows}
    state_refs = {row.output_state_ref for row in rows}
    bottoms = {row.story_bottom_z_mm for row in rows}
    tops = {row.story_top_z_mm for row in rows}
    if len(analysis_refs) != 1 or len(proof_refs) != 1:
        raise StoryRelativeTranslationError(
            "column translations do not share one B5 AnalysisResultIdentity/execution proof"
        )
    if len(state_refs) != 1:
        raise StoryRelativeTranslationError("column translations do not share one concurrent output state")
    if len(bottoms) != 1 or len(tops) != 1:
        raise StoryRelativeTranslationError("column translations do not share exact story boundaries")

    reference_rows = tuple(row for row in rows if row.component_id == reference_component)
    if len(reference_rows) != 1:
        raise StoryRelativeTranslationError(
            "reference_component_id must identify exactly one row in the complete story population"
        )
    reference = reference_rows[0].signed_relative_translation_mm
    values = tuple(row.signed_relative_translation_mm for row in rows)
    minimum = min(values)
    maximum = max(values)
    spread = maximum - minimum
    uniform = all(
        abs(value - reference) <= tolerance.absolute_tolerance_mm + 1e-12
        for value in values
    )
    common_refs = tuple(
        dict.fromkeys(
            (
                next(iter(analysis_refs)),
                next(iter(proof_refs)),
                next(iter(state_refs)),
                tolerance.source_ref,
                *(ref for row in rows for ref in row.direction_source_refs),
                *(ref for row in rows for ref in row.boundary_source_refs),
                *(ref for row in rows for ref in row.source_refs),
            )
        )
    )

    return StoryRelativeTranslationResolution(
        story=story_name,
        output_name=output,
        global_direction=direction,
        status=STATUS_PROVEN if uniform else STATUS_NONUNIFORM,
        reference_component_id=reference_component,
        signed_reference_translation_mm=reference if uniform else None,
        relative_story_displacement_mm=abs(reference) if uniform else None,
        population_min_mm=minimum,
        population_max_mm=maximum,
        population_spread_mm=spread,
        expected_column_count=len(expected),
        produced_column_count=len(rows),
        output_state_ref=next(iter(state_refs)),
        analysis_result_ref=next(iter(analysis_refs)),
        execution_proof_ref=next(iter(proof_refs)),
        story_bottom_z_mm=next(iter(bottoms)),
        story_top_z_mm=next(iter(tops)),
        source_refs=common_refs,
    )


__all__ = [
    "ColumnStoryTranslationEvidence",
    "ReviewedStoryTranslationTolerance",
    "STATUS_NONUNIFORM",
    "STATUS_PROVEN",
    "STORY_TRANSLATION_AUTHORITY",
    "StoryRelativeTranslationError",
    "StoryRelativeTranslationResolution",
    "resolve_uniform_story_relative_translation",
]
