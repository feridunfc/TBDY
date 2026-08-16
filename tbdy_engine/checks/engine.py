"""Canonical boundary-safe CheckEngine with registered wall evaluators."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tbdy_engine.checks.diagnostics import CheckDiagnostic, CheckDiagnosticCode, CheckDiagnosticSeverity
from tbdy_engine.checks.input_adapter import GeometryCheckInput
from tbdy_engine.checks.member_geometry import (
    BEAM_7411_APPLICABILITY_CONTEXT,
    COLUMN_MIN_DIMENSION,
    COLUMN_SECTION_SHAPE_CONTEXT,
    LEGACY_COLUMN_ALIASES,
    MEMBER_FORMAL_CHECK_IDS,
    MEMBER_GEOMETRY_REGISTRATIONS,
    evaluate_member_rule,
)
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.checks.wall_applicability import (
    WallCriticalHeightDerivation,
    critical_region_story_names,
    derive_highest_applicable_story_height_mm,
    derive_ndm_n,
    derive_net_section_area_mm2,
    derive_wall_critical_height,
    resolve_special_branch_applicability,
)
from tbdy_engine.checks.wall_contract import (
    PACK_B_NEW_CHECK_IDS,
    PACK_C_CHECK_IDS,
    WALL_END_REGIONS_REQUIRED_HW_LW_GT2,
    WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW,
    WALL_GEOM_SPECIAL_THICKNESS_GE_200,
    WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20,
    WALL_HCR_GE_HW_DIV6,
    WALL_HCR_GE_LW,
    WALL_HCR_LE_2LW,
    WALL_NET_SECTION_AXIAL_CAPACITY,
)
from tbdy_engine.checks.wall_evaluators import WALL_EVALUATORS
from tbdy_engine.checks.wall_pack_a_contract import (
    PACK_A_CHECK_IDS,
    UNRESTRAINED_GEOMETRY_CLASSIFICATIONS,
    WALL_BODY_CLASSIFICATIONS,
    WALL_GEOM_BODY_THICKNESS_GE_250,
    WALL_GEOM_BODY_THICKNESS_GE_H16,
    WALL_GEOM_RESTRAINED_LEG_THICKNESS,
    WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30,
)
from tbdy_engine.coverage.models import CoverageRow, CoverageStatus
from tbdy_engine.features.result_evidence import ResultRowEvidenceBundle
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValueStatus
from tbdy_engine.features.wall_critical_evidence import (
    WallCriticalHeightFactualEvidence,
    WallRegulatoryReferenceFacts,
)

_WALL_CHECK_IDS = frozenset((*PACK_A_CHECK_IDS, *PACK_B_NEW_CHECK_IDS, *PACK_C_CHECK_IDS))
_MEMBER_COMPATIBILITY_CHECK_IDS = frozenset(LEGACY_COLUMN_ALIASES)
_ALLOWED_CHECKS = frozenset((*MEMBER_FORMAL_CHECK_IDS, *_MEMBER_COMPATIBILITY_CHECK_IDS, *_WALL_CHECK_IDS))
_GENERAL_BRANCH_IDS = {WALL_GEOM_BODY_THICKNESS_GE_H16, WALL_GEOM_BODY_THICKNESS_GE_250}
_SPECIAL_BRANCH_IDS = {WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20, WALL_GEOM_SPECIAL_THICKNESS_GE_200}


def _component_type_norm(value: Any) -> str:
    return str(value or "").strip().casefold()


@dataclass(frozen=True, slots=True)
class MinimalCheckEngine:
    """Single canonical engineering decision authority for registered checks."""

    check_definitions: Mapping[str, Mapping[str, Any]]

    def run_check(self, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow) -> CheckResult:
        """Legacy geometry compatibility wrapper; all execution delegates to CheckInput.

        Wall checks with mandatory execution context cannot use this legacy API.
        They must arrive as a fully materialized canonical GeometryCheckInput via
        ``run_input``.
        """
        if not isinstance(snapshot, FeatureSnapshot):
            raise TypeError("run_check snapshot must be a FeatureSnapshot")
        if not isinstance(coverage, CoverageRow):
            raise TypeError("run_check coverage must be a CoverageRow")
        definition = self.check_definitions.get(check_id)
        required_features = tuple(
            str(name)
            for name in ((definition or {}).get("required_features") or coverage.required_features or ())
        )
        required_execution = tuple(
            str(name) for name in ((definition or {}).get("required_execution_context", ()) or ())
        )
        if required_execution:
            raise TypeError(
                "Legacy run_check cannot execute checks with mandatory execution context; "
                "build canonical CheckInput and call run_input(check_input)"
            )
        evidence_by_feature = {
            feature_name: tuple(snapshot.features[feature_name].evidence)
            if feature_name in snapshot.features else ()
            for feature_name in required_features
        }
        return self.run_input(GeometryCheckInput(
            check_id=check_id,
            component_id=snapshot.component_id,
            component_type=snapshot.component_type,
            story=self._story(snapshot),
            section=self._section(snapshot),
            required_features=required_features,
            snapshot=snapshot,
            coverage=coverage,
            evidence_by_feature=evidence_by_feature,
        ))

    def run_input(self, check_input: GeometryCheckInput) -> CheckResult:
        """Execute one canonical CheckInput; no parallel execution-context channel exists."""
        if not isinstance(check_input, GeometryCheckInput):
            raise TypeError("run_input requires canonical GeometryCheckInput")
        if check_input.check_id != check_input.coverage.check_id:
            raise ValueError("CheckInput and CoverageRow check_id must match")
        if check_input.component_id != check_input.snapshot.component_id:
            raise ValueError("CheckInput and FeatureSnapshot component identity must match")
        check_id = check_input.check_id
        snapshot = check_input.snapshot
        coverage = check_input.coverage
        definition = self.check_definitions.get(check_id)
        if definition is None:
            return self._no_data(check_id, snapshot, coverage, "Unknown check_id for canonical MinimalCheckEngine")
        definition = dict(definition)
        if check_id not in _ALLOWED_CHECKS:
            return self._blocked(check_id, snapshot, coverage, "Check is outside the canonical registered-check set")
        if check_id in LEGACY_COLUMN_ALIASES:
            canonical = LEGACY_COLUMN_ALIASES[check_id]
            return self._blocked(
                check_id, snapshot, coverage,
                f"Compatibility-only legacy projection; canonical engineering authority is {canonical}",
                code_ref="B1-COMPATIBILITY-ONLY",
            )
        if coverage.coverage_status == CoverageStatus.BLOCKED:
            return self._blocked(
                check_id, snapshot, coverage,
                coverage.reason or "Coverage is BLOCKED; check not executed",
                code_ref=str(definition.get("code_ref") or "contract"),
                diagnostics=(CheckDiagnostic(
                    CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.COVERAGE_BLOCKED,
                    "Coverage blocks execution", coverage.as_dict(),
                ),),
            )
        expected_type = _component_type_norm(definition.get("element_type") or coverage.component_type)
        if expected_type and _component_type_norm(snapshot.component_type) != expected_type:
            return self._out_of_scope(
                check_id, snapshot, coverage,
                f"Check applies to component_type={expected_type}; snapshot has component_type={snapshot.component_type}",
                code_ref=str(definition.get("code_ref") or "contract"),
            )
        if coverage.coverage_status == CoverageStatus.PARTIAL:
            if check_id in _WALL_CHECK_IDS or check_id in MEMBER_FORMAL_CHECK_IDS:
                return self._blocked(
                    check_id, snapshot, coverage,
                    coverage.reason or "Formal checks require FULL executable coverage",
                    code_ref=str(definition.get("code_ref") or "contract"),
                    diagnostics=(CheckDiagnostic(
                        CheckDiagnosticSeverity.ERROR, CheckDiagnosticCode.COVERAGE_BLOCKED,
                        "Partial coverage is not executable for formal checks", coverage.as_dict(),
                    ),),
                )
            return self._warning(check_id, snapshot, coverage, coverage.reason or "Coverage is partial; result is screening only")
        return self._evaluate(check_input, definition)

    def _evaluate(self, check_input: GeometryCheckInput, definition: Mapping[str, Any]) -> CheckResult:
        check_id = check_input.check_id
        snapshot = check_input.snapshot
        coverage = check_input.coverage
        required = list(definition.get("required_features") or coverage.required_features)
        missing = [name for name in required if name not in snapshot.features]
        if missing:
            return self._no_data(
                check_id, snapshot, coverage,
                "Required features missing from snapshot: " + ", ".join(missing),
                code_ref=str(definition.get("code_ref") or "contract"),
            )
        evidence: list[Any] = []
        variables: dict[str, Any] = {}
        for feature_name in required:
            fv = snapshot.features[feature_name]
            evidence.extend(ev.as_dict() for ev in fv.evidence)
            if fv.status != FeatureValueStatus.RESOLVED:
                if check_id in _WALL_CHECK_IDS or check_id in MEMBER_FORMAL_CHECK_IDS:
                    return self._blocked(
                        check_id, snapshot, coverage,
                        f"Required canonical feature is not resolved: {feature_name}",
                        evidence=evidence,
                        code_ref=str(definition.get("code_ref") or "contract"),
                    )
                return self._warning(
                    check_id, snapshot, coverage,
                    f"Feature is not fully resolved: {feature_name}", evidence=evidence,
                )
            if check_id in MEMBER_FORMAL_CHECK_IDS and fv.unit != "mm":
                return self._blocked(
                    check_id, snapshot, coverage,
                    f"Formal member geometry requires explicit mm feature units; {feature_name} has unit={fv.unit!r}",
                    evidence=evidence,
                    code_ref=str(definition.get("code_ref") or "contract"),
                )
            variables[feature_name] = fv.value
        if check_id in MEMBER_FORMAL_CHECK_IDS:
            return self._evaluate_registered_member_check(check_input, definition, variables, evidence)
        if check_id in _WALL_CHECK_IDS:
            return self._evaluate_registered_wall_check(check_input, definition, variables, evidence)
        return self._blocked(check_id, snapshot, coverage, "No canonical evaluator registered for check")

    def _evaluate_registered_member_check(
        self,
        check_input: GeometryCheckInput,
        definition: Mapping[str, Any],
        variables: Mapping[str, Any],
        evidence: Sequence[Any],
    ) -> CheckResult:
        check_id = check_input.check_id
        snapshot = check_input.snapshot
        coverage = check_input.coverage
        registration = MEMBER_GEOMETRY_REGISTRATIONS[check_id]
        code_ref = str(definition.get("code_ref") or registration.code_ref)
        context = check_input.execution_context.values
        if check_id == COLUMN_MIN_DIMENSION:
            shape = context.get(COLUMN_SECTION_SHAPE_CONTEXT)
            if not isinstance(shape, str) or not shape.strip():
                return self._blocked(check_id, snapshot, coverage, "Rectangular-column applicability is unresolved", code_ref=code_ref, evidence=evidence)
            if shape.strip().upper() != "RECTANGULAR":
                return self._out_of_scope(check_id, snapshot, coverage, f"Rectangular-column rule is not applicable to section shape {shape}", code_ref=code_ref, evidence=evidence)
        else:
            applies = context.get(BEAM_7411_APPLICABILITY_CONTEXT)
            if not isinstance(applies, bool):
                return self._blocked(check_id, snapshot, coverage, "TBDY §7.4.1.1 beam applicability is unresolved", code_ref=code_ref, evidence=evidence)
            if applies is False:
                return self._out_of_scope(check_id, snapshot, coverage, "TBDY §7.4.1.1 is proven not applicable to this beam", code_ref=code_ref, evidence=evidence)
        try:
            rule = evaluate_member_rule(registration, variables)
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            return self._blocked(check_id, snapshot, coverage, str(exc), code_ref=code_ref, evidence=evidence)
        return CheckResult(
            check_id=check_id, component=snapshot.component_id, component_type=snapshot.component_type,
            story=self._story(snapshot), section=self._section(snapshot),
            status=CheckStatus.OK if rule.is_satisfied else CheckStatus.FAIL,
            value=rule.value, limit=rule.limit, ratio=rule.ratio, ratio_type=rule.ratio_type,
            pass_rule=rule.ratio_type, unit=rule.unit, evaluation_level=EvaluationLevel.DESIGN_LEVEL,
            evidence=evidence, messages=("Formal canonical beam/column geometry CheckResult",),
            code_ref=code_ref, diagnostics=(),
        )

    def _evaluate_registered_wall_check(
        self,
        check_input: GeometryCheckInput,
        definition: Mapping[str, Any],
        variables: Mapping[str, Any],
        evidence: Sequence[Any],
    ) -> CheckResult:
        check_id = check_input.check_id
        snapshot = check_input.snapshot
        coverage = check_input.coverage
        code_ref = str(definition.get("code_ref") or "contract")
        evidence_rows = list(evidence)
        try:
            if "wall_is_basement" in variables and self._boolean("wall_is_basement", variables["wall_is_basement"]):
                return self._out_of_scope(
                    check_id, snapshot, coverage,
                    "TBDY §7.6.1 wall section conditions exclude basement walls",
                    code_ref=code_ref, evidence=evidence_rows,
                )
            if check_id in _GENERAL_BRANCH_IDS:
                body = self._text("wall_body_classification", variables.get("wall_body_classification"))
                if body not in WALL_BODY_CLASSIFICATIONS:
                    return self._out_of_scope(
                        check_id, snapshot, coverage,
                        "Resolved wall body classification is outside §7.6.1.2(a) scope",
                        code_ref=code_ref, evidence=evidence_rows,
                    )
                special, reason = self._special_applicability(check_input)
                if special is None:
                    return self._blocked(check_id, snapshot, coverage, reason or "§7.6.1.3 applicability unresolved", code_ref=code_ref, evidence=evidence_rows)
                if special:
                    return self._out_of_scope(
                        check_id, snapshot, coverage,
                        "§7.6.1.3 special branch applies; general §7.6.1.2(a) check is not applicable",
                        code_ref=code_ref, evidence=evidence_rows,
                    )
            elif check_id in _SPECIAL_BRANCH_IDS:
                special, reason = self._special_applicability(check_input)
                if special is None:
                    return self._blocked(check_id, snapshot, coverage, reason or "§7.6.1.3 applicability unresolved", code_ref=code_ref, evidence=evidence_rows)
                if not special:
                    return self._out_of_scope(
                        check_id, snapshot, coverage,
                        "§7.6.1.3 special branch is proven not applicable",
                        code_ref=code_ref, evidence=evidence_rows,
                    )
            if check_id == WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30:
                classification = self._text("wall_geometry_classification", variables.get("wall_geometry_classification"))
                if classification not in UNRESTRAINED_GEOMETRY_CLASSIFICATIONS:
                    return self._out_of_scope(
                        check_id, snapshot, coverage,
                        "Resolved geometry classification is outside §7.6.1.2(b) scope",
                        code_ref=code_ref, evidence=evidence_rows,
                    )
            if check_id == WALL_GEOM_RESTRAINED_LEG_THICKNESS:
                if not self._boolean("wall_both_ends_laterally_restrained", variables.get("wall_both_ends_laterally_restrained")):
                    return self._out_of_scope(
                        check_id, snapshot, coverage,
                        "Wall leg is not laterally restrained by a wall at both ends",
                        code_ref=code_ref, evidence=evidence_rows,
                    )

            engineering_inputs: dict[str, Any] = {}
            if check_id == WALL_GEOM_SPECIAL_THICKNESS_GE_HMAX20:
                height = derive_highest_applicable_story_height_mm(
                    check_input.execution_context.values.get("highest_applicable_story_height_mm")
                )
                if height.status != "RESOLVED":
                    return self._blocked(
                        check_id, snapshot, coverage,
                        height.diagnostic or "Highest applicable story height unresolved",
                        code_ref=code_ref, evidence=evidence_rows,
                    )
                engineering_inputs["highest_applicable_story_height_mm"] = height.value
            if check_id == WALL_NET_SECTION_AXIAL_CAPACITY:
                derived = self._derive_axial_inputs(check_input)
                if isinstance(derived, str):
                    return self._blocked(check_id, snapshot, coverage, derived, code_ref=code_ref, evidence=evidence_rows)
                engineering_inputs.update(derived)
            if check_id in PACK_C_CHECK_IDS:
                facts = check_input.execution_context.evidence.get("wall_critical_height_facts")
                reference_facts = check_input.execution_context.values.get("wall_regulatory_reference_facts")
                if not isinstance(facts, WallCriticalHeightFactualEvidence):
                    return self._blocked(
                        check_id, snapshot, coverage,
                        "Canonical Pack C wall factual evidence is unavailable from CheckInput",
                        code_ref=code_ref, evidence=evidence_rows,
                    )
                if facts.component_id != check_input.component_id:
                    return self._blocked(
                        check_id, snapshot, coverage,
                        "Pack C factual evidence identity differs from CheckInput component",
                        code_ref=code_ref, evidence=evidence_rows,
                    )
                if not isinstance(reference_facts, WallRegulatoryReferenceFacts):
                    return self._blocked(
                        check_id, snapshot, coverage,
                        "Run-level Pack C regulatory reference facts are unavailable from CheckInput",
                        code_ref=code_ref, evidence=evidence_rows,
                    )
                derivation = derive_wall_critical_height(facts, reference_facts)
                if derivation.status != "RESOLVED":
                    return self._blocked(
                        check_id, snapshot, coverage,
                        derivation.diagnostic or "Hw/Hcr derivation is blocked",
                        code_ref=code_ref, evidence=evidence_rows,
                    )
                if not derivation.applicable_segments:
                    return self._out_of_scope(
                        check_id, snapshot, coverage,
                        "TBDY §7.6.2 end-region/critical-height branch is not triggered because no proven segment has Hw/lw > 2.0",
                        code_ref=code_ref, evidence=evidence_rows,
                    )
                if check_id == WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW:
                    shape = facts.wall_section_shape
                    if shape is None:
                        return self._blocked(
                            check_id, snapshot, coverage,
                            "Wall section shape is unproven; §7.6.2.3 rectangular applicability cannot be established",
                            code_ref=code_ref, evidence=evidence_rows,
                        )
                    if shape != "RECTANGULAR":
                        return self._out_of_scope(
                            check_id, snapshot, coverage,
                            f"TBDY §7.6.2.3 applies only to rectangular wall sections; factual shape is {shape}",
                            code_ref=code_ref, evidence=evidence_rows,
                        )
                derived_c = self._derive_pack_c_inputs(check_input, facts, derivation)
                if isinstance(derived_c, str):
                    return self._blocked(check_id, snapshot, coverage, derived_c, code_ref=code_ref, evidence=evidence_rows)
                engineering_inputs.update(derived_c)
                evidence_rows.append(facts.as_dict())
                evidence_rows.append({"run_level_regulatory_reference": reference_facts.as_dict()})

            evaluator = WALL_EVALUATORS.get(check_id)
            if evaluator is None:
                return self._blocked(
                    check_id, snapshot, coverage, "No registered formal wall evaluator",
                    code_ref=code_ref, evidence=evidence_rows,
                )
            rule = evaluator(variables, engineering_inputs)
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            return self._no_data(check_id, snapshot, coverage, str(exc), code_ref=code_ref)
        status = CheckStatus.OK if rule.is_satisfied else CheckStatus.FAIL
        return CheckResult(
            check_id=check_id,
            component=snapshot.component_id,
            component_type=snapshot.component_type,
            story=self._story(snapshot),
            section=self._section(snapshot),
            status=status,
            value=rule.value,
            limit=rule.limit,
            ratio=rule.ratio,
            ratio_type=rule.ratio_type,
            pass_rule=rule.pass_rule,
            unit=rule.unit,
            evaluation_level=EvaluationLevel.DESIGN_LEVEL,
            evidence=evidence_rows,
            messages=("Formal canonical wall CheckResult",),
            code_ref=code_ref,
            diagnostics=(),
        )

    @staticmethod
    def _special_applicability(check_input: GeometryCheckInput) -> tuple[bool | None, str | None]:
        return resolve_special_branch_applicability(check_input.execution_context.values.get("wall_system_context"))

    @staticmethod
    def _derive_axial_inputs(check_input: GeometryCheckInput) -> Mapping[str, float] | str:
        context = check_input.execution_context
        pier_bundle = context.evidence.get("pier_forces_result_bundle")
        if pier_bundle is not None and not isinstance(pier_bundle, ResultRowEvidenceBundle):
            return "Pier Forces execution evidence is not a canonical ResultRowEvidenceBundle"
        pier_name = context.values.get("wall_to_pier_binding")
        ndm = derive_ndm_n(
            component_id=check_input.component_id,
            pier_name=None if pier_name is None else str(pier_name),
            pier_forces=pier_bundle,
        )
        if ndm.status != "RESOLVED":
            return ndm.diagnostic or "Ndm is unresolved"
        topology = context.values.get("net_section_topology")
        ac = derive_net_section_area_mm2(check_input.component_id, topology if isinstance(topology, Mapping) else None)
        if ac.status != "RESOLVED":
            return ac.diagnostic or "Net Ac is unresolved"
        return {"Ndm_N": float(ndm.value), "net_section_area_mm2": float(ac.value)}

    @staticmethod
    def _derive_pack_c_inputs(
        check_input: GeometryCheckInput,
        facts: WallCriticalHeightFactualEvidence,
        derivation: WallCriticalHeightDerivation,
    ) -> Mapping[str, float] | str:
        segments = derivation.applicable_segments
        check_id = check_input.check_id
        if check_id == WALL_END_REGIONS_REQUIRED_HW_LW_GT2:
            if facts.end_region_topology_proven is not True:
                return "End-region existence/topology is not proven after Hw/lw > 2.0 applicability was established"
            lowest_reference = min(segment.reference_elevation_mm for segment in segments)
            target_stories = tuple(
                row.story for row in facts.story_geometry if row.top_elevation_mm > lowest_reference + 1e-6
            )
            topology = facts.end_region_by_story
            for story in target_stories:
                row = topology.get(story)
                if row is None or row.left_exists is None or row.right_exists is None:
                    return f"End-region existence is not proven for story {story}"
            proven = 2.0 if all(topology[story].left_exists and topology[story].right_exists for story in target_stories) else 0.0
            return {"proven_end_region_ends": proven}
        if check_id == WALL_HCR_GE_LW:
            governing = min(segments, key=lambda segment: segment.hcr_governing_mm / segment.lw_mm)
            return {"hcr_governing_mm": governing.hcr_governing_mm, "lw_governing_mm": governing.lw_mm, "hw_governing_mm": governing.hw_mm}
        if check_id == WALL_HCR_GE_HW_DIV6:
            governing = min(segments, key=lambda segment: segment.hcr_governing_mm / (segment.hw_mm / 6.0))
            return {"hcr_governing_mm": governing.hcr_governing_mm, "lw_governing_mm": governing.lw_mm, "hw_governing_mm": governing.hw_mm}
        if check_id == WALL_HCR_LE_2LW:
            governing = min(segments, key=lambda segment: (2.0 * segment.lw_mm) / segment.hcr_governing_mm)
            return {"hcr_governing_mm": governing.hcr_governing_mm, "lw_governing_mm": governing.lw_mm, "hw_governing_mm": governing.hw_mm}
        if check_id == WALL_END_REGION_LENGTH_CRITICAL_GE_MAX_0_2LW_2BW:
            if facts.end_region_topology_proven is not True:
                return "End-region topology/plan lengths are not proven after Hw/lw > 2.0 applicability was established"
            critical_stories = critical_region_story_names(facts, derivation)
            if not critical_stories:
                return "Derived critical region does not intersect proven wall story geometry"
            geometry_by_story = {row.story: row for row in facts.story_geometry}
            topology = facts.end_region_by_story
            candidates: list[tuple[float, float, float]] = []
            for story in critical_stories:
                geometry = geometry_by_story[story]
                required = max(0.2 * geometry.wall_length_mm, 2.0 * geometry.wall_thickness_mm)
                end = topology.get(story)
                if end is None or end.left_exists is None or end.right_exists is None:
                    return f"End-region topology is not proven for critical-region story {story}"
                for exists, actual in (
                    (end.left_exists, end.left_plan_length_mm),
                    (end.right_exists, end.right_plan_length_mm),
                ):
                    if exists is False:
                        candidates.append((0.0, required, 0.0))
                    elif actual is None:
                        return f"End-region plan length is not proven for critical-region story {story}"
                    else:
                        candidates.append((float(actual), required, float(actual) / required))
            actual, required, _ = min(candidates, key=lambda item: item[2])
            return {
                "governing_end_region_plan_length_mm": actual,
                "governing_required_end_region_plan_length_mm": required,
            }
        return "Pack C check has no shared engineering-input derivation"

    @staticmethod
    def _number(name: str, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"Required numeric feature is missing or non-numeric: {name}")
        return float(value)

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

    @staticmethod
    def _story(snapshot: FeatureSnapshot) -> str | None:
        value = snapshot.identity.get("story")
        return None if value is None else str(value)

    @staticmethod
    def _section(snapshot: FeatureSnapshot) -> str | None:
        value = snapshot.identity.get("section") or snapshot.identity.get("assigned_wall_property")
        return None if value is None else str(value)

    def _blocked(self, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str, *, diagnostics: Sequence[CheckDiagnostic] = (), evidence: Sequence[Any] = (), code_ref: str | None = None) -> CheckResult:
        return CheckResult(check_id=check_id, component=snapshot.component_id, component_type=snapshot.component_type, story=self._story(snapshot), section=self._section(snapshot), status=CheckStatus.BLOCKED, evaluation_level=EvaluationLevel.NO_DATA, evidence=evidence, messages=(message,), code_ref=code_ref, diagnostics=tuple(diagnostics))

    def _no_data(self, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str, *, diagnostics: Sequence[CheckDiagnostic] = (), evidence: Sequence[Any] = (), code_ref: str | None = None) -> CheckResult:
        return CheckResult(check_id=check_id, component=snapshot.component_id, component_type=snapshot.component_type, story=self._story(snapshot), section=self._section(snapshot), status=CheckStatus.NO_DATA, evaluation_level=EvaluationLevel.NO_DATA, evidence=evidence, messages=(message,), code_ref=code_ref, diagnostics=tuple(diagnostics))

    def _warning(self, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str, *, diagnostics: Sequence[CheckDiagnostic] = (), evidence: Sequence[Any] = ()) -> CheckResult:
        return CheckResult(check_id=check_id, component=snapshot.component_id, component_type=snapshot.component_type, story=self._story(snapshot), section=self._section(snapshot), status=CheckStatus.WARNING, evaluation_level=EvaluationLevel.SCREENING, evidence=evidence, messages=(message,), diagnostics=tuple(diagnostics))

    def _out_of_scope(self, check_id: str, snapshot: FeatureSnapshot, coverage: CoverageRow, message: str, *, evidence: Sequence[Any] = (), code_ref: str | None = None) -> CheckResult:
        return CheckResult(check_id=check_id, component=snapshot.component_id, component_type=snapshot.component_type, story=self._story(snapshot), section=self._section(snapshot), status=CheckStatus.OUT_OF_SCOPE, evaluation_level=EvaluationLevel.NO_DATA, evidence=evidence, messages=(message,), code_ref=code_ref)


__all__ = ["MinimalCheckEngine", "_ALLOWED_CHECKS"]
