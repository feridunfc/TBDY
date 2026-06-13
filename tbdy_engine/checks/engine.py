"""C6 Minimal CheckEngine.

The engine consumes already-resolved FeatureSnapshot and CoverageRow objects.
It does not import providers, resolver code, ETABS adapters, table registries,
combo policies, runner_v2, runtime, or archx.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tbdy_engine.checks.diagnostics import CheckDiagnostic, CheckDiagnosticCode, CheckDiagnosticSeverity
from tbdy_engine.checks.pass_rules import PassRuleEvaluator
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.coverage.models import CoverageRow, CoverageStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValueStatus


_ALLOWED_CHECKS = {
    "beam_geometry_min_width",
    "beam_depth_width_ratio",
    "story_drift_availability",
    "story_drift_ratio",
    "modal_mass_availability",
    "column_min_dimension",
}


@dataclass(frozen=True, slots=True)
class MinimalCheckEngine:
    check_definitions: Mapping[str, Mapping[str, Any]]
    evaluator: PassRuleEvaluator = PassRuleEvaluator()

    def run_check(self, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow) -> CheckResult:
        if check_id not in self.check_definitions:
            return self._no_data(
                check_id=check_id,
                snapshot=snapshot,
                coverage=coverage,
                message="Unknown check_id for minimal CheckEngine",
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.CHECK_DEFINITION_INVALID, "Unknown check_id"),),
            )
        definition = dict(self.check_definitions[check_id])
        if check_id not in _ALLOWED_CHECKS and not definition.get("c6_allowed", False):
            return self._no_data(
                check_id=check_id,
                snapshot=snapshot,
                coverage=coverage,
                message="Check is not in the C6 minimal allowlist",
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.CHECK_NOT_ALLOWED, "Not C6 allowed"),),
            )
        if coverage.coverage_status == CoverageStatus.BLOCKED:
            return self._no_data(
                check_id=check_id,
                snapshot=snapshot,
                coverage=coverage,
                message=coverage.reason or "Coverage is BLOCKED; check not executed",
                diagnostics=(
                    CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.COVERAGE_BLOCKED, "BLOCKED coverage never emits OK", coverage.as_dict()),
                ),
            )
        if coverage.coverage_status == CoverageStatus.PARTIAL:
            return self._warning(
                check_id=check_id,
                snapshot=snapshot,
                coverage=coverage,
                message=coverage.reason or "Coverage is PARTIAL; result is warning only",
                diagnostics=(
                    CheckDiagnostic(CheckDiagnosticSeverity.WARNING, CheckDiagnosticCode.COVERAGE_PARTIAL, "PARTIAL coverage never silently emits OK", coverage.as_dict()),
                ),
            )
        return self._evaluate_runnable(check_id, definition, snapshot, coverage)

    def _evaluate_runnable(self, check_id: str, definition: Mapping[str, Any], snapshot: FeatureSnapshot, coverage: CoverageRow) -> CheckResult:
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
        for feature_name in required:
            fv = snapshot.features[feature_name]
            evidence.extend(ev.as_dict() for ev in fv.evidence)
            if fv.status != FeatureValueStatus.RESOLVED:
                return self._warning(check_id=check_id, snapshot=snapshot, coverage=coverage, message=f"Feature is not fully resolved: {feature_name}", evidence=evidence)

        ratio_type = str(definition.get("ratio_type") or definition.get("pass_rule", {}).get("ratio_type") or "availability")
        unit = definition.get("unit")
        code_ref = definition.get("code_ref", "contract")

        variables = {name: snapshot.features[name].value for name in required}
        value = None
        limit = definition.get("limit")
        demand = definition.get("demand")
        capacity = definition.get("capacity")
        ratio = definition.get("ratio")
        actual = definition.get("actual")
        minimum = definition.get("minimum")
        selected = definition.get("selected")
        required_value = definition.get("required")

        # C6 intentionally supports only tiny fixture semantics for the allowlist.
        if check_id == "beam_geometry_min_width":
            value = variables[required[0]] if required else None
            minimum = definition.get("minimum", limit if limit is not None else 250)
            ratio_type = "actual_over_minimum"
            actual = value
        elif check_id == "beam_depth_width_ratio":
            depth = variables.get("beam_depth_mm")
            width = variables.get("beam_width_mm")
            value = (depth / width) if isinstance(depth, (int, float)) and isinstance(width, (int, float)) and width else None
            ratio_type = "value_over_maximum"
            limit = definition.get("limit", 3.5)
        elif check_id == "story_drift_availability":
            value = variables[required[0]] if required else None
            ratio_type = "availability"
        elif check_id == "story_drift_ratio":
            value = variables[required[0]] if required else None
            ratio_type = "value_over_maximum"
            limit = definition.get("limit", 1.0)
        elif check_id == "modal_mass_availability":
            value = variables[required[0]] if required else None
            ratio_type = "availability"
        elif check_id == "modal_mass_participation":
            ux = variables.get("modal_sum_ux")
            uy = variables.get("modal_sum_uy")
            values = [item for item in (ux, uy) if isinstance(item, (int, float))]
            value = min(values) if len(values) == 2 else None
            ratio_type = "value_over_minimum"
            minimum = definition.get("minimum", limit if limit is not None else 0.90)
        elif check_id == "column_min_dimension":
            values = [variables[name] for name in required if isinstance(variables.get(name), (int, float))]
            value = min(values) if values else None
            minimum = definition.get("minimum", limit if limit is not None else 300)
            ratio_type = "actual_over_minimum"
            actual = value
        else:
            value = variables[required[0]] if required else None

        result = self.evaluator.evaluate(
            ratio_type=ratio_type,
            value=value,
            ratio=ratio,
            demand=demand,
            capacity=capacity,
            actual=actual,
            minimum=minimum,
            maximum=definition.get("maximum"),
            selected=selected,
            required=required_value,
            limit=limit,
        )
        return CheckResult(
            check_id=check_id,
            component=snapshot.component_id,
            component_type=snapshot.component_type,
            story=str(snapshot.identity.get("story")) if snapshot.identity.get("story") is not None else None,
            section=str(snapshot.identity.get("section")) if snapshot.identity.get("section") is not None else None,
            status=result.status,
            value=value,
            limit=limit if limit is not None else minimum,
            demand=demand,
            capacity=capacity,
            ratio=result.ratio,
            ratio_type=ratio_type,
            pass_rule=ratio_type,
            unit=unit,
            evaluation_level=EvaluationLevel.SCREENING,
            evidence=evidence,
            messages=result.messages,
            code_ref=code_ref,
            diagnostics=result.diagnostics,
        )

    def _base_identity(self, snapshot: FeatureSnapshot) -> dict[str, str | None]:
        return {
            "component": snapshot.component_id,
            "component_type": snapshot.component_type,
            "story": str(snapshot.identity.get("story")) if snapshot.identity.get("story") is not None else None,
            "section": str(snapshot.identity.get("section")) if snapshot.identity.get("section") is not None else None,
        }

    def _no_data(self, *, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str, diagnostics: Sequence[CheckDiagnostic] = ()) -> CheckResult:
        return CheckResult(
            check_id=check_id,
            **self._base_identity(snapshot),
            status=CheckStatus.NO_DATA,
            evaluation_level=EvaluationLevel.NO_DATA,
            evidence=[coverage.as_dict()],
            messages=(message,),
            code_ref="contract",
            diagnostics=diagnostics,
        )

    def _warning(self, *, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str, diagnostics: Sequence[CheckDiagnostic] = (), evidence: Sequence[Any] = ()) -> CheckResult:
        combined_evidence = list(evidence) + [coverage.as_dict()]
        return CheckResult(
            check_id=check_id,
            **self._base_identity(snapshot),
            status=CheckStatus.WARNING,
            evaluation_level=EvaluationLevel.SCREENING,
            evidence=combined_evidence,
            messages=(message,),
            code_ref="contract",
            diagnostics=diagnostics,
        )


__all__ = ["MinimalCheckEngine"]
