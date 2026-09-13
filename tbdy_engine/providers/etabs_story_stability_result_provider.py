"""Factual ETABS result acquisition for TS500 story-stability composition.

The provider reads one already-existing ETABS output case/combo after the sole
B5 analysis generation.  It captures global story shear, StoryDrifts and the
full column-force population and binds those facts to the exact B5 result
identity/proof supplied by the application composer.

No TS500 load-basis matching, sway classification, effective-length math or
moment magnification is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

from tbdy_engine.etabs.oapi import fetch_display_table_for_output_from_session
from tbdy_engine.etabs.oapi.story_drift_results import read_story_drifts_from_session
from tbdy_engine.etabs.safety import EtabsVerifiedSession, RuntimeCaptureStatus
from tbdy_engine.features.column_shear_topology import (
    ColumnTopologyEvidence,
    StrictColumnTopologyBundle,
)
from tbdy_engine.providers.etabs_column_force_result_population_provider import (
    ColumnForcePopulationExpectation,
    capture_column_force_result_population_from_session,
)


TABLE_STORY_FORCES = "Story Forces"
STORY_STABILITY_FACT_AUTHORITY = "ETABS_B5_STORY_STABILITY_FACTS"


class StoryStabilityResultProviderError(RuntimeError):
    """Raised when exact post-B5 story-stability facts cannot be established."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise StoryStabilityResultProviderError(f"{label} must be a nonblank canonical string")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            result = float(value)  # ETABS table parser may preserve numeric strings.
        except (TypeError, ValueError) as exc:
            raise StoryStabilityResultProviderError(f"{label} must be numeric") from exc
    else:
        result = float(value)
    if not math.isfinite(result):
        raise StoryStabilityResultProviderError(f"{label} must be finite")
    return result


def _require_full(fetch, label: str) -> tuple[Mapping[str, Any], ...]:
    if fetch.capture_status is not RuntimeCaptureStatus.FULL:
        raise StoryStabilityResultProviderError(
            f"{label} requires FULL runtime capture; got {fetch.capture_status.value}"
        )
    rows = tuple(dict(row) for row in fetch.parsed.rows)
    reported = fetch.parsed.row_count_reported
    if reported is not None and len(rows) != int(reported):
        raise StoryStabilityResultProviderError(
            f"{label} FULL row mismatch: captured={len(rows)} reported={reported}"
        )
    if not rows:
        raise StoryStabilityResultProviderError(f"{label} returned no rows")
    return rows


def _restore_verified(fetch) -> bool:
    return any(
        item.get("phase") == "restore_verify" and item.get("success") is True
        for item in fetch.state_diagnostics
    )


def _field(row: Mapping[str, Any], names: Sequence[str], label: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    raise StoryStabilityResultProviderError(
        f"{label} missing required field; accepted aliases={tuple(names)}"
    )


def _story_height_mm(topology: StrictColumnTopologyBundle, story: str) -> tuple[float, tuple[str, ...]]:
    columns = tuple(item for item in topology.columns if item.story == story)
    if not columns:
        raise StoryStabilityResultProviderError(f"strict topology has no columns in story {story!r}")
    heights = tuple(abs(item.top_coord_m[2] - item.bottom_coord_m[2]) for item in columns)
    if any(value <= 0.0 or not math.isfinite(value) for value in heights):
        raise StoryStabilityResultProviderError(f"story {story!r} contains nonpositive column height")
    reference = heights[0]
    if any(not math.isclose(value, reference, rel_tol=1e-9, abs_tol=1e-6) for value in heights[1:]):
        raise StoryStabilityResultProviderError(
            f"story {story!r} column elevations do not prove one exact story height: {heights!r}"
        )
    refs = tuple(
        f"strict-topology:{item.unique_name}:z={item.bottom_coord_m[2]:.12g}->{item.top_coord_m[2]:.12g}"
        for item in columns
    )
    return reference * 1000.0, refs


def _bottom_station_row(
    column: ColumnTopologyEvidence,
    rows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    exact = tuple(row for row in rows if row.get("UniqueName") == column.unique_name)
    if not exact:
        raise StoryStabilityResultProviderError(
            f"combo column-force population lacks {column.unique_name!r}"
        )
    stations = tuple(_finite(row.get("Station"), f"{column.unique_name}.Station") for row in exact)
    point_i = column.connectivity_row.get("UniquePtI")
    point_j = column.connectivity_row.get("UniquePtJ")
    if point_i == column.joint_bottom and point_j == column.joint_top:
        target = min(stations)
    elif point_j == column.joint_bottom and point_i == column.joint_top:
        target = max(stations)
    else:
        raise StoryStabilityResultProviderError(
            f"column {column.unique_name!r} bottom/top joint identity is inconsistent with connectivity row"
        )
    matches = tuple(
        row for row in exact
        if math.isclose(_finite(row.get("Station"), "Station"), target, rel_tol=1e-9, abs_tol=1e-9)
    )
    if len(matches) != 1:
        raise StoryStabilityResultProviderError(
            f"column {column.unique_name!r} requires exactly one physical-bottom force row; got {len(matches)}"
        )
    return matches[0]


def _sum_story_axial_compression_n(
    topology: StrictColumnTopologyBundle,
    *,
    story: str,
    force_rows: Sequence[Mapping[str, Any]],
    force_unit: str,
) -> tuple[float, tuple[str, ...]]:
    if force_unit != "kN":
        raise StoryStabilityResultProviderError(
            "COLUMN-R1 current result-unit contract requires reviewed force_unit='kN'"
        )
    columns = tuple(item for item in topology.columns if item.story == story)
    if not columns:
        raise StoryStabilityResultProviderError(f"story {story!r} has no strict-topology columns")
    total_n = 0.0
    refs: list[str] = []
    for column in columns:
        row = _bottom_station_row(column, force_rows)
        # Existing Column demand normalization contract is factual ETABS
        # negative-compression P.  Preserve signed summation so a tensile
        # column reduces the story compression rather than being clipped.
        p_kn = _finite(row.get("P"), f"{column.unique_name}.P")
        total_n += -p_kn * 1000.0
        refs.append(
            f"ETABS:Element Forces - Columns:{column.unique_name}:physical-bottom:P={p_kn:.12g}kN"
        )
    if not math.isfinite(total_n) or total_n <= 0.0:
        raise StoryStabilityResultProviderError(
            f"story {story!r} summed design axial compression must be >0; got {total_n} N"
        )
    return total_n, tuple(refs)


def _story_shear_row(
    rows: Sequence[Mapping[str, Any]],
    *,
    output_name: str,
    story: str,
) -> Mapping[str, Any]:
    exact = []
    for row in rows:
        if row.get("Story") != story:
            continue
        output = row.get("OutputCase", row.get("Output Case"))
        if output != output_name:
            continue
        location = str(row.get("Location", "")).strip().casefold()
        if location and location != "bottom":
            continue
        exact.append(row)
    if len(exact) != 1:
        raise StoryStabilityResultProviderError(
            f"{TABLE_STORY_FORCES}@{output_name}/{story} requires exactly one Bottom row; got {len(exact)}"
        )
    return exact[0]


def _direction_from_story_shear(row: Mapping[str, Any]) -> tuple[str, float, float]:
    vx = _finite(_field(row, ("VX", "Vx"), "Story Forces"), "Story Forces.VX")
    vy = _finite(_field(row, ("VY", "Vy"), "Story Forces"), "Story Forces.VY")
    ax = abs(vx)
    ay = abs(vy)
    major = max(ax, ay)
    if major <= 1e-12:
        raise StoryStabilityResultProviderError("story shear vector is zero")
    minor = min(ax, ay)
    if minor > max(1e-9, 1e-6 * major):
        raise StoryStabilityResultProviderError(
            f"story shear does not prove a single global X/Y direction: VX={vx}, VY={vy}"
        )
    return ("X", vx, vy) if ax > ay else ("Y", vx, vy)


@dataclass(frozen=True, slots=True)
class EtabsStoryStabilityComboFact:
    output_name: str
    story: str
    global_direction: str
    story_height_mm: float
    drift_ratio_abs: float
    relative_story_displacement_mm: float
    story_shear_n: float
    sum_column_axial_design_force_n: float
    governing_drift_point_label: str
    analysis_result_ref: str
    execution_proof_ref: str
    source_refs: tuple[str, ...]
    authority: str = STORY_STABILITY_FACT_AUTHORITY


def capture_story_stability_combo_fact_from_session(
    session: EtabsVerifiedSession,
    *,
    output_name: str,
    story: str,
    topology: StrictColumnTopologyBundle,
    analysis_result_ref: str,
    execution_proof_ref: str,
    reviewed_force_unit: str,
    timeout_seconds: float = 30.0,
) -> EtabsStoryStabilityComboFact:
    """Capture one existing combo's exact post-B5 story stability facts."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    name = _text(output_name, "output_name")
    story_name = _text(story, "story")
    analysis_ref = _text(analysis_result_ref, "analysis_result_ref")
    proof_ref = _text(execution_proof_ref, "execution_proof_ref")
    if not isinstance(topology, StrictColumnTopologyBundle):
        raise TypeError("topology must be StrictColumnTopologyBundle")

    height_mm, height_refs = _story_height_mm(topology, story_name)

    story_forces = fetch_display_table_for_output_from_session(
        session,
        TABLE_STORY_FORCES,
        preferred_output_case=name,
        max_rows=None,
        timeout_seconds=timeout_seconds,
    )
    force_rows = _require_full(story_forces, f"{TABLE_STORY_FORCES}@{name}")
    if not _restore_verified(story_forces):
        raise StoryStabilityResultProviderError(
            f"{TABLE_STORY_FORCES}@{name} output-selection restoration did not verify"
        )
    shear_row = _story_shear_row(force_rows, output_name=name, story=story_name)
    direction, vx_kn, vy_kn = _direction_from_story_shear(shear_row)
    shear_kn = abs(vx_kn if direction == "X" else vy_kn)

    drift_fact = read_story_drifts_from_session(
        session,
        output_name=name,
        output_kind="combo",
        timeout_seconds=timeout_seconds,
    )
    drift_rows = tuple(
        row for row in drift_fact.rows
        if row.story == story_name and row.direction == direction
    )
    if not drift_rows:
        raise StoryStabilityResultProviderError(
            f"Results.StoryDrifts@{name}/{story_name}/{direction} returned no exact rows"
        )
    governing_drift = max(drift_rows, key=lambda row: (abs(row.drift), row.point_label))
    drift_ratio_abs = abs(governing_drift.drift)
    if not math.isfinite(drift_ratio_abs) or drift_ratio_abs < 0.0:
        raise StoryStabilityResultProviderError("governing StoryDrifts value is invalid")

    expectation = ColumnForcePopulationExpectation(
        expected_unique_names=tuple(item.unique_name for item in topology.columns),
        source_row_count=len(topology.columns),
    )
    column_forces = capture_column_force_result_population_from_session(
        session,
        case_name=name,
        expectation=expectation,
        timeout_seconds=timeout_seconds,
    )
    story_rows = tuple(row for row in column_forces.rows if row.get("Story") == story_name)
    sum_nd_n, axial_refs = _sum_story_axial_compression_n(
        topology,
        story=story_name,
        force_rows=story_rows,
        force_unit=reviewed_force_unit,
    )

    # CSI Results.StoryDrifts is the factual story-drift output.  The provider
    # carries its dimensionless drift value explicitly as a ratio and derives
    # Delta_d with the source-bound exact story height; no TS500 decision is
    # made here.
    delta_mm = drift_ratio_abs * height_mm
    refs = tuple(
        dict.fromkeys(
            (
                analysis_ref,
                proof_ref,
                *height_refs,
                f"ETABS:{TABLE_STORY_FORCES}:{name}:{story_name}:Bottom",
                drift_fact.evidence_ref,
                f"ETABS:Results.StoryDrifts:{name}:{story_name}:{direction}:{governing_drift.point_label}",
                column_forces.evidence_ref,
                *axial_refs,
            )
        )
    )
    return EtabsStoryStabilityComboFact(
        output_name=name,
        story=story_name,
        global_direction=direction,
        story_height_mm=height_mm,
        drift_ratio_abs=drift_ratio_abs,
        relative_story_displacement_mm=delta_mm,
        story_shear_n=shear_kn * 1000.0,
        sum_column_axial_design_force_n=sum_nd_n,
        governing_drift_point_label=governing_drift.point_label,
        analysis_result_ref=analysis_ref,
        execution_proof_ref=proof_ref,
        source_refs=refs,
    )


__all__ = [
    "EtabsStoryStabilityComboFact",
    "STORY_STABILITY_FACT_AUTHORITY",
    "StoryStabilityResultProviderError",
    "TABLE_STORY_FORCES",
    "capture_story_stability_combo_fact_from_session",
]
