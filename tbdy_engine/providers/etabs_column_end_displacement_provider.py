"""Post-B5 factual column-end displacement population for TS500 sway evidence.

The provider joins strict factual column topology with exact
``Results.JointDispl`` point-object reads.  Signed top-minus-bottom translations
are materialized only after a source-bound signed/concurrent LINEAR_ADD output
state has been qualified by ``stability_output_state``.

This remains a factual provider: it does not choose a storey aggregation, does
not promote TS500 ``Delta_i``, does not classify sway, and never runs analysis.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from tbdy_engine.design.columns.stability_output_state import (
    SIGNED_LINEAR_ADD_STATE,
    StabilityConcurrentOutputStateBinding,
)
from tbdy_engine.etabs.oapi.joint_displacement_results import (
    JointDisplacementResultFact,
    JointDisplacementResultRow,
    read_joint_displ_from_session,
)
from tbdy_engine.etabs.safety import EtabsVerifiedSession
from tbdy_engine.features.column_shear_topology import (
    ColumnTopologyEvidence,
    StrictColumnTopologyBundle,
)


COLUMN_END_DISPLACEMENT_AUTHORITY = "ETABS_B5_COLUMN_END_DISPLACEMENT_FACTS"
POINT_OBJECT_BOUNDARY_SEMANTICS = "CSI_POINT_OBJECT_TRANSLATION_AT_EXACT_STORY_BOUNDARY"


class ColumnEndDisplacementProviderError(RuntimeError):
    """Raised when an exact post-B5 column-end displacement fact cannot be bound."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnEndDisplacementProviderError(f"{label} must be a nonblank canonical string")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnEndDisplacementProviderError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ColumnEndDisplacementProviderError(f"{label} must be finite numeric")
    return result


def _unit_scale_to_mm(unit: str) -> float:
    value = _text(unit, "reviewed_displacement_unit")
    if value == "m":
        return 1000.0
    if value == "mm":
        return 1.0
    raise ColumnEndDisplacementProviderError(
        "reviewed_displacement_unit must be explicitly 'm' or 'mm'"
    )


def _single_exact_state_row(
    fact: JointDisplacementResultFact,
    *,
    point: str,
    state: StabilityConcurrentOutputStateBinding,
) -> JointDisplacementResultRow:
    rows = tuple(
        row
        for row in fact.rows
        if row.point_object == point and row.load_case == state.output_name
    )
    if len(rows) != 1:
        raise ColumnEndDisplacementProviderError(
            f"JointDispl@{state.output_name}/{point} requires exactly one exact row for "
            f"the qualified concurrent state; got {len(rows)}"
        )
    row = rows[0]
    if row.step_type != state.required_step_type:
        raise ColumnEndDisplacementProviderError(
            f"JointDispl@{state.output_name}/{point} StepType={row.step_type!r} is not the "
            "qualified signed LINEAR_ADD state"
        )
    if not math.isclose(
        row.step_number,
        state.required_step_number,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ColumnEndDisplacementProviderError(
            f"JointDispl@{state.output_name}/{point} StepNum={row.step_number!r} differs "
            "from the qualified signed LINEAR_ADD state"
        )
    return row


def _story_boundaries_m(
    topology: StrictColumnTopologyBundle,
    story: str,
) -> tuple[float, float, tuple[ColumnTopologyEvidence, ...], tuple[str, ...]]:
    columns = tuple(column for column in topology.columns if column.story == story)
    if not columns:
        raise ColumnEndDisplacementProviderError(
            f"strict topology contains no columns for story {story!r}"
        )
    bottoms = tuple(_finite(column.bottom_coord_m[2], f"{column.unique_name}.bottom_z") for column in columns)
    tops = tuple(_finite(column.top_coord_m[2], f"{column.unique_name}.top_z") for column in columns)
    bottom = bottoms[0]
    top = tops[0]
    if any(not math.isclose(value, bottom, rel_tol=0.0, abs_tol=1e-9) for value in bottoms[1:]):
        raise ColumnEndDisplacementProviderError(
            f"story {story!r} columns do not share one exact bottom-joint elevation"
        )
    if any(not math.isclose(value, top, rel_tol=0.0, abs_tol=1e-9) for value in tops[1:]):
        raise ColumnEndDisplacementProviderError(
            f"story {story!r} columns do not share one exact top-joint elevation"
        )
    if top <= bottom:
        raise ColumnEndDisplacementProviderError(
            f"story {story!r} top-joint elevation must exceed bottom-joint elevation"
        )
    refs = tuple(
        f"strict-topology:{column.unique_name}:story-boundary:"
        f"{column.joint_bottom}@{column.bottom_coord_m[2]:.12g}->"
        f"{column.joint_top}@{column.top_coord_m[2]:.12g}"
        for column in columns
    )
    return bottom, top, columns, refs


@dataclass(frozen=True, slots=True)
class ColumnEndDisplacementFact:
    component_id: str
    story: str
    column_unique_name: str
    bottom_joint: str
    top_joint: str
    story_bottom_z_mm: float
    story_top_z_mm: float
    bottom_frame_end_offset_mm: float
    top_frame_end_offset_mm: float
    output_name: str
    output_kind: str
    global_direction: str
    output_state_ref: str
    output_state_semantics: str
    step_type: str
    step_number: float
    bottom_u1_mm: float
    bottom_u2_mm: float
    top_u1_mm: float
    top_u2_mm: float
    delta_column_x_mm: float
    delta_column_y_mm: float
    analysis_result_ref: str
    execution_proof_ref: str
    source_refs: tuple[str, ...]
    displacement_location_semantics: str = POINT_OBJECT_BOUNDARY_SEMANTICS
    authority: str = COLUMN_END_DISPLACEMENT_AUTHORITY

    def __post_init__(self) -> None:
        for name in (
            "component_id",
            "story",
            "column_unique_name",
            "bottom_joint",
            "top_joint",
            "output_name",
            "output_kind",
            "global_direction",
            "output_state_ref",
            "output_state_semantics",
            "analysis_result_ref",
            "execution_proof_ref",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.output_kind != "combo":
            raise ColumnEndDisplacementProviderError("supported stability displacement slice requires combo output")
        if self.global_direction not in {"X", "Y"}:
            raise ColumnEndDisplacementProviderError("global_direction must be X or Y")
        if self.output_state_semantics != SIGNED_LINEAR_ADD_STATE:
            raise ColumnEndDisplacementProviderError("unsupported output-state semantics")
        if self.displacement_location_semantics != POINT_OBJECT_BOUNDARY_SEMANTICS:
            raise ColumnEndDisplacementProviderError("unsupported displacement location semantics")
        for name in (
            "story_bottom_z_mm",
            "story_top_z_mm",
            "bottom_frame_end_offset_mm",
            "top_frame_end_offset_mm",
            "step_number",
            "bottom_u1_mm",
            "bottom_u2_mm",
            "top_u1_mm",
            "top_u2_mm",
            "delta_column_x_mm",
            "delta_column_y_mm",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.story_top_z_mm <= self.story_bottom_z_mm:
            raise ColumnEndDisplacementProviderError("story boundary elevations are invalid")
        refs = tuple(_text(ref, "source_ref") for ref in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ColumnEndDisplacementProviderError("source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)

    @property
    def signed_directional_delta_mm(self) -> float:
        return self.delta_column_x_mm if self.global_direction == "X" else self.delta_column_y_mm


@dataclass(frozen=True, slots=True)
class ColumnEndDisplacementPopulation:
    story: str
    output_name: str
    output_kind: str
    global_direction: str
    output_state_ref: str
    output_state_semantics: str
    story_bottom_z_mm: float
    story_top_z_mm: float
    rows: tuple[ColumnEndDisplacementFact, ...]
    expected_column_unique_names: tuple[str, ...]
    analysis_result_ref: str
    execution_proof_ref: str
    source_refs: tuple[str, ...]
    authority: str = COLUMN_END_DISPLACEMENT_AUTHORITY

    def __post_init__(self) -> None:
        story = _text(self.story, "story")
        output = _text(self.output_name, "output_name")
        analysis_ref = _text(self.analysis_result_ref, "analysis_result_ref")
        proof_ref = _text(self.execution_proof_ref, "execution_proof_ref")
        if self.output_kind != "combo":
            raise ColumnEndDisplacementProviderError("supported stability displacement slice requires combo output")
        if self.global_direction not in {"X", "Y"}:
            raise ColumnEndDisplacementProviderError("global_direction must be X or Y")
        if self.output_state_semantics != SIGNED_LINEAR_ADD_STATE:
            raise ColumnEndDisplacementProviderError("unsupported population output-state semantics")
        rows = tuple(sorted(self.rows, key=lambda row: row.column_unique_name))
        expected = tuple(sorted(_text(name, "expected_column_unique_name") for name in self.expected_column_unique_names))
        if not rows or not expected:
            raise ColumnEndDisplacementProviderError("column-end displacement population must be nonempty")
        if len(set(expected)) != len(expected):
            raise ColumnEndDisplacementProviderError("expected column identities must be unique")
        if tuple(row.column_unique_name for row in rows) != expected:
            raise ColumnEndDisplacementProviderError(
                "captured displacement population does not exactly cover expected strict-topology columns"
            )
        for row in rows:
            if (
                row.story != story
                or row.output_name != output
                or row.output_kind != self.output_kind
                or row.global_direction != self.global_direction
                or row.output_state_ref != self.output_state_ref
                or row.output_state_semantics != self.output_state_semantics
                or row.analysis_result_ref != analysis_ref
                or row.execution_proof_ref != proof_ref
                or not math.isclose(row.story_bottom_z_mm, self.story_bottom_z_mm, rel_tol=0.0, abs_tol=1e-9)
                or not math.isclose(row.story_top_z_mm, self.story_top_z_mm, rel_tol=0.0, abs_tol=1e-9)
            ):
                raise ColumnEndDisplacementProviderError(
                    "column-end displacement row identity/state differs from population identity"
                )
        object.__setattr__(self, "story", story)
        object.__setattr__(self, "output_name", output)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "expected_column_unique_names", expected)
        object.__setattr__(self, "analysis_result_ref", analysis_ref)
        object.__setattr__(self, "execution_proof_ref", proof_ref)
        refs = tuple(_text(ref, "source_ref") for ref in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ColumnEndDisplacementProviderError("population source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)


def _capture_column(
    session: EtabsVerifiedSession,
    *,
    column: ColumnTopologyEvidence,
    state: StabilityConcurrentOutputStateBinding,
    story_bottom_z_mm: float,
    story_top_z_mm: float,
    scale_to_mm: float,
    timeout_seconds: float,
) -> ColumnEndDisplacementFact:
    bottom_fact = read_joint_displ_from_session(
        session,
        point_object=column.joint_bottom,
        output_name=state.output_name,
        output_kind=state.output_kind,
        timeout_seconds=timeout_seconds,
    )
    top_fact = read_joint_displ_from_session(
        session,
        point_object=column.joint_top,
        output_name=state.output_name,
        output_kind=state.output_kind,
        timeout_seconds=timeout_seconds,
    )
    bottom = _single_exact_state_row(bottom_fact, point=column.joint_bottom, state=state)
    top = _single_exact_state_row(top_fact, point=column.joint_top, state=state)
    bottom_u1 = bottom.u1 * scale_to_mm
    bottom_u2 = bottom.u2 * scale_to_mm
    top_u1 = top.u1 * scale_to_mm
    top_u2 = top.u2 * scale_to_mm
    refs = tuple(
        dict.fromkeys(
            (
                state.analysis_result_ref,
                state.execution_proof_ref,
                state.binding_ref,
                *state.source_refs,
                bottom_fact.evidence_ref,
                top_fact.evidence_ref,
                f"strict-topology:{column.unique_name}:bottom={column.joint_bottom}",
                f"strict-topology:{column.unique_name}:top={column.joint_top}",
                f"strict-topology:{column.unique_name}:end-offsets="
                f"{column.offset_bottom_m:.12g},{column.offset_top_m:.12g}m",
                POINT_OBJECT_BOUNDARY_SEMANTICS,
            )
        )
    )
    return ColumnEndDisplacementFact(
        component_id=column.component_id,
        story=column.story,
        column_unique_name=column.unique_name,
        bottom_joint=column.joint_bottom,
        top_joint=column.joint_top,
        story_bottom_z_mm=story_bottom_z_mm,
        story_top_z_mm=story_top_z_mm,
        bottom_frame_end_offset_mm=column.offset_bottom_m * 1000.0,
        top_frame_end_offset_mm=column.offset_top_m * 1000.0,
        output_name=state.output_name,
        output_kind=state.output_kind,
        global_direction=state.global_direction,
        output_state_ref=state.binding_ref,
        output_state_semantics=state.state_semantics,
        step_type=bottom.step_type,
        step_number=bottom.step_number,
        bottom_u1_mm=bottom_u1,
        bottom_u2_mm=bottom_u2,
        top_u1_mm=top_u1,
        top_u2_mm=top_u2,
        delta_column_x_mm=top_u1 - bottom_u1,
        delta_column_y_mm=top_u2 - bottom_u2,
        analysis_result_ref=state.analysis_result_ref,
        execution_proof_ref=state.execution_proof_ref,
        source_refs=refs,
    )


def capture_column_end_displacement_population_from_session(
    session: EtabsVerifiedSession,
    *,
    topology: StrictColumnTopologyBundle,
    story: str,
    output_state: StabilityConcurrentOutputStateBinding,
    reviewed_displacement_unit: str,
    timeout_seconds: float = 30.0,
) -> ColumnEndDisplacementPopulation:
    """Capture complete exact-storey signed column-end translations.

    Every row is tied to one qualified concurrent output state and the same B5
    AnalysisResultIdentity/execution proof.  The provider intentionally stops at
    factual per-column deltas; TS500 ``Delta_i`` remains a downstream authority.
    """
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    if not isinstance(topology, StrictColumnTopologyBundle):
        raise TypeError("topology must be StrictColumnTopologyBundle")
    if not isinstance(output_state, StabilityConcurrentOutputStateBinding):
        raise TypeError("output_state must be StabilityConcurrentOutputStateBinding")
    if output_state.output_kind != "combo" or output_state.state_semantics != SIGNED_LINEAR_ADD_STATE:
        raise ColumnEndDisplacementProviderError(
            "column-end subtraction requires qualified signed concurrent LINEAR_ADD combo state"
        )
    story_name = _text(story, "story")
    scale = _unit_scale_to_mm(reviewed_displacement_unit)
    bottom_m, top_m, columns, boundary_refs = _story_boundaries_m(topology, story_name)
    bottom_mm = bottom_m * 1000.0
    top_mm = top_m * 1000.0

    rows = tuple(
        _capture_column(
            session,
            column=column,
            state=output_state,
            story_bottom_z_mm=bottom_mm,
            story_top_z_mm=top_mm,
            scale_to_mm=scale,
            timeout_seconds=timeout_seconds,
        )
        for column in columns
    )
    expected = tuple(sorted(column.unique_name for column in columns))
    refs = tuple(
        dict.fromkeys(
            (
                output_state.binding_ref,
                *output_state.source_refs,
                *boundary_refs,
                *(ref for row in rows for ref in row.source_refs),
            )
        )
    )
    return ColumnEndDisplacementPopulation(
        story=story_name,
        output_name=output_state.output_name,
        output_kind=output_state.output_kind,
        global_direction=output_state.global_direction,
        output_state_ref=output_state.binding_ref,
        output_state_semantics=output_state.state_semantics,
        story_bottom_z_mm=bottom_mm,
        story_top_z_mm=top_mm,
        rows=rows,
        expected_column_unique_names=expected,
        analysis_result_ref=output_state.analysis_result_ref,
        execution_proof_ref=output_state.execution_proof_ref,
        source_refs=refs,
    )


__all__ = [
    "COLUMN_END_DISPLACEMENT_AUTHORITY",
    "POINT_OBJECT_BOUNDARY_SEMANTICS",
    "ColumnEndDisplacementFact",
    "ColumnEndDisplacementPopulation",
    "ColumnEndDisplacementProviderError",
    "capture_column_end_displacement_population_from_session",
]
