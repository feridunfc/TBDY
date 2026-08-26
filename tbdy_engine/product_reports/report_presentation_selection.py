"""Renderer-only presentation selection policy for UR-1C.

Selection changes what a generated review artifact shows. It never changes
assessment population, FCR accounting, canonical statuses, report bindings,
or any upstream engineering/regulatory decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.product_reports.building_report_projection import (
    BuildingReportProjection,
    ReportView,
)


class ReportPresentationSelectionError(ValueError):
    """Raised when a presentation-only selection cannot bind exactly."""


def _optional_text(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ReportPresentationSelectionError(
            f"{label} must be None or a nonblank canonical string"
        )
    return value


def _exact_texts(values: Sequence[str], label: str) -> tuple[str, ...]:
    frozen: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ReportPresentationSelectionError(
                f"{label}[{index}] must be a nonblank canonical string"
            )
        frozen.append(value)
    if len(frozen) != len(set(frozen)):
        raise ReportPresentationSelectionError(f"{label} must not contain duplicates")
    return tuple(sorted(frozen))


@dataclass(frozen=True, slots=True, order=True)
class ComponentFacetRef:
    """Exact presentation reference to one canonical component facet."""

    component_type: str | None
    component_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "component_type",
            _optional_text(self.component_type, "component_ref.component_type"),
        )
        object.__setattr__(
            self,
            "component_id",
            _optional_text(self.component_id, "component_ref.component_id"),
        )

    def as_dict(self) -> dict[str, str | None]:
        return {
            "component_type": self.component_type,
            "component_id": self.component_id,
        }


@dataclass(frozen=True, slots=True)
class ReportPresentationSelection:
    """Immutable deterministic visibility policy for one rendered artifact."""

    include_overview: bool = True
    include_coverage: bool = True
    include_results: bool = True
    include_components: bool = True
    include_evidence: bool = False
    include_actions: bool = True
    statuses: tuple[str, ...] = ()
    contribution_kinds: tuple[str, ...] = ()
    component_refs: tuple[ComponentFacetRef, ...] = ()
    contribution_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "include_overview",
            "include_coverage",
            "include_results",
            "include_components",
            "include_evidence",
            "include_actions",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")
        object.__setattr__(self, "statuses", _exact_texts(self.statuses, "statuses"))
        object.__setattr__(
            self,
            "contribution_kinds",
            _exact_texts(self.contribution_kinds, "contribution_kinds"),
        )
        refs = tuple(self.component_refs)
        if any(not isinstance(item, ComponentFacetRef) for item in refs):
            raise TypeError("component_refs must contain ComponentFacetRef")
        if len(refs) != len(set(refs)):
            raise ReportPresentationSelectionError(
                "component_refs must not contain duplicates"
            )
        object.__setattr__(self, "component_refs", tuple(sorted(refs)))
        object.__setattr__(
            self,
            "contribution_refs",
            _exact_texts(self.contribution_refs, "contribution_refs"),
        )

    @property
    def contribution_filter_active(self) -> bool:
        return bool(
            self.statuses
            or self.contribution_kinds
            or self.component_refs
            or self.contribution_refs
        )

    @property
    def section_filter_active(self) -> bool:
        return not all(
            (
                self.include_overview,
                self.include_coverage,
                self.include_results,
                self.include_components,
                self.include_actions,
            )
        )

    @property
    def presentation_filter_active(self) -> bool:
        return self.section_filter_active or self.contribution_filter_active

    def as_dict(self) -> dict[str, object]:
        return {
            "include_overview": self.include_overview,
            "include_coverage": self.include_coverage,
            "include_results": self.include_results,
            "include_components": self.include_components,
            "include_evidence": self.include_evidence,
            "include_actions": self.include_actions,
            "statuses": list(self.statuses),
            "contribution_kinds": list(self.contribution_kinds),
            "component_refs": [item.as_dict() for item in self.component_refs],
            "contribution_refs": list(self.contribution_refs),
        }

    def validate_against(
        self,
        projection: BuildingReportProjection,
    ) -> "ReportPresentationSelection":
        if not isinstance(projection, BuildingReportProjection):
            raise TypeError("projection must be BuildingReportProjection")

        payload = projection.as_dict()
        if self.include_evidence and projection.view is not ReportView.AUDIT:
            raise ReportPresentationSelectionError(
                "Audit-specific evidence selection requires ReportView.AUDIT"
            )

        known_statuses = {
            str(item["status"])
            for item in payload.get("status_facets", [])
            if isinstance(item, dict) and "status" in item
        }
        unknown_statuses = tuple(sorted(set(self.statuses) - known_statuses))
        if unknown_statuses:
            raise ReportPresentationSelectionError(
                "unknown exact status selection: " + ", ".join(unknown_statuses)
            )

        known_kinds = {
            str(item["contribution_kind"])
            for item in payload.get("contribution_kind_facets", [])
            if isinstance(item, dict) and "contribution_kind" in item
        }
        unknown_kinds = tuple(sorted(set(self.contribution_kinds) - known_kinds))
        if unknown_kinds:
            raise ReportPresentationSelectionError(
                "unknown exact contribution_kind selection: " + ", ".join(unknown_kinds)
            )

        known_components = {
            ComponentFacetRef(item.get("component_type"), item.get("component_id"))
            for item in payload.get("component_facets", [])
            if isinstance(item, dict)
        }
        unknown_components = tuple(
            item for item in self.component_refs if item not in known_components
        )
        if unknown_components:
            detail = ", ".join(
                f"({item.component_type!r},{item.component_id!r})"
                for item in unknown_components
            )
            raise ReportPresentationSelectionError(
                "unknown exact component selection: " + detail
            )

        known_refs = {
            str(item["contribution_ref"])
            for item in payload.get("contributions", [])
            if isinstance(item, dict) and "contribution_ref" in item
        }
        unknown_refs = tuple(sorted(set(self.contribution_refs) - known_refs))
        if unknown_refs:
            raise ReportPresentationSelectionError(
                "unknown exact contribution_ref selection: " + ", ".join(unknown_refs)
            )
        return self

    def selected_contribution_refs(
        self,
        projection: BuildingReportProjection,
    ) -> tuple[str, ...]:
        """Return exact selected refs without changing projection truth."""

        self.validate_against(projection)
        payload = projection.as_dict()
        component_filter = set(self.component_refs)
        explicit_ref_filter = set(self.contribution_refs)
        status_filter = set(self.statuses)
        kind_filter = set(self.contribution_kinds)

        selected: list[str] = []
        for contribution in payload.get("contributions", []):
            if not isinstance(contribution, dict):
                continue
            ref = str(contribution["contribution_ref"])
            if explicit_ref_filter and ref not in explicit_ref_filter:
                continue
            if status_filter and contribution.get("status") not in status_filter:
                continue
            if kind_filter and contribution.get("contribution_kind") not in kind_filter:
                continue
            if component_filter:
                component = ComponentFacetRef(
                    contribution.get("component_type"),
                    contribution.get("component_id"),
                )
                if component not in component_filter:
                    continue
            selected.append(ref)
        return tuple(selected)


def default_presentation_selection(
    projection: BuildingReportProjection,
) -> ReportPresentationSelection:
    """Return default professional visibility for one canonical view."""

    if not isinstance(projection, BuildingReportProjection):
        raise TypeError("projection must be BuildingReportProjection")
    selection = ReportPresentationSelection(
        include_evidence=projection.view is ReportView.AUDIT,
    )
    return selection.validate_against(projection)


def resolve_presentation_selection(
    projection: BuildingReportProjection,
    selection: ReportPresentationSelection | None,
) -> ReportPresentationSelection:
    if selection is None:
        return default_presentation_selection(projection)
    if not isinstance(selection, ReportPresentationSelection):
        raise TypeError("selection must be ReportPresentationSelection or None")
    return selection.validate_against(projection)


__all__ = [
    "ComponentFacetRef",
    "ReportPresentationSelection",
    "ReportPresentationSelectionError",
    "default_presentation_selection",
    "resolve_presentation_selection",
]
