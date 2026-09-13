"""Source-bound TS500 storey relative-translation promotion.

This module deliberately does not average or maximize a torsionally nonuniform
column-end displacement population.  It promotes a TS500 ``Delta_i`` only for
the bounded supported slice where every strict-topology column proves the same
signed global storey translation within an explicitly reviewed numerical
tolerance.  Nonuniform populations remain unresolved for another reviewed
aggregation/proof route.
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
    signed_relative_translation_mm: float
    analysis_result_ref: str
    execution_proof_ref: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "component_id",
            "story",
            "column_unique_name",
            "output_name",
            "analysis_result_ref",
            "execution_proof_ref",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        direction = _text(self.global_direction, "global_direction")
        if direction not in {"X", "Y"}:
            raise StoryRelativeTranslationError("global_direction must be X or Y")
        object.__setattr__(self, "global_direction", direction)
        object.__setattr__(
            self,
            "signed_relative_translation_mm",
            _finite(self.signed_relative_translation_mm, "signed_relative_translation_mm"),
        )
        refs = tuple(_text(ref, "source_ref") for ref in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise StoryRelativeTranslationError("source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)


@dataclass(frozen=True, slots=True)
class StoryRelativeTranslationResolution:
    story: str
    output_name: str
    global_direction: str
    status: str
    signed_reference_translation_mm: float | None
    relative_story_displacement_mm: float | None
    population_min_mm: float
    population_max_mm: float
    population_spread_mm: float
    column_count: int
    analysis_result_ref: str
    execution_proof_ref: str
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
    tolerance: ReviewedStoryTranslationTolerance,
) -> StoryRelativeTranslationResolution:
    """Promote one storey translation only when the full column population agrees.

    ``signed_reference_translation_mm`` is the deterministic translation of the
    lexicographically first column after the full-population uniformity proof.
    It is not an average/max/min engineering aggregation.  Once all values are
    within the reviewed tolerance, each row represents the same supported-scope
    storey translation to that reviewed numerical resolution.
    """
    story_name = _text(story, "story")
    output = _text(output_name, "output_name")
    direction = _text(global_direction, "global_direction")
    if direction not in {"X", "Y"}:
        raise StoryRelativeTranslationError("global_direction must be X or Y")
    if not isinstance(tolerance, ReviewedStoryTranslationTolerance):
        raise TypeError("tolerance must be ReviewedStoryTranslationTolerance")

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
    if len({row.column_unique_name for row in rows}) != len(rows):
        raise StoryRelativeTranslationError("duplicate column identity in translation evidence")
    analysis_refs = {row.analysis_result_ref for row in rows}
    proof_refs = {row.execution_proof_ref for row in rows}
    if len(analysis_refs) != 1 or len(proof_refs) != 1:
        raise StoryRelativeTranslationError(
            "column translations do not share one B5 AnalysisResultIdentity/execution proof"
        )

    values = tuple(row.signed_relative_translation_mm for row in rows)
    minimum = min(values)
    maximum = max(values)
    spread = maximum - minimum
    common_refs = tuple(
        dict.fromkeys(
            (
                next(iter(analysis_refs)),
                next(iter(proof_refs)),
                tolerance.source_ref,
                *(ref for row in rows for ref in row.source_refs),
            )
        )
    )
    if spread > tolerance.absolute_tolerance_mm + 1e-12:
        return StoryRelativeTranslationResolution(
            story=story_name,
            output_name=output,
            global_direction=direction,
            status=STATUS_NONUNIFORM,
            signed_reference_translation_mm=None,
            relative_story_displacement_mm=None,
            population_min_mm=minimum,
            population_max_mm=maximum,
            population_spread_mm=spread,
            column_count=len(rows),
            analysis_result_ref=next(iter(analysis_refs)),
            execution_proof_ref=next(iter(proof_refs)),
            source_refs=common_refs,
        )

    reference = rows[0].signed_relative_translation_mm
    return StoryRelativeTranslationResolution(
        story=story_name,
        output_name=output,
        global_direction=direction,
        status=STATUS_PROVEN,
        signed_reference_translation_mm=reference,
        relative_story_displacement_mm=abs(reference),
        population_min_mm=minimum,
        population_max_mm=maximum,
        population_spread_mm=spread,
        column_count=len(rows),
        analysis_result_ref=next(iter(analysis_refs)),
        execution_proof_ref=next(iter(proof_refs)),
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
