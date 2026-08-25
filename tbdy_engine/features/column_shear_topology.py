"""Strict factual topology kernel for the VS6 RC-column shear slice.

This module consumes exact ETABS object/connectivity/assignment rows and builds
column-to-joint-to-beam topology. It performs no regulatory calculation and
contains no section-name parsing, angle-based frame classification, coordinate
fallbacks, default dimensions, or reinforcement/design authority.

``analysis_clear_length_candidate_m`` is a factual ETABS geometry candidate
computed from object length minus the reported I/J end-length offsets. It is
*not* promoted here to the regulatory ``l_n`` used by TBDY 7.3.7.

The model may contain non-RC beams (for example steel canopy framing). Those
objects are preserved as exact joint attachments instead of blocking the whole
RC-column topology population. They are explicitly marked unsupported for the
RC beam-capacity path so later regulatory logic cannot silently treat them as
reinforced-concrete beams.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence


class ColumnShearTopologyError(RuntimeError):
    """Raised when strict topology cannot be proven from exact ETABS rows."""


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnShearTopologyError(f"{label} must be a nonblank canonical string")
    return value


def _float(value: Any, label: str) -> float:
    if isinstance(value, bool) or value is None:
        raise ColumnShearTopologyError(f"{label} must be a finite numeric scalar")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ColumnShearTopologyError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise ColumnShearTopologyError(f"{label} must be finite")
    return result


def _freeze(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(row))


def _index_unique(
    rows: Sequence[Mapping[str, Any]],
    field: str,
    label: str,
) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        key = _text(row.get(field), f"{label}[{index}].{field}")
        if key in out:
            raise ColumnShearTopologyError(f"duplicate {label}.{field}={key}")
        out[key] = row
    return out


@dataclass(frozen=True, slots=True)
class PointTopologyEvidence:
    unique_name: str
    story: str
    x_m: float
    y_m: float
    z_m: float
    source_row: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "unique_name", _text(self.unique_name, "point.unique_name"))
        object.__setattr__(self, "story", _text(self.story, "point.story"))
        for name in ("x_m", "y_m", "z_m"):
            object.__setattr__(self, name, _float(getattr(self, name), f"point.{name}"))
        object.__setattr__(self, "source_row", _freeze(self.source_row))

    @property
    def coord_m(self) -> tuple[float, float, float]:
        return (self.x_m, self.y_m, self.z_m)


@dataclass(frozen=True, slots=True)
class BeamJointConnection:
    beam_unique_name: str
    beam_label: str
    story: str
    joint_unique_name: str
    connected_end: str
    other_joint_unique_name: str
    section: str
    shape: str
    is_supported_rc_beam: bool
    width_t2_m: float | None
    depth_t3_m: float | None
    vector_from_joint_m: tuple[float, float, float]
    horizontal_azimuth_deg: float | None
    connectivity_row: Mapping[str, Any]
    assignment_row: Mapping[str, Any]
    section_row: Mapping[str, Any] | None

    def as_dict(self) -> dict[str, object]:
        return {
            "beam_unique_name": self.beam_unique_name,
            "beam_label": self.beam_label,
            "story": self.story,
            "joint_unique_name": self.joint_unique_name,
            "connected_end": self.connected_end,
            "other_joint_unique_name": self.other_joint_unique_name,
            "section": self.section,
            "shape": self.shape,
            "is_supported_rc_beam": self.is_supported_rc_beam,
            "width_t2_m": self.width_t2_m,
            "depth_t3_m": self.depth_t3_m,
            "vector_from_joint_m": list(self.vector_from_joint_m),
            "horizontal_azimuth_deg": self.horizontal_azimuth_deg,
            "source_rows": {
                "connectivity": dict(self.connectivity_row),
                "section_assignment": dict(self.assignment_row),
                "section_definition": None if self.section_row is None else dict(self.section_row),
            },
        }


@dataclass(frozen=True, slots=True)
class ColumnTopologyEvidence:
    unique_name: str
    column_label: str
    story: str
    section: str
    width_t2_m: float
    depth_t3_m: float
    object_length_m: float
    coordinate_length_m: float
    joint_bottom: str
    joint_top: str
    bottom_coord_m: tuple[float, float, float]
    top_coord_m: tuple[float, float, float]
    offset_bottom_m: float
    offset_top_m: float
    analysis_clear_length_candidate_m: float
    local_axis_angle_deg: float | None
    local_axis_explicit: bool
    beams_at_bottom: tuple[BeamJointConnection, ...]
    beams_at_top: tuple[BeamJointConnection, ...]
    connectivity_row: Mapping[str, Any]
    assignment_row: Mapping[str, Any]
    end_offset_row: Mapping[str, Any]
    section_row: Mapping[str, Any]
    local_axis_row: Mapping[str, Any] | None

    @property
    def component_id(self) -> str:
        return f"{self.story}:{self.column_label}:{self.unique_name}"

    @property
    def unsupported_beams_at_bottom(self) -> tuple[BeamJointConnection, ...]:
        return tuple(item for item in self.beams_at_bottom if not item.is_supported_rc_beam)

    @property
    def unsupported_beams_at_top(self) -> tuple[BeamJointConnection, ...]:
        return tuple(item for item in self.beams_at_top if not item.is_supported_rc_beam)

    def as_dict(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "UniqueName": self.unique_name,
            "Story": self.story,
            "Column": self.column_label,
            "Section": self.section,
            "width_t2_m": self.width_t2_m,
            "depth_t3_m": self.depth_t3_m,
            "object_length_m": self.object_length_m,
            "coordinate_length_m": self.coordinate_length_m,
            "length_delta_m": self.coordinate_length_m - self.object_length_m,
            "joint_bottom": self.joint_bottom,
            "joint_top": self.joint_top,
            "bottom_coord_m": list(self.bottom_coord_m),
            "top_coord_m": list(self.top_coord_m),
            "offset_bottom_m": self.offset_bottom_m,
            "offset_top_m": self.offset_top_m,
            "analysis_clear_length_candidate_m": self.analysis_clear_length_candidate_m,
            "regulatory_ln_status": "NOT_PROMOTED_FROM_FACTUAL_CANDIDATE",
            "local_axis_angle_deg": self.local_axis_angle_deg,
            "local_axis_explicit": self.local_axis_explicit,
            "beams_at_bottom": [item.as_dict() for item in self.beams_at_bottom],
            "beams_at_top": [item.as_dict() for item in self.beams_at_top],
            "unsupported_beam_attachment_count": (
                len(self.unsupported_beams_at_bottom) + len(self.unsupported_beams_at_top)
            ),
            "rc_beam_capacity_attachment_status": (
                "REQUIRES_SCOPE_CLASSIFICATION"
                if self.unsupported_beams_at_bottom or self.unsupported_beams_at_top
                else "SUPPORTED_RC_ATTACHMENTS_ONLY"
            ),
            "source_rows": {
                "connectivity": dict(self.connectivity_row),
                "section_assignment": dict(self.assignment_row),
                "end_length_offsets": dict(self.end_offset_row),
                "section_definition": dict(self.section_row),
                "local_axis": None if self.local_axis_row is None else dict(self.local_axis_row),
            },
        }


@dataclass(frozen=True, slots=True)
class StrictColumnTopologyBundle:
    columns: tuple[ColumnTopologyEvidence, ...]
    point_count: int
    beam_count: int
    supported_rc_beam_count: int
    unsupported_beam_count: int
    reviewed_length_unit: str

    def __post_init__(self) -> None:
        if self.reviewed_length_unit != "m":
            raise ColumnShearTopologyError("VS6 strict topology initial length contract requires m")
        if not self.columns:
            raise ColumnShearTopologyError("strict topology requires at least one column")
        if len({item.unique_name for item in self.columns}) != len(self.columns):
            raise ColumnShearTopologyError("duplicate column UniqueName in strict topology bundle")
        if self.supported_rc_beam_count + self.unsupported_beam_count != self.beam_count:
            raise ColumnShearTopologyError("beam population accounting mismatch")

    def column(self, unique_name: str) -> ColumnTopologyEvidence:
        uid = _text(unique_name, "column_unique_name")
        matches = tuple(item for item in self.columns if item.unique_name == uid)
        if len(matches) != 1:
            raise KeyError(f"expected exactly one column UniqueName={uid}, got {len(matches)}")
        return matches[0]

    def summary(self) -> dict[str, object]:
        connected_top = sum(bool(item.beams_at_top) for item in self.columns)
        connected_bottom = sum(bool(item.beams_at_bottom) for item in self.columns)
        explicit_axis = sum(item.local_axis_explicit for item in self.columns)
        clear_lengths = [item.analysis_clear_length_candidate_m for item in self.columns]
        columns_with_unsupported = sum(
            bool(item.unsupported_beams_at_top or item.unsupported_beams_at_bottom)
            for item in self.columns
        )
        return {
            "status": "PROVEN_STRICT_TOPOLOGY",
            "column_count": len(self.columns),
            "beam_count": self.beam_count,
            "supported_rc_beam_count": self.supported_rc_beam_count,
            "unsupported_beam_count": self.unsupported_beam_count,
            "point_count": self.point_count,
            "columns_with_top_beams": connected_top,
            "columns_with_bottom_beams": connected_bottom,
            "columns_with_unsupported_beam_attachments": columns_with_unsupported,
            "rc_beam_capacity_attachment_status": (
                "REQUIRES_SCOPE_CLASSIFICATION"
                if columns_with_unsupported
                else "SUPPORTED_RC_ATTACHMENTS_ONLY"
            ),
            "explicit_column_local_axis_count": explicit_axis,
            "analysis_clear_length_candidate_min_m": min(clear_lengths),
            "analysis_clear_length_candidate_max_m": max(clear_lengths),
            "regulatory_ln_status": "NOT_PROMOTED_FROM_FACTUAL_CANDIDATE",
            "heuristics_used": False,
        }


def _distance(a: PointTopologyEvidence, b: PointTopologyEvidence) -> float:
    return math.dist(a.coord_m, b.coord_m)


def _beam_connection(
    *,
    row: Mapping[str, Any],
    connected_end: str,
    joint: PointTopologyEvidence,
    other: PointTopologyEvidence,
    assignment: Mapping[str, Any],
    section: str,
    shape: str,
    is_supported_rc_beam: bool,
    section_row: Mapping[str, Any] | None,
) -> BeamJointConnection:
    dx = other.x_m - joint.x_m
    dy = other.y_m - joint.y_m
    dz = other.z_m - joint.z_m
    horizontal = math.hypot(dx, dy)
    azimuth = None if horizontal <= 1e-12 else (math.degrees(math.atan2(dy, dx)) % 360.0)
    return BeamJointConnection(
        beam_unique_name=_text(row.get("UniqueName"), "beam.UniqueName"),
        beam_label=_text(row.get("BeamBay"), "beam.BeamBay"),
        story=_text(row.get("Story"), "beam.Story"),
        joint_unique_name=joint.unique_name,
        connected_end=connected_end,
        other_joint_unique_name=other.unique_name,
        section=section,
        shape=shape,
        is_supported_rc_beam=is_supported_rc_beam,
        width_t2_m=(None if section_row is None else _float(section_row.get("t2"), "beam.section.t2")),
        depth_t3_m=(None if section_row is None else _float(section_row.get("t3"), "beam.section.t3")),
        vector_from_joint_m=(dx, dy, dz),
        horizontal_azimuth_deg=azimuth,
        connectivity_row=_freeze(row),
        assignment_row=_freeze(assignment),
        section_row=None if section_row is None else _freeze(section_row),
    )


def build_strict_column_topology(
    *,
    point_rows: Sequence[Mapping[str, Any]],
    column_rows: Sequence[Mapping[str, Any]],
    beam_rows: Sequence[Mapping[str, Any]],
    section_assignment_rows: Sequence[Mapping[str, Any]],
    end_offset_rows: Sequence[Mapping[str, Any]],
    local_axis_rows: Sequence[Mapping[str, Any]],
    rectangular_section_rows: Sequence[Mapping[str, Any]],
    reviewed_length_unit: str,
    coordinate_length_tolerance_m: float = 0.002,
) -> StrictColumnTopologyBundle:
    """Build exact column/joint/beam topology from ETABS factual rows.

    Object-level endpoint identity and coordinates come from ``Point Object
    Connectivity``. Non-rectangular/non-RC beams remain factual attachments but
    are explicitly excluded from the supported RC beam-capacity population.
    """
    if reviewed_length_unit != "m":
        raise ColumnShearTopologyError("VS6 strict topology initial length contract requires m")
    tolerance = _float(coordinate_length_tolerance_m, "coordinate_length_tolerance_m")
    if tolerance < 0.0:
        raise ColumnShearTopologyError("coordinate_length_tolerance_m must be >= 0")

    point_by_uid_raw = _index_unique(point_rows, "UniqueName", "Point Object Connectivity")
    assignment_by_uid = _index_unique(
        section_assignment_rows,
        "UniqueName",
        "Frame Assignments - Section Properties",
    )
    offset_by_uid = _index_unique(
        end_offset_rows,
        "UniqueName",
        "Frame Assignments - End Length Offsets",
    )
    section_by_name = _index_unique(
        rectangular_section_rows,
        "Name",
        "Frame Section Property Definitions - Concrete Rectangular",
    )
    local_axis_by_uid = _index_unique(
        local_axis_rows,
        "UniqueName",
        "Frame Assignments - Local Axes",
    )

    points = {
        uid: PointTopologyEvidence(
            unique_name=uid,
            story=_text(row.get("Story"), f"point {uid}.Story"),
            x_m=_float(row.get("X"), f"point {uid}.X"),
            y_m=_float(row.get("Y"), f"point {uid}.Y"),
            z_m=_float(row.get("Z"), f"point {uid}.Z"),
            source_row=row,
        )
        for uid, row in point_by_uid_raw.items()
    }

    def exact_assignment(row: Mapping[str, Any], *, kind: str) -> tuple[str, Mapping[str, Any]]:
        uid = _text(row.get("UniqueName"), f"{kind}.UniqueName")
        assignment = assignment_by_uid.get(uid)
        if assignment is None:
            raise ColumnShearTopologyError(f"missing section assignment for {kind} UniqueName={uid}")
        return uid, assignment

    def exact_endpoints(
        row: Mapping[str, Any], *, kind: str, uid: str
    ) -> tuple[str, str, PointTopologyEvidence, PointTopologyEvidence, float]:
        point_i_uid = _text(row.get("UniquePtI"), f"{kind} {uid}.UniquePtI")
        point_j_uid = _text(row.get("UniquePtJ"), f"{kind} {uid}.UniquePtJ")
        point_i = points.get(point_i_uid)
        point_j = points.get(point_j_uid)
        if point_i is None or point_j is None:
            raise ColumnShearTopologyError(
                f"{kind} {uid} endpoint point missing: I={point_i_uid in points} J={point_j_uid in points}"
            )
        object_length = _float(row.get("Length"), f"{kind} {uid}.Length")
        coordinate_length = _distance(point_i, point_j)
        if abs(object_length - coordinate_length) > tolerance:
            raise ColumnShearTopologyError(
                f"{kind} {uid} object/coordinate length mismatch: object={object_length} "
                f"coordinate={coordinate_length} tolerance={tolerance}"
            )
        return point_i_uid, point_j_uid, point_i, point_j, object_length

    beam_connections_by_joint: dict[str, list[BeamJointConnection]] = {}
    beam_uids: set[str] = set()
    supported_rc_beam_count = 0
    unsupported_beam_count = 0

    for row in beam_rows:
        uid, assignment = exact_assignment(row, kind="beam")
        if uid in beam_uids:
            raise ColumnShearTopologyError(f"duplicate beam UniqueName={uid}")
        beam_uids.add(uid)

        point_i_uid, point_j_uid, point_i, point_j, _object_length = exact_endpoints(
            row, kind="beam", uid=uid
        )
        shape = _text(assignment.get("Shape"), f"beam {uid}.Shape")
        section = _text(assignment.get("SectProp"), f"beam {uid}.SectProp")

        section_row: Mapping[str, Any] | None = None
        is_supported_rc_beam = False
        if shape == "Concrete Rectangular":
            section_row = section_by_name.get(section)
            if section_row is None:
                raise ColumnShearTopologyError(
                    f"missing rectangular section definition {section} for beam {uid}"
                )
            if section_row.get("DesignType") != "Beam":
                raise ColumnShearTopologyError(
                    f"beam {uid} section {section} DesignType={section_row.get('DesignType')} expected Beam"
                )
            is_supported_rc_beam = True
            supported_rc_beam_count += 1
        else:
            unsupported_beam_count += 1

        beam_connections_by_joint.setdefault(point_i_uid, []).append(
            _beam_connection(
                row=row,
                connected_end="I",
                joint=point_i,
                other=point_j,
                assignment=assignment,
                section=section,
                shape=shape,
                is_supported_rc_beam=is_supported_rc_beam,
                section_row=section_row,
            )
        )
        beam_connections_by_joint.setdefault(point_j_uid, []).append(
            _beam_connection(
                row=row,
                connected_end="J",
                joint=point_j,
                other=point_i,
                assignment=assignment,
                section=section,
                shape=shape,
                is_supported_rc_beam=is_supported_rc_beam,
                section_row=section_row,
            )
        )

    columns: list[ColumnTopologyEvidence] = []
    seen_columns: set[str] = set()
    for row in column_rows:
        uid, assignment = exact_assignment(row, kind="column")
        if uid in seen_columns:
            raise ColumnShearTopologyError(f"duplicate column UniqueName={uid}")
        seen_columns.add(uid)

        if assignment.get("Shape") != "Concrete Rectangular":
            raise ColumnShearTopologyError(
                f"unsupported column Shape for UniqueName={uid}: {assignment.get('Shape')}"
            )
        section = _text(assignment.get("SectProp"), f"column {uid}.SectProp")
        section_row = section_by_name.get(section)
        if section_row is None:
            raise ColumnShearTopologyError(
                f"missing rectangular section definition {section} for column {uid}"
            )
        if section_row.get("DesignType") != "Column":
            raise ColumnShearTopologyError(
                f"column {uid} section {section} DesignType={section_row.get('DesignType')} expected Column"
            )
        offset_row = offset_by_uid.get(uid)
        if offset_row is None:
            raise ColumnShearTopologyError(f"missing end-length offsets for column UniqueName={uid}")

        _point_i_uid, _point_j_uid, point_i, point_j, object_length = exact_endpoints(
            row, kind="column", uid=uid
        )
        if point_i.z_m == point_j.z_m:
            raise ColumnShearTopologyError(
                f"column {uid} endpoints have equal Z; top/bottom identity is unresolved"
            )

        offset_i = _float(offset_row.get("OffsetI"), f"column {uid}.OffsetI")
        offset_j = _float(offset_row.get("OffsetJ"), f"column {uid}.OffsetJ")
        if min(offset_i, offset_j) < 0.0:
            raise ColumnShearTopologyError(f"column {uid} end offsets must be >= 0")

        if point_i.z_m < point_j.z_m:
            bottom, top = point_i, point_j
            offset_bottom, offset_top = offset_i, offset_j
        else:
            bottom, top = point_j, point_i
            offset_bottom, offset_top = offset_j, offset_i

        clear_candidate = object_length - offset_i - offset_j
        if clear_candidate <= 0.0:
            raise ColumnShearTopologyError(
                f"column {uid} nonpositive analysis clear-length candidate {clear_candidate}"
            )

        local_axis_row = local_axis_by_uid.get(uid)
        local_axis_angle = (
            None
            if local_axis_row is None
            else _float(local_axis_row.get("Angle"), f"column {uid}.local_axis.Angle")
        )

        columns.append(
            ColumnTopologyEvidence(
                unique_name=uid,
                column_label=_text(row.get("ColumnBay"), f"column {uid}.ColumnBay"),
                story=_text(row.get("Story"), f"column {uid}.Story"),
                section=section,
                width_t2_m=_float(section_row.get("t2"), f"column {uid}.section.t2"),
                depth_t3_m=_float(section_row.get("t3"), f"column {uid}.section.t3"),
                object_length_m=object_length,
                coordinate_length_m=_distance(point_i, point_j),
                joint_bottom=bottom.unique_name,
                joint_top=top.unique_name,
                bottom_coord_m=bottom.coord_m,
                top_coord_m=top.coord_m,
                offset_bottom_m=offset_bottom,
                offset_top_m=offset_top,
                analysis_clear_length_candidate_m=clear_candidate,
                local_axis_angle_deg=local_axis_angle,
                local_axis_explicit=local_axis_row is not None,
                beams_at_bottom=tuple(
                    sorted(
                        beam_connections_by_joint.get(bottom.unique_name, ()),
                        key=lambda item: (item.beam_unique_name, item.connected_end),
                    )
                ),
                beams_at_top=tuple(
                    sorted(
                        beam_connections_by_joint.get(top.unique_name, ()),
                        key=lambda item: (item.beam_unique_name, item.connected_end),
                    )
                ),
                connectivity_row=_freeze(row),
                assignment_row=_freeze(assignment),
                end_offset_row=_freeze(offset_row),
                section_row=_freeze(section_row),
                local_axis_row=None if local_axis_row is None else _freeze(local_axis_row),
            )
        )

    columns.sort(key=lambda item: (item.story, item.column_label, item.unique_name))
    return StrictColumnTopologyBundle(
        columns=tuple(columns),
        point_count=len(points),
        beam_count=len(beam_uids),
        supported_rc_beam_count=supported_rc_beam_count,
        unsupported_beam_count=unsupported_beam_count,
        reviewed_length_unit=reviewed_length_unit,
    )


__all__ = [
    "ColumnShearTopologyError",
    "PointTopologyEvidence",
    "BeamJointConnection",
    "ColumnTopologyEvidence",
    "StrictColumnTopologyBundle",
    "build_strict_column_topology",
]
