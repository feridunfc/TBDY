"""Post-B5 factual column-end displacement population for TS500 sway evidence.

The provider joins strict factual column topology with exact
``Results.JointDispl`` point-object reads. It computes signed global X/Y
relative translations for every column in one exact storey/output combination.
No storey aggregation, TS500 sway classification, or analysis execution occurs
here.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

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


class ColumnEndDisplacementProviderError(RuntimeError):
    """Raised when an exact post-B5 column-end displacement fact cannot be bound."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnEndDisplacementProviderError(f"{label} must be a nonblank canonical string")
    return value


def _unit_scale_to_mm(unit: str) -> float:
    value = _text(unit, "reviewed_displacement_unit")
    if value == "m":
        return 1000.0
    if value == "mm":
        return 1.0
    raise ColumnEndDisplacementProviderError(
        "reviewed_displacement_unit must be explicitly 'm' or 'mm'"
    )


def _single_exact_row(
    fact: JointDisplacementResultFact,
    *,
    point: str,
    output_name: str,
) -> JointDisplacementResultRow:
    rows = tuple(
        row
        for row in fact.rows
        if row.point_object == point and row.load_case == output_name
    )
    if len(rows) != 1:
        raise ColumnEndDisplacementProviderError(
            f"JointDispl@{output_name}/{point} requires exactly one exact row for "
            f"the supported static-combo slice; got {len(rows)}"
        )
    return rows[0]


@dataclass(frozen=True, slots=True)
class ColumnEndDisplacementFact:
    component_id: str
    story: str
    column_unique_name: str
    bottom_joint: str
    top_joint: str
    output_name: str
    output_kind: str
    bottom_u1_mm: float
    bottom_u2_mm: float
    top_u1_mm: float
    top_u2_mm: float
    delta_column_x_mm: float
    delta_column_y_mm: float
    analysis_result_ref: str
    execution_proof_ref: str
    source_refs: tuple[str, ...]
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
            "analysis_result_ref",
            "execution_proof_ref",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.output_kind not in {"case", "combo"}:
            raise ColumnEndDisplacementProviderError("output_kind must be case or combo")
        for name in (
            "bottom_u1_mm",
            "bottom_u2_mm",
            "top_u1_mm",
            "top_u2_mm",
            "delta_column_x_mm",
            "delta_column_y_mm",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ColumnEndDisplacementProviderError(f"{name} must be finite")
            object.__setattr__(self, name, value)
        refs = tuple(_text(ref, "source_ref") for ref in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ColumnEndDisplacementProviderError("source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)


@dataclass(frozen=True, slots=True)
class ColumnEndDisplacementPopulation:
    story: str
    output_name: str
    output_kind: str
    rows: tuple[ColumnEndDisplacementFact, ...]
    analysis_result_ref: str
    execution_proof_ref: str
    source_refs: tuple[str, ...]
    authority: str = COLUMN_END_DISPLACEMENT_AUTHORITY

    def __post_init__(self) -> None:
        story = _text(self.story, "story")
        output = _text(self.output_name, "output_name")
        analysis_ref = _text(self.analysis_result_ref, "analysis_result_ref")
        proof_ref = _text(self.execution_proof_ref, "execution_proof_ref")
        if self.output_kind not in {"case", "combo"}:
            raise ColumnEndDisplacementProviderError("output_kind must be case or combo")
        rows = tuple(sorted(self.rows, key=lambda row: row.column_unique_name))
        if not rows:
            raise ColumnEndDisplacementProviderError("column-end displacement population must be nonempty")
        if len({row.column_unique_name for row in rows}) != len(rows):
            raise ColumnEndDisplacementProviderError("duplicate column identity in displacement population")
        for row in rows:
            if (
                row.story != story
                or row.output_name != output
                or row.output_kind != self.output_kind
                or row.analysis_result_ref != analysis_ref
                or row.execution_proof_ref != proof_ref
            ):
                raise ColumnEndDisplacementProviderError(
                    "column-end displacement row identity differs from population identity"
                )
        object.__setattr__(self, "story", story)
        object.__setattr__(self, "output_name", output)
        object.__setattr__(self, "rows", rows)
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
    output_name: str,
    output_kind: str,
    analysis_result_ref: str,
    execution_proof_ref: str,
    scale_to_mm: float,
    timeout_seconds: float,
) -> ColumnEndDisplacementFact:
    bottom_fact = read_joint_displ_from_session(
        session,
        point_object=column.joint_bottom,
        output_name=output_name,
        output_kind=output_kind,
        timeout_seconds=timeout_seconds,
    )
    top_fact = read_joint_displ_from_session(
        session,
        point_object=column.joint_top,
        output_name=output_name,
        output_kind=output_kind,
        timeout_seconds=timeout_seconds,
    )
    bottom = _single_exact_row(
        bottom_fact,
        point=column.joint_bottom,
        output_name=output_name,
    )
    top = _single_exact_row(
        top_fact,
        point=column.joint_top,
        output_name=output_name,
    )
    bottom_u1 = bottom.u1 * scale_to_mm
    bottom_u2 = bottom.u2 * scale_to_mm
    top_u1 = top.u1 * scale_to_mm
    top_u2 = top.u2 * scale_to_mm
    refs = tuple(
        dict.fromkeys(
            (
                analysis_result_ref,
                execution_proof_ref,
                bottom_fact.evidence_ref,
                top_fact.evidence_ref,
                f"strict-topology:{column.unique_name}:bottom={column.joint_bottom}",
                f"strict-topology:{column.unique_name}:top={column.joint_top}",
            )
        )
    )
    return ColumnEndDisplacementFact(
        component_id=column.component_id,
        story=column.story,
        column_unique_name=column.unique_name,
        bottom_joint=column.joint_bottom,
        top_joint=column.joint_top,
        output_name=output_name,
        output_kind=output_kind,
        bottom_u1_mm=bottom_u1,
        bottom_u2_mm=bottom_u2,
        top_u1_mm=top_u1,
        top_u2_mm=top_u2,
        delta_column_x_mm=top_u1 - bottom_u1,
        delta_column_y_mm=top_u2 - bottom_u2,
        analysis_result_ref=analysis_result_ref,
        execution_proof_ref=execution_proof_ref,
        source_refs=refs,
    )


def capture_column_end_displacement_population_from_session(
    session: EtabsVerifiedSession,
    *,
    topology: StrictColumnTopologyBundle,
    story: str,
    output_name: str,
    output_kind: str = "combo",
    analysis_result_ref: str,
    execution_proof_ref: str,
    reviewed_displacement_unit: str,
    timeout_seconds: float = 30.0,
) -> ColumnEndDisplacementPopulation:
    """Capture the complete exact-storey column-end displacement population.

    The same ``analysis_result_ref`` and ``execution_proof_ref`` are retained on
    every row. Missing/duplicate point rows fail closed; no averaging, maximum,
    or TS500 storey-displacement promotion occurs in this provider.
    """
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    if not isinstance(topology, StrictColumnTopologyBundle):
        raise TypeError("topology must be StrictColumnTopologyBundle")
    story_name = _text(story, "story")
    name = _text(output_name, "output_name")
    kind = _text(output_kind, "output_kind")
    if kind not in {"case", "combo"}:
        raise ColumnEndDisplacementProviderError("output_kind must be case or combo")
    analysis_ref = _text(analysis_result_ref, "analysis_result_ref")
    proof_ref = _text(execution_proof_ref, "execution_proof_ref")
    scale = _unit_scale_to_mm(reviewed_displacement_unit)

    columns = tuple(column for column in topology.columns if column.story == story_name)
    if not columns:
        raise ColumnEndDisplacementProviderError(
            f"strict topology contains no columns for story {story_name!r}"
        )
    rows = tuple(
        _capture_column(
            session,
            column=column,
            output_name=name,
            output_kind=kind,
            analysis_result_ref=analysis_ref,
            execution_proof_ref=proof_ref,
            scale_to_mm=scale,
            timeout_seconds=timeout_seconds,
        )
        for column in columns
    )
    if {row.column_unique_name for row in rows} != {column.unique_name for column in columns}:
        raise ColumnEndDisplacementProviderError(
            "captured displacement population does not exactly cover strict-topology story columns"
        )
    refs = tuple(dict.fromkeys(ref for row in rows for ref in row.source_refs))
    return ColumnEndDisplacementPopulation(
        story=story_name,
        output_name=name,
        output_kind=kind,
        rows=rows,
        analysis_result_ref=analysis_ref,
        execution_proof_ref=proof_ref,
        source_refs=refs,
    )


__all__ = [
    "COLUMN_END_DISPLACEMENT_AUTHORITY",
    "ColumnEndDisplacementFact",
    "ColumnEndDisplacementPopulation",
    "ColumnEndDisplacementProviderError",
    "capture_column_end_displacement_population_from_session",
]
