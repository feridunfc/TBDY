"""Public VS-4B-A MDEV/Mo evidence API with a directional live-capture boundary.

The private core preserves the already-reviewed factual/mechanics implementation.
This public module deliberately overrides only the two acquisition entry points
whose live boundary must be one-direction-independent.
"""
from __future__ import annotations

from collections.abc import Sequence

from tbdy_engine.features import _etabs_mdev_mo_evidence_core as _core
from tbdy_engine.features._etabs_mdev_mo_evidence_core import *  # noqa: F401,F403

# Keep these names patchable at the public module boundary. Existing tests and
# live callers must not need to reach through the private implementation module.
fetch_display_table = _core.fetch_display_table
fetch_display_table_for_output = _core.fetch_display_table_for_output
process_local_acquisition_lock = _core.process_local_acquisition_lock


def capture_exact_output_case_table(
    database_tables: object,
    table_key: str,
    requested_case: str,
) -> ExactOutputCaseCapture:
    """Capture one FULL table/superset and isolate by factual OutputCase only."""
    fetched = fetch_display_table_for_output(
        database_tables,
        table_key,
        preferred_output_case=requested_case,
        max_rows=None,
    )
    status = _core._capture_status_value(fetched.capture_status)
    if status != _core.RuntimeCaptureStatus.FULL.value:
        raise MdevMoEvidenceError(
            f"{table_key}/{requested_case} capture is {status}, not FULL",
            status=BLOCKED_NON_FULL_ETABS_CAPTURE,
        )
    selection = dict(_core.to_jsonable(fetched.display_selection or {}))
    if not selection.get("display_selection_success") or not selection.get(
        "fetch_after_display_selection"
    ):
        raise MdevMoEvidenceError(
            f"{table_key}/{requested_case} temporary output selection was not verified",
            status=BLOCKED_FACTUAL_OUTPUT_CASE_IDENTITY,
        )
    rows = tuple(dict(_core.to_jsonable(row)) for row in fetched.parsed.rows)
    exact = isolate_exact_output_case_rows(rows, requested_case)
    snapshot, restore, restore_exact = _core._restore_metadata(fetched)
    if not restore_exact:
        raise MdevMoEvidenceError(
            f"{table_key}/{requested_case} output selection restore did not verify exactly",
            status=BLOCKED_FACTUAL_OUTPUT_CASE_IDENTITY,
        )
    return ExactOutputCaseCapture(
        table_key=table_key,
        actual_table_name=str(fetched.parsed.actual_table_name),
        requested_case=requested_case,
        return_code=fetched.parsed.return_code,
        reported_row_count=fetched.parsed.row_count_reported,
        captured_row_count=len(rows),
        capture_status=status,
        fetched_rows=rows,
        exact_rows=exact,
        selection_snapshot=snapshot,
        restore_result=restore,
        restore_exact_equality_result=restore_exact,
        state_diagnostics=tuple(
            dict(_core.to_jsonable(item)) for item in fetched.state_diagnostics
        ),
    )


def capture_live_mdev_mo_evidence(
    *,
    database_tables: object,
    model_fingerprint: str,
    direction: str,
    base_context: ReviewedRegulatoryBaseContext,
    wall_population: ReviewedDirectionalWallPopulation,
    result_context: ReviewedResultPopulationContext,
    case_names: Sequence[str],
    include_pier_labels: bool = True,
) -> LiveMdevMoEvidenceBundle:
    """Capture one coherent read-only evidence epoch for exactly one direction.

    The caller supplies one reviewed direction, one reviewed wall population for
    that direction, and exactly two exact eccentricity cases for that direction.
    The orthogonal direction is neither required nor inferred.
    """
    model_fingerprint = _core._nonblank(model_fingerprint, "model_fingerprint")
    direction = _core._direction(direction)
    if not isinstance(wall_population, ReviewedDirectionalWallPopulation):
        raise TypeError(
            "wall_population must be ReviewedDirectionalWallPopulation"
        )
    if wall_population.direction != direction:
        raise ValueError("wall population direction mismatch")
    cases = tuple(_core._nonblank(item, "case_name") for item in case_names)
    if len(cases) != 2 or len(set(cases)) != 2:
        raise ValueError(
            "one VS-4B-A direction requires exactly two exact eccentricity cases"
        )

    with process_local_acquisition_lock():
        pier_sections = capture_static_table(database_tables, PIER_SECTIONS_TABLE)
        pier_labels: StaticTableCapture | None = None
        if include_pier_labels:
            try:
                candidate = fetch_display_table(
                    database_tables,
                    PIER_LABELS_TABLE,
                    max_rows=None,
                )
                if (
                    _core._capture_status_value(candidate.capture_status)
                    == _core.RuntimeCaptureStatus.FULL.value
                ):
                    pier_labels = StaticTableCapture(
                        table_key=PIER_LABELS_TABLE,
                        actual_table_name=str(candidate.parsed.actual_table_name),
                        return_code=candidate.parsed.return_code,
                        reported_row_count=candidate.parsed.row_count_reported,
                        captured_row_count=len(candidate.parsed.rows),
                        capture_status=_core._capture_status_value(
                            candidate.capture_status
                        ),
                        rows=tuple(
                            dict(_core.to_jsonable(row))
                            for row in candidate.parsed.rows
                        ),
                    )
            except Exception:
                pier_labels = None

        base_captures: list[ExactOutputCaseCapture] = []
        pier_captures: list[ExactOutputCaseCapture] = []
        story_captures: list[ExactOutputCaseCapture] = []
        for case_name in cases:
            base_captures.append(
                capture_exact_output_case_table(
                    database_tables,
                    BASE_REACTIONS_TABLE,
                    case_name,
                )
            )
            pier_captures.append(
                capture_exact_output_case_table(
                    database_tables,
                    PIER_FORCES_TABLE,
                    case_name,
                )
            )
            story_captures.append(
                capture_exact_output_case_table(
                    database_tables,
                    STORY_FORCES_TABLE,
                    case_name,
                )
            )

    raw_for_epoch = {
        "direction": direction,
        "Pier Section Properties": [dict(row) for row in pier_sections.rows],
        "Base Reactions": {
            item.requested_case: [dict(row) for row in item.exact_rows]
            for item in base_captures
        },
        "Pier Forces": {
            item.requested_case: [dict(row) for row in item.exact_rows]
            for item in pier_captures
        },
        "Story Forces": {
            item.requested_case: [dict(row) for row in item.exact_rows]
            for item in story_captures
        },
    }
    evidence_epoch_id = _core._capture_epoch_id(
        model_fingerprint=model_fingerprint,
        raw_payload=raw_for_epoch,
    )
    base_by_case = {
        item.requested_case: item.exact_rows for item in base_captures
    }
    pier_by_case = {
        item.requested_case: item.exact_rows for item in pier_captures
    }
    story_by_case = {
        item.requested_case: item.exact_rows for item in story_captures
    }
    directional_evidence = build_directional_mdev_mo_evidence(
        direction=direction,
        evidence_epoch_id=evidence_epoch_id,
        model_fingerprint=model_fingerprint,
        case_names=cases,
        base_context=base_context,
        wall_population=wall_population,
        result_context=result_context,
        pier_sections=pier_sections.rows,
        pier_force_rows_by_case=pier_by_case,
        story_force_rows_by_case=story_by_case,
        base_reaction_rows_by_case=base_by_case,
    )
    return LiveMdevMoEvidenceBundle(
        evidence_epoch_id=evidence_epoch_id,
        model_fingerprint=model_fingerprint,
        directions=(directional_evidence,),
        base_reaction_captures=tuple(base_captures),
        pier_force_captures=tuple(pier_captures),
        story_force_captures=tuple(story_captures),
        pier_sections=pier_sections,
        pier_labels=pier_labels,
    )


__all__ = _core.__all__
