"""Bounded VS-4A compiled-program composition over structural_system authorities.

The regulatory evaluators remain in ``structural_system``.  This module only
selects the applicable check subset, materializes reviewed contextual inputs,
and invokes the existing F0/F0.9 compiler and engine.
"""
from __future__ import annotations

from typing import Sequence

from tbdy_engine.regulatory.contracts import Grain, PhysicalDimension, SemanticType
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    CompiledRegulatoryProgram,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RegulatoryStoreSnapshot,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_M
from tbdy_engine.regulatory.sources.tbdy2018 import build_vs4a_authority_catalog
from tbdy_engine.regulatory import structural_system as ss


def _selected_registry(
    declarations: ss.ReviewedOrthogonalRcSystemDeclaration,
) -> RegulatoryRegistry:
    checks = [ss.DTS_CHECK_SPEC, ss.ORTHOGONAL_CHECK_SPEC]
    rows = {declarations.x.table_4_1_row, declarations.y.table_4_1_row}
    if rows != {"A16"}:
        checks.append(ss.BYS_CHECK_SPEC)
    if "A31" in rows:
        checks.append(ss.A31_CHECK_SPEC)
    if "A16" in rows:
        checks.append(ss.A16_CHECK_SPEC)
    return RegulatoryRegistry(derivations=ss.VS4A_REGISTRY.derivations, checks=tuple(checks))


def compile_vs4a_program(
    *,
    declarations: ss.ReviewedOrthogonalRcSystemDeclaration,
    seismic: ss.ReviewedSeismicClassificationContext,
    analysis_assumptions: Sequence[ss.DirectionalAnalysisSystemAssumption],
    a16_contexts: Sequence[ss.A16SpecialContext] = (),
) -> CompiledRegulatoryProgram:
    """Compile one VS-4A program with mandatory strict F0.9 source authority."""

    if not isinstance(declarations, ss.ReviewedOrthogonalRcSystemDeclaration):
        raise TypeError("declarations must be ReviewedOrthogonalRcSystemDeclaration")
    if not isinstance(seismic, ss.ReviewedSeismicClassificationContext):
        raise TypeError("seismic must be ReviewedSeismicClassificationContext")

    assumption_items = tuple(analysis_assumptions)
    if any(not isinstance(item, ss.DirectionalAnalysisSystemAssumption) for item in assumption_items):
        raise TypeError("analysis_assumptions must contain DirectionalAnalysisSystemAssumption")
    assumptions = {item.direction: item for item in assumption_items}
    if set(assumptions) != {"X", "Y"} or len(assumption_items) != 2:
        raise ValueError("analysis_assumptions must contain exactly one X and one Y assumption")

    a16_items = tuple(a16_contexts)
    if any(not isinstance(item, ss.A16SpecialContext) for item in a16_items):
        raise TypeError("a16_contexts must contain A16SpecialContext")
    a16_by_direction = {item.direction: item for item in a16_items}
    if len(a16_by_direction) != len(a16_items):
        raise ValueError("duplicate A16 context direction")

    registry = _selected_registry(declarations)
    targets = [
        *ss._directional_targets("X", declarations.x.table_4_1_row),
        *ss._directional_targets("Y", declarations.y.table_4_1_row),
        RuleScopeTarget(
            rule_id=ss.RC_TBDY_4_3_4_2_ORTHOGONAL_DUCTILITY_CONSISTENCY,
            grain=Grain.MODEL,
            scope_ref="MODEL",
            direction=None,
            applicability_input=ss.DirectionalApplicabilityInput(),
            analysis_basis_status=AnalysisBasisStatus.MATCH,
        ),
    ]

    authorities = [
        ss._external(
            "vs4a:orthogonal_rows",
            ss.ORTHOGONAL_ROWS_KEY,
            SemanticType.RC_ORTHOGONAL_SYSTEM_DECLARATION,
            (declarations.x.table_4_1_row, declarations.y.table_4_1_row),
            scope_ref="MODEL",
            direction=None,
            grain=Grain.MODEL,
            provenance_refs=declarations.provenance_refs,
        )
    ]

    for declaration in (declarations.x, declarations.y):
        direction = declaration.direction
        assumption = assumptions[direction]
        shared_refs = tuple(
            sorted(
                set(
                    (*declaration.review_refs, *declaration.provenance_refs, *seismic.provenance_refs)
                )
            )
        )
        authorities.extend(
            (
                ss._external(
                    f"vs4a:{direction}:row", ss.DECLARED_ROW_KEY,
                    SemanticType.RC_TABLE_4_1_ROW, declaration.table_4_1_row,
                    scope_ref=ss.BUILDING_SCOPE, direction=direction, grain=Grain.DIRECTION,
                    provenance_refs=shared_refs,
                ),
                ss._external(
                    f"vs4a:{direction}:dts", ss.DTS_KEY, SemanticType.RC_DTS, seismic.dts,
                    scope_ref=ss.BUILDING_SCOPE, direction=direction, grain=Grain.DIRECTION,
                    provenance_refs=seismic.provenance_refs,
                ),
                ss._external(
                    f"vs4a:{direction}:bys", ss.BYS_KEY, SemanticType.RC_BYS, seismic.bys,
                    scope_ref=ss.BUILDING_SCOPE, direction=direction, grain=Grain.DIRECTION,
                    provenance_refs=seismic.provenance_refs,
                ),
                ss._external(
                    f"vs4a:{direction}:assumed_row", ss.ASSUMED_ROW_KEY,
                    SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION, assumption.assumed_table_4_1_row,
                    scope_ref=ss.BUILDING_SCOPE, direction=direction, grain=Grain.DIRECTION,
                    provenance_refs=(*assumption.analysis_evidence_refs, *assumption.provenance_refs),
                ),
                ss._external(
                    f"vs4a:{direction}:assumed_r", ss.ASSUMED_R_KEY,
                    SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION, assumption.assumed_r,
                    scope_ref=ss.BUILDING_SCOPE, direction=direction, grain=Grain.DIRECTION,
                    unit=UNIT_DIMENSIONLESS, dimension=PhysicalDimension.DIMENSIONLESS,
                    provenance_refs=(*assumption.analysis_evidence_refs, *assumption.provenance_refs),
                ),
                ss._external(
                    f"vs4a:{direction}:assumed_d", ss.ASSUMED_D_KEY,
                    SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION, assumption.assumed_d,
                    scope_ref=ss.BUILDING_SCOPE, direction=direction, grain=Grain.DIRECTION,
                    unit=UNIT_DIMENSIONLESS, dimension=PhysicalDimension.DIMENSIONLESS,
                    provenance_refs=(*assumption.analysis_evidence_refs, *assumption.provenance_refs),
                ),
            )
        )
        if declaration.table_4_1_row == "A16":
            context = a16_by_direction.get(direction)
            if context is None:
                raise ValueError(f"A16 declaration in {direction} requires A16SpecialContext")
            authorities.extend(
                (
                    ss._external(
                        f"vs4a:{direction}:a16_story_count", ss.A16_STORY_COUNT_KEY,
                        SemanticType.RC_A16_SPECIAL_CONTEXT, context.story_count,
                        scope_ref=ss.BUILDING_SCOPE, direction=direction, grain=Grain.DIRECTION,
                        unit=UNIT_DIMENSIONLESS, dimension=PhysicalDimension.DIMENSIONLESS,
                        provenance_refs=context.provenance_refs,
                    ),
                    ss._external(
                        f"vs4a:{direction}:a16_height", ss.A16_HEIGHT_KEY,
                        SemanticType.RC_A16_SPECIAL_CONTEXT, context.building_height_m,
                        scope_ref=ss.BUILDING_SCOPE, direction=direction, grain=Grain.DIRECTION,
                        unit=UNIT_M, dimension=PhysicalDimension.LENGTH,
                        provenance_refs=context.provenance_refs,
                    ),
                    ss._external(
                        f"vs4a:{direction}:a16_roof", ss.A16_ROOF_CONNECTION_KEY,
                        SemanticType.RC_A16_SPECIAL_CONTEXT, context.roof_connection_condition.value,
                        scope_ref=ss.BUILDING_SCOPE, direction=direction, grain=Grain.DIRECTION,
                        provenance_refs=context.provenance_refs,
                    ),
                )
            )

    return RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(
            rule_targets=tuple(targets),
            external_authorities=tuple(authorities),
            regulatory_authority_catalog=build_vs4a_authority_catalog(),
        ),
    )


def execute_vs4a_program(program: CompiledRegulatoryProgram) -> RegulatoryStoreSnapshot:
    return RegulatoryEngine.execute(program)


__all__ = ["compile_vs4a_program", "execute_vs4a_program"]
