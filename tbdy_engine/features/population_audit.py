"""Authoritative source-population scope classification for live geometry probes.

This module owns only ETABS source-population classification. It deliberately
contains no coverage-readiness or engineering-verdict semantics.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import json
from types import MappingProxyType


class PopulationDisposition(str, Enum):
    IN_SCOPE = "IN_SCOPE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    BLOCKED = "BLOCKED"


IN_SCOPE_CONCRETE_RECTANGULAR_BEAM = "IN_SCOPE_CONCRETE_RECTANGULAR_BEAM"
IN_SCOPE_CONCRETE_RECTANGULAR_COLUMN = "IN_SCOPE_CONCRETE_RECTANGULAR_COLUMN"
OUT_OF_SCOPE_NULL_FRAME = "OUT_OF_SCOPE_NULL_FRAME"
OUT_OF_SCOPE_BRACE = "OUT_OF_SCOPE_BRACE"
OUT_OF_SCOPE_STEEL_SECTION = "OUT_OF_SCOPE_STEEL_SECTION"
OUT_OF_SCOPE_UNSUPPORTED_SECTION_FAMILY = "OUT_OF_SCOPE_UNSUPPORTED_SECTION_FAMILY"
BLOCKED_COMPONENT_TYPE_MISSING = "BLOCKED_COMPONENT_TYPE_MISSING"
BLOCKED_COMPONENT_TYPE_AMBIGUOUS = "BLOCKED_COMPONENT_TYPE_AMBIGUOUS"
BLOCKED_SECTION_ASSIGNMENT_MISSING = "BLOCKED_SECTION_ASSIGNMENT_MISSING"
BLOCKED_SECTION_DEFINITION_READ_FAILURE = "BLOCKED_SECTION_DEFINITION_READ_FAILURE"
BLOCKED_SUPPORTED_SECTION_GEOMETRY_UNRESOLVED = "BLOCKED_SUPPORTED_SECTION_GEOMETRY_UNRESOLVED"

_REASON_DISPOSITION: Mapping[str, PopulationDisposition] = MappingProxyType(
    {
        IN_SCOPE_CONCRETE_RECTANGULAR_BEAM: PopulationDisposition.IN_SCOPE,
        IN_SCOPE_CONCRETE_RECTANGULAR_COLUMN: PopulationDisposition.IN_SCOPE,
        OUT_OF_SCOPE_NULL_FRAME: PopulationDisposition.OUT_OF_SCOPE,
        OUT_OF_SCOPE_BRACE: PopulationDisposition.OUT_OF_SCOPE,
        OUT_OF_SCOPE_STEEL_SECTION: PopulationDisposition.OUT_OF_SCOPE,
        OUT_OF_SCOPE_UNSUPPORTED_SECTION_FAMILY: PopulationDisposition.OUT_OF_SCOPE,
        BLOCKED_COMPONENT_TYPE_MISSING: PopulationDisposition.BLOCKED,
        BLOCKED_COMPONENT_TYPE_AMBIGUOUS: PopulationDisposition.BLOCKED,
        BLOCKED_SECTION_ASSIGNMENT_MISSING: PopulationDisposition.BLOCKED,
        BLOCKED_SECTION_DEFINITION_READ_FAILURE: PopulationDisposition.BLOCKED,
        BLOCKED_SUPPORTED_SECTION_GEOMETRY_UNRESOLVED: PopulationDisposition.BLOCKED,
    }
)

_SOURCE_TABLE = "Frame Assignments - Summary"
_RECOGNIZED_COMPONENT_TYPES = frozenset({"beam", "column", "brace", "null"})
_CONCRETE_RECTANGULAR_SHAPES = frozenset({"rectangular", "concrete rectangular"})


@dataclass(frozen=True, slots=True)
class PopulationAuditRow:
    component_id: str
    label: str | None
    story: str | None
    raw_component_type: str | None
    assigned_section: str | None
    analysis_section: str | None
    design_section: str | None
    section_shape: str | None
    disposition: PopulationDisposition
    reason_code: str
    source_table: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id))
        for field_name in (
            "label",
            "story",
            "raw_component_type",
            "assigned_section",
            "analysis_section",
            "design_section",
            "section_shape",
        ):
            object.__setattr__(self, field_name, _text_or_none(getattr(self, field_name)))
        source_table = _text(self.source_table)
        if not source_table:
            raise ValueError("PopulationAuditRow.source_table is required")
        object.__setattr__(self, "source_table", source_table)
        expected_disposition = _REASON_DISPOSITION.get(self.reason_code)
        if expected_disposition is None:
            raise ValueError(f"Unsupported population reason_code: {self.reason_code}")
        if self.disposition is not expected_disposition:
            raise ValueError("Population disposition and reason_code are inconsistent")

    @property
    def canonical_sort_key(self) -> tuple[str, str, str, str]:
        return (
            self.component_id,
            self.raw_component_type or "",
            self.assigned_section or "",
            self.reason_code,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "analysis_section": self.analysis_section,
            "assigned_section": self.assigned_section,
            "component_id": self.component_id,
            "design_section": self.design_section,
            "disposition": self.disposition.value,
            "label": self.label,
            "raw_component_type": self.raw_component_type,
            "reason_code": self.reason_code,
            "section_shape": self.section_shape,
            "source_table": self.source_table,
            "story": self.story,
        }


@dataclass(frozen=True, slots=True, init=False)
class PopulationAudit:
    source_row_count: int
    in_scope_row_count: int
    out_of_scope_row_count: int
    blocked_row_count: int
    disposition_counts: Mapping[str, int]
    reason_counts: Mapping[str, int]
    rows: tuple[PopulationAuditRow, ...]

    def __init__(self, rows: Sequence[PopulationAuditRow]) -> None:
        canonical_rows = tuple(sorted(tuple(rows), key=lambda row: row.canonical_sort_key))
        duplicate_ids = _duplicate_non_empty_ids(canonical_rows)
        if duplicate_ids:
            raise ValueError(
                "Duplicate non-empty population component IDs: " + ", ".join(duplicate_ids)
            )

        disposition_counter = Counter(row.disposition.value for row in canonical_rows)
        reason_counter = Counter(row.reason_code for row in canonical_rows)
        in_scope = disposition_counter[PopulationDisposition.IN_SCOPE.value]
        out_of_scope = disposition_counter[PopulationDisposition.OUT_OF_SCOPE.value]
        blocked = disposition_counter[PopulationDisposition.BLOCKED.value]
        source_count = len(canonical_rows)
        if source_count != in_scope + out_of_scope + blocked:
            raise ValueError("Population audit counts do not reconcile")

        object.__setattr__(self, "source_row_count", source_count)
        object.__setattr__(self, "in_scope_row_count", in_scope)
        object.__setattr__(self, "out_of_scope_row_count", out_of_scope)
        object.__setattr__(self, "blocked_row_count", blocked)
        object.__setattr__(
            self,
            "disposition_counts",
            MappingProxyType(
                {
                    disposition.value: disposition_counter[disposition.value]
                    for disposition in PopulationDisposition
                }
            ),
        )
        object.__setattr__(
            self,
            "reason_counts",
            MappingProxyType({key: reason_counter[key] for key in sorted(reason_counter)}),
        )
        object.__setattr__(self, "rows", canonical_rows)

    def as_dict(self) -> dict[str, object]:
        return {
            "blocked_row_count": self.blocked_row_count,
            "disposition_counts": dict(self.disposition_counts),
            "in_scope_row_count": self.in_scope_row_count,
            "out_of_scope_row_count": self.out_of_scope_row_count,
            "reason_counts": dict(self.reason_counts),
            "rows": [row.as_dict() for row in self.rows],
            "source_row_count": self.source_row_count,
        }


@dataclass(frozen=True, slots=True)
class _AssignmentEvidence:
    component_id: str
    assigned_section: str | None
    section_shape: str | None
    story: str | None
    label: str | None

    def __post_init__(self) -> None:
        component_id = _text(self.component_id)
        if not component_id:
            raise ValueError("Assignment evidence component_id is required")
        object.__setattr__(self, "component_id", component_id)
        for field_name in ("assigned_section", "section_shape", "story", "label"):
            object.__setattr__(self, field_name, _text_or_none(getattr(self, field_name)))



def build_population_audit(
    *,
    source_rows: Sequence[Mapping[str, object]],
    assignment_rows: Sequence[Mapping[str, object]] = (),
    property_rows: Sequence[Mapping[str, object]] = (),
    source_table: str = _SOURCE_TABLE,
    join_key_column: str = "UniqueName",
    component_type_column: str = "Type",
    assignment_section_column: str = "SectProp",
    assignment_shape_column: str = "Shape",
    assignment_story_column: str = "Story",
    assignment_label_column: str = "Label",
    property_name_column: str = "Name",
    property_width_column: str = "t2",
    property_depth_column: str = "t3",
    property_definition_read_failed: bool = False,
    resolved_geometry_component_ids: frozenset[str] | None = None,
) -> PopulationAudit:
    """Classify each authoritative Summary population row exactly once.

    Component identity and type come from ``source_rows``. Section assignment,
    section family/shape, and identity fallback values come only from the joined
    assignment table row with the same ``UniqueName``. Concrete rectangular
    geometry comes only from the accepted property definition table.

    ``resolved_geometry_component_ids`` may be supplied by the accepted geometry
    resolver. When supplied, a supported concrete candidate is IN_SCOPE only
    when that exact component was resolved; otherwise it fails closed as BLOCKED.
    """

    assignments_by_id = _index_assignment_evidence(
        assignment_rows,
        join_key_column=join_key_column,
        assignment_section_column=assignment_section_column,
        assignment_shape_column=assignment_shape_column,
        assignment_story_column=assignment_story_column,
        assignment_label_column=assignment_label_column,
    )
    valid_properties = _valid_property_names(
        property_rows,
        name_column=property_name_column,
        width_column=property_width_column,
        depth_column=property_depth_column,
    )

    rows: list[PopulationAuditRow] = []
    for raw_row in source_rows:
        summary_row = dict(raw_row)
        component_id = _text(summary_row.get(join_key_column))
        raw_type = _text_or_none(summary_row.get(component_type_column))
        raw_type_key = (raw_type or "").casefold()
        assignment = assignments_by_id.get(component_id)
        assigned_section = None if assignment is None else assignment.assigned_section
        section_shape = None if assignment is None else assignment.section_shape
        shape_key = _normalized_shape(section_shape)

        if not raw_type:
            disposition = PopulationDisposition.BLOCKED
            reason = BLOCKED_COMPONENT_TYPE_MISSING
        elif raw_type_key == "null":
            disposition = PopulationDisposition.OUT_OF_SCOPE
            reason = OUT_OF_SCOPE_NULL_FRAME
        elif raw_type_key == "brace":
            disposition = PopulationDisposition.OUT_OF_SCOPE
            reason = OUT_OF_SCOPE_BRACE
        elif raw_type_key not in _RECOGNIZED_COMPONENT_TYPES:
            disposition = PopulationDisposition.BLOCKED
            reason = BLOCKED_COMPONENT_TYPE_AMBIGUOUS
        elif assignment is None or not assigned_section:
            disposition = PopulationDisposition.BLOCKED
            reason = BLOCKED_SECTION_ASSIGNMENT_MISSING
        elif _is_steel_shape(section_shape):
            disposition = PopulationDisposition.OUT_OF_SCOPE
            reason = OUT_OF_SCOPE_STEEL_SECTION
        elif section_shape and shape_key not in _CONCRETE_RECTANGULAR_SHAPES:
            disposition = PopulationDisposition.OUT_OF_SCOPE
            reason = OUT_OF_SCOPE_UNSUPPORTED_SECTION_FAMILY
        elif property_definition_read_failed:
            disposition = PopulationDisposition.BLOCKED
            reason = BLOCKED_SECTION_DEFINITION_READ_FAILURE
        elif resolved_geometry_component_ids is not None:
            if component_id and component_id in resolved_geometry_component_ids:
                disposition = PopulationDisposition.IN_SCOPE
                reason = _in_scope_reason(raw_type_key)
            else:
                disposition = PopulationDisposition.BLOCKED
                reason = BLOCKED_SUPPORTED_SECTION_GEOMETRY_UNRESOLVED
        elif assigned_section in valid_properties:
            disposition = PopulationDisposition.IN_SCOPE
            reason = _in_scope_reason(raw_type_key)
        else:
            disposition = PopulationDisposition.BLOCKED
            reason = BLOCKED_SUPPORTED_SECTION_GEOMETRY_UNRESOLVED

        rows.append(
            PopulationAuditRow(
                component_id=component_id,
                label=_text_or_none(summary_row.get("Label"))
                or (None if assignment is None else assignment.label),
                story=_text_or_none(summary_row.get("Story"))
                or (None if assignment is None else assignment.story),
                raw_component_type=raw_type,
                assigned_section=assigned_section,
                analysis_section=_text_or_none(summary_row.get("AnalysisSect")),
                design_section=_text_or_none(summary_row.get("DesignSect")),
                section_shape=section_shape,
                disposition=disposition,
                reason_code=reason,
                source_table=source_table,
            )
        )
    return PopulationAudit(rows)



def canonical_population_audit_json(audit: PopulationAudit) -> str:
    return json.dumps(
        audit.as_dict(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"



def _index_assignment_evidence(
    rows: Sequence[Mapping[str, object]],
    *,
    join_key_column: str,
    assignment_section_column: str,
    assignment_shape_column: str,
    assignment_story_column: str,
    assignment_label_column: str,
) -> dict[str, _AssignmentEvidence]:
    evidence_by_id: dict[str, set[_AssignmentEvidence]] = {}
    for raw_row in rows:
        row = dict(raw_row)
        component_id = _text(row.get(join_key_column))
        if not component_id:
            continue
        evidence = _AssignmentEvidence(
            component_id=component_id,
            assigned_section=_text_or_none(row.get(assignment_section_column)),
            section_shape=_text_or_none(row.get(assignment_shape_column)),
            story=_text_or_none(row.get(assignment_story_column)),
            label=_text_or_none(row.get(assignment_label_column)),
        )
        evidence_by_id.setdefault(component_id, set()).add(evidence)

    indexed: dict[str, _AssignmentEvidence] = {}
    for component_id, evidence_values in evidence_by_id.items():
        if len(evidence_values) == 1:
            indexed[component_id] = next(iter(evidence_values))
    return indexed



def _valid_property_names(
    rows: Sequence[Mapping[str, object]],
    *,
    name_column: str,
    width_column: str,
    depth_column: str,
) -> frozenset[str]:
    valid: set[str] = set()
    ambiguous: set[str] = set()
    seen: set[str] = set()
    for row in rows:
        name = _text(row.get(name_column))
        if not name:
            continue
        if name in seen:
            ambiguous.add(name)
        seen.add(name)
        width = _plain_positive_number(row.get(width_column))
        depth = _plain_positive_number(row.get(depth_column))
        if width is not None and depth is not None:
            valid.add(name)
    return frozenset(valid - ambiguous)



def _plain_positive_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if number <= 0 or number != number or number in {float("inf"), float("-inf")}:
        return None
    return number



def _normalized_shape(shape: str | None) -> str:
    return " ".join((shape or "").casefold().split())



def _is_steel_shape(shape: str | None) -> bool:
    return "steel" in _normalized_shape(shape)



def _in_scope_reason(component_type: str) -> str:
    if component_type == "beam":
        return IN_SCOPE_CONCRETE_RECTANGULAR_BEAM
    if component_type == "column":
        return IN_SCOPE_CONCRETE_RECTANGULAR_COLUMN
    raise ValueError("Only beam or column can be in scope")



def _duplicate_non_empty_ids(rows: Sequence[PopulationAuditRow]) -> tuple[str, ...]:
    counts = Counter(row.component_id for row in rows if row.component_id)
    return tuple(sorted(component_id for component_id, count in counts.items() if count > 1))



def _text(value: object) -> str:
    return "" if value is None else str(value).strip()



def _text_or_none(value: object) -> str | None:
    text = _text(value)
    return text or None


__all__ = [
    "BLOCKED_COMPONENT_TYPE_AMBIGUOUS",
    "BLOCKED_COMPONENT_TYPE_MISSING",
    "BLOCKED_SECTION_ASSIGNMENT_MISSING",
    "BLOCKED_SECTION_DEFINITION_READ_FAILURE",
    "BLOCKED_SUPPORTED_SECTION_GEOMETRY_UNRESOLVED",
    "IN_SCOPE_CONCRETE_RECTANGULAR_BEAM",
    "IN_SCOPE_CONCRETE_RECTANGULAR_COLUMN",
    "OUT_OF_SCOPE_BRACE",
    "OUT_OF_SCOPE_NULL_FRAME",
    "OUT_OF_SCOPE_STEEL_SECTION",
    "OUT_OF_SCOPE_UNSUPPORTED_SECTION_FAMILY",
    "PopulationAudit",
    "PopulationAuditRow",
    "PopulationDisposition",
    "build_population_audit",
    "canonical_population_audit_json",
]
