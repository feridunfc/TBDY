"""Single VS-4A composition path for the cast-in-place RC baseline policy pack."""
from __future__ import annotations

from typing import Sequence

from tbdy_engine.regulatory import structural_system as ss
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    CompiledRegulatoryProgram,
    ExternalDependencyAuthority,
    PopulationCompleteness,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RegulatoryStoreSnapshot,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.sources.tbdy2018 import build_vs4a_authority_catalog
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE


def _external(
    authority_id: str,
    key,
    semantic: SemanticType,
    value: object,
    *,
    scope_ref: str,
    direction: str | None,
    grain: Grain,
    unit=UNIT_ENUM_STATE,
    dimension: PhysicalDimension = PhysicalDimension.ENUM_STATE,
    provenance_refs: Sequence[str],
) -> ExternalDependencyAuthority:
    refs = tuple(provenance_refs)
    if not refs:
        raise ValueError(f"{authority_id} requires real provenance/review refs")
    return ExternalDependencyAuthority(
        authority_id=authority_id,
        key=key,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=semantic,
        physical_dimension=dimension,
        grain=grain,
        scope_ref=scope_ref,
        direction=direction,
        unit=unit,
        availability=AvailabilityState.RESOLVED,
        population_completeness=PopulationCompleteness.FULL,
        value=value,
        provenance_refs=refs,
    )


def _directional_targets(direction: str) -> tuple[RuleScopeTarget, ...]:
    return tuple(
        RuleScopeTarget(
            rule_id=rule_id,
            grain=Grain.DIRECTION,
            scope_ref=ss.BUILDING_SCOPE,
            direction=direction,
            applicability_input=ss.DirectionalApplicabilityInput(),
            analysis_basis_status=AnalysisBasisStatus.MATCH,
        )
        for rule_id in ss.DIRECTIONAL_VS4A_RULE_IDS
    )


def _reviewed_refs(*groups: Sequence[str]) -> tuple[str, ...]:
    refs = tuple(sorted({ref for group in groups for ref in group}))
    if not refs:
        raise ValueError("reviewed input must carry real review/provenance refs")
    return refs


def compile_vs4a_program(
    *,
    declarations: ss.ReviewedOrthogonalRcSystemDeclaration,
    seismic: ss.ReviewedSeismicClassificationContext,
    analysis_assumptions: Sequence[ss.DirectionalAnalysisSystemAssumption],
    a16_contexts: Sequence[ss.A16SpecialContext] = (),
) -> CompiledRegulatoryProgram:
    """Compile one strict F0/F0.9 VS-4A program from reviewed inputs only."""

    if not isinstance(declarations, ss.ReviewedOrthogonalRcSystemDeclaration):
        raise TypeError("declarations must be ReviewedOrthogonalRcSystemDeclaration")
    if not isinstance(seismic, ss.ReviewedSeismicClassificationContext):
        raise TypeError("seismic must be ReviewedSeismicClassificationContext")

    assumption_items = tuple(analysis_assumptions)
    if any(
        not isinstance(item, ss.DirectionalAnalysisSystemAssumption)
        for item in assumption_items
    ):
        raise TypeError(
            "analysis_assumptions must contain DirectionalAnalysisSystemAssumption"
        )
    assumptions = {item.direction: item for item in assumption_items}
    if set(assumptions) != {"X", "Y"} or len(assumption_items) != 2:
        raise ValueError(
            "analysis_assumptions must contain exactly one X and one Y assumption"
        )

    a16_items = tuple(a16_contexts)
    if any(not isinstance(item, ss.A16SpecialContext) for item in a16_items):
        raise TypeError("a16_contexts must contain A16SpecialContext")
    a16_by_direction = {item.direction: item for item in a16_items}
    if len(a16_by_direction) != len(a16_items):
        raise ValueError("duplicate A16 context direction")
    required_a16_directions = {
        declaration.direction
        for declaration in (declarations.x, declarations.y)
        if declaration.table_4_1_row == "A16"
    }
    if set(a16_by_direction) != required_a16_directions:
        raise ValueError(
            "a16_contexts must match exactly the directions declared as A16"
        )

    targets = [
        *_directional_targets("X"),
        *_directional_targets("Y"),
        RuleScopeTarget(
            rule_id=ss.RC_TBDY_4_3_4_2_ORTHOGONAL_DUCTILITY_CONSISTENCY,
            grain=Grain.MODEL,
            scope_ref="MODEL",
            direction=None,
            applicability_input=ss.DirectionalApplicabilityInput(),
            analysis_basis_status=AnalysisBasisStatus.MATCH,
        ),
    ]

    orthogonal_refs = _reviewed_refs(
        declarations.review_refs, declarations.provenance_refs
    )
    authorities = [
        _external(
            "vs4a:orthogonal_rows",
            ss.ORTHOGONAL_ROWS_KEY,
            SemanticType.RC_ORTHOGONAL_SYSTEM_DECLARATION,
            (declarations.x.table_4_1_row, declarations.y.table_4_1_row),
            scope_ref="MODEL",
            direction=None,
            grain=Grain.MODEL,
            provenance_refs=orthogonal_refs,
        )
    ]

    seismic_refs = _reviewed_refs(seismic.review_refs, seismic.provenance_refs)
    for declaration in (declarations.x, declarations.y):
        direction = declaration.direction
        assumption = assumptions[direction]
        declaration_refs = _reviewed_refs(
            declaration.review_refs, declaration.provenance_refs
        )
        assumption_refs = _reviewed_refs(
            assumption.analysis_evidence_refs, assumption.provenance_refs
        )

        if declaration.table_4_1_row == "A16":
            context = a16_by_direction[direction]
            a16_value: object = {
                "applicable": True,
                "story_count": context.story_count,
                "building_height_m": context.building_height_m,
                "roof_connection_condition": context.roof_connection_condition.value,
            }
            a16_refs = _reviewed_refs(
                context.roof_connection_review_refs,
                context.provenance_refs,
                declaration.review_refs,
            )
        else:
            a16_value = {"applicable": False}
            a16_refs = declaration_refs

        authorities.extend(
            (
                _external(
                    f"vs4a:{direction}:row",
                    ss.DECLARED_ROW_KEY,
                    SemanticType.RC_TABLE_4_1_ROW,
                    declaration.table_4_1_row,
                    scope_ref=ss.BUILDING_SCOPE,
                    direction=direction,
                    grain=Grain.DIRECTION,
                    provenance_refs=declaration_refs,
                ),
                _external(
                    f"vs4a:{direction}:dts",
                    ss.DTS_KEY,
                    SemanticType.RC_DTS,
                    seismic.dts,
                    scope_ref=ss.BUILDING_SCOPE,
                    direction=direction,
                    grain=Grain.DIRECTION,
                    provenance_refs=seismic_refs,
                ),
                _external(
                    f"vs4a:{direction}:bys",
                    ss.BYS_KEY,
                    SemanticType.RC_BYS,
                    seismic.bys,
                    scope_ref=ss.BUILDING_SCOPE,
                    direction=direction,
                    grain=Grain.DIRECTION,
                    provenance_refs=seismic_refs,
                ),
                _external(
                    f"vs4a:{direction}:a16_context",
                    ss.A16_CONTEXT_KEY,
                    SemanticType.RC_A16_SPECIAL_CONTEXT,
                    a16_value,
                    scope_ref=ss.BUILDING_SCOPE,
                    direction=direction,
                    grain=Grain.DIRECTION,
                    provenance_refs=a16_refs,
                ),
                _external(
                    f"vs4a:{direction}:assumed_row",
                    ss.ASSUMED_ROW_KEY,
                    SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,
                    assumption.assumed_table_4_1_row,
                    scope_ref=ss.BUILDING_SCOPE,
                    direction=direction,
                    grain=Grain.DIRECTION,
                    provenance_refs=assumption_refs,
                ),
                _external(
                    f"vs4a:{direction}:assumed_r",
                    ss.ASSUMED_R_KEY,
                    SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,
                    assumption.assumed_r,
                    scope_ref=ss.BUILDING_SCOPE,
                    direction=direction,
                    grain=Grain.DIRECTION,
                    unit=UNIT_DIMENSIONLESS,
                    dimension=PhysicalDimension.DIMENSIONLESS,
                    provenance_refs=assumption_refs,
                ),
                _external(
                    f"vs4a:{direction}:assumed_d",
                    ss.ASSUMED_D_KEY,
                    SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,
                    assumption.assumed_d,
                    scope_ref=ss.BUILDING_SCOPE,
                    direction=direction,
                    grain=Grain.DIRECTION,
                    unit=UNIT_DIMENSIONLESS,
                    dimension=PhysicalDimension.DIMENSIONLESS,
                    provenance_refs=assumption_refs,
                ),
            )
        )

    return RegulatoryCompiler.compile(
        ss.VS4A_REGISTRY,
        RegulatoryCompileInputs(
            rule_targets=tuple(targets),
            external_authorities=tuple(authorities),
            regulatory_authority_catalog=build_vs4a_authority_catalog(),
        ),
    )


def execute_vs4a_program(program: CompiledRegulatoryProgram) -> RegulatoryStoreSnapshot:
    return RegulatoryEngine.execute(program)


__all__ = ["compile_vs4a_program", "execute_vs4a_program"]
