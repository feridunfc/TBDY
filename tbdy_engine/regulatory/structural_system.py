"""VS-4A source-bound cast-in-place RC structural-system baseline policy.

This module is deliberately bounded to pre-analysis/Table 4.1 policy and
analysis-basis compatibility. Post-analysis MDEV/Mo engineering calculations
belong to VS-4B.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import math
from types import MappingProxyType
from typing import Mapping, Sequence

from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.regulatory.contracts import (
    ApplicabilityBinding, ApplicabilityState, AvailabilityState,
    CheckEvaluatorBinding, CheckSpec, DependencyKey, DependencySourceKind,
    DependencySpec, DerivationEvaluatorBinding, DirectionPolicy, Grain,
    PhysicalDimension, PopulationRequirement, RegulatoryDerivationSpec,
    RegulatoryOutputContract, RegulatoryQuantity, RuleId, ScopePolicy,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus, CompiledRegulatoryProgram, ExternalDependencyAuthority,
    MaterializedDependency, PopulationCompleteness, RegulatoryCompileInputs,
    RegulatoryCompiler, RegulatoryEngine, RegulatoryStoreSnapshot,
    RuleExecutionEnvelope, RuleScopeTarget,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE, UNIT_M

SOURCE_ID = "TBDY2018_AFAD"
RULE_VERSION = "vs4a-v1"
BUILDING_SCOPE = "BUILDING"


class RcDuctilityLevel(StrEnum):
    HIGH = "HIGH"
    MIXED = "MIXED"
    LIMITED = "LIMITED"


class RcPostAnalysisQualificationRequirement(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    UNRESOLVED = "UNRESOLVED"


class RcBaselineResolutionState(StrEnum):
    RESOLVED = "RESOLVED"
    PROVISIONAL = "PROVISIONAL"
    UNRESOLVED = "UNRESOLVED"


class RoofConnectionCondition(StrEnum):
    PINNED = "PINNED"
    NOT_PINNED = "NOT_PINNED"
    UNREVIEWED = "UNREVIEWED"


@dataclass(frozen=True, slots=True)
class Table41RowPolicy:
    row: str
    ductility: RcDuctilityLevel
    r: float
    d: float
    minimum_bys: int | None
    has_rc_wall: bool
    row_claim_id: str


_ROW_DATA = (
    Table41RowPolicy("A11", RcDuctilityLevel.HIGH, 8.0, 3.0, 3, False, "TBDY2018_TABLE4_1_A11"),
    Table41RowPolicy("A12", RcDuctilityLevel.HIGH, 7.0, 2.5, 2, True, "TBDY2018_TABLE4_1_A12"),
    Table41RowPolicy("A13", RcDuctilityLevel.HIGH, 6.0, 2.5, 2, True, "TBDY2018_TABLE4_1_A13"),
    Table41RowPolicy("A14", RcDuctilityLevel.HIGH, 8.0, 2.5, 2, True, "TBDY2018_TABLE4_1_A14"),
    Table41RowPolicy("A15", RcDuctilityLevel.HIGH, 7.0, 2.5, 2, True, "TBDY2018_TABLE4_1_A15"),
    Table41RowPolicy("A16", RcDuctilityLevel.HIGH, 3.0, 2.0, None, False, "TBDY2018_TABLE4_1_A16"),
    Table41RowPolicy("A21", RcDuctilityLevel.MIXED, 6.0, 2.5, 4, True, "TBDY2018_TABLE4_1_A21"),
    Table41RowPolicy("A22", RcDuctilityLevel.MIXED, 5.0, 2.5, 4, True, "TBDY2018_TABLE4_1_A22"),
    Table41RowPolicy("A23", RcDuctilityLevel.MIXED, 6.0, 2.5, 6, True, "TBDY2018_TABLE4_1_A23"),
    Table41RowPolicy("A24", RcDuctilityLevel.MIXED, 5.0, 2.5, 6, True, "TBDY2018_TABLE4_1_A24"),
    Table41RowPolicy("A31", RcDuctilityLevel.LIMITED, 4.0, 2.5, 7, False, "TBDY2018_TABLE4_1_A31"),
    Table41RowPolicy("A32", RcDuctilityLevel.LIMITED, 4.0, 2.0, 6, True, "TBDY2018_TABLE4_1_A32"),
    Table41RowPolicy("A33", RcDuctilityLevel.LIMITED, 4.0, 2.0, 6, True, "TBDY2018_TABLE4_1_A33"),
)
TABLE_4_1_A_SERIES: Mapping[str, Table41RowPolicy] = MappingProxyType({item.row: item for item in _ROW_DATA})
TABLE_4_1_ROWS = tuple(sorted(TABLE_4_1_A_SERIES))
TABLE_4_1_ROW_CLAIM_IDS = tuple(TABLE_4_1_A_SERIES[row].row_claim_id for row in TABLE_4_1_ROWS)
VALID_DTS = frozenset({"1", "1a", "2", "2a", "3", "3a", "4", "4a"})
LIMITED_PROHIBITED_DTS = frozenset({"1a", "2a", "3a", "4a"})
MIXED_RESTRICTED_DTS = frozenset({"1a", "2a"})
A31_ALLOWED_DTS = frozenset({"3", "4"})
WALL_DISTRIBUTION_DTS = frozenset({"1", "1a", "2", "2a"})


def table_4_1_policy(row: str) -> Table41RowPolicy:
    if not isinstance(row, str) or row not in TABLE_4_1_A_SERIES:
        raise ValueError(f"unknown cast-in-place RC Table 4.1 row: {row!r}")
    return TABLE_4_1_A_SERIES[row]


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{label} must be a sequence of strings")
    refs = tuple(_text(value, label) for value in values)
    if len(refs) != len(set(refs)):
        raise ValueError(f"{label} contains duplicates")
    return tuple(sorted(refs))


def _direction(value: str) -> str:
    value = _text(value, "direction")
    if value not in {"X", "Y"}:
        raise ValueError("direction must be X or Y")
    return value


def _dts(value: str) -> str:
    value = _text(value, "DTS")
    if value not in VALID_DTS:
        raise ValueError(f"unsupported DTS: {value}")
    return value


def _bys(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in range(1, 9):
        raise ValueError("BYS must be an integer from 1 through 8")
    return value


def _positive_finite(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return number


@dataclass(frozen=True, slots=True)
class ReviewedDirectionalRcSystemDeclaration:
    direction: str
    table_4_1_row: str
    review_refs: tuple[str, ...] = field(default_factory=tuple)
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "direction", _direction(self.direction))
        table_4_1_policy(self.table_4_1_row)
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "review_ref"))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))


@dataclass(frozen=True, slots=True)
class ReviewedSeismicClassificationContext:
    dts: str
    bys: int
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "dts", _dts(self.dts))
        object.__setattr__(self, "bys", _bys(self.bys))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))


@dataclass(frozen=True, slots=True)
class ReviewedOrthogonalRcSystemDeclaration:
    x: ReviewedDirectionalRcSystemDeclaration
    y: ReviewedDirectionalRcSystemDeclaration
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.x, ReviewedDirectionalRcSystemDeclaration) or not isinstance(self.y, ReviewedDirectionalRcSystemDeclaration):
            raise TypeError("x/y must be ReviewedDirectionalRcSystemDeclaration")
        if self.x.direction != "X" or self.y.direction != "Y":
            raise ValueError("orthogonal declaration must own X then Y directional declarations")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))


@dataclass(frozen=True, slots=True)
class A16SpecialContext:
    direction: str
    story_count: int
    building_height_m: float
    roof_connection_condition: RoofConnectionCondition
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "direction", _direction(self.direction))
        if isinstance(self.story_count, bool) or not isinstance(self.story_count, int) or self.story_count <= 0:
            raise ValueError("story_count must be a positive integer")
        object.__setattr__(self, "building_height_m", _positive_finite(self.building_height_m, "building_height_m"))
        if not isinstance(self.roof_connection_condition, RoofConnectionCondition):
            raise TypeError("roof_connection_condition must be RoofConnectionCondition")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))


@dataclass(frozen=True, slots=True)
class DirectionalAnalysisSystemAssumption:
    direction: str
    assumed_table_4_1_row: str
    assumed_r: float
    assumed_d: float
    analysis_evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "direction", _direction(self.direction))
        table_4_1_policy(self.assumed_table_4_1_row)
        object.__setattr__(self, "assumed_r", _positive_finite(self.assumed_r, "assumed_r"))
        object.__setattr__(self, "assumed_d", _positive_finite(self.assumed_d, "assumed_d"))
        evidence = _refs(self.analysis_evidence_refs, "analysis_evidence_ref")
        if not evidence:
            raise ValueError("analysis_evidence_refs must not be empty")
        object.__setattr__(self, "analysis_evidence_refs", evidence)
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))


DECLARED_ROW_KEY = DependencyKey("rc_declared_table_4_1_row")
DTS_KEY = DependencyKey("rc_dts")
BYS_KEY = DependencyKey("rc_bys")
ORTHOGONAL_ROWS_KEY = DependencyKey("rc_orthogonal_declared_rows")
A16_STORY_COUNT_KEY = DependencyKey("rc_a16_story_count")
A16_HEIGHT_KEY = DependencyKey("rc_a16_building_height_m")
A16_ROOF_CONNECTION_KEY = DependencyKey("rc_a16_roof_connection_condition")
ASSUMED_ROW_KEY = DependencyKey("rc_analysis_assumed_table_4_1_row")
ASSUMED_R_KEY = DependencyKey("rc_analysis_assumed_r")
ASSUMED_D_KEY = DependencyKey("rc_analysis_assumed_d")

DUCTILITY_KEY = DependencyKey("rc_system_ductility_class")
BASE_R_KEY = DependencyKey("rc_table_4_1_base_r")
BASE_D_KEY = DependencyKey("rc_table_4_1_base_d")
BASE_BYS_POLICY_KEY = DependencyKey("rc_table_4_1_base_bys_policy")
EFFECTIVE_BYS_POLICY_KEY = DependencyKey("rc_effective_preanalysis_bys_policy")
POSTQUAL_KEY = DependencyKey("rc_post_analysis_system_qualification_requirement")
BASELINE_POLICY_KEY = DependencyKey("rc_directional_baseline_system_policy")
ANALYSIS_BASIS_STATUS_KEY = DependencyKey("rc_analysis_basis_status")

RC_SYSTEM_DUCTILITY_CLASS = RuleId("RC_SYSTEM_DUCTILITY_CLASS")
RC_TABLE_4_1_BASE_R = RuleId("RC_TABLE_4_1_BASE_R")
RC_TABLE_4_1_BASE_D = RuleId("RC_TABLE_4_1_BASE_D")
RC_TABLE_4_1_BASE_BYS_POLICY = RuleId("RC_TABLE_4_1_BASE_BYS_POLICY")
RC_EFFECTIVE_PREANALYSIS_BYS_POLICY = RuleId("RC_EFFECTIVE_PREANALYSIS_BYS_POLICY")
RC_POST_ANALYSIS_SYSTEM_QUALIFICATION_REQUIREMENT = RuleId("RC_POST_ANALYSIS_SYSTEM_QUALIFICATION_REQUIREMENT")
RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY = RuleId("RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY")
RC_ANALYSIS_BASIS_COMPATIBILITY = RuleId("RC_ANALYSIS_BASIS_COMPATIBILITY")
RC_TABLE_4_1_BYS_ELIGIBILITY = RuleId("RC_TABLE_4_1_BYS_ELIGIBILITY")
RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY = RuleId("RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY")
RC_TBDY_4_3_4_2_ORTHOGONAL_DUCTILITY_CONSISTENCY = RuleId("RC_TBDY_4_3_4_2_ORTHOGONAL_DUCTILITY_CONSISTENCY")
RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY = RuleId("RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY")
RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY = RuleId("RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY")


@dataclass(frozen=True, slots=True)
class DirectionalApplicabilityInput:
    enabled: bool = True


def _applies(value: DirectionalApplicabilityInput) -> ApplicabilityState:
    if not isinstance(value, DirectionalApplicabilityInput):
        raise TypeError("applicability requires DirectionalApplicabilityInput")
    return ApplicabilityState.APPLIES if value.enabled else ApplicabilityState.PROVEN_NOT_APPLICABLE


@dataclass(frozen=True, slots=True)
class StructuralSystemExecutionInput:
    envelope: RuleExecutionEnvelope
    dependencies: tuple[MaterializedDependency, ...]

    @classmethod
    def from_declared_dependencies(cls, envelope: RuleExecutionEnvelope, dependencies: Sequence[MaterializedDependency]) -> "StructuralSystemExecutionInput":
        deps = tuple(dependencies)
        if any(not isinstance(item, MaterializedDependency) for item in deps):
            raise TypeError("dependencies must contain MaterializedDependency")
        if len({item.key for item in deps}) != len(deps):
            raise ValueError("duplicate materialized dependency")
        return cls(envelope, tuple(sorted(deps, key=lambda item: item.key.value)))

    def value(self, key: DependencyKey) -> object:
        for item in self.dependencies:
            if item.key == key:
                return item.value
        raise KeyError(key.value)


def _row_from_input(inp: StructuralSystemExecutionInput) -> Table41RowPolicy:
    return table_4_1_policy(str(inp.value(DECLARED_ROW_KEY)))


def _quantity(inp: StructuralSystemExecutionInput, *, key: DependencyKey, semantic: SemanticType, dimension: PhysicalDimension, unit, value: object, code_refs: tuple[str, ...], governing_claims: tuple[str, ...], availability: AvailabilityState = AvailabilityState.RESOLVED) -> RegulatoryQuantity:
    return RegulatoryQuantity(
        quantity_key=key, producer_instance_id=inp.envelope.instance_id,
        semantic_type=semantic, physical_dimension=dimension,
        grain=inp.envelope.instance_id.grain, scope_ref=inp.envelope.instance_id.scope_ref,
        direction=inp.envelope.instance_id.direction, value=value, unit=unit,
        availability=availability, rule_version=inp.envelope.rule_version,
        code_refs=code_refs, dependency_refs=inp.envelope.declared_dependency_refs,
        evidence_refs=(), provenance=(SOURCE_ID,),
        derivation_trace=(inp.envelope.rule_id.value,), governing_trace=governing_claims,
    )


def evaluate_ductility_class(inp: StructuralSystemExecutionInput) -> RegulatoryQuantity:
    policy = _row_from_input(inp)
    return _quantity(inp, key=DUCTILITY_KEY, semantic=SemanticType.RC_DUCTILITY_CLASS, dimension=PhysicalDimension.ENUM_STATE, unit=UNIT_ENUM_STATE, value=policy.ductility.value, code_refs=("TBDY 2018 4.3.3.1; Table 4.1",), governing_claims=(policy.row_claim_id, "TBDY2018_4_3_3_1_DUCTILITY_CLASSES"))


def evaluate_base_r(inp: StructuralSystemExecutionInput) -> RegulatoryQuantity:
    policy = _row_from_input(inp)
    return _quantity(inp, key=BASE_R_KEY, semantic=SemanticType.RC_BASE_R, dimension=PhysicalDimension.DIMENSIONLESS, unit=UNIT_DIMENSIONLESS, value=policy.r, code_refs=("TBDY 2018 4.3.2.1; Table 4.1",), governing_claims=(policy.row_claim_id, "TBDY2018_4_3_2_1_TABLE4_1_RD"))


def evaluate_base_d(inp: StructuralSystemExecutionInput) -> RegulatoryQuantity:
    policy = _row_from_input(inp)
    return _quantity(inp, key=BASE_D_KEY, semantic=SemanticType.RC_BASE_D, dimension=PhysicalDimension.DIMENSIONLESS, unit=UNIT_DIMENSIONLESS, value=policy.d, code_refs=("TBDY 2018 4.3.2.1; Table 4.1",), governing_claims=(policy.row_claim_id, "TBDY2018_4_3_2_1_TABLE4_1_RD"))


def evaluate_base_bys_policy(inp: StructuralSystemExecutionInput) -> RegulatoryQuantity:
    policy = _row_from_input(inp)
    value: object = policy.minimum_bys if policy.minimum_bys is not None else "SPECIAL_A16"
    return _quantity(inp, key=BASE_BYS_POLICY_KEY, semantic=SemanticType.RC_BYS_POLICY, dimension=PhysicalDimension.ENUM_STATE, unit=UNIT_ENUM_STATE, value=value, code_refs=("TBDY 2018 Table 4.1",), governing_claims=(policy.row_claim_id,))


def evaluate_effective_preanalysis_bys_policy(inp: StructuralSystemExecutionInput) -> RegulatoryQuantity:
    policy = _row_from_input(inp)
    dts = _dts(str(inp.value(DTS_KEY)))
    base = inp.value(BASE_BYS_POLICY_KEY)
    if policy.row in {"A21", "A22"} and dts == "4":
        value: object = 2
        claims = (policy.row_claim_id, "TBDY2018_4_3_1_2_A21_A22_DTS4_BYS")
    else:
        value = base
        claims = (policy.row_claim_id,)
    return _quantity(inp, key=EFFECTIVE_BYS_POLICY_KEY, semantic=SemanticType.RC_BYS_POLICY, dimension=PhysicalDimension.ENUM_STATE, unit=UNIT_ENUM_STATE, value=value, code_refs=("TBDY 2018 4.3.1.2; Table 4.1",), governing_claims=claims)


def evaluate_post_analysis_qualification_requirement(inp: StructuralSystemExecutionInput) -> RegulatoryQuantity:
    policy = _row_from_input(inp)
    dts = _dts(str(inp.value(DTS_KEY)))
    reasons: list[str] = []
    claims: list[str] = [policy.row_claim_id]
    if policy.row in {"A14", "A15"}:
        reasons.append("TBDY_4_3_4_5")
        claims.append("TBDY2018_4_3_4_5_HIGH_COMBINED_QUALIFICATION")
    if policy.row in {"A21", "A22", "A23", "A24"}:
        reasons.append("TBDY_4_3_4_6")
        claims.append("TBDY2018_4_3_4_6_MIXED_QUALIFICATION")
    if policy.row == "A33":
        reasons.append("TBDY_4_3_4_7")
        claims.append("TBDY2018_4_3_4_7_LIMITED_WALL_FRAME_QUALIFICATION")
    if policy.has_rc_wall and dts in WALL_DISTRIBUTION_DTS:
        reasons.append("TBDY_4_3_2_4")
        claims.append("TBDY2018_4_3_2_4_WALL_DISTRIBUTION_R_POLICY")
    state = RcPostAnalysisQualificationRequirement.REQUIRED if reasons else RcPostAnalysisQualificationRequirement.NOT_REQUIRED
    return _quantity(inp, key=POSTQUAL_KEY, semantic=SemanticType.RC_POST_ANALYSIS_QUALIFICATION_REQUIREMENT, dimension=PhysicalDimension.ENUM_STATE, unit=UNIT_ENUM_STATE, value={"state": state.value, "reasons": tuple(sorted(set(reasons)))}, code_refs=("TBDY 2018 4.3.2.4, 4.3.4.5, 4.3.4.6, 4.3.4.7",), governing_claims=tuple(sorted(set(claims))))


def evaluate_directional_baseline_policy(inp: StructuralSystemExecutionInput) -> RegulatoryQuantity:
    policy = _row_from_input(inp)
    ductility = str(inp.value(DUCTILITY_KEY)); r = float(inp.value(BASE_R_KEY)); d = float(inp.value(BASE_D_KEY))
    bys_policy = inp.value(EFFECTIVE_BYS_POLICY_KEY); postqual = inp.value(POSTQUAL_KEY)
    if not isinstance(postqual, Mapping):
        raise TypeError("post-analysis qualification value must be a mapping")
    requirement = str(postqual["state"])
    if requirement == RcPostAnalysisQualificationRequirement.NOT_REQUIRED.value:
        resolution = RcBaselineResolutionState.RESOLVED
    elif requirement == RcPostAnalysisQualificationRequirement.REQUIRED.value:
        resolution = RcBaselineResolutionState.PROVISIONAL
    else:
        resolution = RcBaselineResolutionState.UNRESOLVED
    return _quantity(inp, key=BASELINE_POLICY_KEY, semantic=SemanticType.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY, dimension=PhysicalDimension.ENUM_STATE, unit=UNIT_ENUM_STATE, value={"table_4_1_row": policy.row, "ductility_level": ductility, "baseline_r": r, "baseline_d": d, "effective_preanalysis_bys_policy": bys_policy, "post_analysis_qualification_requirement": requirement, "post_analysis_qualification_reasons": tuple(postqual.get("reasons", ())), "resolution_state": resolution.value, "governing_row_claim": policy.row_claim_id}, code_refs=("TBDY 2018 4.3; Table 4.1",), governing_claims=(policy.row_claim_id,))


def evaluate_analysis_basis_compatibility(inp: StructuralSystemExecutionInput) -> RegulatoryQuantity:
    policy = inp.value(BASELINE_POLICY_KEY)
    if not isinstance(policy, Mapping):
        raise TypeError("baseline system policy must be a mapping")
    assumed_row = str(inp.value(ASSUMED_ROW_KEY)); assumed_r = float(inp.value(ASSUMED_R_KEY)); assumed_d = float(inp.value(ASSUMED_D_KEY))
    table_4_1_policy(assumed_row)
    if policy["resolution_state"] != RcBaselineResolutionState.RESOLVED.value:
        status = AnalysisBasisStatus.UNRESOLVED
    else:
        exact = assumed_row == policy["table_4_1_row"] and math.isclose(assumed_r, float(policy["baseline_r"]), rel_tol=0.0, abs_tol=1e-12) and math.isclose(assumed_d, float(policy["baseline_d"]), rel_tol=0.0, abs_tol=1e-12)
        status = AnalysisBasisStatus.MATCH if exact else AnalysisBasisStatus.REANALYSIS_REQUIRED
    return _quantity(inp, key=ANALYSIS_BASIS_STATUS_KEY, semantic=SemanticType.RC_ANALYSIS_BASIS_STATUS, dimension=PhysicalDimension.ENUM_STATE, unit=UNIT_ENUM_STATE, value=status.value, code_refs=("TBDY 2018 4.3.2.1; Table 4.1 and applicable 4.3 qualification clauses",), governing_claims=("TBDY2018_VS4A_ANALYSIS_BASIS_COMPATIBILITY",))


def _result(inp: StructuralSystemExecutionInput, *, status: CheckStatus, value: object, limit: object, pass_rule: str, code_ref: str, messages: tuple[str, ...], evidence: tuple[object, ...], ratio: float | None = None, ratio_type: str | None = None) -> CheckResult:
    return CheckResult(check_id=inp.envelope.rule_id.value, component=inp.envelope.instance_id.scope_ref, component_type="rc_structural_system_policy", status=status, value=value, limit=limit, ratio=ratio, ratio_type=ratio_type, pass_rule=pass_rule, unit=None, evaluation_level=EvaluationLevel.DESIGN_LEVEL, evidence=evidence, messages=messages, code_ref=code_ref, diagnostics=())


def evaluate_bys_eligibility(inp: StructuralSystemExecutionInput) -> CheckResult:
    policy = _row_from_input(inp); actual = _bys(int(inp.value(BYS_KEY))); allowed = inp.value(EFFECTIVE_BYS_POLICY_KEY)
    if not isinstance(allowed, int):
        return _result(inp, status=CheckStatus.BLOCKED, value=actual, limit=allowed, pass_rule="A16 uses its special one-storey/height/connection eligibility path", code_ref="TBDY 2018 Table 4.1", messages=("ORDINARY_BYS_POLICY_NOT_APPLICABLE_TO_A16",), evidence=(SOURCE_ID, policy.row_claim_id))
    ok = actual >= allowed
    return _result(inp, status=CheckStatus.OK if ok else CheckStatus.FAIL, value=actual, limit=allowed, ratio=float(actual)/float(allowed), ratio_type="value_over_minimum", pass_rule="actual BYS >= effective minimum permitted BYS class", code_ref="TBDY 2018 4.3.1.2; Table 4.1", messages=("BYS_ELIGIBLE" if ok else "BYS_NOT_ELIGIBLE",), evidence=(SOURCE_ID, policy.row_claim_id))


def evaluate_dts_system_eligibility(inp: StructuralSystemExecutionInput) -> CheckResult:
    dts = _dts(str(inp.value(DTS_KEY))); bys = _bys(int(inp.value(BYS_KEY))); ductility = RcDuctilityLevel(str(inp.value(DUCTILITY_KEY)))
    if ductility is RcDuctilityLevel.LIMITED:
        ok = dts not in LIMITED_PROHIBITED_DTS; reason = "LIMITED_DTS_ELIGIBLE" if ok else "LIMITED_SYSTEM_PROHIBITED_IN_A_DTS"
    elif ductility is RcDuctilityLevel.MIXED:
        prohibited = dts in MIXED_RESTRICTED_DTS and bys <= 6; ok = not prohibited; reason = "MIXED_DTS_BYS_ELIGIBLE" if ok else "MIXED_SYSTEM_PROHIBITED_FOR_DTS_AND_BYS"
    else:
        ok = True; reason = "HIGH_NOT_RESTRICTED_BY_4_3_4_1"
    return _result(inp, status=CheckStatus.OK if ok else CheckStatus.FAIL, value={"ductility": ductility.value, "dts": dts, "bys": bys}, limit="TBDY_4_3_4_1", ratio=1.0 if ok else 0.0, ratio_type="boolean", pass_rule="TBDY 4.3.4.1 LIMITED/MIXED system restrictions", code_ref="TBDY 2018 4.3.4.1", messages=(reason,), evidence=(SOURCE_ID, "TBDY2018_4_3_4_1_LIMITED_DTS", "TBDY2018_4_3_4_1_MIXED_DTS_BYS"))


def evaluate_orthogonal_ductility_consistency(inp: StructuralSystemExecutionInput) -> CheckResult:
    rows = inp.value(ORTHOGONAL_ROWS_KEY)
    if type(rows) is not tuple or len(rows) != 2:
        raise TypeError("orthogonal declaration must materialize as (X_row, Y_row)")
    x_policy = table_4_1_policy(str(rows[0])); y_policy = table_4_1_policy(str(rows[1])); ok = x_policy.ductility is y_policy.ductility
    return _result(inp, status=CheckStatus.OK if ok else CheckStatus.FAIL, value={"x": x_policy.ductility.value, "y": y_policy.ductility.value}, limit="same ductility level", ratio=1.0 if ok else 0.0, ratio_type="boolean", pass_rule="X and Y ductility levels are identical; R and D may differ", code_ref="TBDY 2018 4.3.4.2", messages=("ORTHOGONAL_DUCTILITY_CONSISTENT" if ok else "ORTHOGONAL_DUCTILITY_MISMATCH",), evidence=(SOURCE_ID, "TBDY2018_4_3_4_2_ORTHOGONAL_DUCTILITY", x_policy.row_claim_id, y_policy.row_claim_id))


def evaluate_a31_dts_eligibility(inp: StructuralSystemExecutionInput) -> CheckResult:
    policy = _row_from_input(inp)
    if policy.row != "A31": raise ValueError("A31 DTS eligibility rule may only target A31")
    dts = _dts(str(inp.value(DTS_KEY))); ok = dts in A31_ALLOWED_DTS
    return _result(inp, status=CheckStatus.OK if ok else CheckStatus.FAIL, value=dts, limit=("3", "4"), ratio=1.0 if ok else 0.0, ratio_type="boolean", pass_rule="A31 may be used only for DTS=3 or DTS=4", code_ref="TBDY 2018 4.3.4.3", messages=("A31_DTS_ELIGIBLE" if ok else "A31_DTS_NOT_ELIGIBLE",), evidence=(SOURCE_ID, policy.row_claim_id, "TBDY2018_4_3_4_3_A31_DTS"))


def evaluate_a16_special_eligibility(inp: StructuralSystemExecutionInput) -> CheckResult:
    policy = _row_from_input(inp)
    if policy.row != "A16": raise ValueError("A16 special eligibility rule may only target A16")
    story_count = int(inp.value(A16_STORY_COUNT_KEY)); height = float(inp.value(A16_HEIGHT_KEY)); connection = RoofConnectionCondition(str(inp.value(A16_ROOF_CONNECTION_KEY)))
    if connection is RoofConnectionCondition.UNREVIEWED:
        return _result(inp, status=CheckStatus.BLOCKED, value={"story_count": story_count, "height_m": height, "roof_connection": connection.value}, limit={"story_count":1,"height_m_max":12.0,"roof_connection":"PINNED"}, pass_rule="A16 requires reviewed pinned roof-level connections", code_ref="TBDY 2018 Table 4.1 A16", messages=("A16_ROOF_CONNECTION_REVIEW_MISSING",), evidence=(SOURCE_ID, policy.row_claim_id))
    ok = story_count == 1 and height <= 12.0 and connection is RoofConnectionCondition.PINNED
    return _result(inp, status=CheckStatus.OK if ok else CheckStatus.FAIL, value={"story_count": story_count, "height_m": height, "roof_connection": connection.value}, limit={"story_count":1,"height_m_max":12.0,"roof_connection":"PINNED"}, ratio=1.0 if ok else 0.0, ratio_type="boolean", pass_rule="single story and H<=12m and reviewed roof-level connections pinned", code_ref="TBDY 2018 Table 4.1 A16", messages=("A16_SPECIAL_ELIGIBLE" if ok else "A16_SPECIAL_NOT_ELIGIBLE",), evidence=(SOURCE_ID, policy.row_claim_id))


def _ctx_dep(key: DependencyKey, semantic: SemanticType, *, grain: Grain=Grain.DIRECTION, unit=UNIT_ENUM_STATE, dimension=PhysicalDimension.ENUM_STATE, direction_policy=DirectionPolicy.SAME_DIRECTION) -> DependencySpec:
    return DependencySpec(key=key, source_kind=DependencySourceKind.CONTEXT, semantic_type=semantic, physical_dimension=dimension, grain=grain, scope_policy=ScopePolicy.SAME_SCOPE, direction_policy=direction_policy, unit_requirement=unit, required_availability=AvailabilityState.RESOLVED, population_completeness_requirement=PopulationRequirement.FULL)


def _reg_dep(key: DependencyKey, semantic: SemanticType, *, unit=UNIT_ENUM_STATE, dimension=PhysicalDimension.ENUM_STATE) -> DependencySpec:
    return DependencySpec(key=key, source_kind=DependencySourceKind.REGULATORY_QUANTITY, semantic_type=semantic, physical_dimension=dimension, grain=Grain.DIRECTION, scope_policy=ScopePolicy.SAME_SCOPE, direction_policy=DirectionPolicy.SAME_DIRECTION, unit_requirement=unit, required_availability=AvailabilityState.RESOLVED, population_completeness_requirement=PopulationRequirement.FULL)


def _derivation(rule_id: RuleId, key: DependencyKey, semantic: SemanticType, dimension: PhysicalDimension, unit, dependencies: tuple[DependencySpec,...], evaluator, code_refs: tuple[str,...]) -> RegulatoryDerivationSpec:
    return RegulatoryDerivationSpec(rule_id=rule_id, code_refs=code_refs, rule_version=RULE_VERSION, output_contract=RegulatoryOutputContract(key,semantic,dimension,Grain.DIRECTION,unit), dependencies=dependencies, applicability=ApplicabilityBinding(f"vs4a:{rule_id.value}:applicability",DirectionalApplicabilityInput,_applies), evaluator=DerivationEvaluatorBinding(f"vs4a:{rule_id.value}:evaluator",StructuralSystemExecutionInput,evaluator))


def _check(rule_id: RuleId, dependencies: tuple[DependencySpec,...], evaluator, code_refs: tuple[str,...]) -> CheckSpec:
    return CheckSpec(rule_id=rule_id, code_refs=code_refs, rule_version=RULE_VERSION, formal_result_type=CheckResult, dependencies=dependencies, applicability=ApplicabilityBinding(f"vs4a:{rule_id.value}:applicability",DirectionalApplicabilityInput,_applies), evaluator=CheckEvaluatorBinding(f"vs4a:{rule_id.value}:evaluator",StructuralSystemExecutionInput,evaluator))


ROW_DEP=_ctx_dep(DECLARED_ROW_KEY,SemanticType.RC_TABLE_4_1_ROW); DTS_DEP=_ctx_dep(DTS_KEY,SemanticType.RC_DTS); BYS_DEP=_ctx_dep(BYS_KEY,SemanticType.RC_BYS)
BASE_BYS_REG_DEP=_reg_dep(BASE_BYS_POLICY_KEY,SemanticType.RC_BYS_POLICY); EFFECTIVE_BYS_REG_DEP=_reg_dep(EFFECTIVE_BYS_POLICY_KEY,SemanticType.RC_BYS_POLICY); DUCTILITY_REG_DEP=_reg_dep(DUCTILITY_KEY,SemanticType.RC_DUCTILITY_CLASS)
BASE_R_REG_DEP=_reg_dep(BASE_R_KEY,SemanticType.RC_BASE_R,unit=UNIT_DIMENSIONLESS,dimension=PhysicalDimension.DIMENSIONLESS); BASE_D_REG_DEP=_reg_dep(BASE_D_KEY,SemanticType.RC_BASE_D,unit=UNIT_DIMENSIONLESS,dimension=PhysicalDimension.DIMENSIONLESS)
POSTQUAL_REG_DEP=_reg_dep(POSTQUAL_KEY,SemanticType.RC_POST_ANALYSIS_QUALIFICATION_REQUIREMENT); BASELINE_POLICY_REG_DEP=_reg_dep(BASELINE_POLICY_KEY,SemanticType.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY)

DUCTILITY_SPEC=_derivation(RC_SYSTEM_DUCTILITY_CLASS,DUCTILITY_KEY,SemanticType.RC_DUCTILITY_CLASS,PhysicalDimension.ENUM_STATE,UNIT_ENUM_STATE,(ROW_DEP,),evaluate_ductility_class,("TBDY 2018 4.3.3.1; Table 4.1",))
BASE_R_SPEC=_derivation(RC_TABLE_4_1_BASE_R,BASE_R_KEY,SemanticType.RC_BASE_R,PhysicalDimension.DIMENSIONLESS,UNIT_DIMENSIONLESS,(ROW_DEP,),evaluate_base_r,("TBDY 2018 4.3.2.1; Table 4.1",))
BASE_D_SPEC=_derivation(RC_TABLE_4_1_BASE_D,BASE_D_KEY,SemanticType.RC_BASE_D,PhysicalDimension.DIMENSIONLESS,UNIT_DIMENSIONLESS,(ROW_DEP,),evaluate_base_d,("TBDY 2018 4.3.2.1; Table 4.1",))
BASE_BYS_SPEC=_derivation(RC_TABLE_4_1_BASE_BYS_POLICY,BASE_BYS_POLICY_KEY,SemanticType.RC_BYS_POLICY,PhysicalDimension.ENUM_STATE,UNIT_ENUM_STATE,(ROW_DEP,),evaluate_base_bys_policy,("TBDY 2018 Table 4.1",))
EFFECTIVE_BYS_SPEC=_derivation(RC_EFFECTIVE_PREANALYSIS_BYS_POLICY,EFFECTIVE_BYS_POLICY_KEY,SemanticType.RC_BYS_POLICY,PhysicalDimension.ENUM_STATE,UNIT_ENUM_STATE,(ROW_DEP,DTS_DEP,BASE_BYS_REG_DEP),evaluate_effective_preanalysis_bys_policy,("TBDY 2018 4.3.1.2; Table 4.1",))
POSTQUAL_SPEC=_derivation(RC_POST_ANALYSIS_SYSTEM_QUALIFICATION_REQUIREMENT,POSTQUAL_KEY,SemanticType.RC_POST_ANALYSIS_QUALIFICATION_REQUIREMENT,PhysicalDimension.ENUM_STATE,UNIT_ENUM_STATE,(ROW_DEP,DTS_DEP),evaluate_post_analysis_qualification_requirement,("TBDY 2018 4.3.2.4, 4.3.4.5, 4.3.4.6, 4.3.4.7",))
BASELINE_POLICY_SPEC=_derivation(RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY,BASELINE_POLICY_KEY,SemanticType.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY,PhysicalDimension.ENUM_STATE,UNIT_ENUM_STATE,(ROW_DEP,DUCTILITY_REG_DEP,BASE_R_REG_DEP,BASE_D_REG_DEP,EFFECTIVE_BYS_REG_DEP,POSTQUAL_REG_DEP),evaluate_directional_baseline_policy,("TBDY 2018 4.3; Table 4.1",))
ANALYSIS_BASIS_SPEC=_derivation(RC_ANALYSIS_BASIS_COMPATIBILITY,ANALYSIS_BASIS_STATUS_KEY,SemanticType.RC_ANALYSIS_BASIS_STATUS,PhysicalDimension.ENUM_STATE,UNIT_ENUM_STATE,(BASELINE_POLICY_REG_DEP,_ctx_dep(ASSUMED_ROW_KEY,SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION),_ctx_dep(ASSUMED_R_KEY,SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,unit=UNIT_DIMENSIONLESS,dimension=PhysicalDimension.DIMENSIONLESS),_ctx_dep(ASSUMED_D_KEY,SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,unit=UNIT_DIMENSIONLESS,dimension=PhysicalDimension.DIMENSIONLESS)),evaluate_analysis_basis_compatibility,("TBDY 2018 4.3.2.1 and applicable 4.3 qualification clauses",))
BYS_CHECK_SPEC=_check(RC_TABLE_4_1_BYS_ELIGIBILITY,(ROW_DEP,BYS_DEP,EFFECTIVE_BYS_REG_DEP),evaluate_bys_eligibility,("TBDY 2018 4.3.1.2; Table 4.1",))
DTS_CHECK_SPEC=_check(RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY,(DTS_DEP,BYS_DEP,DUCTILITY_REG_DEP),evaluate_dts_system_eligibility,("TBDY 2018 4.3.4.1",))
ORTHOGONAL_CHECK_SPEC=CheckSpec(rule_id=RC_TBDY_4_3_4_2_ORTHOGONAL_DUCTILITY_CONSISTENCY,code_refs=("TBDY 2018 4.3.4.2",),rule_version=RULE_VERSION,formal_result_type=CheckResult,dependencies=(_ctx_dep(ORTHOGONAL_ROWS_KEY,SemanticType.RC_ORTHOGONAL_SYSTEM_DECLARATION,grain=Grain.MODEL,direction_policy=DirectionPolicy.NO_DIRECTION),),applicability=ApplicabilityBinding(f"vs4a:{RC_TBDY_4_3_4_2_ORTHOGONAL_DUCTILITY_CONSISTENCY.value}:applicability",DirectionalApplicabilityInput,_applies),evaluator=CheckEvaluatorBinding(f"vs4a:{RC_TBDY_4_3_4_2_ORTHOGONAL_DUCTILITY_CONSISTENCY.value}:evaluator",StructuralSystemExecutionInput,evaluate_orthogonal_ductility_consistency))
A31_CHECK_SPEC=_check(RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY,(ROW_DEP,DTS_DEP),evaluate_a31_dts_eligibility,("TBDY 2018 4.3.4.3",))
A16_CHECK_SPEC=_check(RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY,(ROW_DEP,_ctx_dep(A16_STORY_COUNT_KEY,SemanticType.RC_A16_SPECIAL_CONTEXT,unit=UNIT_DIMENSIONLESS,dimension=PhysicalDimension.DIMENSIONLESS),_ctx_dep(A16_HEIGHT_KEY,SemanticType.RC_A16_SPECIAL_CONTEXT,unit=UNIT_M,dimension=PhysicalDimension.LENGTH),_ctx_dep(A16_ROOF_CONNECTION_KEY,SemanticType.RC_A16_SPECIAL_CONTEXT)),evaluate_a16_special_eligibility,("TBDY 2018 Table 4.1 A16",))

VS4A_REGISTRY=RegulatoryRegistry(derivations=(DUCTILITY_SPEC,BASE_R_SPEC,BASE_D_SPEC,BASE_BYS_SPEC,EFFECTIVE_BYS_SPEC,POSTQUAL_SPEC,BASELINE_POLICY_SPEC,ANALYSIS_BASIS_SPEC),checks=(BYS_CHECK_SPEC,DTS_CHECK_SPEC,ORTHOGONAL_CHECK_SPEC,A31_CHECK_SPEC,A16_CHECK_SPEC))


def _external(authority_id:str,key:DependencyKey,semantic:SemanticType,value:object,*,scope_ref:str,direction:str|None,grain:Grain,unit=UNIT_ENUM_STATE,dimension=PhysicalDimension.ENUM_STATE,provenance_refs:Sequence[str]=())->ExternalDependencyAuthority:
    return ExternalDependencyAuthority(authority_id=authority_id,key=key,source_kind=DependencySourceKind.CONTEXT,semantic_type=semantic,physical_dimension=dimension,grain=grain,scope_ref=scope_ref,direction=direction,unit=unit,availability=AvailabilityState.RESOLVED,population_completeness=PopulationCompleteness.FULL,value=value,provenance_refs=tuple(provenance_refs))


def _directional_targets(direction:str,row:str)->tuple[RuleScopeTarget,...]:
    ids=[RC_SYSTEM_DUCTILITY_CLASS,RC_TABLE_4_1_BASE_R,RC_TABLE_4_1_BASE_D,RC_TABLE_4_1_BASE_BYS_POLICY,RC_EFFECTIVE_PREANALYSIS_BYS_POLICY,RC_POST_ANALYSIS_SYSTEM_QUALIFICATION_REQUIREMENT,RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY,RC_ANALYSIS_BASIS_COMPATIBILITY,RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY]
    if row!="A16": ids.append(RC_TABLE_4_1_BYS_ELIGIBILITY)
    if row=="A31": ids.append(RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY)
    if row=="A16": ids.append(RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY)
    return tuple(RuleScopeTarget(rule_id=i,grain=Grain.DIRECTION,scope_ref=BUILDING_SCOPE,direction=direction,applicability_input=DirectionalApplicabilityInput(),analysis_basis_status=AnalysisBasisStatus.MATCH) for i in ids)


def compile_vs4a_program(*,declarations:ReviewedOrthogonalRcSystemDeclaration,seismic:ReviewedSeismicClassificationContext,analysis_assumptions:Sequence[DirectionalAnalysisSystemAssumption],a16_contexts:Sequence[A16SpecialContext]=())->CompiledRegulatoryProgram:
    """Compile the VS-4A production program; strict F0.9 authority is mandatory."""
    if not isinstance(declarations,ReviewedOrthogonalRcSystemDeclaration): raise TypeError("declarations must be ReviewedOrthogonalRcSystemDeclaration")
    if not isinstance(seismic,ReviewedSeismicClassificationContext): raise TypeError("seismic must be ReviewedSeismicClassificationContext")
    assumptions={item.direction:item for item in analysis_assumptions}
    if set(assumptions)!={"X","Y"} or len(assumptions)!=2: raise ValueError("analysis_assumptions must contain exactly one X and one Y assumption")
    a16_by_direction={item.direction:item for item in a16_contexts}
    if len(a16_by_direction)!=len(tuple(a16_contexts)): raise ValueError("duplicate A16 context direction")
    targets=[*_directional_targets("X",declarations.x.table_4_1_row),*_directional_targets("Y",declarations.y.table_4_1_row),RuleScopeTarget(rule_id=RC_TBDY_4_3_4_2_ORTHOGONAL_DUCTILITY_CONSISTENCY,grain=Grain.MODEL,scope_ref="MODEL",direction=None,applicability_input=DirectionalApplicabilityInput(),analysis_basis_status=AnalysisBasisStatus.MATCH)]
    authorities=[_external("vs4a:orthogonal_rows",ORTHOGONAL_ROWS_KEY,SemanticType.RC_ORTHOGONAL_SYSTEM_DECLARATION,(declarations.x.table_4_1_row,declarations.y.table_4_1_row),scope_ref="MODEL",direction=None,grain=Grain.MODEL,provenance_refs=declarations.provenance_refs)]
    for declaration in (declarations.x,declarations.y):
        direction=declaration.direction; assumption=assumptions[direction]; shared_refs=tuple(sorted(set((*declaration.review_refs,*declaration.provenance_refs,*seismic.provenance_refs))))
        authorities.extend((_external(f"vs4a:{direction}:row",DECLARED_ROW_KEY,SemanticType.RC_TABLE_4_1_ROW,declaration.table_4_1_row,scope_ref=BUILDING_SCOPE,direction=direction,grain=Grain.DIRECTION,provenance_refs=shared_refs),_external(f"vs4a:{direction}:dts",DTS_KEY,SemanticType.RC_DTS,seismic.dts,scope_ref=BUILDING_SCOPE,direction=direction,grain=Grain.DIRECTION,provenance_refs=seismic.provenance_refs),_external(f"vs4a:{direction}:bys",BYS_KEY,SemanticType.RC_BYS,seismic.bys,scope_ref=BUILDING_SCOPE,direction=direction,grain=Grain.DIRECTION,provenance_refs=seismic.provenance_refs),_external(f"vs4a:{direction}:assumed_row",ASSUMED_ROW_KEY,SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,assumption.assumed_table_4_1_row,scope_ref=BUILDING_SCOPE,direction=direction,grain=Grain.DIRECTION,provenance_refs=(*assumption.analysis_evidence_refs,*assumption.provenance_refs)),_external(f"vs4a:{direction}:assumed_r",ASSUMED_R_KEY,SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,assumption.assumed_r,scope_ref=BUILDING_SCOPE,direction=direction,grain=Grain.DIRECTION,unit=UNIT_DIMENSIONLESS,dimension=PhysicalDimension.DIMENSIONLESS,provenance_refs=(*assumption.analysis_evidence_refs,*assumption.provenance_refs)),_external(f"vs4a:{direction}:assumed_d",ASSUMED_D_KEY,SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,assumption.assumed_d,scope_ref=BUILDING_SCOPE,direction=direction,grain=Grain.DIRECTION,unit=UNIT_DIMENSIONLESS,dimension=PhysicalDimension.DIMENSIONLESS,provenance_refs=(*assumption.analysis_evidence_refs,*assumption.provenance_refs))))
        if declaration.table_4_1_row=="A16":
            context=a16_by_direction.get(direction)
            if context is None: raise ValueError(f"A16 declaration in {direction} requires A16SpecialContext")
            authorities.extend((_external(f"vs4a:{direction}:a16_story_count",A16_STORY_COUNT_KEY,SemanticType.RC_A16_SPECIAL_CONTEXT,context.story_count,scope_ref=BUILDING_SCOPE,direction=direction,grain=Grain.DIRECTION,unit=UNIT_DIMENSIONLESS,dimension=PhysicalDimension.DIMENSIONLESS,provenance_refs=context.provenance_refs),_external(f"vs4a:{direction}:a16_height",A16_HEIGHT_KEY,SemanticType.RC_A16_SPECIAL_CONTEXT,context.building_height_m,scope_ref=BUILDING_SCOPE,direction=direction,grain=Grain.DIRECTION,unit=UNIT_M,dimension=PhysicalDimension.LENGTH,provenance_refs=context.provenance_refs),_external(f"vs4a:{direction}:a16_roof",A16_ROOF_CONNECTION_KEY,SemanticType.RC_A16_SPECIAL_CONTEXT,context.roof_connection_condition.value,scope_ref=BUILDING_SCOPE,direction=direction,grain=Grain.DIRECTION,provenance_refs=context.provenance_refs)))
    from tbdy_engine.regulatory.sources.tbdy2018 import build_vs4a_authority_catalog
    return RegulatoryCompiler.compile(VS4A_REGISTRY,RegulatoryCompileInputs(rule_targets=tuple(targets),external_authorities=tuple(authorities),regulatory_authority_catalog=build_vs4a_authority_catalog()))


def execute_vs4a_program(program:CompiledRegulatoryProgram)->RegulatoryStoreSnapshot:
    return RegulatoryEngine.execute(program)


def directional_quantity(snapshot:RegulatoryStoreSnapshot,rule_id:RuleId,direction:str)->RegulatoryQuantity:
    direction=_direction(direction); matches=tuple(q for q in snapshot.regulatory_quantities if q.producer_instance_id.rule_id==rule_id and q.producer_instance_id.direction==direction)
    if len(matches)!=1: raise ValueError(f"expected exactly one {rule_id.value} quantity for {direction}")
    return matches[0]


ALL_VS4A_RULE_IDS=tuple(spec.rule_id for spec in (*VS4A_REGISTRY.derivations,*VS4A_REGISTRY.checks))

__all__=["RcDuctilityLevel","RcPostAnalysisQualificationRequirement","RcBaselineResolutionState","RoofConnectionCondition","Table41RowPolicy","TABLE_4_1_A_SERIES","TABLE_4_1_ROWS","TABLE_4_1_ROW_CLAIM_IDS","ReviewedDirectionalRcSystemDeclaration","ReviewedSeismicClassificationContext","ReviewedOrthogonalRcSystemDeclaration","A16SpecialContext","DirectionalAnalysisSystemAssumption","table_4_1_policy","compile_vs4a_program","execute_vs4a_program","directional_quantity","VS4A_REGISTRY","ALL_VS4A_RULE_IDS","RC_SYSTEM_DUCTILITY_CLASS","RC_TABLE_4_1_BASE_R","RC_TABLE_4_1_BASE_D","RC_TABLE_4_1_BASE_BYS_POLICY","RC_EFFECTIVE_PREANALYSIS_BYS_POLICY","RC_POST_ANALYSIS_SYSTEM_QUALIFICATION_REQUIREMENT","RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY","RC_ANALYSIS_BASIS_COMPATIBILITY","RC_TABLE_4_1_BYS_ELIGIBILITY","RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY","RC_TBDY_4_3_4_2_ORTHOGONAL_DUCTILITY_CONSISTENCY","RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY","RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY"]
