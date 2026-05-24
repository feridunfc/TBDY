from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol


class ReportSpecLike(Protocol):
    formats: list[str]
    include: list[str]
    sections: list[str]
    filters: dict[str, object]
    include_fields: list[str]
    metrics: list[str]


@dataclass(frozen=True)
class PlannedReport:
    report_id: str
    formats: tuple[str, ...] = field(default_factory=tuple)
    include: tuple[str, ...] = field(default_factory=tuple)
    sections: tuple[str, ...] = field(default_factory=tuple)
    filters: Mapping[str, object] = field(default_factory=dict)
    include_fields: tuple[str, ...] = field(default_factory=tuple)
    metrics: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ReportPlan:
    reports: Mapping[str, PlannedReport]

    def report_ids(self) -> tuple[str, ...]:
        return tuple(self.reports.keys())

    def get(self, report_id: str) -> PlannedReport:
        return self.reports[report_id]


class ReportPlanner:
    def __init__(self, reports: Mapping[str, ReportSpecLike | Mapping[str, object]]):
        self._reports = reports

    def plan(self) -> ReportPlan:
        return ReportPlan(
            reports={
                report_id: self._planned_report(report_id, spec)
                for report_id, spec in self._reports.items()
            }
        )

    def _planned_report(
        self,
        report_id: str,
        spec: ReportSpecLike | Mapping[str, object],
    ) -> PlannedReport:
        return PlannedReport(
            report_id=report_id,
            formats=tuple(self._get_sequence(spec, "formats")),
            include=tuple(self._get_sequence(spec, "include")),
            sections=tuple(self._get_sequence(spec, "sections")),
            filters=dict(self._get_mapping(spec, "filters")),
            include_fields=tuple(self._get_sequence(spec, "include_fields")),
            metrics=tuple(self._get_sequence(spec, "metrics")),
        )

    def _get_sequence(
        self,
        spec: ReportSpecLike | Mapping[str, object],
        field_name: str,
    ) -> list[str]:
        value = self._get_value(spec, field_name, [])
        if value is None:
            return []
        return [str(item) for item in value]

    def _get_mapping(
        self,
        spec: ReportSpecLike | Mapping[str, object],
        field_name: str,
    ) -> Mapping[str, object]:
        value = self._get_value(spec, field_name, {})
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise TypeError(f"Report field '{field_name}' must be a mapping")
        return value

    def _get_value(
        self,
        spec: ReportSpecLike | Mapping[str, object],
        field_name: str,
        default: object,
    ) -> object:
        if isinstance(spec, Mapping):
            return spec.get(field_name, default)
        return getattr(spec, field_name, default)
