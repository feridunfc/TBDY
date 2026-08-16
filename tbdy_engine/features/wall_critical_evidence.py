"""Canonical factual evidence for wall critical-height/end-region checks.

This module carries source-proven component facts plus one typed run-level
regulatory reference context. It does not calculate Hw, Hcr, Hw/lw
applicability, critical-region membership, or verdicts.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


def _positive(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    number = float(value)
    if number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


def _number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    return float(value)


@dataclass(frozen=True, slots=True)
class WallStoryGeometryEvidence:
    """Factual story-by-story wall geometry in canonical millimetres."""

    story: str
    base_elevation_mm: float
    story_height_mm: float
    wall_length_mm: float
    wall_thickness_mm: float
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.story, str) or not self.story.strip():
            raise ValueError("WallStoryGeometryEvidence requires a nonblank story")
        object.__setattr__(self, "story", self.story.strip())
        object.__setattr__(self, "base_elevation_mm", _number("base_elevation_mm", self.base_elevation_mm))
        object.__setattr__(self, "story_height_mm", _positive("story_height_mm", self.story_height_mm))
        object.__setattr__(self, "wall_length_mm", _positive("wall_length_mm", self.wall_length_mm))
        object.__setattr__(self, "wall_thickness_mm", _positive("wall_thickness_mm", self.wall_thickness_mm))
        refs = tuple(str(ref) for ref in self.source_refs if str(ref).strip())
        if not refs:
            raise ValueError("Story geometry marked factual requires source_refs")
        object.__setattr__(self, "source_refs", refs)

    @property
    def top_elevation_mm(self) -> float:
        return self.base_elevation_mm + self.story_height_mm


@dataclass(frozen=True, slots=True)
class WallRegulatoryReferenceFacts:
    """Single run-level regulatory reference truth shared by all walls in a run."""

    foundation_top_elevation_mm: float | None
    ground_floor_elevation_mm: float | None
    rigid_basement_perimeter_walls: bool | None
    rigid_basement_diaphragm: bool | None
    first_basement_story_height_mm: float | None = None
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.foundation_top_elevation_mm is not None:
            object.__setattr__(self, "foundation_top_elevation_mm", _number("foundation_top_elevation_mm", self.foundation_top_elevation_mm))
        if self.ground_floor_elevation_mm is not None:
            object.__setattr__(self, "ground_floor_elevation_mm", _number("ground_floor_elevation_mm", self.ground_floor_elevation_mm))
        for name in ("rigid_basement_perimeter_walls", "rigid_basement_diaphragm"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"{name} must be bool or None")
        if self.first_basement_story_height_mm is not None:
            object.__setattr__(self, "first_basement_story_height_mm", _positive("first_basement_story_height_mm", self.first_basement_story_height_mm))
        object.__setattr__(self, "source_refs", tuple(str(ref) for ref in self.source_refs if str(ref).strip()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "foundation_top_elevation_mm": self.foundation_top_elevation_mm,
            "ground_floor_elevation_mm": self.ground_floor_elevation_mm,
            "rigid_basement_perimeter_walls": self.rigid_basement_perimeter_walls,
            "rigid_basement_diaphragm": self.rigid_basement_diaphragm,
            "first_basement_story_height_mm": self.first_basement_story_height_mm,
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True, slots=True)
class WallEndRegionStoryEvidence:
    """Factual end-region existence and plan lengths for one wall story."""

    story: str
    left_exists: bool | None
    right_exists: bool | None
    left_plan_length_mm: float | None = None
    right_plan_length_mm: float | None = None
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.story, str) or not self.story.strip():
            raise ValueError("WallEndRegionStoryEvidence requires a nonblank story")
        object.__setattr__(self, "story", self.story.strip())
        for name in ("left_exists", "right_exists"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"{name} must be bool or None")
        for name in ("left_plan_length_mm", "right_plan_length_mm"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _positive(name, value))
        object.__setattr__(self, "source_refs", tuple(str(ref) for ref in self.source_refs if str(ref).strip()))


_ALLOWED_SECTION_SHAPES = frozenset({"RECTANGULAR", "L", "T", "U", "OTHER_NON_RECTANGULAR"})


@dataclass(frozen=True, slots=True)
class WallCriticalHeightFactualEvidence:
    """Per-wall factual execution evidence for §7.6.2 checks.

    Proof booleans describe acquisition/completeness only. Regulatory reference
    truth is deliberately absent: it is supplied once at run/system grain via
    WallExecutionEvidence. Section shape is a factual classification, not an
    engineering applicability boolean.
    """

    component_id: str
    story_geometry: tuple[WallStoryGeometryEvidence, ...]
    vertical_continuity_proven: bool | None
    section_reduction_evidence_complete: bool | None
    wall_section_shape: str | None = None
    wall_section_shape_source_refs: tuple[str, ...] = ()
    end_region_geometry: tuple[WallEndRegionStoryEvidence, ...] = ()
    end_region_topology_proven: bool | None = None
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, str) or not self.component_id:
            raise ValueError("WallCriticalHeightFactualEvidence requires component_id")
        geometry = tuple(self.story_geometry)
        if any(not isinstance(row, WallStoryGeometryEvidence) for row in geometry):
            raise TypeError("story_geometry must contain WallStoryGeometryEvidence")
        if len({row.story for row in geometry}) != len(geometry):
            raise ValueError("story_geometry must contain unique story identities")
        geometry = tuple(sorted(geometry, key=lambda row: (row.base_elevation_mm, row.story)))
        for name in ("vertical_continuity_proven", "section_reduction_evidence_complete", "end_region_topology_proven"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"{name} must be bool or None")
        shape = self.wall_section_shape
        if shape is not None:
            if not isinstance(shape, str) or not shape.strip():
                raise TypeError("wall_section_shape must be a nonblank string or None")
            shape = shape.strip().upper()
            if shape not in _ALLOWED_SECTION_SHAPES:
                raise ValueError("wall_section_shape must be an allowed factual shape classification")
        shape_refs = tuple(str(ref) for ref in self.wall_section_shape_source_refs if str(ref).strip())
        if shape is not None and not shape_refs:
            raise ValueError("Proven wall section shape requires wall_section_shape_source_refs")
        end_rows = tuple(self.end_region_geometry)
        if any(not isinstance(row, WallEndRegionStoryEvidence) for row in end_rows):
            raise TypeError("end_region_geometry must contain WallEndRegionStoryEvidence")
        if len({row.story for row in end_rows}) != len(end_rows):
            raise ValueError("end_region_geometry must contain unique story identities")
        refs = tuple(str(ref) for ref in self.source_refs if str(ref).strip())
        if (self.vertical_continuity_proven is True or self.section_reduction_evidence_complete is True or self.end_region_topology_proven is True) and not refs:
            raise ValueError("Proven Pack C component facts require source_refs")
        object.__setattr__(self, "story_geometry", geometry)
        object.__setattr__(self, "wall_section_shape", shape)
        object.__setattr__(self, "wall_section_shape_source_refs", shape_refs)
        object.__setattr__(self, "end_region_geometry", end_rows)
        object.__setattr__(self, "source_refs", refs)

    @property
    def end_region_by_story(self) -> Mapping[str, WallEndRegionStoryEvidence]:
        return MappingProxyType({row.story: row for row in self.end_region_geometry})

    def as_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "story_geometry": [
                {
                    "story": row.story,
                    "base_elevation_mm": row.base_elevation_mm,
                    "story_height_mm": row.story_height_mm,
                    "wall_length_mm": row.wall_length_mm,
                    "wall_thickness_mm": row.wall_thickness_mm,
                    "source_refs": list(row.source_refs),
                }
                for row in self.story_geometry
            ],
            "vertical_continuity_proven": self.vertical_continuity_proven,
            "section_reduction_evidence_complete": self.section_reduction_evidence_complete,
            "wall_section_shape": self.wall_section_shape,
            "wall_section_shape_source_refs": list(self.wall_section_shape_source_refs),
            "end_region_topology_proven": self.end_region_topology_proven,
            "end_region_story_count": len(self.end_region_geometry),
            "source_refs": list(self.source_refs),
            "derived_hw_hcr": None,
        }


__all__ = [
    "WallCriticalHeightFactualEvidence",
    "WallEndRegionStoryEvidence",
    "WallRegulatoryReferenceFacts",
    "WallStoryGeometryEvidence",
]
