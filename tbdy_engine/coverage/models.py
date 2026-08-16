"""Coverage matrix models for C5/C5.1.

Coverage describes whether a check has the factual and execution dependencies
needed to run. It never evaluates formulas or emits engineering verdicts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Sequence

from tbdy_engine.contracts.models import freeze_data
from tbdy_engine.coverage.diagnostics import CoverageDiagnostic

_FORBIDDEN_ROW_TOKENS = (
    "CheckResult", "check_result", "pass_rule", "formula", " OK", " FAIL",
    "'OK'", "'FAIL'", '"OK"', '"FAIL"',
)
_FORBIDDEN_FIELD_NAMES = {"ratio", "ratios", "check_result", "check_results", "CheckResult", "pass_rule", "formula"}


class CoverageStatus(StrEnum):
    RUNNABLE = "RUNNABLE"
    BLOCKED = "BLOCKED"
    PARTIAL = "PARTIAL"


class CoveragePolicyStatus(StrEnum):
    RESOLVED = "RESOLVED"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CoverageEvidenceStatus(StrEnum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


class CoverageExecutionContextStatus(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


class ExpectedSourceKind(StrEnum):
    ETABS_TABLE = "etabs_table"
    COMPUTED = "computed"
    DESIGN_CONTEXT = "design_context"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CoverageExecutionContextReadiness:
    context_name: str
    status: CoverageExecutionContextStatus | str
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.context_name:
            raise ValueError("execution context readiness requires context_name")
        normalized = CoverageExecutionContextStatus(str(self.status))
        if normalized != CoverageExecutionContextStatus.READY and not self.reason:
            raise ValueError("PARTIAL/BLOCKED execution context readiness requires a reason")
        object.__setattr__(self, "status", normalized)

    def as_dict(self) -> dict[str, Any]:
        return {"context_name": self.context_name, "status": self.status.value, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class CoverageMissingFeature:
    feature_name: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"feature_name": self.feature_name, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class CoverageMissingDesignContext:
    context_field: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"context_field": self.context_field, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class CoverageExpectedSource:
    source_kind: ExpectedSourceKind | str
    feature_name: str | None = None
    context_name: str | None = None
    table_key: str | None = None
    table_aliases: tuple[str, ...] = field(default_factory=tuple)
    field_aliases: tuple[str, ...] = field(default_factory=tuple)
    filters: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    combo_family: str | None = None
    aggregation: str | None = None
    custom_resolver: str | None = None
    required_inputs: tuple[str, ...] = field(default_factory=tuple)
    source_contract: str | None = None
    source_field: str | None = None
    unit: str | None = None
    expected_evidence_fields: tuple[str, ...] = field(default_factory=tuple)

    def __init__(
        self,
        *,
        source_kind: ExpectedSourceKind | str,
        feature_name: str | None = None,
        context_name: str | None = None,
        table_key: str | None = None,
        table_aliases: Sequence[str] | None = None,
        field_aliases: Sequence[str] | None = None,
        filters: Sequence[Mapping[str, Any]] | None = None,
        combo_family: str | None = None,
        aggregation: str | None = None,
        custom_resolver: str | None = None,
        required_inputs: Sequence[str] | None = None,
        source_contract: str | None = None,
        source_field: str | None = None,
        unit: str | None = None,
        expected_evidence_fields: Sequence[str] | None = None,
    ) -> None:
        object.__setattr__(self, "source_kind", ExpectedSourceKind(str(source_kind)))
        object.__setattr__(self, "feature_name", feature_name)
        object.__setattr__(self, "context_name", context_name)
        object.__setattr__(self, "table_key", table_key)
        object.__setattr__(self, "table_aliases", tuple(str(x) for x in (table_aliases or ())))
        object.__setattr__(self, "field_aliases", tuple(str(x) for x in (field_aliases or ())))
        object.__setattr__(self, "filters", freeze_data([dict(x) for x in (filters or ())]))
        object.__setattr__(self, "combo_family", combo_family)
        object.__setattr__(self, "aggregation", aggregation)
        object.__setattr__(self, "custom_resolver", custom_resolver)
        object.__setattr__(self, "required_inputs", tuple(str(x) for x in (required_inputs or ())))
        object.__setattr__(self, "source_contract", source_contract)
        object.__setattr__(self, "source_field", source_field)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "expected_evidence_fields", tuple(str(x) for x in (expected_evidence_fields or ())))

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_kind": self.source_kind.value,
            "unit": self.unit,
            "expected_evidence_fields": list(self.expected_evidence_fields),
        }
        if self.feature_name is not None:
            payload["feature_name"] = self.feature_name
        if self.context_name is not None:
            payload["context_name"] = self.context_name
        if self.source_kind == ExpectedSourceKind.ETABS_TABLE:
            payload["table_key"] = self.table_key or ""
            payload["table_aliases"] = list(self.table_aliases)
            payload["field_aliases"] = list(self.field_aliases)
            payload["combo_family"] = self.combo_family
            payload["aggregation"] = self.aggregation
            if self.filters:
                payload["filters"] = [dict(item) for item in self.filters]
        else:
            if self.table_key is not None:
                payload["table_key"] = self.table_key
            if self.table_aliases:
                payload["table_aliases"] = list(self.table_aliases)
            if self.field_aliases:
                payload["field_aliases"] = list(self.field_aliases)
            if self.filters:
                payload["filters"] = [dict(item) for item in self.filters]
            if self.combo_family is not None:
                payload["combo_family"] = self.combo_family
            if self.aggregation is not None:
                payload["aggregation"] = self.aggregation
        if self.source_kind == ExpectedSourceKind.COMPUTED:
            payload["custom_resolver"] = self.custom_resolver or "computed_resolver"
            payload["required_inputs"] = list(self.required_inputs)
        elif self.custom_resolver is not None:
            payload["custom_resolver"] = self.custom_resolver
        elif self.required_inputs:
            payload["required_inputs"] = list(self.required_inputs)
        if self.source_contract is not None:
            payload["source_contract"] = self.source_contract
        if self.source_field is not None:
            payload["source_field"] = self.source_field
        return payload


@dataclass(frozen=True, slots=True)
class CoverageRow:
    check_id: str
    component_type: str
    component_id: str
    required_features: tuple[str, ...]
    resolved_features: tuple[str, ...]
    missing_features: tuple[CoverageMissingFeature, ...]
    required_design_context: tuple[str, ...]
    resolved_design_context: tuple[str, ...]
    missing_design_context: tuple[CoverageMissingDesignContext, ...]
    combo_policy_status: CoveragePolicyStatus
    section_state_status: CoveragePolicyStatus
    ductility_context_status: CoveragePolicyStatus
    evidence_status: CoverageEvidenceStatus
    coverage_status: CoverageStatus
    reason: str | None = None
    diagnostics: tuple[CoverageDiagnostic, ...] = field(default_factory=tuple)
    missing_feature_sources: Mapping[str, CoverageExpectedSource] = field(default_factory=dict)
    missing_design_context_sources: Mapping[str, CoverageExpectedSource] = field(default_factory=dict)
    expected_evidence_requirements: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    source_diagnostics: tuple[CoverageDiagnostic, ...] = field(default_factory=tuple)
    required_execution_context: tuple[str, ...] = field(default_factory=tuple)
    execution_context_readiness: tuple[CoverageExecutionContextReadiness, ...] = field(default_factory=tuple)

    def __init__(
        self,
        *,
        check_id: str,
        component_type: str,
        component_id: str,
        required_features: Sequence[str] | None = None,
        resolved_features: Sequence[str] | None = None,
        missing_features: Sequence[CoverageMissingFeature | Mapping[str, str]] | None = None,
        required_design_context: Sequence[str] | None = None,
        resolved_design_context: Sequence[str] | None = None,
        missing_design_context: Sequence[CoverageMissingDesignContext | Mapping[str, str]] | None = None,
        combo_policy_status: CoveragePolicyStatus | str = CoveragePolicyStatus.NOT_APPLICABLE,
        section_state_status: CoveragePolicyStatus | str = CoveragePolicyStatus.NOT_APPLICABLE,
        ductility_context_status: CoveragePolicyStatus | str = CoveragePolicyStatus.NOT_APPLICABLE,
        evidence_status: CoverageEvidenceStatus | str = CoverageEvidenceStatus.FULL,
        coverage_status: CoverageStatus | str = CoverageStatus.RUNNABLE,
        reason: str | None = None,
        diagnostics: Sequence[CoverageDiagnostic] | None = None,
        missing_feature_sources: Mapping[str, CoverageExpectedSource | Mapping[str, Any]] | None = None,
        missing_design_context_sources: Mapping[str, CoverageExpectedSource | Mapping[str, Any]] | None = None,
        expected_evidence_requirements: Mapping[str, Sequence[str]] | None = None,
        source_diagnostics: Sequence[CoverageDiagnostic] | None = None,
        required_execution_context: Sequence[str] | None = None,
        execution_context_readiness: Sequence[CoverageExecutionContextReadiness | Mapping[str, Any]] | None = None,
        **extra: Any,
    ) -> None:
        if extra:
            bad = sorted(set(extra) & _FORBIDDEN_FIELD_NAMES)
            if bad:
                raise ValueError("CoverageRow must not contain ratio, CheckResult, formula, or pass_rule fields")
            raise TypeError("Unexpected CoverageRow field(s): " + ", ".join(sorted(extra)))
        if not check_id or not component_type or not component_id:
            raise ValueError("CoverageRow requires check_id, component_type, and component_id")
        normalized_missing = tuple(
            item if isinstance(item, CoverageMissingFeature) else CoverageMissingFeature(**dict(item))
            for item in (missing_features or ())
        )
        normalized_missing_context = tuple(
            item if isinstance(item, CoverageMissingDesignContext) else CoverageMissingDesignContext(**dict(item))
            for item in (missing_design_context or ())
        )
        normalized_execution = tuple(
            item if isinstance(item, CoverageExecutionContextReadiness) else CoverageExecutionContextReadiness(**dict(item))
            for item in (execution_context_readiness or ())
        )
        required_execution = tuple(str(item) for item in (required_execution_context or ()))
        execution_by_name = {item.context_name: item for item in normalized_execution}
        if len(execution_by_name) != len(normalized_execution):
            raise ValueError("execution_context_readiness must not contain duplicate context_name values")
        unexpected_execution = sorted(set(execution_by_name) - set(required_execution))
        if unexpected_execution:
            raise ValueError("Execution readiness supplied for undeclared context: " + ", ".join(unexpected_execution))
        normalized_status = CoverageStatus(str(coverage_status))
        normalized_evidence = CoverageEvidenceStatus(str(evidence_status))
        normalized_diagnostics = tuple(diagnostics or ())
        normalized_source_diagnostics = tuple(source_diagnostics or ())
        normalized_feature_sources = {
            str(key): value if isinstance(value, CoverageExpectedSource) else CoverageExpectedSource(**dict(value))
            for key, value in (missing_feature_sources or {}).items()
        }
        normalized_context_sources = {
            str(key): value if isinstance(value, CoverageExpectedSource) else CoverageExpectedSource(**dict(value))
            for key, value in (missing_design_context_sources or {}).items()
        }
        normalized_evidence_requirements = {
            str(key): tuple(str(item) for item in value)
            for key, value in (expected_evidence_requirements or {}).items()
        }
        if normalized_status == CoverageStatus.RUNNABLE:
            missing_exec = [name for name in required_execution if name not in execution_by_name]
            nonready_exec = [
                name for name in required_execution
                if name in execution_by_name and execution_by_name[name].status != CoverageExecutionContextStatus.READY
            ]
            if missing_exec or nonready_exec:
                raise ValueError("RUNNABLE coverage requires every mandatory execution context to be READY")
        if normalized_status == CoverageStatus.BLOCKED and not (
            reason or normalized_missing or normalized_missing_context or normalized_execution
        ):
            raise ValueError("BLOCKED coverage requires a reason or missing dependency list")
        if normalized_status in {CoverageStatus.BLOCKED, CoverageStatus.PARTIAL}:
            if not (
                normalized_feature_sources
                or normalized_context_sources
                or normalized_evidence_requirements
                or normalized_source_diagnostics
                or normalized_execution
            ):
                raise ValueError("BLOCKED/PARTIAL coverage requires expected source/readiness diagnostics")
        payload_probe = {
            "check_id": check_id,
            "component_type": component_type,
            "component_id": component_id,
            "required_features": list(required_features or ()),
            "resolved_features": list(resolved_features or ()),
            "missing_features": [m.as_dict() for m in normalized_missing],
            "required_design_context": list(required_design_context or ()),
            "resolved_design_context": list(resolved_design_context or ()),
            "missing_design_context": [m.as_dict() for m in normalized_missing_context],
            "required_execution_context": list(required_execution),
            "execution_context_readiness": [item.as_dict() for item in normalized_execution],
            "reason": reason,
            "missing_feature_sources": {k: v.as_dict() for k, v in normalized_feature_sources.items()},
            "missing_design_context_sources": {k: v.as_dict() for k, v in normalized_context_sources.items()},
            "expected_evidence_requirements": {k: list(v) for k, v in normalized_evidence_requirements.items()},
        }
        self._reject_forbidden(payload_probe)
        object.__setattr__(self, "check_id", check_id)
        object.__setattr__(self, "component_type", component_type)
        object.__setattr__(self, "component_id", component_id)
        object.__setattr__(self, "required_features", tuple(str(x) for x in (required_features or ())))
        object.__setattr__(self, "resolved_features", tuple(str(x) for x in (resolved_features or ())))
        object.__setattr__(self, "missing_features", normalized_missing)
        object.__setattr__(self, "required_design_context", tuple(str(x) for x in (required_design_context or ())))
        object.__setattr__(self, "resolved_design_context", tuple(str(x) for x in (resolved_design_context or ())))
        object.__setattr__(self, "missing_design_context", normalized_missing_context)
        object.__setattr__(self, "combo_policy_status", CoveragePolicyStatus(str(combo_policy_status)))
        object.__setattr__(self, "section_state_status", CoveragePolicyStatus(str(section_state_status)))
        object.__setattr__(self, "ductility_context_status", CoveragePolicyStatus(str(ductility_context_status)))
        object.__setattr__(self, "evidence_status", normalized_evidence)
        object.__setattr__(self, "coverage_status", normalized_status)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "diagnostics", normalized_diagnostics)
        object.__setattr__(self, "missing_feature_sources", freeze_data(normalized_feature_sources))
        object.__setattr__(self, "missing_design_context_sources", freeze_data(normalized_context_sources))
        object.__setattr__(self, "expected_evidence_requirements", freeze_data(normalized_evidence_requirements))
        object.__setattr__(self, "source_diagnostics", normalized_source_diagnostics)
        object.__setattr__(self, "required_execution_context", required_execution)
        object.__setattr__(self, "execution_context_readiness", normalized_execution)

    @staticmethod
    def _reject_forbidden(value: Any) -> None:
        text = repr(value)
        for token in _FORBIDDEN_ROW_TOKENS:
            if token in text:
                raise ValueError("CoverageRow must not contain CheckResult, formula, pass_rule, OK, or FAIL semantics")

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "component_type": self.component_type,
            "component_id": self.component_id,
            "required_features": list(self.required_features),
            "resolved_features": list(self.resolved_features),
            "missing_features": [item.as_dict() for item in self.missing_features],
            "required_design_context": list(self.required_design_context),
            "resolved_design_context": list(self.resolved_design_context),
            "missing_design_context": [item.as_dict() for item in self.missing_design_context],
            "required_execution_context": list(self.required_execution_context),
            "execution_context_readiness": [item.as_dict() for item in self.execution_context_readiness],
            "combo_policy_status": self.combo_policy_status.value,
            "section_state_status": self.section_state_status.value,
            "ductility_context_status": self.ductility_context_status.value,
            "evidence_status": self.evidence_status.value,
            "coverage_status": self.coverage_status.value,
            "reason": self.reason,
            "diagnostics": [diagnostic.as_dict() for diagnostic in self.diagnostics],
            "missing_feature_sources": {key: source.as_dict() for key, source in self.missing_feature_sources.items()},
            "missing_design_context_sources": {key: source.as_dict() for key, source in self.missing_design_context_sources.items()},
            "expected_evidence_requirements": {key: list(value) for key, value in self.expected_evidence_requirements.items()},
            "source_diagnostics": [diagnostic.as_dict() for diagnostic in self.source_diagnostics],
        }

    def as_schema_check_item(
        self,
        check_readiness_status: str = "ready",
        effective_evaluation_level: str | None = None,
    ) -> dict[str, Any]:
        level = effective_evaluation_level or (
            "NO_DATA" if self.coverage_status == CoverageStatus.BLOCKED
            else "SCREENING" if self.coverage_status == CoverageStatus.PARTIAL
            else "DESIGN_LEVEL"
        )
        payload = self.as_dict()
        payload["check_readiness_status"] = check_readiness_status
        payload["effective_evaluation_level"] = level
        return payload


@dataclass(frozen=True, slots=True)
class CoverageMatrix:
    rows: tuple[CoverageRow, ...]
    diagnostics: tuple[CoverageDiagnostic, ...] = field(default_factory=tuple)

    def __init__(
        self,
        rows: Sequence[CoverageRow] | None = None,
        diagnostics: Sequence[CoverageDiagnostic] | None = None,
    ) -> None:
        normalized_rows = tuple(rows or ())
        if any(not isinstance(row, CoverageRow) for row in normalized_rows):
            raise TypeError("CoverageMatrix rows must be CoverageRow objects")
        object.__setattr__(self, "rows", normalized_rows)
        object.__setattr__(self, "diagnostics", tuple(diagnostics or ()))

    def as_dict(self) -> dict[str, Any]:
        return {"rows": [row.as_dict() for row in self.rows], "diagnostics": [d.as_dict() for d in self.diagnostics]}

    def as_schema_document(self, check_readiness: Mapping[str, str] | None = None) -> dict[str, Any]:
        readiness = check_readiness or {}
        return {
            "contract_version": "1.0",
            "checks": [
                row.as_schema_check_item(check_readiness_status=readiness.get(row.check_id, "ready"))
                for row in self.rows
            ],
        }


__all__ = [
    "CoverageEvidenceStatus", "CoverageExecutionContextReadiness",
    "CoverageExecutionContextStatus", "CoverageExpectedSource", "CoverageMatrix",
    "CoverageMissingDesignContext", "CoverageMissingFeature", "CoveragePolicyStatus",
    "CoverageRow", "CoverageStatus", "ExpectedSourceKind",
]
