"""Canonical production orchestration for VS6 column design-demand states.

This module owns the engineering interpretation boundary between factual ETABS
combination/case evidence and promoted column P-M2-M3 design states. CLI tools
and report writers are adapters only and must not duplicate this logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.design.columns.combo_pattern_engine import (
    ComboPatternClassification,
    ComboPatternConstituent,
    classify_combo_pattern,
)
from tbdy_engine.design.columns.design_demand_states import (
    ComboDesignDemandBuild,
    ComboObservedSubsetVerification,
    LinearComboConstituent,
    build_linear_combo_design_demands,
    verify_observed_combo_rows_are_generated_subset,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState


@dataclass(frozen=True, slots=True)
class ColumnComboDefinition:
    name: str
    combo_type: str
    constituents: tuple[ComboPatternConstituent, ...]


@dataclass(frozen=True, slots=True)
class ColumnComboDemandResult:
    definition: ColumnComboDefinition
    classification: ComboPatternClassification
    build: ComboDesignDemandBuild | None
    verification: ComboObservedSubsetVerification | None
    status: str


@dataclass(frozen=True, slots=True)
class ColumnDesignDemandEngineResult:
    component_id: str
    status: str
    combo_results: tuple[ColumnComboDemandResult, ...]
    promoted_states: tuple[ColumnDemandState, ...]
    blocked_combo_names: tuple[str, ...]

    @property
    def combination_scope_resolved(self) -> bool:
        return self.status == "PROVEN_COLUMN_DESIGN_DEMAND_SCOPE"


class ColumnDesignDemandEngineError(ValueError):
    """Raised when factual engine inputs are malformed or internally inconsistent."""


def _case_type_map(case_demands: Sequence[ColumnDemandState]) -> dict[str, str]:
    result: dict[str, str] = {}
    for state in case_demands:
        existing = result.get(state.output_case)
        if existing is None:
            result[state.output_case] = state.case_type
        elif existing != state.case_type:
            raise ColumnDesignDemandEngineError(
                f"case {state.output_case} has conflicting factual case types: {existing} vs {state.case_type}"
            )
    return result


def _promote_supported_constituents(
    constituents: Sequence[ComboPatternConstituent],
) -> tuple[LinearComboConstituent, ...]:
    """Cross the factual-definition boundary only after pattern support is proven."""
    return tuple(
        LinearComboConstituent(
            name=item.name,
            scale_factor=item.scale_factor,
            cname_type=item.cname_type,
        )
        for item in constituents
    )


def evaluate_column_design_demands(
    *,
    component_id: str,
    definitions: Sequence[ColumnComboDefinition],
    case_demands: Sequence[ColumnDemandState],
    observed_combo_demands: Sequence[ColumnDemandState] = (),
    verify_observed_rows: bool = False,
    force_tolerance_n: float = 250.0,
    moment_tolerance_nmm: float = 250_000.0,
) -> ColumnDesignDemandEngineResult:
    """Classify combinations and promote only explicitly supported design states.

    The function is deterministic and name-blind with respect to engineering
    semantics. Combination names are identifiers only. Unsupported definitions
    remain visible as blocked combo results and prevent a fully resolved
    combination scope.
    """
    combo_defs = tuple(definitions)
    if not combo_defs:
        raise ColumnDesignDemandEngineError("at least one combination definition is required")
    if len({item.name for item in combo_defs}) != len(combo_defs):
        raise ColumnDesignDemandEngineError("combination definitions must have unique names")

    factual_case_demands = tuple(case_demands)
    if not factual_case_demands:
        raise ColumnDesignDemandEngineError("case_demands must be nonempty")
    if any(item.component_id != component_id for item in factual_case_demands):
        raise ColumnDesignDemandEngineError("case_demands contain a different component_id")

    observed = tuple(observed_combo_demands)
    if any(item.component_id != component_id for item in observed):
        raise ColumnDesignDemandEngineError("observed_combo_demands contain a different component_id")

    case_types = _case_type_map(factual_case_demands)
    results: list[ColumnComboDemandResult] = []
    promoted: list[ColumnDemandState] = []
    blocked: list[str] = []

    for definition in combo_defs:
        classification = classify_combo_pattern(
            combo_name=definition.name,
            combo_type=definition.combo_type,
            constituents=definition.constituents,
            case_types=case_types,
        )
        if not classification.supported:
            blocked.append(definition.name)
            results.append(
                ColumnComboDemandResult(
                    definition=definition,
                    classification=classification,
                    build=None,
                    verification=None,
                    status="BLOCKED_UNSUPPORTED_COMBO_PATTERN",
                )
            )
            continue

        build = build_linear_combo_design_demands(
            component_id=component_id,
            combo_name=definition.name,
            combo_type=definition.combo_type,
            constituents=_promote_supported_constituents(definition.constituents),
            case_demands=factual_case_demands,
        )
        verification: ComboObservedSubsetVerification | None = None
        status = "PROVEN_PROMOTED_DESIGN_DEMAND"
        if verify_observed_rows:
            verification = verify_observed_combo_rows_are_generated_subset(
                generated=build,
                observed_combo_demands=observed,
                force_tolerance_n=force_tolerance_n,
                moment_tolerance_nmm=moment_tolerance_nmm,
            )
            if verification.status != "PROVEN_OBSERVED_ROWS_SUBSET_OF_DESIGN_PERMUTATIONS":
                status = "BLOCKED_OBSERVED_ROW_VERIFICATION"
                blocked.append(definition.name)
            else:
                promoted.extend(build.states)
        else:
            promoted.extend(build.states)

        results.append(
            ColumnComboDemandResult(
                definition=definition,
                classification=classification,
                build=build,
                verification=verification,
                status=status,
            )
        )

    promoted.sort(key=lambda item: item.state_id)
    all_proven = not blocked and bool(promoted)
    return ColumnDesignDemandEngineResult(
        component_id=component_id,
        status="PROVEN_COLUMN_DESIGN_DEMAND_SCOPE" if all_proven else "BLOCKED_COLUMN_DESIGN_DEMAND_SCOPE",
        combo_results=tuple(results),
        promoted_states=tuple(promoted),
        blocked_combo_names=tuple(blocked),
    )


__all__ = [
    "ColumnComboDefinition",
    "ColumnComboDemandResult",
    "ColumnDesignDemandEngineError",
    "ColumnDesignDemandEngineResult",
    "evaluate_column_design_demands",
]
