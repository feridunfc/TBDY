"""COLUMN-R1 A16 -> A17 live sway composition.

Application owns only sequencing/identity joins here.  The TS500 unfavorable
load-basis resolution remains in ``sway_stability`` and global-X/Y -> local
M2/M3 mapping remains in ``local_axis_sway_binding``.

No sway-permitted state is manufactured by this seam.  If Eq.7.13 does not
positively prove sway prevention for every global direction contributing to a
local bending axis, the local classification remains unresolved for downstream
second-order composition.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.design.columns.local_axis_sway_binding import (
    ColumnLocalAxisSwayBinding,
    GlobalSwayDirectionEvidence,
    LOCAL_SWAY_PREVENTED,
    bind_global_sway_to_column_local_axes,
)
from tbdy_engine.design.columns.sway_stability import (
    StorySwayStabilityResolution,
    resolve_ts500_story_sway_from_stability_indices,
)
from tbdy_engine.features.column_shear_topology import StrictColumnTopologyBundle


STATUS_READY = "READY_LOCAL_AXIS_SWAY_BINDING"
STATUS_UNRESOLVED = "UNRESOLVED_LOCAL_AXIS_SWAY_CLASSIFICATION"


class ColumnLocalSwayRuntimeError(RuntimeError):
    """Raised when A16 evidence cannot be joined to exact factual local axes."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnLocalSwayRuntimeError(f"{label} must be a nonblank canonical string")
    return value


def _target_column(topology: StrictColumnTopologyBundle, component_id: str):
    if not isinstance(topology, StrictColumnTopologyBundle):
        raise TypeError("topology must be StrictColumnTopologyBundle")
    component = _text(component_id, "component_id")
    matches = tuple(item for item in topology.columns if item.component_id == component)
    if len(matches) != 1:
        raise ColumnLocalSwayRuntimeError(
            f"expected exactly one strict-topology Column for {component!r}; got {len(matches)}"
        )
    column = matches[0]
    if column.local_axis_angle_deg is None:
        raise ColumnLocalSwayRuntimeError(
            "strict topology does not expose a factual local-axis angle for A17"
        )
    return column


def _resolve_direction(
    candidate_runtimes: Sequence[object],
    *,
    story: str,
    direction: str,
) -> StorySwayStabilityResolution:
    evidences = tuple(
        item.stability_evidence
        for item in candidate_runtimes
        if getattr(item, "story", None) == story
        and getattr(item, "global_direction", None) == direction
        and getattr(item, "stability_evidence", None) is not None
    )
    try:
        return resolve_ts500_story_sway_from_stability_indices(
            evidences,
            story=story,
            direction=direction,
        )
    except Exception as exc:
        raise ColumnLocalSwayRuntimeError(
            f"A16 global {direction} sway resolution failed closed: {exc}"
        ) from exc


@dataclass(frozen=True, slots=True)
class ColumnLocalAxisSwayRuntime:
    component_id: str
    story: str
    global_x: StorySwayStabilityResolution
    global_y: StorySwayStabilityResolution
    local_binding: ColumnLocalAxisSwayBinding
    status: str
    source_refs: tuple[str, ...]

    @property
    def local_sway_resolved(self) -> bool:
        """Whether A17 produced positive local-axis sway-prevented classifications.

        This property is intentionally scoped to A17 only.  A17 is not, by
        itself, FND-COL-2 readiness; A18-A23 still have to close.
        """
        return self.status == STATUS_READY


def compose_column_local_axis_sway_runtime(
    *,
    topology: StrictColumnTopologyBundle,
    component_id: str,
    story: str,
    candidate_runtimes: Sequence[object],
    projection_tolerance: float = 1.0e-10,
) -> ColumnLocalAxisSwayRuntime:
    """Resolve A16 X/Y evidence and bind it to the Column's factual M2/M3 axes.

    ``candidate_runtimes`` are the already composed A14-A16 candidate artifacts.
    The existing sway owner selects the unfavorable required TS500 load basis.
    The existing local-axis owner then projects those global classifications to
    local M2/M3 without assuming X=M2 or Y=M3.
    """
    story_name = _text(story, "story")
    column = _target_column(topology, component_id)
    if column.story != story_name:
        raise ColumnLocalSwayRuntimeError(
            "requested story does not match the strict-topology Column story"
        )

    global_x = _resolve_direction(
        candidate_runtimes,
        story=story_name,
        direction="X",
    )
    global_y = _resolve_direction(
        candidate_runtimes,
        story=story_name,
        direction="Y",
    )

    local_axis_ref = (
        f"strict-topology:{column.unique_name}:local-axis:"
        f"angle={float(column.local_axis_angle_deg):.12g}deg"
    )
    global_x_evidence = GlobalSwayDirectionEvidence(
        direction="X",
        status=global_x.status,
        source_refs=global_x.source_refs,
    )
    global_y_evidence = GlobalSwayDirectionEvidence(
        direction="Y",
        status=global_y.status,
        source_refs=global_y.source_refs,
    )
    local_binding = bind_global_sway_to_column_local_axes(
        component_id=column.component_id,
        local_axis_angle_deg=float(column.local_axis_angle_deg),
        local_axis_source_refs=(local_axis_ref,),
        global_x=global_x_evidence,
        global_y=global_y_evidence,
        projection_tolerance=projection_tolerance,
    )

    local_ready = (
        local_binding.m2.status == LOCAL_SWAY_PREVENTED
        and local_binding.m3.status == LOCAL_SWAY_PREVENTED
    )
    status = STATUS_READY if local_ready else STATUS_UNRESOLVED
    refs = tuple(
        dict.fromkeys(
            (
                local_axis_ref,
                *global_x.source_refs,
                *global_y.source_refs,
                *local_binding.source_refs,
            )
        )
    )
    return ColumnLocalAxisSwayRuntime(
        component_id=column.component_id,
        story=story_name,
        global_x=global_x,
        global_y=global_y,
        local_binding=local_binding,
        status=status,
        source_refs=refs,
    )


__all__ = [
    "ColumnLocalAxisSwayRuntime",
    "ColumnLocalSwayRuntimeError",
    "STATUS_READY",
    "STATUS_UNRESOLVED",
    "compose_column_local_axis_sway_runtime",
]
