"""Canonical boundary-safe CheckEngine, extended with P2.10 Wall Check Pack A."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tbdy_engine.checks.diagnostics import CheckDiagnostic, CheckDiagnosticCode, CheckDiagnosticSeverity
from tbdy_engine.checks.input_adapter import GeometryCheckInput
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.checks.wall_pack_a_contract import (
    PACK_A_CHECK_IDS,
    UNRESTRAINED_GEOMETRY_CLASSIFICATIONS,
    WALL_BODY_CLASSIFICATIONS,
    WALL_GEOM_BODY_THICKNESS_GE_250,
    WALL_GEOM_BODY_THICKNESS_GE_H16,
    WALL_GEOM_DEFINITION_LW_BW_GE6,
    WALL_GEOM_RESTRAINED_LEG_THICKNESS,
    WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30,
)
from tbdy_engine.coverage.models import CoverageRow, CoverageStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValueStatus

_ALLOWED_CHECKS = {
    "column_geometry_min_dimension", "column_geometry_min_width", "column_geometry_min_depth",
    "beam_geometry_min_width", "beam_geometry_min_depth", "beam_depth_width_ratio", *PACK_A_CHECK_IDS,
}
_GEOMETRY_LIMITS = {
    "column_geometry_min_dimension": 300.0, "column_geometry_min_width": 300.0,
    "column_geometry_min_depth": 300.0, "beam_geometry_min_width": 250.0,
    "beam_geometry_min_depth": 300.0, "beam_depth_width_ratio": 3.5,
}


def _component_type_norm(value: Any) -> str:
    return str(value or "").strip().casefold()


@dataclass(frozen=True, slots=True)
class MinimalCheckEngine:
    """Single canonical engineering decision authority for registered checks."""

    check_definitions: Mapping[str, Mapping[str, Any]]

    def run_input(self, check_input: GeometryCheckInput) -> CheckResult:
        if not isinstance(check_input, GeometryCheckInput):
            raise TypeError("run_input requires canonical GeometryCheckInput")
        if check_input.check_id != check_input.coverage.check_id:
            raise ValueError("CheckInput and CoverageRow check_id must match")
        if check_input.component_id != check_input.snapshot.component_id:
            raise ValueError("CheckInput and FeatureSnapshot component identity must match")
        return self.run_check(check_input.check_id, check_input.snapshot, check_input.coverage)

    def run_check(self, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow) -> CheckResult:
        if check_id not in self.check_definitions:
            return self._no_data(
                check_id=check_id, snapshot=snapshot, coverage=coverage,
                message="Unknown check_id for canonical MinimalCheckEngine",
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.CHECK_DEFINITION_INVALID, "Unknown check_id"),),
            )
        definition = dict(self.check_definitions[check_id])
        if check_id not in _ALLOWED_CHECKS:
            return self._blocked(
                check_id=check_id, snapshot=snapshot, coverage=coverage,
                message="Check is outside the canonical geometry allowlist",
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.CHECK_NOT_ALLOWED, "Check blocked by canonical geometry allowlist"),),
            )
        if coverage.coverage_status == CoverageStatus.BLOCKED:
            return self._blocked(
                check_id=check_id, snapshot=snapshot, coverage=coverage,
                message=coverage.reason or "Coverage is BLOCKED; check not executed",
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.COVERAGE_BLOCKED, "Coverage blocks execution", coverage.as_dict()),),
                code_ref=str(definition.get("code_ref") or "contract"),
            )
        expected_type = _component_type_norm(definition.get("element_type") or coverage.component_type)
        actual_type = _component_type_norm(snapshot.component_type)
        if expected_type and actual_type != expected_type:
            return self._out_of_scope(
                check_id=check_id, snapshot=snapshot, coverage=coverage,
                message=f"Check applies to component_type={expected_type}; snapshot has component_type={snapshot.component_type}",
                code_ref=str(definition.get("code_ref") or "contract"),
            )
        if coverage.coverage_status == CoverageStatus.PARTIAL:
            if check_id in PACK_A_CHECK_IDS:
                return self._blocked(
                    check_id=check_id, snapshot=snapshot, coverage=coverage,
                    message=coverage.reason or "Pack A requires FULL canonical fact coverage",
                    diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.COVERAGE_BLOCKED, "Partial coverage is not executable for formal Pack A checks", coverage.as_dict()),),
                    code_ref=str(definition.get("code_ref") or "contract"),
                )
            return self._warning(
                check_id=check_id, snapshot=snapshot, coverage=coverage,
                message=coverage.reason or "Coverage is partial; result is screening only",
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.WARNING, CheckDiagnosticCode.COVERAGE_PARTIAL, "Partial coverage never silently emits OK", coverage.as_dict()),),
            )
        return self._evaluate_geometry_check(check_id, definition, snapshot, coverage)

    def _evaluate_geometry_check(self, check_id: str, definition: Mapping[str, Any], snapshot: FeatureSnapshot, coverage: CoverageRow) -> CheckResult:
        required = list(definition.get("required_features") or coverage.required_features)
        missing = [name for name in required if name not in snapshot.features]
        if missing:
            return self._no_data(
                check_id=check_id, snapshot=snapshot, coverage=coverage,
                message="Required features missing from snapshot: " + ", ".join(missing),
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.FEATURE_MISSING, "Required feature missing", {"missing": missing}),),
                code_ref=str(definition.get("code_ref") or "contract"),
            )
        evidence: list[Any] = []
        variables: dict[str, Any] = {}
        for feature_name in required:
            fv = snapshot.features[feature_name]
            evidence.extend(ev.as_dict() for ev in fv.evidence)
            if fv.status != FeatureValueStatus.RESOLVED:
                if check_id in PACK_A_CHECK_IDS:
                    return self._blocked(
                        check_id=check_id, snapshot=snapshot, coverage=coverage,
                        message=f"Required canonical feature is not resolved: {feature_name}",
                        evidence=evidence, code_ref=str(definition.get("code_ref") or "contract"),
                    )
                return self._warning(
                    check_id=check_id, snapshot=snapshot, coverage=coverage,
                    message=f"Feature is not fully resolved: {feature_name}",
                    diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.WARNING, CheckDiagnosticCode.FEATURE_MISSING, "Feature is not fully resolved", {"feature": feature_name}),),
                    evidence=evidence,
                )
            variables[feature_name] = fv.value

        if check_id in PACK_A_CHECK_IDS:
            return self._evaluate_wall_pack_a(check_id, definition, snapshot, coverage, variables, evidence)

        try:
            value, limit, ratio, ratio_type = self._geometry_value(check_id, variables)
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            return self._no_data(
                check_id=check_id, snapshot=snapshot, coverage=coverage, message=str(exc),
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.FEATURE_MISSING, str(exc)),),
            )
        status = CheckStatus.OK if self._geometry_satisfies(check_id, value, limit) else CheckStatus.FAIL
        return CheckResult(
            check_id=check_id, component=snapshot.component_id, component_type=snapshot.component_type,
            story=self._story(snapshot), section=self._section(snapshot), status=status,
            value=value, limit=limit, ratio=ratio, ratio_type=ratio_type, pass_rule=ratio_type,
            unit="mm" if check_id != "beam_depth_width_ratio" else "",
            evaluation_level=EvaluationLevel.SCREENING, evidence=evidence,
            messages=("Canonical geometry CheckResult",), code_ref=definition.get("code_ref", "contract"), diagnostics=(),
        )

    def _evaluate_wall_pack_a(
        self, check_id: str, definition: Mapping[str, Any], snapshot: FeatureSnapshot,
        coverage: CoverageRow, variables: Mapping[str, Any], evidence: Sequence[Any],
    ) -> CheckResult:
        code_ref = str(definition.get("code_ref") or "contract")
        try:
            basement = self._boolean("wall_is_basement", variables.get("wall_is_basement"))
            if basement:
                return self._out_of_scope(
                    check_id=check_id, snapshot=snapshot, coverage=coverage,
                    message="TBDY §7.6.1 Pack A does not apply to basement walls", code_ref=code_ref, evidence=evidence,
                )
            if check_id in {WALL_GEOM_BODY_THICKNESS_GE_H16, WALL_GEOM_BODY_THICKNESS_GE_250}:
                body = self._text("wall_body_classification", variables.get("wall_body_classification"))
                if body not in WALL_BODY_CLASSIFICATIONS:
                    return self._out_of_scope(
                        check_id=check_id, snapshot=snapshot, coverage=coverage,
                        message="Resolved wall body classification is outside §7.6.1.2(a) Pack A scope", code_ref=code_ref, evidence=evidence,
                    )
                special = self._boolean("wall_special_branch_7_6_1_3_applies", variables.get("wall_special_branch_7_6_1_3_applies"))
                if special:
                    return self._out_of_scope(
                        check_id=check_id, snapshot=snapshot, coverage=coverage,
                        message="§7.6.1.3 special branch is explicitly outside Pack A", code_ref=code_ref, evidence=evidence,
                    )
            if check_id == WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30:
                classification = self._text("wall_geometry_classification", variables.get("wall_geometry_classification"))
                if classification not in UNRESTRAINED_GEOMETRY_CLASSIFICATIONS:
                    return self._out_of_scope(
                        check_id=check_id, snapshot=snapshot, coverage=coverage,
                        message="Resolved geometry classification is outside §7.6.1.2(b) scope", code_ref=code_ref, evidence=evidence,
                    )
            if check_id == WALL_GEOM_RESTRAINED_LEG_THICKNESS:
                restrained = self._boolean("wall_both_ends_laterally_restrained", variables.get("wall_both_ends_laterally_restrained"))
                if not restrained:
                    return self._out_of_scope(
                        check_id=check_id, snapshot=snapshot, coverage=coverage,
                        message="Wall leg is not laterally restrained by a wall at both ends", code_ref=code_ref, evidence=evidence,
                    )
            value, limit, ratio, unit = self._wall_pack_a_value(check_id, variables)
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            return self._no_data(
                check_id=check_id, snapshot=snapshot, coverage=coverage, message=str(exc),
                diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.FEATURE_MISSING, str(exc)),),
                code_ref=code_ref,
            )
        status = CheckStatus.OK if value >= limit else CheckStatus.FAIL
        return CheckResult(
            check_id=check_id, component=snapshot.component_id, component_type=snapshot.component_type,
            story=self._story(snapshot), section=self._section(snapshot), status=status,
            value=value, limit=limit, ratio=ratio, ratio_type="actual_over_minimum", pass_rule="actual_over_minimum",
            unit=unit, evaluation_level=EvaluationLevel.DESIGN_LEVEL, evidence=evidence,
            messages=("Formal P2.10 Wall Check Pack A canonical result",), code_ref=code_ref, diagnostics=(),
        )

    def _wall_pack_a_value(self, check_id: str, variables: Mapping[str, Any]) -> tuple[float, float, float, str]:
        thickness = self._positive("wall_thickness_mm", variables.get("wall_thickness_mm"))
        if check_id == WALL_GEOM_DEFINITION_LW_BW_GE6:
            length = self._positive("wall_length_mm", variables.get("wall_length_mm"))
            value = length / thickness
            minimum = 6.0
            return value, minimum, value / minimum, ""
        if check_id == WALL_GEOM_BODY_THICKNESS_GE_H16:
            story_height = self._positive("story_height_mm", variables.get("story_height_mm"))
            minimum = story_height / 16.0
            return thickness, minimum, thickness / minimum, "mm"
        if check_id == WALL_GEOM_BODY_THICKNESS_GE_250:
            minimum = 250.0
            return thickness, minimum, thickness / minimum, "mm"
        if check_id == WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30:
            unrestrained = self._positive("unrestrained_plan_length_mm", variables.get("unrestrained_plan_length_mm"))
            minimum = unrestrained / 30.0
            return thickness, minimum, thickness / minimum, "mm"
        if check_id == WALL_GEOM_RESTRAINED_LEG_THICKNESS:
            story_height = self._positive("story_height_mm", variables.get("story_height_mm"))
            minimum = max(story_height / 20.0, 250.0)
            return thickness, minimum, thickness / minimum, "mm"
        raise ValueError("Unknown Pack A wall geometry check")

    @staticmethod
    def _number(name: str, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"Required numeric feature is missing or non-numeric: {name}")
        return float(value)

    @classmethod
    def _positive(cls, name: str, value: Any) -> float:
        number = cls._number(name, value)
        if number <= 0:
            raise ValueError(f"Required canonical length must be positive: {name}")
        return number

    @staticmethod
    def _boolean(name: str, value: Any) -> bool:
        if not isinstance(value, bool):
            raise TypeError(f"Required applicability/topology fact must be boolean: {name}")
        return value

    @staticmethod
    def _text(name: str, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"Required classification fact must be a nonblank string: {name}")
        return value.strip()

    def _geometry_value(self, check_id: str, variables: Mapping[str, Any]) -> tuple[float, float, float, str]:
        if check_id == "column_geometry_min_dimension":
            width = self._number("column_width_mm", variables.get("column_width_mm")); depth = self._number("column_depth_mm", variables.get("column_depth_mm"))
            value = min(width, depth); minimum = _GEOMETRY_LIMITS[check_id]
            return value, minimum, value / minimum, "actual_over_minimum"
        if check_id == "column_geometry_min_width":
            value = self._number("column_width_mm", variables.get("column_width_mm")); minimum = _GEOMETRY_LIMITS[check_id]
            return value, minimum, value / minimum, "actual_over_minimum"
        if check_id == "column_geometry_min_depth":
            value = self._number("column_depth_mm", variables.get("column_depth_mm")); minimum = _GEOMETRY_LIMITS[check_id]
            return value, minimum, value / minimum, "actual_over_minimum"
        if check_id == "beam_geometry_min_width":
            value = self._number("beam_width_mm", variables.get("beam_width_mm")); minimum = _GEOMETRY_LIMITS[check_id]
            return value, minimum, value / minimum, "actual_over_minimum"
        if check_id == "beam_geometry_min_depth":
            value = self._number("beam_depth_mm", variables.get("beam_depth_mm")); minimum = _GEOMETRY_LIMITS[check_id]
            return value, minimum, value / minimum, "actual_over_minimum"
        if check_id == "beam_depth_width_ratio":
            depth = self._number("beam_depth_mm", variables.get("beam_depth_mm")); width = self._number("beam_width_mm", variables.get("beam_width_mm"))
            if width == 0:
                raise ZeroDivisionError("beam_width_mm is zero; depth/width ratio cannot be evaluated")
            maximum = _GEOMETRY_LIMITS[check_id]; value = depth / width
            return value, maximum, value / maximum, "value_over_maximum"
        raise ValueError("Check is outside canonical geometry implementation")

    @staticmethod
    def _geometry_satisfies(check_id: str, value: float, limit: float) -> bool:
        return value <= limit if check_id == "beam_depth_width_ratio" else value >= limit

    @staticmethod
    def _story(snapshot: FeatureSnapshot) -> str | None:
        value = snapshot.identity.get("story")
        return None if value is None else str(value)

    @staticmethod
    def _section(snapshot: FeatureSnapshot) -> str | None:
        value = snapshot.identity.get("section")
        return None if value is None else str(value)

    def _base_identity(self, snapshot: FeatureSnapshot) -> dict[str, str | None]:
        return {"component": snapshot.component_id, "component_type": snapshot.component_type, "story": self._story(snapshot), "section": self._section(snapshot)}

    def _no_data(self, *, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str, diagnostics: Sequence[CheckDiagnostic] = (), code_ref: str = "contract") -> CheckResult:
        return CheckResult(check_id=check_id, **self._base_identity(snapshot), status=CheckStatus.NO_DATA, evaluation_level=EvaluationLevel.NO_DATA, evidence=[coverage.as_dict()], messages=(message,), code_ref=code_ref, diagnostics=diagnostics)

    def _blocked(self, *, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str, diagnostics: Sequence[CheckDiagnostic] = (), evidence: Sequence[Any] = (), code_ref: str = "contract") -> CheckResult:
        return CheckResult(check_id=check_id, **self._base_identity(snapshot), status=CheckStatus.BLOCKED, evaluation_level=EvaluationLevel.NO_DATA, evidence=list(evidence) + [coverage.as_dict()], messages=(message,), code_ref=code_ref, diagnostics=diagnostics)

    def _out_of_scope(self, *, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str, code_ref: str = "contract", evidence: Sequence[Any] = ()) -> CheckResult:
        return CheckResult(
            check_id=check_id, **self._base_identity(snapshot), status=CheckStatus.OUT_OF_SCOPE,
            evaluation_level=EvaluationLevel.NO_DATA, evidence=list(evidence) + [coverage.as_dict()], messages=(message,), code_ref=code_ref,
            diagnostics=(CheckDiagnostic(CheckDiagnosticSeverity.INFO, CheckDiagnosticCode.CHECK_NOT_ALLOWED, "Resolved applicability places component outside this check scope"),),
        )

    def _warning(self, *, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str, diagnostics: Sequence[CheckDiagnostic] = (), evidence: Sequence[Any] = ()) -> CheckResult:
        return CheckResult(
            check_id=check_id, **self._base_identity(snapshot), status=CheckStatus.WARNING,
            evaluation_level=EvaluationLevel.SCREENING, evidence=list(evidence) + [coverage.as_dict()],
            messages=(message,), code_ref="contract", diagnostics=diagnostics,
        )


__all__ = ["MinimalCheckEngine", "_ALLOWED_CHECKS"]
