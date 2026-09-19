"""Production F0 composition for TBDY §7.7.5 limited-column shear."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from tbdy_engine.checks.result import CheckResult
from tbdy_engine.design.columns.column_shear_upper_bounds import (
    ColumnEffectiveDepthResolution,
)
from tbdy_engine.regulatory.column_shear_limited import (
    COLUMN_DEPTH_MM_KEY,
    COLUMN_SHEAR_LIMITED_775_REGISTRY,
    COLUMN_WIDTH_MM_KEY,
    CONCRETE_FCK_MPA_KEY,
    EVIDENCE_TRACE_KEY,
    LIMITED_BRITTLE_RULE_ID,
    LIMITED_VD_KN_KEY,
    SECTION_KEY,
    STORY_KEY,
    ColumnShearLimitedApplicabilityInput,
)
from tbdy_engine.regulatory.column_shear_p7 import (
    COLUMN_DEPTH_MM_KEY as P7_COLUMN_DEPTH_MM_KEY,
    COLUMN_WIDTH_MM_KEY as P7_COLUMN_WIDTH_MM_KEY,
    EFFECTIVE_DEPTH_MM_KEY,
    EVIDENCE_TRACE_KEY as P7_EVIDENCE_TRACE_KEY,
    SECTION_KEY as P7_SECTION_KEY,
    STORY_KEY as P7_STORY_KEY,
    TS500_FCD_MPA_KEY,
    TS500_VD_KN_KEY,
    TS500_WEB_CHECK_SPEC,
    TS500_WEB_RULE_ID,
    ColumnShearP7ApplicabilityInput,
)
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    ExternalDependencyAuthority,
    PopulationCompleteness,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RegulatoryStoreSnapshot,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.sources.column_shear_limited_775 import (
    build_column_shear_limited_775_authority_catalog,
)
from tbdy_engine.regulatory.sources.vs6_column_shear_p7 import (
    build_vs6_column_shear_p7_authority_catalog,
)
from tbdy_engine.regulatory.units import (
    UNIT_DIMENSIONLESS,
    UNIT_ENUM_STATE,
    UNIT_KN,
    UNIT_MM,
    UNIT_MPA,
)
from tbdy_engine.regulatory.vs6_column_shear_p7_program import (
    SourceBoundShearDemand,
)


class LimitedColumnShearProgramError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LimitedColumnShearDirectionRun:
    component_id: str
    story: str
    section: str
    direction: str
    vd: SourceBoundShearDemand
    effective_depth: ColumnEffectiveDepthResolution
    tbdy_brittle_result: CheckResult
    ts500_web_result: CheckResult
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.direction not in {"V2", "V3"}:
            raise LimitedColumnShearProgramError(
                "direction must be V2 or V3"
            )
        if (
            self.vd.demand_kn < 0.0
            or not self.effective_depth.resolved
        ):
            raise LimitedColumnShearProgramError(
                "limited shear direction requires resolved demand/depth"
            )
        if (
            self.effective_depth.component_id != self.component_id
            or self.effective_depth.direction != self.direction
        ):
            raise LimitedColumnShearProgramError(
                "limited shear effective-depth identity mismatch"
            )
        refs = tuple(self.source_refs)
        if not refs or any(
            not isinstance(item, str) or not item.strip()
            for item in refs
        ):
            raise LimitedColumnShearProgramError(
                "source_refs must be nonempty strings"
            )
        object.__setattr__(
            self,
            "source_refs",
            tuple(dict.fromkeys(refs)),
        )

    @property
    def vd_kn(self) -> float:
        return float(self.vd.demand_kn)


@dataclass(frozen=True, slots=True)
class LimitedColumnShearRun:
    component_id: str
    directions: tuple[
        LimitedColumnShearDirectionRun, ...
    ]

    def __post_init__(self) -> None:
        directions = tuple(
            sorted(
                self.directions,
                key=lambda item: item.direction,
            )
        )
        if (
            len(directions) != 2
            or {item.direction for item in directions}
            != {"V2", "V3"}
            or any(
                item.component_id != self.component_id
                for item in directions
            )
        ):
            raise LimitedColumnShearProgramError(
                "limited run must cover V2/V3 for one component"
            )
        object.__setattr__(
            self,
            "directions",
            directions,
        )


def _ext(
    *,
    authority_id: str,
    key,
    source_kind: DependencySourceKind,
    semantic_type: SemanticType,
    dimension: PhysicalDimension,
    grain: Grain,
    scope_ref: str,
    direction: str | None,
    unit,
    value: object,
    provenance_refs: Sequence[str],
) -> ExternalDependencyAuthority:
    return ExternalDependencyAuthority(
        authority_id=authority_id,
        key=key,
        source_kind=source_kind,
        semantic_type=semantic_type,
        physical_dimension=dimension,
        grain=grain,
        scope_ref=scope_ref,
        direction=direction,
        unit=unit,
        availability=AvailabilityState.RESOLVED,
        population_completeness=(
            PopulationCompleteness.FULL
        ),
        value=value,
        provenance_refs=tuple(provenance_refs),
    )


def _one_result(
    snapshot: RegulatoryStoreSnapshot,
    instance_id,
) -> CheckResult:
    items = snapshot.formal_results_for(
        instance_id
    )
    if len(items) != 1:
        raise LimitedColumnShearProgramError(
            "expected exactly one canonical CheckResult"
        )
    return items[0]


def _evidence(
    vd: SourceBoundShearDemand,
    effective_depth: ColumnEffectiveDepthResolution,
    geometry_source_ref: str,
    material_source_refs: Sequence[str],
    extra_refs: Sequence[str],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *vd.source_refs,
                *effective_depth.source_refs,
                geometry_source_ref,
                *tuple(material_source_refs),
                *tuple(extra_refs),
            )
        )
    )


def _run_tbdy_7752(
    *,
    component_id: str,
    story: str,
    section: str,
    direction: str,
    vd: SourceBoundShearDemand,
    width_mm: float,
    depth_mm: float,
    fck_mpa: float,
    geometry_source_ref: str,
    evidence: tuple[str, ...],
) -> CheckResult:
    target = RuleScopeTarget(
        rule_id=LIMITED_BRITTLE_RULE_ID,
        grain=Grain.COMPONENT_DIRECTION,
        scope_ref=component_id,
        direction=direction,
        mandatory=True,
        applicability_input=(
            ColumnShearLimitedApplicabilityInput(
                component_type="column",
                reinforced_concrete=True,
                limited_ductility_applies=True,
            )
        ),
    )
    authorities = (
        _ext(
            authority_id=(
                f"LD775:{component_id}:{direction}:VD"
            ),
            key=LIMITED_VD_KN_KEY,
            source_kind=(
                DependencySourceKind.SELECTED_SOURCE_QUANTITY
            ),
            semantic_type=(
                SemanticType.CHECK_EVIDENCE_TRACE
            ),
            dimension=PhysicalDimension.FORCE,
            grain=Grain.COMPONENT_DIRECTION,
            scope_ref=component_id,
            direction=direction,
            unit=UNIT_KN,
            value=vd.demand_kn,
            provenance_refs=vd.source_refs,
        ),
        _ext(
            authority_id=(
                f"LD775:{component_id}:WIDTH"
            ),
            key=COLUMN_WIDTH_MM_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.COLUMN_WIDTH,
            dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_MM,
            value=width_mm,
            provenance_refs=(geometry_source_ref,),
        ),
        _ext(
            authority_id=(
                f"LD775:{component_id}:DEPTH"
            ),
            key=COLUMN_DEPTH_MM_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.COLUMN_DEPTH,
            dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_MM,
            value=depth_mm,
            provenance_refs=(geometry_source_ref,),
        ),
        _ext(
            authority_id=(
                f"LD775:{component_id}:FCK"
            ),
            key=CONCRETE_FCK_MPA_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.CONCRETE_FCK,
            dimension=PhysicalDimension.STRESS,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_MPA,
            value=fck_mpa,
            provenance_refs=evidence,
        ),
        _ext(
            authority_id=(
                f"LD775:{component_id}:STORY"
            ),
            key=STORY_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_STORY,
            dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_ENUM_STATE,
            value=story,
            provenance_refs=(f"STORY:{story}",),
        ),
        _ext(
            authority_id=(
                f"LD775:{component_id}:SECTION"
            ),
            key=SECTION_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_SECTION,
            dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_ENUM_STATE,
            value=section,
            provenance_refs=(geometry_source_ref,),
        ),
        _ext(
            authority_id=(
                f"LD775:{component_id}:{direction}:EVIDENCE"
            ),
            key=EVIDENCE_TRACE_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT_DIRECTION,
            scope_ref=component_id,
            direction=direction,
            unit=UNIT_DIMENSIONLESS,
            value=evidence,
            provenance_refs=evidence,
        ),
    )
    compiled = RegulatoryCompiler.compile(
        COLUMN_SHEAR_LIMITED_775_REGISTRY,
        RegulatoryCompileInputs(
            rule_targets=(target,),
            external_authorities=authorities,
            regulatory_authority_catalog=(
                build_column_shear_limited_775_authority_catalog()
            ),
        ),
    )
    snapshot = RegulatoryEngine.execute(
        compiled
    )
    return _one_result(
        snapshot,
        target.instance_id,
    )


def _run_ts500_web(
    *,
    component_id: str,
    story: str,
    section: str,
    direction: str,
    vd: SourceBoundShearDemand,
    width_mm: float,
    depth_mm: float,
    fcd_mpa: float,
    effective_depth: ColumnEffectiveDepthResolution,
    geometry_source_ref: str,
    evidence: tuple[str, ...],
) -> CheckResult:
    if (
        effective_depth.effective_depth_d_mm
        is None
    ):
        raise LimitedColumnShearProgramError(
            "exact effective depth is required"
        )
    target = RuleScopeTarget(
        rule_id=TS500_WEB_RULE_ID,
        grain=Grain.COMPONENT_DIRECTION,
        scope_ref=component_id,
        direction=direction,
        mandatory=True,
        applicability_input=(
            ColumnShearP7ApplicabilityInput(
                component_type="column",
                reinforced_concrete=True,
                tbdy_737_high_ductility_applies=False,
            )
        ),
    )
    authorities = (
        _ext(
            authority_id=(
                f"LD775-TS500:{component_id}:{direction}:VD"
            ),
            key=TS500_VD_KN_KEY,
            source_kind=(
                DependencySourceKind.SELECTED_SOURCE_QUANTITY
            ),
            semantic_type=(
                SemanticType.CHECK_EVIDENCE_TRACE
            ),
            dimension=PhysicalDimension.FORCE,
            grain=Grain.COMPONENT_DIRECTION,
            scope_ref=component_id,
            direction=direction,
            unit=UNIT_KN,
            value=vd.demand_kn,
            provenance_refs=vd.source_refs,
        ),
        _ext(
            authority_id=(
                f"LD775-TS500:{component_id}:FCD"
            ),
            key=TS500_FCD_MPA_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=(
                SemanticType.CHECK_EVIDENCE_TRACE
            ),
            dimension=PhysicalDimension.STRESS,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_MPA,
            value=fcd_mpa,
            provenance_refs=evidence,
        ),
        _ext(
            authority_id=(
                f"LD775-TS500:{component_id}:WIDTH"
            ),
            key=P7_COLUMN_WIDTH_MM_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.COLUMN_WIDTH,
            dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_MM,
            value=width_mm,
            provenance_refs=(geometry_source_ref,),
        ),
        _ext(
            authority_id=(
                f"LD775-TS500:{component_id}:DEPTH"
            ),
            key=P7_COLUMN_DEPTH_MM_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.COLUMN_DEPTH,
            dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_MM,
            value=depth_mm,
            provenance_refs=(geometry_source_ref,),
        ),
        _ext(
            authority_id=(
                f"LD775-TS500:{component_id}:{direction}:D"
            ),
            key=EFFECTIVE_DEPTH_MM_KEY,
            source_kind=(
                DependencySourceKind.SELECTED_SOURCE_QUANTITY
            ),
            semantic_type=(
                SemanticType.CHECK_EVIDENCE_TRACE
            ),
            dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT_DIRECTION,
            scope_ref=component_id,
            direction=direction,
            unit=UNIT_MM,
            value=(
                effective_depth.effective_depth_d_mm
            ),
            provenance_refs=(
                effective_depth.source_refs
            ),
        ),
        _ext(
            authority_id=(
                f"LD775-TS500:{component_id}:STORY"
            ),
            key=P7_STORY_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_STORY,
            dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_ENUM_STATE,
            value=story,
            provenance_refs=(f"STORY:{story}",),
        ),
        _ext(
            authority_id=(
                f"LD775-TS500:{component_id}:SECTION"
            ),
            key=P7_SECTION_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_SECTION,
            dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_ENUM_STATE,
            value=section,
            provenance_refs=(geometry_source_ref,),
        ),
        _ext(
            authority_id=(
                f"LD775-TS500:{component_id}:{direction}:EVIDENCE"
            ),
            key=P7_EVIDENCE_TRACE_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=(
                SemanticType.CHECK_EVIDENCE_TRACE
            ),
            dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT_DIRECTION,
            scope_ref=component_id,
            direction=direction,
            unit=UNIT_DIMENSIONLESS,
            value=evidence,
            provenance_refs=evidence,
        ),
    )
    registry = RegulatoryRegistry(
        checks=(TS500_WEB_CHECK_SPEC,),
    )
    compiled = RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(
            rule_targets=(target,),
            external_authorities=authorities,
            regulatory_authority_catalog=(
                build_vs6_column_shear_p7_authority_catalog()
            ),
        ),
    )
    snapshot = RegulatoryEngine.execute(
        compiled
    )
    return _one_result(
        snapshot,
        target.instance_id,
    )


def run_limited_column_shear_direction(
    *,
    component_id: str,
    story: str,
    section: str,
    direction: str,
    vd: SourceBoundShearDemand,
    d_amplified_vertical_plus_earthquake_proven: bool,
    authority_ref: str,
    width_mm: float,
    depth_mm: float,
    fck_mpa: float,
    fcd_mpa: float,
    geometry_source_ref: str,
    material_source_refs: Sequence[str],
    effective_depth: ColumnEffectiveDepthResolution,
    source_refs: Sequence[str],
) -> LimitedColumnShearDirectionRun:
    if direction not in {"V2", "V3"}:
        raise LimitedColumnShearProgramError(
            "direction must be V2 or V3"
        )
    if type(
        d_amplified_vertical_plus_earthquake_proven
    ) is not bool:
        raise TypeError(
            "d_amplified_vertical_plus_earthquake_proven "
            "must be bool"
        )
    if not d_amplified_vertical_plus_earthquake_proven:
        raise LimitedColumnShearProgramError(
            "TBDY 7.7.5.1 requires reviewed vertical + "
            "D-amplified earthquake combination semantics"
        )
    if (
        not isinstance(authority_ref, str)
        or not authority_ref.strip()
    ):
        raise LimitedColumnShearProgramError(
            "authority_ref must be nonblank"
        )
    scalars = (
        float(width_mm),
        float(depth_mm),
        float(fck_mpa),
        float(fcd_mpa),
    )
    if any(
        not math.isfinite(value)
        or value <= 0.0
        for value in scalars
    ):
        raise LimitedColumnShearProgramError(
            "geometry/material scalars must be finite and > 0"
        )
    if (
        not effective_depth.resolved
        or effective_depth.component_id != component_id
        or effective_depth.direction != direction
    ):
        raise LimitedColumnShearProgramError(
            "limited shear exact effective depth is unresolved"
        )

    evidence = _evidence(
        vd,
        effective_depth,
        geometry_source_ref,
        material_source_refs,
        (
            authority_ref,
            *tuple(source_refs),
            "regulatory-anchor:TBDY2018_AFAD:7.7.5.1",
            "regulatory-anchor:TBDY2018_AFAD:7.7.5.2",
        ),
    )

    brittle = _run_tbdy_7752(
        component_id=component_id,
        story=story,
        section=section,
        direction=direction,
        vd=vd,
        width_mm=scalars[0],
        depth_mm=scalars[1],
        fck_mpa=scalars[2],
        geometry_source_ref=geometry_source_ref,
        evidence=evidence,
    )
    web = _run_ts500_web(
        component_id=component_id,
        story=story,
        section=section,
        direction=direction,
        vd=vd,
        width_mm=scalars[0],
        depth_mm=scalars[1],
        fcd_mpa=scalars[3],
        effective_depth=effective_depth,
        geometry_source_ref=geometry_source_ref,
        evidence=evidence,
    )

    return LimitedColumnShearDirectionRun(
        component_id=component_id,
        story=story,
        section=section,
        direction=direction,
        vd=vd,
        effective_depth=effective_depth,
        tbdy_brittle_result=brittle,
        ts500_web_result=web,
        source_refs=evidence,
    )


def build_limited_column_shear_run(
    *,
    component_id: str,
    directions: Sequence[
        LimitedColumnShearDirectionRun
    ],
) -> LimitedColumnShearRun:
    return LimitedColumnShearRun(
        component_id=component_id,
        directions=tuple(directions),
    )


__all__ = [
    "LimitedColumnShearDirectionRun",
    "LimitedColumnShearProgramError",
    "LimitedColumnShearRun",
    "build_limited_column_shear_run",
    "run_limited_column_shear_direction",
]
