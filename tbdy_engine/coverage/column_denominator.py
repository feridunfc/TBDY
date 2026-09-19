"""A38 complete supported Column denominator composition.

This module is a product-completeness adapter only.  It consumes already
authoritative A1-A37 artifacts and emits deterministic expected-leaf identities
plus one truthful runtime outcome for every expected leaf.  It performs no
engineering calculation and owns no ETABS acquisition path.

The F0 regulatory contracts remain authoritative where they exist.  A38 uses a
bounded product-level vocabulary only for lifecycle/product leaves that cannot
truthfully be forced into ``ClosureExecutionStatus`` (for example explicit
unresolved, reanalysis-required and deferred cross-domain states).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from typing import Iterable, Mapping, Sequence

from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.regulatory.column_axial_dual_code import (
    TBDY_RULE_ID as COLUMN_TBDY_AXIAL_RULE_ID,
    TS500_RULE_ID as COLUMN_TS500_AXIAL_RULE_ID,
)
from tbdy_engine.regulatory.contracts import ClosureExecutionStatus, RuleId


class ColumnDenominatorError(ValueError):
    """Malformed or non-reconciled A38 denominator population."""


class ColumnLeafApplicability(StrEnum):
    MANDATORY = "MANDATORY"
    CONDITIONAL = "CONDITIONAL"
    PROVEN_NOT_APPLICABLE = "PROVEN_NOT_APPLICABLE"


class ColumnLeafOutcomeStatus(StrEnum):
    EXECUTED_PASS = "EXECUTED/PASS"
    EXECUTED_FAIL = "EXECUTED/FAIL"
    PROVEN_NOT_APPLICABLE = "PROVEN_NOT_APPLICABLE"
    BLOCKED = "BLOCKED"
    NO_DATA = "NO_DATA"
    EXPLICIT_UNRESOLVED = "EXPLICIT_UNRESOLVED"
    REANALYSIS_REQUIRED = "REANALYSIS_REQUIRED"


@dataclass(frozen=True, slots=True)
class ColumnDenominatorLeafIdentity:
    value: str
    component_id: str
    leaf_key: str
    model_fingerprint: str
    evidence_epoch_id: str
    direction: str | None = None
    scope_ref: str | None = None
    generation_ref: str | None = None

    @classmethod
    def build(
        cls,
        *,
        component_id: str,
        leaf_key: str,
        model_fingerprint: str,
        evidence_epoch_id: str,
        direction: str | None = None,
        scope_ref: str | None = None,
        generation_ref: str | None = None,
    ) -> "ColumnDenominatorLeafIdentity":
        values = {
            "component_id": _text(component_id, "component_id"),
            "leaf_key": _text(leaf_key, "leaf_key"),
            "model_fingerprint": _text(model_fingerprint, "model_fingerprint"),
            "evidence_epoch_id": _text(evidence_epoch_id, "evidence_epoch_id"),
            "direction": _optional_text(direction, "direction"),
            "scope_ref": _optional_text(scope_ref, "scope_ref"),
            "generation_ref": _optional_text(generation_ref, "generation_ref"),
        }
        encoded = json.dumps(
            values,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return cls(
            value="column-denominator-leaf:sha256:" + hashlib.sha256(encoded).hexdigest(),
            **values,
        )

    def __post_init__(self) -> None:
        if not self.value.startswith("column-denominator-leaf:sha256:"):
            raise ColumnDenominatorError("leaf identity must use canonical sha256 prefix")
        digest = self.value.removeprefix("column-denominator-leaf:sha256:")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ColumnDenominatorError("leaf identity must contain lowercase sha256")
        for name in (
            "component_id",
            "leaf_key",
            "model_fingerprint",
            "evidence_epoch_id",
        ):
            _text(getattr(self, name), name)
        _optional_text(self.direction, "direction")
        _optional_text(self.scope_ref, "scope_ref")
        _optional_text(self.generation_ref, "generation_ref")


@dataclass(frozen=True, slots=True)
class ColumnExpectedLeaf:
    identity: ColumnDenominatorLeafIdentity
    family: str
    applicability: ColumnLeafApplicability

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ColumnDenominatorLeafIdentity):
            raise TypeError("identity must be ColumnDenominatorLeafIdentity")
        object.__setattr__(self, "family", _text(self.family, "family"))
        if not isinstance(self.applicability, ColumnLeafApplicability):
            raise TypeError("applicability must be ColumnLeafApplicability")


@dataclass(frozen=True, slots=True)
class ColumnLeafOutcome:
    identity: ColumnDenominatorLeafIdentity
    status: ColumnLeafOutcomeStatus
    source_ref: str
    canonical_artifact_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    blocker_refs: tuple[str, ...] = ()
    analysis_basis_ref: str | None = None
    dependency_refs: tuple[str, ...] = ()
    deferred_owner: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ColumnDenominatorLeafIdentity):
            raise TypeError("identity must be ColumnDenominatorLeafIdentity")
        if not isinstance(self.status, ColumnLeafOutcomeStatus):
            raise TypeError("status must be ColumnLeafOutcomeStatus")
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))
        object.__setattr__(
            self,
            "canonical_artifact_ref",
            _optional_text(self.canonical_artifact_ref, "canonical_artifact_ref"),
        )
        object.__setattr__(
            self,
            "analysis_basis_ref",
            _optional_text(self.analysis_basis_ref, "analysis_basis_ref"),
        )
        object.__setattr__(
            self,
            "deferred_owner",
            _optional_text(self.deferred_owner, "deferred_owner"),
        )
        object.__setattr__(self, "evidence_refs", _refs(self.evidence_refs))
        object.__setattr__(self, "blocker_refs", _refs(self.blocker_refs))
        object.__setattr__(self, "dependency_refs", _refs(self.dependency_refs))
        if self.deferred_owner is not None:
            if (
                self.status
                is not ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
                or not self.dependency_refs
            ):
                raise ColumnDenominatorError(
                    "cross-domain deferral must be EXPLICIT_UNRESOLVED "
                    "with explicit dependency refs"
                )


@dataclass(frozen=True, slots=True)
class SupportedColumnDenominator:
    """Exact A38 expected-vs-runtime Column denominator population."""

    expected_leaves: tuple[ColumnExpectedLeaf, ...]
    outcomes: tuple[ColumnLeafOutcome, ...]

    def __init__(
        self,
        expected_leaves: Sequence[ColumnExpectedLeaf],
        outcomes: Sequence[ColumnLeafOutcome],
    ) -> None:
        expected = tuple(expected_leaves)
        observed = tuple(outcomes)
        if not expected:
            raise ColumnDenominatorError("expected Column denominator must be nonempty")
        if any(not isinstance(item, ColumnExpectedLeaf) for item in expected):
            raise TypeError("expected_leaves must contain ColumnExpectedLeaf")
        if any(not isinstance(item, ColumnLeafOutcome) for item in observed):
            raise TypeError("outcomes must contain ColumnLeafOutcome")

        expected_ids = tuple(item.identity.value for item in expected)
        observed_ids = tuple(item.identity.value for item in observed)
        if len(expected_ids) != len(set(expected_ids)):
            raise ColumnDenominatorError("duplicate expected Column leaf identity")
        if len(observed_ids) != len(set(observed_ids)):
            raise ColumnDenominatorError("duplicate runtime Column leaf identity")

        expected_set = set(expected_ids)
        observed_set = set(observed_ids)
        missing = tuple(sorted(expected_set - observed_set))
        orphan = tuple(sorted(observed_set - expected_set))
        if missing:
            raise ColumnDenominatorError(
                "silent missing Column denominator outcomes: " + ",".join(missing)
            )
        if orphan:
            raise ColumnDenominatorError(
                "orphan Column denominator outcomes: " + ",".join(orphan)
            )

        expected_by_id = {item.identity.value: item for item in expected}
        for outcome in observed:
            expected_leaf = expected_by_id[outcome.identity.value]
            if (
                expected_leaf.applicability
                is ColumnLeafApplicability.PROVEN_NOT_APPLICABLE
                and outcome.status
                is not ColumnLeafOutcomeStatus.PROVEN_NOT_APPLICABLE
            ):
                raise ColumnDenominatorError(
                    "PNA expected leaf must retain PROVEN_NOT_APPLICABLE outcome"
                )
            if (
                outcome.status
                is ColumnLeafOutcomeStatus.PROVEN_NOT_APPLICABLE
                and expected_leaf.applicability
                is not ColumnLeafApplicability.PROVEN_NOT_APPLICABLE
            ):
                raise ColumnDenominatorError(
                    "runtime PNA requires proven expected-leaf applicability"
                )

        object.__setattr__(
            self,
            "expected_leaves",
            tuple(sorted(expected, key=lambda item: item.identity.value)),
        )
        object.__setattr__(
            self,
            "outcomes",
            tuple(sorted(observed, key=lambda item: item.identity.value)),
        )

    @property
    def expected_component_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted({item.identity.component_id for item in self.expected_leaves})
        )

    @property
    def expected_column_count(self) -> int:
        return len(self.expected_component_ids)

    @property
    def expected_leaf_count(self) -> int:
        """Unique product leaf-key/direction population per component."""
        return len(
            {
                (item.identity.leaf_key, item.identity.direction)
                for item in self.expected_leaves
            }
        )

    @property
    def expected_instance_count(self) -> int:
        return len(self.expected_leaves)

    @property
    def silent_missing_count(self) -> int:
        return 0

    @property
    def duplicate_count(self) -> int:
        return 0

    @property
    def orphan_count(self) -> int:
        return 0

    @property
    def population_reconciled(self) -> bool:
        return True

    @property
    def fully_resolved(self) -> bool:
        unresolved = {
            ColumnLeafOutcomeStatus.BLOCKED,
            ColumnLeafOutcomeStatus.NO_DATA,
            ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED,
            ColumnLeafOutcomeStatus.REANALYSIS_REQUIRED,
        }
        return not any(item.status in unresolved for item in self.outcomes)

    @property
    def outcome_counts(self) -> Mapping[str, int]:
        counts = {status.value: 0 for status in ColumnLeafOutcomeStatus}
        for outcome in self.outcomes:
            counts[outcome.status.value] += 1
        return counts

    @property
    def required_report_source_refs(self) -> tuple[str, ...]:
        return tuple(sorted(item.source_ref for item in self.outcomes))

    def outcome(
        self,
        component_id: str,
        leaf_key: str,
        direction: str | None = None,
    ) -> ColumnLeafOutcome:
        matches = tuple(
            item
            for item in self.outcomes
            if item.identity.component_id == component_id
            and item.identity.leaf_key == leaf_key
            and item.identity.direction == direction
        )
        if len(matches) != 1:
            raise KeyError(
                f"expected exactly one denominator outcome for "
                f"{component_id}:{leaf_key}:{direction}; got {len(matches)}"
            )
        return matches[0]

    def as_dict(self) -> dict[str, object]:
        expected = []
        for leaf in self.expected_leaves:
            expected.append(
                {
                    "identity": leaf.identity.value,
                    "component_id": leaf.identity.component_id,
                    "leaf_key": leaf.identity.leaf_key,
                    "family": leaf.family,
                    "direction": leaf.identity.direction,
                    "scope_ref": leaf.identity.scope_ref,
                    "generation_ref": leaf.identity.generation_ref,
                    "model_fingerprint": leaf.identity.model_fingerprint,
                    "evidence_epoch_id": leaf.identity.evidence_epoch_id,
                    "applicability": leaf.applicability.value,
                }
            )
        outcomes = []
        for outcome in self.outcomes:
            outcomes.append(
                {
                    "identity": outcome.identity.value,
                    "status": outcome.status.value,
                    "source_ref": outcome.source_ref,
                    "canonical_artifact_ref": outcome.canonical_artifact_ref,
                    "evidence_refs": list(outcome.evidence_refs),
                    "blocker_refs": list(outcome.blocker_refs),
                    "analysis_basis_ref": outcome.analysis_basis_ref,
                    "dependency_refs": list(outcome.dependency_refs),
                    "deferred_owner": outcome.deferred_owner,
                }
            )
        return {
            "schema_version": "supported_column_denominator.a38.v1",
            "artifact_type": "SUPPORTED_COLUMN_DENOMINATOR",
            "expected_column_count": self.expected_column_count,
            "expected_leaf_count": self.expected_leaf_count,
            "expected_instance_count": self.expected_instance_count,
            "outcome_counts": dict(self.outcome_counts),
            "silent_missing_count": self.silent_missing_count,
            "duplicate_count": self.duplicate_count,
            "orphan_count": self.orphan_count,
            "population_reconciled": self.population_reconciled,
            "fully_resolved": self.fully_resolved,
            "expected_leaves": expected,
            "outcomes": outcomes,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ) + "\n"


@dataclass(frozen=True, slots=True)
class _LeafSpec:
    leaf_key: str
    family: str
    direction: str | None = None


_BASE_SPECS = (
    _LeafSpec("COLUMN_IDENTITY_TOPOLOGY", "COLUMN_IDENTITY_TOPOLOGY"),
    _LeafSpec("SECTION_GEOMETRY_APPLICABILITY", "SECTION_GEOMETRY_APPLICABILITY"),
    _LeafSpec("FACTUAL_MATERIAL_DESIGN_BASIS", "FACTUAL_MATERIAL_DESIGN_BASIS"),
    _LeafSpec("ACTION_COMBO_QUALIFICATION", "ACTION_COMBO_QUALIFICATION"),
    _LeafSpec("B4B_ANALYSIS_STATE", "B4B_ANALYSIS_STATE"),
    _LeafSpec("B5_ANALYSIS_RESULT_GENERATION", "B5_ANALYSIS_RESULT_GENERATION"),
    _LeafSpec("EXACT_CONCURRENT_COLUMN_DEMAND_POPULATION", "EXACT_CONCURRENT_COLUMN_DEMAND_POPULATION"),
    _LeafSpec("GEOMETRY_CHECKS", "GEOMETRY_CHECKS"),
    _LeafSpec("TBDY_AXIAL", "TBDY_AXIAL"),
    _LeafSpec("TS500_AXIAL", "TS500_AXIAL"),
    _LeafSpec("SHORT_COLUMN_APPLICABILITY", "SHORT_COLUMN_APPLICABILITY"),
    _LeafSpec("MINIMUM_ECCENTRICITY", "MINIMUM_ECCENTRICITY"),
    _LeafSpec("STORY_RELATIVE_TRANSLATION_SWAY", "STORY_RELATIVE_TRANSLATION_SWAY"),
    _LeafSpec("GLOBAL_TO_LOCAL_M2_M3_BINDING", "GLOBAL_TO_LOCAL_M2_M3_BINDING"),
    _LeafSpec("END_RESTRAINT_ALPHA", "END_RESTRAINT_ALPHA"),
    _LeafSpec("EFFECTIVE_LENGTH_K_LK", "EFFECTIVE_LENGTH_K_LK"),
    _LeafSpec("SAME_STATE_M1_M2", "SAME_STATE_M1_M2"),
    _LeafSpec("SLENDERNESS", "SLENDERNESS"),
    _LeafSpec("MOMENT_MAGNIFICATION_OR_REANALYSIS", "MOMENT_MAGNIFICATION_OR_REANALYSIS"),
    _LeafSpec("CANONICAL_A23_DESIGN_DEMAND", "CANONICAL_A23_DESIGN_DEMAND"),
    _LeafSpec("FND_COL_2_READINESS", "FND_COL_2_READINESS"),
    _LeafSpec("DESIGN_STATE_IDENTITY", "DESIGN_STATE_IDENTITY"),
    _LeafSpec("B6_CONTROLLED_DESIGN", "B6_CONTROLLED_DESIGN"),
    _LeafSpec("DESIGN_RESULT_IDENTITY_LINEAGE", "DESIGN_RESULT_IDENTITY_LINEAGE"),
    _LeafSpec("ETABS_REQUIRED_REBAR", "ETABS_REQUIRED_REBAR"),
    _LeafSpec("FND_COL_1_LONGITUDINAL_REQUIREMENT", "FND_COL_1_LONGITUDINAL_REQUIREMENT"),
    _LeafSpec("LONGITUDINAL_LAYOUT", "LONGITUDINAL_LAYOUT"),
    _LeafSpec("PMM_SECTION_CAPACITY", "PMM_SECTION_CAPACITY"),
    _LeafSpec("CANDIDATE_ADEQUACY", "CANDIDATE_ADEQUACY"),
    _LeafSpec("DETERMINISTIC_REBAR_SELECTION", "DETERMINISTIC_REBAR_SELECTION"),
    _LeafSpec("ENGINE_SELECTED_REBAR", "ENGINE_SELECTED_REBAR"),
    _LeafSpec("LONGITUDINAL_DETAILING", "LONGITUDINAL_DETAILING"),
    _LeafSpec("TRANSVERSE_CONFINEMENT", "TRANSVERSE_CONFINEMENT"),
    _LeafSpec("HIGH_SHEAR_APPLICABILITY", "HIGH_LIMITED_SHEAR_APPLICABILITY"),
    _LeafSpec("LIMITED_SHEAR_APPLICABILITY", "HIGH_LIMITED_SHEAR_APPLICABILITY"),
    _LeafSpec("SHORT_COLUMN_FULL_LENGTH_CONFINEMENT", "SHORT_COLUMN_FULL_LENGTH_CONFINEMENT"),
    _LeafSpec("SCWB", "CROSS_DOMAIN"),
    _LeafSpec("BEAM_COLUMN_JOINT", "CROSS_DOMAIN"),
)

_DIRECTIONAL_SPECS = tuple(
    _LeafSpec(key, family, direction)
    for direction in ("V2", "V3")
    for key, family in (
        ("SHORT_COLUMN_SHEAR", "SHORT_COLUMN_SHEAR"),
        ("P7_OR_LIMITED_FINAL_SHEAR", "P7_FINAL_SHEAR"),
        ("VC", "VC_ASW_VR"),
        ("ASW_D_MAPPING", "VC_ASW_VR"),
        ("VE_LE_VR", "VC_ASW_VR"),
    )
)

_ALL_SPECS = _BASE_SPECS + _DIRECTIONAL_SPECS


def canonical_column_leaf_source_ref(
    identity: ColumnDenominatorLeafIdentity,
) -> str:
    if not isinstance(identity, ColumnDenominatorLeafIdentity):
        raise TypeError("identity must be ColumnDenominatorLeafIdentity")
    return f"{identity.value}:ColumnLeafOutcome"


def compose_supported_column_denominator(
    columns: Sequence[object],
    *,
    short_column_contexts: Sequence[object] = (),
) -> SupportedColumnDenominator:
    """Compose exact A38 truth from existing Column artifacts.

    The caller supplies the actual produced Column artifact population, never a
    separate authoritative component list.  Short-column contexts are reviewed
    application dependencies already used by A37; absence is represented as
    explicit unresolved, never as ordinary-column proof.
    """
    frozen_columns = tuple(columns)
    if not frozen_columns:
        raise ColumnDenominatorError("Column artifact population must be nonempty")

    by_component: dict[str, object] = {}
    for column in frozen_columns:
        component = _text(getattr(column, "component_id", None), "column.component_id")
        if component in by_component:
            raise ColumnDenominatorError("duplicate Column artifact component identity")
        _text(getattr(column, "model_fingerprint", None), "column.model_fingerprint")
        _text(getattr(column, "evidence_epoch_id", None), "column.evidence_epoch_id")
        by_component[component] = column

    short_by_component: dict[str, object] = {}
    for context in tuple(short_column_contexts):
        component = _text(
            getattr(context, "component_id", None),
            "short_column_context.component_id",
        )
        if component in short_by_component:
            raise ColumnDenominatorError("duplicate short-column context component")
        if component not in by_component:
            raise ColumnDenominatorError(
                "orphan short-column context outside exact Column population"
            )
        short_by_component[component] = context

    expected: list[ColumnExpectedLeaf] = []
    outcomes: list[ColumnLeafOutcome] = []

    for component_id in sorted(by_component):
        column = by_component[component_id]
        _compose_component(
            column,
            short_context=short_by_component.get(component_id),
            expected=expected,
            outcomes=outcomes,
        )

    return SupportedColumnDenominator(expected, outcomes)


def _compose_component(
    column: object,
    *,
    short_context: object | None,
    expected: list[ColumnExpectedLeaf],
    outcomes: list[ColumnLeafOutcome],
) -> None:
    component = _text(getattr(column, "component_id", None), "component_id")
    model = _text(getattr(column, "model_fingerprint", None), "model_fingerprint")
    epoch = _text(getattr(column, "evidence_epoch_id", None), "evidence_epoch_id")
    blockers = _refs(getattr(column, "blockers", ()) or ())
    column_status = str(getattr(column, "status", "UNRESOLVED"))

    execution = getattr(column, "fnd_col_2_execution", None)
    readiness = None if execution is None else getattr(execution, "readiness", None)
    readiness_binding = getattr(column, "readiness_binding", None)
    readiness_refs = _refs(
        (
            *tuple(getattr(readiness, "source_refs", ()) or ()),
            *tuple(getattr(readiness_binding, "provenance_refs", ()) or ()),
            *(
                ()
                if readiness_binding is None
                else (getattr(readiness_binding, "readiness_ref", None),)
            ),
        )
    )
    readiness_outcome = _readiness_status(readiness, column_status, blockers)

    runtime = getattr(column, "longitudinal_runtime", None)
    layout = getattr(column, "layout_authority", None)
    if layout is None and runtime is not None:
        layout = getattr(runtime, "layout_authority", None)
    selection = getattr(column, "longitudinal_selection", None)
    if selection is None and runtime is not None:
        selection = getattr(runtime, "selection", None)
    detailing = None if runtime is None else getattr(runtime, "detailing", None)
    transverse = getattr(column, "transverse_confinement", None)
    p7 = getattr(column, "column_shear_p7", None)
    limited = getattr(column, "column_shear_limited", None)

    design_state = getattr(column, "design_state", None)
    controlled = getattr(column, "controlled_design_result", None)
    design_result = getattr(column, "design_result_identity", None)
    design_lineage = getattr(column, "design_lineage", None)

    design_generation_ref = (
        None if controlled is None else getattr(controlled, "design_generation_ref", None)
    )
    analysis_result_ref = (
        None
        if design_state is None
        else getattr(design_state, "parent_analysis_result_ref", None)
    )

    bound_basis = None if runtime is None else getattr(runtime, "bound_design_basis", None)
    high_applies = None if bound_basis is None else getattr(bound_basis, "high_ductility_applies", None)
    limited_applies = (
        None if bound_basis is None else getattr(bound_basis, "limited_ductility_applies", None)
    )
    short_applies = (
        None
        if short_context is None
        else getattr(short_context, "short_column_applies", None)
    )

    def add(
        leaf_key: str,
        family: str,
        status: ColumnLeafOutcomeStatus,
        *,
        direction: str | None = None,
        applicability: ColumnLeafApplicability = ColumnLeafApplicability.MANDATORY,
        evidence_refs: Iterable[object] = (),
        blocker_refs: Iterable[object] = (),
        canonical_artifact_ref: object | None = None,
        analysis_basis_ref: object | None = None,
        dependency_refs: Iterable[object] = (),
        deferred_owner: str | None = None,
        generation_ref: object | None = None,
    ) -> None:
        identity = ColumnDenominatorLeafIdentity.build(
            component_id=component,
            leaf_key=leaf_key,
            model_fingerprint=model,
            evidence_epoch_id=epoch,
            direction=direction,
            scope_ref=component,
            generation_ref=_optional_text_or_none(generation_ref),
        )
        expected.append(
            ColumnExpectedLeaf(
                identity=identity,
                family=family,
                applicability=applicability,
            )
        )
        outcomes.append(
            ColumnLeafOutcome(
                identity=identity,
                status=status,
                source_ref=canonical_column_leaf_source_ref(identity),
                canonical_artifact_ref=_optional_text_or_none(canonical_artifact_ref),
                evidence_refs=_refs(evidence_refs),
                blocker_refs=_refs(blocker_refs),
                analysis_basis_ref=_optional_text_or_none(analysis_basis_ref),
                dependency_refs=_refs(dependency_refs),
                deferred_owner=deferred_owner,
            )
        )

    # A1-A17 factual / analysis chain.  FND2 is a lawful downstream proof that
    # these already ran in the public A5 causal spine; it is not used to omit
    # their denominator identities.
    identity_refs = (model, epoch)
    add(
        "COLUMN_IDENTITY_TOPOLOGY",
        "COLUMN_IDENTITY_TOPOLOGY",
        ColumnLeafOutcomeStatus.EXECUTED_PASS,
        evidence_refs=identity_refs,
        canonical_artifact_ref=component,
    )
    upstream = (
        ColumnLeafOutcomeStatus.EXECUTED_PASS
        if execution is not None
        else _column_fallback(column_status)
    )
    for key, family in (
        ("SECTION_GEOMETRY_APPLICABILITY", "SECTION_GEOMETRY_APPLICABILITY"),
        ("B4B_ANALYSIS_STATE", "B4B_ANALYSIS_STATE"),
        ("B5_ANALYSIS_RESULT_GENERATION", "B5_ANALYSIS_RESULT_GENERATION"),
        ("GEOMETRY_CHECKS", "GEOMETRY_CHECKS"),
    ):
        add(
            key,
            family,
            upstream,
            evidence_refs=readiness_refs,
            blocker_refs=() if upstream is ColumnLeafOutcomeStatus.EXECUTED_PASS else blockers,
            canonical_artifact_ref=analysis_result_ref if key == "B5_ANALYSIS_RESULT_GENERATION" else None,
            generation_ref=analysis_result_ref if key == "B5_ANALYSIS_RESULT_GENERATION" else None,
        )

    # Material/basis and combo qualification are retained by longitudinal runtime.
    if runtime is not None and bound_basis is not None:
        add(
            "FACTUAL_MATERIAL_DESIGN_BASIS",
            "FACTUAL_MATERIAL_DESIGN_BASIS",
            ColumnLeafOutcomeStatus.EXECUTED_PASS,
            evidence_refs=_object_refs(bound_basis),
            canonical_artifact_ref=getattr(bound_basis, "binding_ref", None),
        )
    else:
        add(
            "FACTUAL_MATERIAL_DESIGN_BASIS",
            "FACTUAL_MATERIAL_DESIGN_BASIS",
            _downstream_block(column_status),
            blocker_refs=blockers or ("LONGITUDINAL_RUNTIME_NOT_AVAILABLE",),
        )

    combo = None if runtime is None else getattr(runtime, "combo_reconciliation", None)
    if combo is not None and bool(getattr(combo, "reconciled", False)):
        add(
            "ACTION_COMBO_QUALIFICATION",
            "ACTION_COMBO_QUALIFICATION",
            ColumnLeafOutcomeStatus.EXECUTED_PASS,
            evidence_refs=_object_refs(combo),
        )
    else:
        add(
            "ACTION_COMBO_QUALIFICATION",
            "ACTION_COMBO_QUALIFICATION",
            _downstream_block(column_status),
            evidence_refs=_object_refs(combo),
            blocker_refs=blockers or ("COMBO_QUALIFICATION_NOT_AVAILABLE",),
        )

    demand_states = tuple(getattr(column, "a23_demand_states", ()) or ())
    if not demand_states and readiness is not None:
        demand_states = tuple(getattr(readiness, "demand_states", ()) or ())
    demand_status = (
        ColumnLeafOutcomeStatus.EXECUTED_PASS if demand_states else readiness_outcome
    )
    add(
        "EXACT_CONCURRENT_COLUMN_DEMAND_POPULATION",
        "EXACT_CONCURRENT_COLUMN_DEMAND_POPULATION",
        demand_status,
        evidence_refs=(
            *readiness_refs,
            *tuple(
                getattr(item, "source_identity", None)
                for item in demand_states
            ),
        ),
        blocker_refs=() if demand_states else blockers,
    )

    # VS5 dual axial is physically executed in the A36 production materializer.
    # Project exact retained VS5 formal-result / F0 closure truth.
    vs5 = getattr(column, "column_axial_vs5", None)
    for key, rule_id, formal_result, default_applicability in (
        (
            "TBDY_AXIAL",
            COLUMN_TBDY_AXIAL_RULE_ID,
            None if vs5 is None else getattr(vs5, "tbdy_result", None),
            ColumnLeafApplicability.CONDITIONAL,
        ),
        (
            "TS500_AXIAL",
            COLUMN_TS500_AXIAL_RULE_ID,
            None if vs5 is None else getattr(vs5, "ts500_result", None),
            ColumnLeafApplicability.MANDATORY,
        ),
    ):
        if vs5 is None:
            axial_outcome = _downstream_block(column_status)
            axial_applicability = default_applicability
            axial_refs = ()
            axial_blockers = blockers or ("VS5_COLUMN_AXIAL_RUN_NOT_RETAINED",)
        else:
            (
                axial_outcome,
                axial_applicability,
                axial_refs,
                axial_blockers,
            ) = _f0_check_outcome(
                assessment=getattr(vs5, "assessment", None),
                result=formal_result,
                rule_id=rule_id,
                component_id=component,
                default_applicability=default_applicability,
            )
        add(
            key,
            key,
            axial_outcome,
            applicability=axial_applicability,
            evidence_refs=axial_refs,
            blocker_refs=axial_blockers,
            canonical_artifact_ref=(
                None if formal_result is None else formal_result.check_id
            ),
        )

    # Short-column applicability is a reviewed A37 dependency and absence is
    # explicit unresolved, never ordinary-column proof.
    if short_context is None or type(short_applies) is not bool:
        add(
            "SHORT_COLUMN_APPLICABILITY",
            "SHORT_COLUMN_APPLICABILITY",
            ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED,
            blocker_refs=("SHORT_COLUMN_APPLICABILITY_NOT_REVIEWED",),
        )
    else:
        add(
            "SHORT_COLUMN_APPLICABILITY",
            "SHORT_COLUMN_APPLICABILITY",
            ColumnLeafOutcomeStatus.EXECUTED_PASS,
            evidence_refs=_object_refs(short_context),
            canonical_artifact_ref=(
                f"SHORT_COLUMN_APPLIES:{str(short_applies).upper()}"
            ),
        )

    # A18-A23 are retained inside the typed FND2 readiness artifact.
    min_ecc = None if readiness is None else getattr(readiness, "minimum_eccentricity", None)
    add(
        "MINIMUM_ECCENTRICITY",
        "MINIMUM_ECCENTRICITY",
        _object_or_readiness(min_ecc, readiness_outcome),
        evidence_refs=(*readiness_refs, *_object_refs(min_ecc)),
        blocker_refs=() if min_ecc is not None else blockers,
    )

    basis = None if readiness is None else getattr(readiness, "slenderness_basis", None)
    state_slenderness = (
        () if readiness is None else tuple(getattr(readiness, "state_slenderness", ()) or ())
    )
    basis_available = basis is not None or bool(state_slenderness)
    basis_status = (
        ColumnLeafOutcomeStatus.EXECUTED_PASS if basis_available else readiness_outcome
    )
    for key, family in (
        ("STORY_RELATIVE_TRANSLATION_SWAY", "STORY_RELATIVE_TRANSLATION_SWAY"),
        ("GLOBAL_TO_LOCAL_M2_M3_BINDING", "GLOBAL_TO_LOCAL_M2_M3_BINDING"),
        ("END_RESTRAINT_ALPHA", "END_RESTRAINT_ALPHA"),
        ("EFFECTIVE_LENGTH_K_LK", "EFFECTIVE_LENGTH_K_LK"),
        ("SAME_STATE_M1_M2", "SAME_STATE_M1_M2"),
    ):
        add(
            key,
            family,
            basis_status,
            evidence_refs=(*readiness_refs, *_object_refs(basis)),
            blocker_refs=() if basis_available else blockers,
        )

    slenderness = None if readiness is None else getattr(readiness, "slenderness", None)
    slenderness_available = slenderness is not None or bool(state_slenderness)
    add(
        "SLENDERNESS",
        "SLENDERNESS",
        (
            _object_status(slenderness)
            if slenderness is not None
            else ColumnLeafOutcomeStatus.EXECUTED_PASS
            if state_slenderness
            else readiness_outcome
        ),
        evidence_refs=(
            *readiness_refs,
            *_object_refs(slenderness),
            *tuple(ref for item in state_slenderness for ref in _object_refs(item)),
        ),
        blocker_refs=() if slenderness_available else blockers,
    )

    second_order = (
        None if readiness is None else getattr(readiness, "second_order_treatment", None)
    )
    add(
        "MOMENT_MAGNIFICATION_OR_REANALYSIS",
        "MOMENT_MAGNIFICATION_OR_REANALYSIS",
        _second_order_status(second_order, readiness_outcome),
        evidence_refs=readiness_refs,
        blocker_refs=blockers if readiness_outcome is not ColumnLeafOutcomeStatus.EXECUTED_PASS else (),
        analysis_basis_ref=(
            None if readiness is None else getattr(readiness, "analysis_basis_status", None)
        ),
    )

    add(
        "CANONICAL_A23_DESIGN_DEMAND",
        "CANONICAL_A23_DESIGN_DEMAND",
        demand_status,
        evidence_refs=readiness_refs,
        blocker_refs=() if demand_states else blockers,
    )
    add(
        "FND_COL_2_READINESS",
        "FND_COL_2_READINESS",
        readiness_outcome,
        evidence_refs=readiness_refs,
        blocker_refs=tuple(getattr(readiness, "blocked_items", ()) or ()) or blockers,
        canonical_artifact_ref=(
            None if readiness_binding is None else getattr(readiness_binding, "readiness_ref", None)
        ),
        analysis_basis_ref=(
            None if readiness is None else getattr(readiness, "analysis_basis_status", None)
        ),
    )

    # B6 lineage.
    if design_state is not None:
        add(
            "DESIGN_STATE_IDENTITY",
            "DESIGN_STATE_IDENTITY",
            ColumnLeafOutcomeStatus.EXECUTED_PASS,
            evidence_refs=_object_refs(design_state),
            canonical_artifact_ref=getattr(design_state, "identity_ref", None),
            generation_ref=analysis_result_ref,
        )
    else:
        add(
            "DESIGN_STATE_IDENTITY",
            "DESIGN_STATE_IDENTITY",
            _downstream_block(column_status),
            blocker_refs=blockers or ("DESIGN_STATE_IDENTITY_NOT_AVAILABLE",),
        )

    if controlled is not None:
        add(
            "B6_CONTROLLED_DESIGN",
            "B6_CONTROLLED_DESIGN",
            ColumnLeafOutcomeStatus.EXECUTED_PASS,
            evidence_refs=_object_refs(controlled),
            canonical_artifact_ref=getattr(controlled, "design_attempt_ref", None),
            generation_ref=design_generation_ref,
        )
    else:
        add(
            "B6_CONTROLLED_DESIGN",
            "B6_CONTROLLED_DESIGN",
            _downstream_block(column_status),
            blocker_refs=blockers or ("CONTROLLED_B6_DESIGN_NOT_AVAILABLE",),
        )

    if (
        design_result is not None
        and design_lineage is not None
        and bool(getattr(design_lineage, "qualified", False))
    ):
        add(
            "DESIGN_RESULT_IDENTITY_LINEAGE",
            "DESIGN_RESULT_IDENTITY_LINEAGE",
            ColumnLeafOutcomeStatus.EXECUTED_PASS,
            evidence_refs=(
                *_object_refs(design_result),
                *_object_refs(design_lineage),
            ),
            canonical_artifact_ref=getattr(design_result, "identity_ref", None),
            generation_ref=design_generation_ref,
        )
    else:
        add(
            "DESIGN_RESULT_IDENTITY_LINEAGE",
            "DESIGN_RESULT_IDENTITY_LINEAGE",
            _downstream_block(column_status),
            blocker_refs=blockers or ("DESIGN_RESULT_LINEAGE_NOT_AVAILABLE",),
        )

    # A34-A35 longitudinal.
    contract = None if selection is None else getattr(selection, "selection_contract", None)
    requirement_ids = tuple(getattr(contract, "etabs_requirement_ids", ()) or ())
    add(
        "ETABS_REQUIRED_REBAR",
        "ETABS_REQUIRED_REBAR",
        (
            ColumnLeafOutcomeStatus.EXECUTED_PASS
            if requirement_ids
            else _downstream_block(column_status)
        ),
        evidence_refs=(*_object_refs(contract), *requirement_ids),
        blocker_refs=() if requirement_ids else blockers or ("ETABS_REQUIRED_REBAR_NOT_AVAILABLE",),
        generation_ref=design_generation_ref,
    )

    requirement = None if layout is None else getattr(layout, "requirement", None)
    add(
        "FND_COL_1_LONGITUDINAL_REQUIREMENT",
        "FND_COL_1_LONGITUDINAL_REQUIREMENT",
        (
            ColumnLeafOutcomeStatus.EXECUTED_PASS
            if requirement is not None
            else _downstream_block(column_status)
        ),
        evidence_refs=_object_refs(requirement),
        blocker_refs=() if requirement is not None else blockers or ("FND_COL_1_REQUIREMENT_NOT_AVAILABLE",),
    )

    layout_status = getattr(layout, "status", None)
    if layout is None:
        layout_outcome = _downstream_block(column_status)
    elif layout_status == "PROVEN":
        layout_outcome = ColumnLeafOutcomeStatus.EXECUTED_PASS
    elif layout_status == "NO_REGULATORILY_ELIGIBLE_LAYOUT":
        layout_outcome = ColumnLeafOutcomeStatus.EXECUTED_FAIL
    else:
        layout_outcome = _object_status(layout)
    add(
        "LONGITUDINAL_LAYOUT",
        "LONGITUDINAL_LAYOUT",
        layout_outcome,
        evidence_refs=_object_refs(layout),
        blocker_refs=() if layout is not None else blockers,
    )

    adequacy = None if selection is None else getattr(selection, "adequacy_population", None)
    pmm_refs = tuple(
        ref
        for item in tuple(getattr(adequacy, "candidate_assessments", ()) or ())
        for ref in tuple(getattr(item, "pmm_decision_ids", ()) or ())
    )
    if adequacy is None:
        pmm_status = _downstream_block(column_status)
    elif bool(getattr(adequacy, "complete", False)):
        pmm_status = ColumnLeafOutcomeStatus.EXECUTED_PASS
    else:
        pmm_status = ColumnLeafOutcomeStatus.BLOCKED
    add(
        "PMM_SECTION_CAPACITY",
        "PMM_SECTION_CAPACITY",
        pmm_status,
        evidence_refs=(*_object_refs(adequacy), *pmm_refs),
        blocker_refs=() if adequacy is not None else blockers,
    )

    if adequacy is None:
        adequacy_status = _downstream_block(column_status)
    elif int(getattr(adequacy, "unresolved_candidate_count", 0) or 0) > 0:
        adequacy_status = ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
    elif not bool(getattr(adequacy, "complete", False)):
        adequacy_status = ColumnLeafOutcomeStatus.BLOCKED
    elif int(getattr(adequacy, "adequate_candidate_count", 0) or 0) > 0:
        adequacy_status = ColumnLeafOutcomeStatus.EXECUTED_PASS
    else:
        adequacy_status = ColumnLeafOutcomeStatus.EXECUTED_FAIL
    add(
        "CANDIDATE_ADEQUACY",
        "CANDIDATE_ADEQUACY",
        adequacy_status,
        evidence_refs=_object_refs(adequacy),
        blocker_refs=tuple(getattr(selection, "blockers", ()) or ()) if selection is not None else blockers,
    )

    selected = bool(getattr(selection, "selected", False)) if selection is not None else False
    selection_status_text = None if selection is None else str(getattr(selection, "status", ""))
    if selected:
        selection_outcome = ColumnLeafOutcomeStatus.EXECUTED_PASS
    elif selection_status_text == "NO_PROVEN_ADEQUATE_CANDIDATE":
        selection_outcome = ColumnLeafOutcomeStatus.EXECUTED_FAIL
    elif "UNRESOLVED" in (selection_status_text or ""):
        selection_outcome = ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
    else:
        selection_outcome = _downstream_block(column_status)
    add(
        "DETERMINISTIC_REBAR_SELECTION",
        "DETERMINISTIC_REBAR_SELECTION",
        selection_outcome,
        evidence_refs=_object_refs(selection),
        blocker_refs=tuple(getattr(selection, "blockers", ()) or ()) if selection is not None else blockers,
    )

    selected_rebar = None if selection is None else getattr(selection, "selected_rebar", None)
    add(
        "ENGINE_SELECTED_REBAR",
        "ENGINE_SELECTED_REBAR",
        (
            ColumnLeafOutcomeStatus.EXECUTED_PASS
            if selected_rebar is not None and selected
            else selection_outcome
        ),
        evidence_refs=_object_refs(selected_rebar),
        blocker_refs=tuple(getattr(selection, "blockers", ()) or ()) if not selected else (),
        canonical_artifact_ref=(
            None if selected_rebar is None else getattr(selected_rebar, "selected_rebar_ref", None)
        ),
    )

    detail_status = None if detailing is None else str(getattr(detailing, "status", ""))
    if detailing is None:
        detail_outcome = _downstream_block(column_status)
    elif detail_status == "DETAILING_PROVEN":
        detail_outcome = ColumnLeafOutcomeStatus.EXECUTED_PASS
    elif detail_status == "FINAL_DETAILING_REQUIRED":
        detail_outcome = ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
    else:
        detail_outcome = _object_status(detailing)
    add(
        "LONGITUDINAL_DETAILING",
        "LONGITUDINAL_DETAILING",
        detail_outcome,
        evidence_refs=_object_refs(detailing),
        blocker_refs=tuple(getattr(detailing, "unresolved_items", ()) or ()),
    )

    # A36 aggregate transverse result.
    add(
        "TRANSVERSE_CONFINEMENT",
        "TRANSVERSE_CONFINEMENT",
        (
            _aggregate_checks(tuple(getattr(transverse, "checks", ()) or ()))
            if transverse is not None
            else _downstream_block(column_status)
        ),
        evidence_refs=_object_refs(transverse),
        blocker_refs=tuple(getattr(transverse, "blockers", ()) or ()) if transverse is not None else blockers,
    )

    # Ductility branch applicability: inactive branch is positively PNA only
    # when the reviewed bound design basis says so.
    for key, applies in (
        ("HIGH_SHEAR_APPLICABILITY", high_applies),
        ("LIMITED_SHEAR_APPLICABILITY", limited_applies),
    ):
        if applies is True:
            applicability = ColumnLeafApplicability.CONDITIONAL
            status = ColumnLeafOutcomeStatus.EXECUTED_PASS
        elif applies is False:
            applicability = ColumnLeafApplicability.PROVEN_NOT_APPLICABLE
            status = ColumnLeafOutcomeStatus.PROVEN_NOT_APPLICABLE
        else:
            applicability = ColumnLeafApplicability.CONDITIONAL
            status = ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
        add(
            key,
            "HIGH_LIMITED_SHEAR_APPLICABILITY",
            status,
            applicability=applicability,
            evidence_refs=_object_refs(bound_basis),
            blocker_refs=() if applies is not None else ("DUCTILITY_APPLICABILITY_NOT_PROVEN",),
        )

    # Directional shear leaves.  The A37 high/short path exposes P7 while the
    # ordinary LIMITED path exposes the dedicated 7.7.5 run.
    transverse_checks = tuple(getattr(transverse, "checks", ()) or ())
    transverse_by_id = {
        getattr(item, "check_id", ""): item
        for item in transverse_checks
        if isinstance(item, CheckResult)
    }
    for direction, transverse_direction in (("V2", "DIR2"), ("V3", "DIR3")):
        short_classification = (
            ColumnLeafApplicability.PROVEN_NOT_APPLICABLE
            if short_applies is False
            else ColumnLeafApplicability.CONDITIONAL
        )
        if short_applies is False:
            short_shear_status = ColumnLeafOutcomeStatus.PROVEN_NOT_APPLICABLE
            short_refs: tuple[str, ...] = ()
        elif short_applies is None:
            short_shear_status = ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
            short_refs = ()
        else:
            direction_run = _shear_direction(p7, direction)
            short_shear_status = (
                _shear_run_status(direction_run)
                if direction_run is not None
                else _downstream_block(column_status)
            )
            short_refs = _object_refs(direction_run)
        add(
            "SHORT_COLUMN_SHEAR",
            "SHORT_COLUMN_SHEAR",
            short_shear_status,
            direction=direction,
            applicability=short_classification,
            evidence_refs=short_refs,
            blocker_refs=(
                ()
                if short_shear_status
                in {
                    ColumnLeafOutcomeStatus.EXECUTED_PASS,
                    ColumnLeafOutcomeStatus.EXECUTED_FAIL,
                    ColumnLeafOutcomeStatus.PROVEN_NOT_APPLICABLE,
                }
                else blockers or ("SHORT_COLUMN_SHEAR_NOT_RESOLVED",)
            ),
        )

        branch_run = _shear_direction(p7, direction)
        if branch_run is None:
            branch_run = _shear_direction(limited, direction)
        branch_status = (
            _shear_run_status(branch_run)
            if branch_run is not None
            else _downstream_block(column_status)
        )
        add(
            "P7_OR_LIMITED_FINAL_SHEAR",
            "P7_FINAL_SHEAR",
            branch_status,
            direction=direction,
            evidence_refs=_object_refs(branch_run),
            blocker_refs=() if branch_run is not None else blockers,
        )

        final_check = transverse_by_id.get(
            f"COL_FINAL_SHEAR_VR_{transverse_direction}"
        )
        final_status = (
            _check_status(final_check)
            if final_check is not None
            else _downstream_block(column_status)
        )
        evidence = () if final_check is None else _check_evidence(final_check)
        add(
            "VE_LE_VR",
            "VC_ASW_VR",
            final_status,
            direction=direction,
            evidence_refs=evidence,
            blocker_refs=() if final_check is not None else blockers,
            canonical_artifact_ref=(
                None if final_check is None else final_check.check_id
            ),
        )

        vc_marker = f"QUALIFIED_VC:{direction}:"
        vc_resolved = any(ref.startswith(vc_marker) for ref in evidence)
        vc_status = (
            ColumnLeafOutcomeStatus.EXECUTED_PASS
            if vc_resolved
            else (
                ColumnLeafOutcomeStatus.NO_DATA
                if final_status is ColumnLeafOutcomeStatus.NO_DATA
                else ColumnLeafOutcomeStatus.BLOCKED
            )
        )
        add(
            "VC",
            "VC_ASW_VR",
            vc_status,
            direction=direction,
            evidence_refs=tuple(ref for ref in evidence if "VC" in ref or "Nd" in ref),
            blocker_refs=() if vc_resolved else ("QUALIFIED_VC_NOT_BOUND",),
        )

        mapping_marker = f"LOCAL_SHEAR_DIRECTION:{direction}"
        mapping_resolved = any(
            mapping_marker == ref or ref.endswith(mapping_marker)
            for ref in evidence
        )
        mapping_status = (
            ColumnLeafOutcomeStatus.EXECUTED_PASS
            if mapping_resolved
            else (
                ColumnLeafOutcomeStatus.NO_DATA
                if final_status is ColumnLeafOutcomeStatus.NO_DATA
                else ColumnLeafOutcomeStatus.BLOCKED
            )
        )
        add(
            "ASW_D_MAPPING",
            "VC_ASW_VR",
            mapping_status,
            direction=direction,
            evidence_refs=tuple(
                ref
                for ref in evidence
                if "LOCAL_SHEAR_DIRECTION" in ref
                or "GET_REBAR_COLUMN_LOCAL_TIE_LEGS" in ref
                or "effective" in ref.lower()
            ),
            blocker_refs=() if mapping_resolved else ("ASW_D_DIRECTION_MAPPING_NOT_PROVEN",),
        )

    short_full_check = transverse_by_id.get(
        "COL_SHORT_COLUMN_FULL_LENGTH_CONFINEMENT"
    )
    if short_applies is False:
        add(
            "SHORT_COLUMN_FULL_LENGTH_CONFINEMENT",
            "SHORT_COLUMN_FULL_LENGTH_CONFINEMENT",
            ColumnLeafOutcomeStatus.PROVEN_NOT_APPLICABLE,
            applicability=ColumnLeafApplicability.PROVEN_NOT_APPLICABLE,
            evidence_refs=_object_refs(short_context),
        )
    elif short_applies is None:
        add(
            "SHORT_COLUMN_FULL_LENGTH_CONFINEMENT",
            "SHORT_COLUMN_FULL_LENGTH_CONFINEMENT",
            ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED,
            applicability=ColumnLeafApplicability.CONDITIONAL,
            blocker_refs=("SHORT_COLUMN_APPLICABILITY_NOT_REVIEWED",),
        )
    else:
        add(
            "SHORT_COLUMN_FULL_LENGTH_CONFINEMENT",
            "SHORT_COLUMN_FULL_LENGTH_CONFINEMENT",
            (
                _check_status(short_full_check)
                if short_full_check is not None
                else _downstream_block(column_status)
            ),
            applicability=ColumnLeafApplicability.CONDITIONAL,
            evidence_refs=() if short_full_check is None else _check_evidence(short_full_check),
            blocker_refs=() if short_full_check is not None else blockers,
            canonical_artifact_ref=(
                None if short_full_check is None else short_full_check.check_id
            ),
        )

    # Cross-domain leaves are explicit and truthful; A38 never fabricates Beam
    # or Joint authority.
    add(
        "SCWB",
        "CROSS_DOMAIN",
        ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED,
        applicability=ColumnLeafApplicability.CONDITIONAL,
        dependency_refs=("CANONICAL_BEAM_CAPACITY_AUTHORITY",),
        deferred_owner="BEAM_DOMAIN",
    )
    add(
        "BEAM_COLUMN_JOINT",
        "CROSS_DOMAIN",
        ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED,
        applicability=ColumnLeafApplicability.CONDITIONAL,
        dependency_refs=("CANONICAL_BEAM_JOINT_GEOMETRY_CAPACITY_SHEAR_AUTHORITY",),
        deferred_owner="BEAM_JOINT_DOMAIN",
    )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnDenominatorError(f"{label} must be a nonblank canonical string")
    return value


def _optional_text(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _optional_text_or_none(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _refs(values: Iterable[object]) -> tuple[str, ...]:
    refs: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            text = value.strip()
            if text not in refs:
                refs.append(text)
    return tuple(sorted(refs))


def _object_refs(value: object | None) -> tuple[str, ...]:
    if value is None:
        return ()
    refs: list[object] = []
    for name in (
        "source_refs",
        "provenance_refs",
        "review_refs",
        "evidence_refs",
    ):
        raw = getattr(value, name, ()) or ()
        if isinstance(raw, str):
            refs.append(raw)
        else:
            try:
                refs.extend(tuple(raw))
            except TypeError:
                pass
    for name in (
        "identity_ref",
        "qualification_ref",
        "binding_ref",
        "authority_binding_ref",
        "selected_rebar_ref",
        "candidate_adequacy_ref",
        "readiness_ref",
        "design_attempt_ref",
        "design_generation_ref",
    ):
        raw = getattr(value, name, None)
        if isinstance(raw, str):
            refs.append(raw)
    return _refs(refs)


def _check_evidence(result: CheckResult) -> tuple[str, ...]:
    refs: list[object] = list(result.evidence)
    refs.extend(result.messages)
    if result.code_ref:
        refs.append(result.code_ref)
    refs.append(result.check_id)
    return _refs(refs)


def _f0_check_outcome(
    *,
    assessment: object | None,
    result: CheckResult | None,
    rule_id: RuleId,
    component_id: str,
    default_applicability: ColumnLeafApplicability,
) -> tuple[
    ColumnLeafOutcomeStatus,
    ColumnLeafApplicability,
    tuple[str, ...],
    tuple[str, ...],
]:
    if result is not None:
        return (
            _check_status(result),
            default_applicability,
            _check_evidence(result),
            (),
        )

    rows = tuple(
        item
        for item in tuple(getattr(assessment, "closure_outcomes", ()) or ())
        if getattr(getattr(item, "compiled_record_ref", None), "rule_id", None) == rule_id
        and getattr(getattr(item, "compiled_record_ref", None), "scope_ref", None) == component_id
    )
    if len(rows) != 1:
        return (
            ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED,
            default_applicability,
            (),
            (f"{rule_id.value}:F0_CLOSURE_NOT_UNIQUE",),
        )

    closure = rows[0]
    status = closure.execution_status
    compiled = getattr(closure, "compiled_record_ref", None)
    refs = _refs(
        (
            getattr(closure, "formal_result_ref", None),
            None if compiled is None else compiled.value,
        )
    )
    if status is ClosureExecutionStatus.PROVEN_NOT_APPLICABLE:
        return (
            ColumnLeafOutcomeStatus.PROVEN_NOT_APPLICABLE,
            ColumnLeafApplicability.PROVEN_NOT_APPLICABLE,
            refs,
            (),
        )
    if status is ClosureExecutionStatus.BLOCKED:
        return (
            ColumnLeafOutcomeStatus.BLOCKED,
            default_applicability,
            refs,
            (f"{rule_id.value}:BLOCKED",),
        )
    if status is ClosureExecutionStatus.NO_DATA:
        return (
            ColumnLeafOutcomeStatus.NO_DATA,
            default_applicability,
            refs,
            (f"{rule_id.value}:NO_DATA",),
        )
    if status is ClosureExecutionStatus.EXECUTED:
        return (
            ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED,
            default_applicability,
            refs,
            (f"{rule_id.value}:EXECUTED_WITHOUT_FORMAL_RESULT",),
        )
    return (
        ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED,
        default_applicability,
        refs,
        (f"{rule_id.value}:{status.value}",),
    )


def _check_status(result: CheckResult | None) -> ColumnLeafOutcomeStatus:
    if result is None:
        return ColumnLeafOutcomeStatus.BLOCKED
    if not isinstance(result, CheckResult):
        raise TypeError("result must be CheckResult or None")
    if result.status is CheckStatus.OK:
        return ColumnLeafOutcomeStatus.EXECUTED_PASS
    if result.status is CheckStatus.FAIL:
        return ColumnLeafOutcomeStatus.EXECUTED_FAIL
    if result.status is CheckStatus.WARNING:
        return ColumnLeafOutcomeStatus.EXECUTED_PASS
    if result.status is CheckStatus.NO_DATA:
        return ColumnLeafOutcomeStatus.NO_DATA
    if result.status is CheckStatus.BLOCKED:
        return ColumnLeafOutcomeStatus.BLOCKED
    if result.status is CheckStatus.OUT_OF_SCOPE:
        return ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
    return ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED


def _aggregate_checks(checks: Sequence[CheckResult]) -> ColumnLeafOutcomeStatus:
    frozen = tuple(item for item in checks if isinstance(item, CheckResult))
    if not frozen:
        return ColumnLeafOutcomeStatus.BLOCKED
    statuses = {_check_status(item) for item in frozen}
    if ColumnLeafOutcomeStatus.NO_DATA in statuses:
        return ColumnLeafOutcomeStatus.NO_DATA
    if ColumnLeafOutcomeStatus.BLOCKED in statuses:
        return ColumnLeafOutcomeStatus.BLOCKED
    if ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED in statuses:
        return ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
    if ColumnLeafOutcomeStatus.EXECUTED_FAIL in statuses:
        return ColumnLeafOutcomeStatus.EXECUTED_FAIL
    return ColumnLeafOutcomeStatus.EXECUTED_PASS


def _object_status(value: object | None) -> ColumnLeafOutcomeStatus:
    if value is None:
        return ColumnLeafOutcomeStatus.BLOCKED
    if isinstance(value, CheckResult):
        return _check_status(value)
    raw = getattr(value, "status", None)
    if raw is None:
        return ColumnLeafOutcomeStatus.EXECUTED_PASS
    status = str(raw)
    if status in {
        "OK",
        "PASS",
        "PROVEN",
        "READY",
        "SELECTED",
        "QUALIFIED",
        "MATCH",
        "DETAILING_PROVEN",
        "RESOLVED",
        "NOT_REQUIRED",
        "MOMENT_MAGNIFICATION_APPLIED",
        "MOMENT_MAGNIFICATION_REQUIRED",
    }:
        return ColumnLeafOutcomeStatus.EXECUTED_PASS
    if status in {"FAIL", "FAILED", "NO_REGULATORILY_ELIGIBLE_LAYOUT"}:
        return ColumnLeafOutcomeStatus.EXECUTED_FAIL
    if status == "NO_DATA":
        return ColumnLeafOutcomeStatus.NO_DATA
    if status in {"REANALYSIS_REQUIRED", "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED"}:
        return ColumnLeafOutcomeStatus.REANALYSIS_REQUIRED
    if "UNRESOLVED" in status or status == "FINAL_DETAILING_REQUIRED":
        return ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
    if "BLOCK" in status or "NOT_AVAILABLE" in status:
        return ColumnLeafOutcomeStatus.BLOCKED
    return ColumnLeafOutcomeStatus.EXECUTED_PASS


def _object_or_readiness(
    value: object | None,
    readiness_status: ColumnLeafOutcomeStatus,
) -> ColumnLeafOutcomeStatus:
    if value is not None:
        return _object_status(value)
    return readiness_status


def _readiness_status(
    readiness: object | None,
    column_status: str,
    blockers: Sequence[str],
) -> ColumnLeafOutcomeStatus:
    if readiness is None:
        return _column_fallback(column_status)
    status = str(getattr(readiness, "status", "UNRESOLVED"))
    if status == "READY":
        return ColumnLeafOutcomeStatus.EXECUTED_PASS
    if status == "REANALYSIS_REQUIRED":
        return ColumnLeafOutcomeStatus.REANALYSIS_REQUIRED
    if status == "UNRESOLVED":
        return ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
    if status == "BLOCKED":
        return ColumnLeafOutcomeStatus.BLOCKED
    return (
        ColumnLeafOutcomeStatus.BLOCKED
        if blockers
        else ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
    )


def _second_order_status(
    second_order_treatment: object | None,
    readiness_status: ColumnLeafOutcomeStatus,
) -> ColumnLeafOutcomeStatus:
    if second_order_treatment is None:
        return readiness_status
    value = str(second_order_treatment)
    if value == "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED":
        return ColumnLeafOutcomeStatus.REANALYSIS_REQUIRED
    if value == "UNRESOLVED":
        return ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
    if value == "BLOCKED":
        return ColumnLeafOutcomeStatus.BLOCKED
    if value in {
        "NOT_REQUIRED",
        "MOMENT_MAGNIFICATION_REQUIRED",
        "MOMENT_MAGNIFICATION_APPLIED",
    }:
        return ColumnLeafOutcomeStatus.EXECUTED_PASS
    return readiness_status


def _column_fallback(column_status: str) -> ColumnLeafOutcomeStatus:
    if column_status == "REANALYSIS_REQUIRED":
        return ColumnLeafOutcomeStatus.REANALYSIS_REQUIRED
    if column_status == "UNRESOLVED":
        return ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
    if "BLOCKED" in column_status:
        return ColumnLeafOutcomeStatus.BLOCKED
    return ColumnLeafOutcomeStatus.BLOCKED


def _downstream_block(column_status: str) -> ColumnLeafOutcomeStatus:
    if column_status == "REANALYSIS_REQUIRED":
        return ColumnLeafOutcomeStatus.REANALYSIS_REQUIRED
    if column_status == "UNRESOLVED":
        return ColumnLeafOutcomeStatus.EXPLICIT_UNRESOLVED
    return ColumnLeafOutcomeStatus.BLOCKED


def _shear_direction(run: object | None, direction: str) -> object | None:
    if run is None:
        return None
    matches = tuple(
        item
        for item in tuple(getattr(run, "directions", ()) or ())
        if getattr(item, "direction", None) == direction
    )
    if len(matches) > 1:
        raise ColumnDenominatorError(
            f"duplicate shear direction {direction} in canonical run"
        )
    return matches[0] if matches else None


def _shear_run_status(direction_run: object | None) -> ColumnLeafOutcomeStatus:
    if direction_run is None:
        return ColumnLeafOutcomeStatus.BLOCKED
    results = tuple(
        item
        for item in (
            getattr(direction_run, "tbdy_brittle_result", None),
            getattr(direction_run, "ts500_web_result", None),
        )
        if isinstance(item, CheckResult)
    )
    if not results:
        return ColumnLeafOutcomeStatus.BLOCKED
    return _aggregate_checks(results)


__all__ = [
    "ColumnDenominatorError",
    "ColumnDenominatorLeafIdentity",
    "ColumnExpectedLeaf",
    "ColumnLeafApplicability",
    "ColumnLeafOutcome",
    "ColumnLeafOutcomeStatus",
    "SupportedColumnDenominator",
    "canonical_column_leaf_source_ref",
    "compose_supported_column_denominator",
]
