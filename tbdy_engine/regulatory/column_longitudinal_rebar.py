"""FND-COL-1 source-bound longitudinal reinforcement and layout authority.

Scope is deliberately bounded to rectangular reinforced-concrete column
longitudinal reinforcement requirements and deterministic layout eligibility.
The module neither reads ETABS nor produces ETABS_REQUIRED_REBAR,
ENGINE_SELECTED_REBAR, PMM capacity, transverse reinforcement, or final shear.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.design.columns.rebar_catalog import RebarCatalog
from tbdy_engine.design.columns.rebar_layout import (
    ColumnRebarGeometryCandidate,
    ColumnRebarGeometryInputs,
    ColumnRebarLayoutError,
    generate_rectangular_column_rebar_geometry_candidates,
    ts500_min_clear_spacing_mm,
)
from tbdy_engine.regulatory.authority import (
    RegulatoryAuthorityCatalog,
    ValidatedRuleAuthority,
    validate_rule_authority,
)
from tbdy_engine.regulatory.contracts import (
    ApplicabilityBinding,
    ApplicabilityState,
    CheckEvaluatorBinding,
    CheckSpec,
    RuleId,
)


class ColumnLongitudinalAuthorityError(ValueError):
    """Fail-closed FND-COL-1 input/authority error."""


FND_COL_1_RULE_ID = RuleId("FND_COL_1_COLUMN_LONGITUDINAL_LAYOUT_AUTHORITY")
FND_COL_1_RULE_VERSION = "1.0.0"
FND_COL_1_EVALUATOR_BINDING_ID = "FND_COL_1_COLUMN_LONGITUDINAL_LAYOUT_CHECK_V1"

TBDY_COLUMN_LONGITUDINAL_RHO_MIN = 0.01
TBDY_COLUMN_LONGITUDINAL_RHO_MAX = 0.04
TBDY_COLUMN_LONGITUDINAL_LAP_SPLICE_TOTAL_RHO_MAX = 0.06
TBDY_COLUMN_LONGITUDINAL_MIN_BAR_DIAMETER_MM = 14.0
TBDY_CIRCULAR_COLUMN_MIN_LONGITUDINAL_BAR_COUNT = 6

_FACTORY_TOKEN = object()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnLongitudinalAuthorityError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: object, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ColumnLongitudinalAuthorityError(f"{label} is required and must be finite and > 0")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ColumnLongitudinalAuthorityError(
            f"{label} is required and must be finite and > 0"
        ) from exc
    if not math.isfinite(result) or result <= 0.0:
        raise ColumnLongitudinalAuthorityError(f"{label} is required and must be finite and > 0")
    return result


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ColumnLongitudinalRequirementInputs:
    """Exact factual identity and rectangular section geometry."""

    component_id: str
    section_id: str
    width_mm: float
    depth_mm: float
    model_identity: str
    evidence_epoch_id: str
    geometry_source_ref: str

    def __post_init__(self) -> None:
        for name in (
            "component_id",
            "section_id",
            "model_identity",
            "evidence_epoch_id",
            "geometry_source_ref",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "width_mm", _positive(self.width_mm, "width_mm"))
        object.__setattr__(self, "depth_mm", _positive(self.depth_mm, "depth_mm"))

    @property
    def gross_area_mm2(self) -> float:
        return self.width_mm * self.depth_mm

    @property
    def factual_fingerprint(self) -> str:
        return _fingerprint(
            {
                "component_id": self.component_id,
                "section_id": self.section_id,
                "width_mm": self.width_mm,
                "depth_mm": self.depth_mm,
                "model_identity": self.model_identity,
                "evidence_epoch_id": self.evidence_epoch_id,
                "geometry_source_ref": self.geometry_source_ref,
            }
        )


@dataclass(frozen=True, slots=True)
class ColumnLongitudinalLayoutInputs:
    """Factual/project layout inputs; regulatory limits are intentionally absent."""

    requirement_inputs: ColumnLongitudinalRequirementInputs
    clear_cover_mm: float
    tie_diameter_mm: float
    aggregate_max_mm: float
    rebar_catalog: RebarCatalog
    cover_source_ref: str
    tie_source_ref: str
    aggregate_source_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.requirement_inputs, ColumnLongitudinalRequirementInputs):
            raise TypeError("requirement_inputs must be ColumnLongitudinalRequirementInputs")
        object.__setattr__(self, "clear_cover_mm", _positive(self.clear_cover_mm, "clear_cover_mm"))
        object.__setattr__(self, "tie_diameter_mm", _positive(self.tie_diameter_mm, "tie_diameter_mm"))
        object.__setattr__(self, "aggregate_max_mm", _positive(self.aggregate_max_mm, "aggregate_max_mm"))
        if not isinstance(self.rebar_catalog, RebarCatalog):
            raise TypeError("rebar_catalog must be factual RebarCatalog")
        if not self.rebar_catalog.entries:
            raise ColumnLongitudinalAuthorityError("rebar_catalog must contain factual project entries")
        if self.rebar_catalog.status != "PROVEN_FACTUAL_REBAR_CATALOG":
            raise ColumnLongitudinalAuthorityError("rebar_catalog must be PROVEN_FACTUAL_REBAR_CATALOG")
        for name in ("cover_source_ref", "tie_source_ref", "aggregate_source_ref"):
            object.__setattr__(self, name, _text(getattr(self, name), name))

    @property
    def factual_fingerprint(self) -> str:
        return _fingerprint(
            {
                "requirement_fingerprint": self.requirement_inputs.factual_fingerprint,
                "clear_cover_mm": self.clear_cover_mm,
                "tie_diameter_mm": self.tie_diameter_mm,
                "aggregate_max_mm": self.aggregate_max_mm,
                "cover_source_ref": self.cover_source_ref,
                "tie_source_ref": self.tie_source_ref,
                "aggregate_source_ref": self.aggregate_source_ref,
                "rebar_catalog": [
                    [entry.name, entry.diameter_mm, entry.source_identity]
                    for entry in self.rebar_catalog.entries
                ],
            }
        )


@dataclass(frozen=True, slots=True, init=False)
class TBDYMinRequiredRebar:
    """Typed canonical TBDY_MIN_REQUIRED_REBAR authority artifact.

    Construction is private to ``derive_tbdy_min_required_rebar`` so a caller
    scalar cannot be promoted into canonical authority.
    """

    component_id: str
    section_id: str
    width_mm: float
    depth_mm: float
    gross_area_mm2: float
    minimum_ratio: float
    maximum_ratio: float
    minimum_area_mm2: float
    maximum_area_mm2: float
    minimum_bar_diameter_mm: float
    factual_fingerprint: str
    model_identity: str
    evidence_epoch_id: str
    geometry_source_ref: str
    rule_id: str
    authority_binding_ref: str
    implementation_fingerprint: str
    source_claim_refs: tuple[str, ...]
    source_review_refs: tuple[str, ...]
    authority: str

    def __init__(self, *, _token: object = None) -> None:
        if _token is not _FACTORY_TOKEN:
            raise TypeError(
                "TBDYMinRequiredRebar is authority-created only; use derive_tbdy_min_required_rebar"
            )


@dataclass(frozen=True, slots=True)
class ColumnLongitudinalRuleProbe:
    component_id: str
    section_id: str
    rho: float
    bar_diameter_mm: float
    clear_spacing_mm: float
    aggregate_max_mm: float


@dataclass(frozen=True, slots=True)
class ColumnLongitudinalLayoutEligibility:
    candidate_id: str
    eligible: bool
    reason_codes: tuple[str, ...]
    bar_diameter_mm: float
    bar_count: int
    rho: float
    clear_spacing_mm: float
    required_clear_spacing_mm: float
    authority: str = "TBDY_COLUMN_LAYOUT_ELIGIBILITY"


@dataclass(frozen=True, slots=True)
class ColumnLongitudinalLayoutAuthorityResult:
    requirement: TBDYMinRequiredRebar
    factual_fingerprint: str
    eligibility: tuple[ColumnLongitudinalLayoutEligibility, ...]
    eligible_candidates: tuple[ColumnRebarGeometryCandidate, ...]
    status: str
    authority_binding_ref: str
    implementation_fingerprint: str
    authority: str = "TBDY_COLUMN_LAYOUT_ELIGIBILITY"


def _probe_applicability(value: object) -> ApplicabilityState:
    if not isinstance(value, ColumnLongitudinalRuleProbe):
        return ApplicabilityState.INVALID_CONTEXT
    return ApplicabilityState.APPLIES


def _evaluate_probe(value: object) -> CheckResult:
    if not isinstance(value, ColumnLongitudinalRuleProbe):
        return CheckResult(
            check_id=FND_COL_1_RULE_ID.value,
            component="UNKNOWN",
            component_type="COLUMN",
            status=CheckStatus.NO_DATA,
            evaluation_level=EvaluationLevel.NO_DATA,
            messages=("FND-COL-1 probe input is missing or invalid.",),
            code_ref="TBDY2018 7.3.2.1 + TS500 9.5.2",
        )
    required_clear = ts500_min_clear_spacing_mm(
        bar_diameter_mm=value.bar_diameter_mm,
        aggregate_max_mm=value.aggregate_max_mm,
    )
    ok = (
        TBDY_COLUMN_LONGITUDINAL_RHO_MIN - 1e-12
        <= float(value.rho)
        <= TBDY_COLUMN_LONGITUDINAL_RHO_MAX + 1e-12
        and float(value.bar_diameter_mm) + 1e-12
        >= TBDY_COLUMN_LONGITUDINAL_MIN_BAR_DIAMETER_MM
        and float(value.clear_spacing_mm) + 1e-9 >= required_clear
    )
    return CheckResult(
        check_id=FND_COL_1_RULE_ID.value,
        component=value.component_id,
        component_type="COLUMN",
        section=value.section_id,
        status=CheckStatus.OK if ok else CheckStatus.FAIL,
        value={
            "rho": float(value.rho),
            "bar_diameter_mm": float(value.bar_diameter_mm),
            "clear_spacing_mm": float(value.clear_spacing_mm),
            "required_clear_spacing_mm": required_clear,
        },
        pass_rule="0.01 <= rho <= 0.04; phi >= 14 mm; clear >= max(1.5phi,4/3 dagg,40 mm)",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        code_ref="TBDY2018 7.3.2.1 + TS500 9.5.2",
    )


FND_COL_1_CHECK_SPEC = CheckSpec(
    rule_id=FND_COL_1_RULE_ID,
    code_refs=("TBDY2018 7.3.2.1", "TS500 9.5.2"),
    rule_version=FND_COL_1_RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=(),
    applicability=ApplicabilityBinding(
        binding_id="FND_COL_1_COLUMN_LONGITUDINAL_APPLICABILITY_V1",
        input_type=ColumnLongitudinalRuleProbe,
        evaluator=_probe_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        binding_id=FND_COL_1_EVALUATOR_BINDING_ID,
        input_type=ColumnLongitudinalRuleProbe,
        evaluator=_evaluate_probe,
    ),
)


def _validated(catalog: RegulatoryAuthorityCatalog) -> ValidatedRuleAuthority:
    if not isinstance(catalog, RegulatoryAuthorityCatalog):
        raise TypeError("authority_catalog must be RegulatoryAuthorityCatalog")
    validated = validate_rule_authority(FND_COL_1_CHECK_SPEC, catalog)
    required_claims = {
        "TBDY2018_COLUMN_LONGITUDINAL_RATIO_1_4",
        "TBDY2018_COLUMN_MIN_LONGITUDINAL_BAR_DIAMETER_14_MM",
        "TS500_COLUMN_LONGITUDINAL_CLEAR_SPACING",
    }
    if not required_claims.issubset(set(validated.claim_refs)):
        raise ColumnLongitudinalAuthorityError(
            "validated authority is missing one or more mandatory FND-COL-1 source claims"
        )
    return validated


def derive_tbdy_min_required_rebar(
    inputs: ColumnLongitudinalRequirementInputs,
    *,
    authority_catalog: RegulatoryAuthorityCatalog,
) -> TBDYMinRequiredRebar:
    """Derive canonical minimum/ordinary maximum directly from validated authority."""

    if not isinstance(inputs, ColumnLongitudinalRequirementInputs):
        raise TypeError("inputs must be ColumnLongitudinalRequirementInputs")
    authority = _validated(authority_catalog)
    gross = inputs.gross_area_mm2

    artifact = TBDYMinRequiredRebar(_token=_FACTORY_TOKEN)
    values = {
        "component_id": inputs.component_id,
        "section_id": inputs.section_id,
        "width_mm": inputs.width_mm,
        "depth_mm": inputs.depth_mm,
        "gross_area_mm2": gross,
        "minimum_ratio": TBDY_COLUMN_LONGITUDINAL_RHO_MIN,
        "maximum_ratio": TBDY_COLUMN_LONGITUDINAL_RHO_MAX,
        "minimum_area_mm2": gross * TBDY_COLUMN_LONGITUDINAL_RHO_MIN,
        "maximum_area_mm2": gross * TBDY_COLUMN_LONGITUDINAL_RHO_MAX,
        "minimum_bar_diameter_mm": TBDY_COLUMN_LONGITUDINAL_MIN_BAR_DIAMETER_MM,
        "factual_fingerprint": inputs.factual_fingerprint,
        "model_identity": inputs.model_identity,
        "evidence_epoch_id": inputs.evidence_epoch_id,
        "geometry_source_ref": inputs.geometry_source_ref,
        "rule_id": FND_COL_1_RULE_ID.value,
        "authority_binding_ref": authority.binding_ref,
        "implementation_fingerprint": authority.approved_implementation_fingerprint,
        "source_claim_refs": authority.claim_refs,
        "source_review_refs": authority.review_refs,
        "authority": "TBDY_MIN_REQUIRED_REBAR",
    }
    for name, value in values.items():
        object.__setattr__(artifact, name, value)
    return artifact


def evaluate_column_longitudinal_layout_candidate(
    candidate: ColumnRebarGeometryCandidate,
    *,
    aggregate_max_mm: float,
) -> ColumnLongitudinalLayoutEligibility:
    """Apply only FND-COL-1 regulatory eligibility to one geometry candidate."""

    if not isinstance(candidate, ColumnRebarGeometryCandidate):
        raise TypeError("candidate must be ColumnRebarGeometryCandidate")
    aggregate = _positive(aggregate_max_mm, "aggregate_max_mm")
    required_clear = ts500_min_clear_spacing_mm(
        bar_diameter_mm=candidate.bar_diameter_mm,
        aggregate_max_mm=aggregate,
    )
    reasons: list[str] = []
    if candidate.rho + 1e-12 < TBDY_COLUMN_LONGITUDINAL_RHO_MIN:
        reasons.append("BELOW_TBDY_MIN_LONGITUDINAL_RATIO")
    if candidate.rho > TBDY_COLUMN_LONGITUDINAL_RHO_MAX + 1e-12:
        reasons.append("ABOVE_TBDY_MAX_LONGITUDINAL_RATIO")
    if candidate.bar_diameter_mm + 1e-12 < TBDY_COLUMN_LONGITUDINAL_MIN_BAR_DIAMETER_MM:
        reasons.append("BELOW_TBDY_MIN_LONGITUDINAL_BAR_DIAMETER")
    if candidate.min_clear_spacing_mm + 1e-9 < required_clear:
        reasons.append("BELOW_TS500_COLUMN_LONGITUDINAL_CLEAR_SPACING")

    return ColumnLongitudinalLayoutEligibility(
        candidate_id=candidate.candidate_id,
        eligible=not reasons,
        reason_codes=tuple(reasons),
        bar_diameter_mm=candidate.bar_diameter_mm,
        bar_count=candidate.bar_count,
        rho=candidate.rho,
        clear_spacing_mm=candidate.min_clear_spacing_mm,
        required_clear_spacing_mm=required_clear,
    )


def evaluate_column_longitudinal_layouts(
    inputs: ColumnLongitudinalLayoutInputs,
    *,
    authority_catalog: RegulatoryAuthorityCatalog,
) -> ColumnLongitudinalLayoutAuthorityResult:
    """Generate factual geometry then apply validated regulatory eligibility."""

    if not isinstance(inputs, ColumnLongitudinalLayoutInputs):
        raise TypeError("inputs must be ColumnLongitudinalLayoutInputs")
    authority = _validated(authority_catalog)
    requirement = derive_tbdy_min_required_rebar(
        inputs.requirement_inputs,
        authority_catalog=authority_catalog,
    )
    try:
        geometry = generate_rectangular_column_rebar_geometry_candidates(
            ColumnRebarGeometryInputs(
                width_mm=inputs.requirement_inputs.width_mm,
                depth_mm=inputs.requirement_inputs.depth_mm,
                clear_cover_mm=inputs.clear_cover_mm,
                tie_diameter_mm=inputs.tie_diameter_mm,
            ),
            bar_diameters_mm=inputs.rebar_catalog.diameters_mm,
        )
    except ColumnRebarLayoutError as exc:
        raise ColumnLongitudinalAuthorityError(str(exc)) from exc

    eligibility = tuple(
        evaluate_column_longitudinal_layout_candidate(
            candidate,
            aggregate_max_mm=inputs.aggregate_max_mm,
        )
        for candidate in geometry.candidates
    )
    eligible_ids = {item.candidate_id for item in eligibility if item.eligible}
    eligible_candidates = tuple(
        candidate for candidate in geometry.candidates if candidate.candidate_id in eligible_ids
    )
    return ColumnLongitudinalLayoutAuthorityResult(
        requirement=requirement,
        factual_fingerprint=inputs.factual_fingerprint,
        eligibility=eligibility,
        eligible_candidates=eligible_candidates,
        status="PROVEN" if eligible_candidates else "NO_REGULATORILY_ELIGIBLE_LAYOUT",
        authority_binding_ref=authority.binding_ref,
        implementation_fingerprint=authority.approved_implementation_fingerprint,
    )


__all__ = [
    "ColumnLongitudinalAuthorityError",
    "ColumnLongitudinalLayoutAuthorityResult",
    "ColumnLongitudinalLayoutEligibility",
    "ColumnLongitudinalLayoutInputs",
    "ColumnLongitudinalRequirementInputs",
    "ColumnLongitudinalRuleProbe",
    "FND_COL_1_CHECK_SPEC",
    "FND_COL_1_EVALUATOR_BINDING_ID",
    "FND_COL_1_RULE_ID",
    "FND_COL_1_RULE_VERSION",
    "TBDYMinRequiredRebar",
    "TBDY_CIRCULAR_COLUMN_MIN_LONGITUDINAL_BAR_COUNT",
    "TBDY_COLUMN_LONGITUDINAL_LAP_SPLICE_TOTAL_RHO_MAX",
    "TBDY_COLUMN_LONGITUDINAL_MIN_BAR_DIAMETER_MM",
    "TBDY_COLUMN_LONGITUDINAL_RHO_MAX",
    "TBDY_COLUMN_LONGITUDINAL_RHO_MIN",
    "derive_tbdy_min_required_rebar",
    "evaluate_column_longitudinal_layout_candidate",
    "evaluate_column_longitudinal_layouts",
]
