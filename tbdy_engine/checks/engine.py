"""C13.4-P1 boundary-safe minimal CheckEngine."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tbdy_engine.checks.diagnostics import CheckDiagnostic, CheckDiagnosticCode, CheckDiagnosticSeverity
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.coverage.models import CoverageRow, CoverageStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValueStatus


_ALLOWED_CHECKS = {
    "column_geometry_min_dimension",
    "column_geometry_min_width",
    "column_geometry_min_depth",
    "beam_geometry_min_width",
    "beam_geometry_min_depth",
    "beam_depth_width_ratio",
}

_GEOMETRY_LIMITS = {
    "column_geometry_min_dimension": 300.0,
    "column_geometry_min_width": 300.0,
    "column_geometry_min_depth": 300.0,
    "beam_geometry_min_width": 250.0,
    "beam_geometry_min_depth": 300.0,
    "beam_depth_width_ratio": 3.5,
}


def _component_type_norm(value: Any) -> str:
    return str(value or "").strip().casefold()


@dataclass(frozen=True, slots=True)
class MinimalCheckEngine:
    check_definitions: Mapping[str, Mapping[str, Any]]

    def run_check(self, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow) -> CheckResult:
        if check_id not in self.check_definitions:
            return self._no_data(
                check_id=check_id,
                snapshot=snapshot,
                coverage=coverage,
                message="Unknown check_id for C13.4-P1 MinimalCheckEngine",
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.CHECK_DEFINITION_INVALID, "Unknown check_id"),),
            )
        definition = dict(self.check_definitions[check_id])
        if check_id not in _ALLOWED_CHECKS:
            return self._blocked(
                check_id=check_id,
                snapshot=snapshot,
                coverage=coverage,
                message="Check is outside the C13.4-P1 geometry-only allowlist",
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.CHECK_NOT_ALLOWED, "Check blocked by C13.4-P1 allowlist"),),
            )
        if coverage.coverage_status == CoverageStatus.BLOCKED:
            return self._blocked(
                check_id=check_id,
                snapshot=snapshot,
                coverage=coverage,
                message=coverage.reason or "Coverage policy is not ready; check not executed",
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.COVERAGE_BLOCKED, "Coverage policy blocks execution", coverage.as_dict()),),
            )
        expected_type = _component_type_norm(definition.get("element_type") or coverage.component_type)
        actual_type = _component_type_norm(snapshot.component_type)
        if expected_type and actual_type != expected_type:
            return self._out_of_scope(
                check_id=check_id,
                snapshot=snapshot,
                coverage=coverage,
                message=f"Check applies to component_type={expected_type}; snapshot has component_type={snapshot.component_type}",
            )
        if coverage.coverage_status == CoverageStatus.PARTIAL:
            return self._warning(
                check_id=check_id,
                snapshot=snapshot,
                coverage=coverage,
                message=coverage.reason or "Coverage is partial; result is screening only",
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.WARNING, CheckDiagnosticCode.COVERAGE_PARTIAL, "Partial coverage never silently emits OK", coverage.as_dict()),),
            )
        return self._evaluate_geometry_check(check_id, definition, snapshot, coverage)

    def _evaluate_geometry_check(self, check_id: str, definition: Mapping[str, Any], snapshot: FeatureSnapshot, coverage: CoverageRow) -> CheckResult:
        required = list(definition.get("required_features") or coverage.required_features)
        missing = [name for name in required if name not in snapshot.features]
        if missing:
            return self._no_data(
                check_id=check_id,
                snapshot=snapshot,
                coverage=coverage,
                message="Required features missing from snapshot: " + ", ".join(missing),
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.FEATURE_MISSING, "Required feature missing", {"missing": missing}),),
            )

        evidence = []
        variables: dict[str, Any] = {}
        for feature_name in required:
            fv = snapshot.features[feature_name]
            evidence.extend(ev.as_dict() for ev in fv.evidence)
            if fv.status != FeatureValueStatus.RESOLVED:
                return self._warning(
                    check_id=check_id,
                    snapshot=snapshot,
                    coverage=coverage,
                    message=f"Feature is not fully resolved: {feature_name}",
                    diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.WARNING, CheckDiagnosticCode.FEATURE_MISSING, "Feature is not fully resolved", {"feature": feature_name}),),
                    evidence=evidence,
                )
            variables[feature_name] = fv.value

        try:
            value, limit, ratio, ratio_type = self._geometry_value(check_id, variables)
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            return self._no_data(
                check_id=check_id,
                snapshot=snapshot,
                coverage=coverage,
                message=str(exc),
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.FEATURE_MISSING, str(exc)),),
            )

        status = CheckStatus.OK if self._geometry_satisfies(check_id, value, limit) else CheckStatus.FAIL
        return CheckResult(
            check_id=check_id,
            component=snapshot.component_id,
            component_type=snapshot.component_type,
            story=str(snapshot.identity.get("story")) if snapshot.identity.get("story") is not None else None,
            section=str(snapshot.identity.get("section")) if snapshot.identity.get("section") is not None else None,
            status=status,
            value=value,
            limit=limit,
            ratio=ratio,
            ratio_type=ratio_type,
            pass_rule=ratio_type,
            unit="mm" if check_id != "beam_depth_width_ratio" else "",
            evaluation_level=EvaluationLevel.SCREENING,
            evidence=evidence,
            messages=("C13.4-P1 geometry-only canonical CheckResult",),
            code_ref=definition.get("code_ref", "contract"),
            diagnostics=(),
        )

    @staticmethod
    def _number(name: str, value: Any) -> float:
        if not isinstance(value, (int, float)):
            raise TypeError(f"Required numeric feature is missing or non-numeric: {name}")
        return float(value)

    def _geometry_value(self, check_id: str, variables: Mapping[str, Any]) -> tuple[float, float, float, str]:
        if check_id == "column_geometry_min_dimension":
            width = self._number("column_width_mm", variables.get("column_width_mm"))
            depth = self._number("column_depth_mm", variables.get("column_depth_mm"))
            value = min(width, depth)
            minimum = _GEOMETRY_LIMITS[check_id]
            return value, minimum, value / minimum, "actual_over_minimum"
        if check_id == "column_geometry_min_width":
            value = self._number("column_width_mm", variables.get("column_width_mm"))
            minimum = _GEOMETRY_LIMITS[check_id]
            return value, minimum, value / minimum, "actual_over_minimum"
        if check_id == "column_geometry_min_depth":
            value = self._number("column_depth_mm", variables.get("column_depth_mm"))
            minimum = _GEOMETRY_LIMITS[check_id]
            return value, minimum, value / minimum, "actual_over_minimum"
        if check_id == "beam_geometry_min_width":
            value = self._number("beam_width_mm", variables.get("beam_width_mm"))
            minimum = _GEOMETRY_LIMITS[check_id]
            return value, minimum, value / minimum, "actual_over_minimum"
        if check_id == "beam_geometry_min_depth":
            value = self._number("beam_depth_mm", variables.get("beam_depth_mm"))
            minimum = _GEOMETRY_LIMITS[check_id]
            return value, minimum, value / minimum, "actual_over_minimum"
        if check_id == "beam_depth_width_ratio":
            depth = self._number("beam_depth_mm", variables.get("beam_depth_mm"))
            width = self._number("beam_width_mm", variables.get("beam_width_mm"))
            if width == 0:
                raise ZeroDivisionError("beam_width_mm is zero; depth/width ratio cannot be evaluated")
            maximum = _GEOMETRY_LIMITS[check_id]
            value = depth / width
            return value, maximum, value / maximum, "value_over_maximum"
        raise ValueError("Check is outside C13.4-P1 geometry implementation")

    @staticmethod
    def _geometry_satisfies(check_id: str, value: float, limit: float) -> bool:
        if check_id == "beam_depth_width_ratio":
            return value <= limit
        return value >= limit

    def _base_identity(self, snapshot: FeatureSnapshot) -> dict[str, str | None]:
        return {
            "component": snapshot.component_id,
            "component_type": snapshot.component_type,
            "story": str(snapshot.identity.get("story")) if snapshot.identity.get("story") is not None else None,
            "section": str(snapshot.identity.get("section")) if snapshot.identity.get("section") is not None else None,
        }

    def _no_data(self, *, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str, diagnostics: Sequence[CheckDiagnostic] = ()) -> CheckResult:
        return CheckResult(check_id=check_id, **self._base_identity(snapshot), status=CheckStatus.NO_DATA, evaluation_level=EvaluationLevel.NO_DATA, evidence=[coverage.as_dict()], messages=(message,), code_ref="contract", diagnostics=diagnostics)

    def _blocked(self, *, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str, diagnostics: Sequence[CheckDiagnostic] = ()) -> CheckResult:
        return CheckResult(check_id=check_id, **self._base_identity(snapshot), status=CheckStatus.BLOCKED, evaluation_level=EvaluationLevel.NO_DATA, evidence=[coverage.as_dict()], messages=(message,), code_ref="contract", diagnostics=diagnostics)

    def _out_of_scope(self, *, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str) -> CheckResult:
        return CheckResult(check_id=check_id, **self._base_identity(snapshot), status=CheckStatus.OUT_OF_SCOPE, evaluation_level=EvaluationLevel.NO_DATA, evidence=[coverage.as_dict()], messages=(message,), code_ref="contract", diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.INFO, CheckDiagnosticCode.CHECK_NOT_ALLOWED, "Component is outside this check scope"),))

    def _warning(self, *, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str, diagnostics: Sequence[CheckDiagnostic] = (), evidence: Sequence[Any] = ()) -> CheckResult:
        combined_evidence = list(evidence) + [coverage.as_dict()]
        return CheckResult(check_id=check_id, **self._base_identity(snapshot), status=CheckStatus.WARNING, evaluation_level=EvaluationLevel.SCREENING, evidence=combined_evidence, messages=(message,), code_ref="contract", diagnostics=diagnostics)


__all__ = ["MinimalCheckEngine", "_ALLOWED_CHECKS"]
