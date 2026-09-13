"""Explicit reviewed project/material design basis for the Column product path.

This is a production dependency, not a request-DTO engineering-truth surface.
It binds reviewed design strengths and aggregate size to exact factual ETABS
material identities before existing longitudinal/PMM owners consume them.

Factual ``fck`` remains owned by ``UsedRcMaterialPopulation``.  Reviewed
``fcd``/``fyd`` are never derived here.  Material-name applicability is exact;
a reviewed value for a different concrete or reinforcement material fails
closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Sequence

from tbdy_engine.design.columns.column_pmm_assessment import (
    ColumnPmmMaterialContextBinding,
)
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial
from tbdy_engine.features.used_rc_material_population import (
    MaterialUsageReference,
    UsedMaterialDefinition,
)
from tbdy_engine.providers.etabs_column_rebar_intent_provider import (
    ColumnRebarIntentFact,
)


COLUMN_DESIGN_BASIS_AUTHORITY = "REVIEWED_PROJECT_COLUMN_DESIGN_BASIS"
COLUMN_DESIGN_BASIS_BINDING_AUTHORITY = "COLUMN_DESIGN_BASIS_FACTUAL_MATERIAL_BINDING"


class ColumnDesignBasisError(ValueError):
    """Raised when reviewed basis and factual ETABS identity cannot be reconciled."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnDesignBasisError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnDesignBasisError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ColumnDesignBasisError(f"{label} must be finite and > 0")
    return result


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    refs = tuple(sorted({_text(value, label) for value in values}))
    if not refs:
        raise ColumnDesignBasisError(f"{label} must be nonempty")
    return refs


def _stable_ref(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return prefix + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ReviewedConcreteDesignStrength:
    material_name: str
    fcd_mpa: float
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "material_name", _text(self.material_name, "concrete.material_name"))
        object.__setattr__(self, "fcd_mpa", _positive(self.fcd_mpa, "concrete.fcd_mpa"))
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "concrete.review_ref"))


@dataclass(frozen=True, slots=True)
class ReviewedLongitudinalSteelDesignStrength:
    material_name: str
    fyd_mpa: float
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "material_name", _text(self.material_name, "steel.material_name"))
        object.__setattr__(self, "fyd_mpa", _positive(self.fyd_mpa, "steel.fyd_mpa"))
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "steel.review_ref"))


@dataclass(frozen=True, slots=True)
class ReviewedAggregateBasis:
    aggregate_max_mm: float
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "aggregate_max_mm", _positive(self.aggregate_max_mm, "aggregate_max_mm"))
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "aggregate.review_ref"))


@dataclass(frozen=True, slots=True)
class ReviewedColumnDesignBasis:
    concrete_strengths: tuple[ReviewedConcreteDesignStrength, ...]
    longitudinal_steel_strengths: tuple[ReviewedLongitudinalSteelDesignStrength, ...]
    aggregate: ReviewedAggregateBasis
    basis_refs: tuple[str, ...]
    authority: str = COLUMN_DESIGN_BASIS_AUTHORITY

    def __post_init__(self) -> None:
        concrete = tuple(self.concrete_strengths)
        steel = tuple(self.longitudinal_steel_strengths)
        if not concrete or not all(isinstance(item, ReviewedConcreteDesignStrength) for item in concrete):
            raise ColumnDesignBasisError("concrete_strengths must contain reviewed concrete basis entries")
        if not steel or not all(isinstance(item, ReviewedLongitudinalSteelDesignStrength) for item in steel):
            raise ColumnDesignBasisError("longitudinal_steel_strengths must contain reviewed steel basis entries")
        if len({item.material_name for item in concrete}) != len(concrete):
            raise ColumnDesignBasisError("reviewed concrete material applicability must be unique")
        if len({item.material_name for item in steel}) != len(steel):
            raise ColumnDesignBasisError("reviewed longitudinal steel material applicability must be unique")
        if not isinstance(self.aggregate, ReviewedAggregateBasis):
            raise TypeError("aggregate must be ReviewedAggregateBasis")
        if self.authority != COLUMN_DESIGN_BASIS_AUTHORITY:
            raise ColumnDesignBasisError("unsupported Column design-basis authority")
        object.__setattr__(self, "concrete_strengths", tuple(sorted(concrete, key=lambda item: item.material_name)))
        object.__setattr__(self, "longitudinal_steel_strengths", tuple(sorted(steel, key=lambda item: item.material_name)))
        object.__setattr__(self, "basis_refs", _refs(self.basis_refs, "basis_ref"))

    def concrete_for(self, material_name: str) -> ReviewedConcreteDesignStrength:
        name = _text(material_name, "factual_concrete_material_name")
        matches = tuple(item for item in self.concrete_strengths if item.material_name == name)
        if len(matches) != 1:
            raise ColumnDesignBasisError(
                f"reviewed fcd applicability does not exactly match factual concrete material {name!r}"
            )
        return matches[0]

    def steel_for(self, material_name: str) -> ReviewedLongitudinalSteelDesignStrength:
        name = _text(material_name, "factual_longitudinal_material_name")
        matches = tuple(item for item in self.longitudinal_steel_strengths if item.material_name == name)
        if len(matches) != 1:
            raise ColumnDesignBasisError(
                f"reviewed fyd applicability does not exactly match factual longitudinal material {name!r}"
            )
        return matches[0]


@dataclass(frozen=True, slots=True)
class BoundColumnDesignBasis:
    component_id: str
    section_id: str
    concrete_material_name: str
    longitudinal_material_name: str
    material_context: ColumnPmmMaterialContextBinding
    aggregate_max_mm: float
    aggregate_source_ref: str
    binding_ref: str
    source_refs: tuple[str, ...]
    authority: str = COLUMN_DESIGN_BASIS_BINDING_AUTHORITY


def bind_reviewed_column_design_basis(
    basis: ReviewedColumnDesignBasis,
    *,
    component_id: str,
    section_id: str,
    factual_concrete_usage: MaterialUsageReference,
    factual_concrete_definition: UsedMaterialDefinition,
    factual_rebar_intent: ColumnRebarIntentFact,
    model_fingerprint: str,
    evidence_epoch_id: str,
) -> BoundColumnDesignBasis:
    """Bind reviewed design values to exact ETABS concrete/rebar identities."""
    if not isinstance(basis, ReviewedColumnDesignBasis):
        raise TypeError("basis must be ReviewedColumnDesignBasis")
    if not isinstance(factual_concrete_usage, MaterialUsageReference):
        raise TypeError("factual_concrete_usage must be MaterialUsageReference")
    if not isinstance(factual_concrete_definition, UsedMaterialDefinition):
        raise TypeError("factual_concrete_definition must be UsedMaterialDefinition")
    if not isinstance(factual_rebar_intent, ColumnRebarIntentFact):
        raise TypeError("factual_rebar_intent must be ColumnRebarIntentFact")

    component = _text(component_id, "component_id")
    section = _text(section_id, "section_id")
    model = _text(model_fingerprint, "model_fingerprint")
    epoch = _text(evidence_epoch_id, "evidence_epoch_id")

    if factual_concrete_usage.component_type != "Column":
        raise ColumnDesignBasisError("factual concrete usage must be a Column usage")
    concrete_name = _text(factual_concrete_usage.material_name, "usage.material_name")
    if concrete_name != factual_concrete_definition.material_name:
        raise ColumnDesignBasisError("Column usage material does not match factual material definition")
    if factual_concrete_definition.model_fingerprint != model:
        raise ColumnDesignBasisError("factual concrete model_fingerprint differs from product identity")
    if not factual_concrete_definition.is_concrete:
        raise ColumnDesignBasisError("factual assigned Column material is not concrete")
    fck = factual_concrete_definition.canonical_fck_mpa
    if fck is None:
        raise ColumnDesignBasisError("factual concrete fck is unresolved")
    fck_mpa = _positive(fck, "factual_concrete_fck_mpa")
    if factual_rebar_intent.section != section:
        raise ColumnDesignBasisError("rebar intent section differs from target Column section")
    long_name = _text(factual_rebar_intent.mat_prop_long, "rebar_intent.mat_prop_long")

    reviewed_concrete = basis.concrete_for(concrete_name)
    reviewed_steel = basis.steel_for(long_name)

    concrete_fact_ref = (
        f"ETABS:UsedRcMaterialPopulation:{factual_concrete_usage.usage_id}:"
        f"{factual_concrete_definition.material_id}:{concrete_name}:fck={fck_mpa:.12g}MPa"
    )
    steel_fact_ref = f"ETABS:PropFrame.GetRebarColumn:{section}:MatPropLong={long_name}"
    section_binding_ref = _stable_ref(
        "column-section-material-binding:sha256:",
        {
            "component_id": component,
            "section_id": section,
            "usage_id": factual_concrete_usage.usage_id,
            "material_id": factual_concrete_definition.material_id,
            "concrete_material_name": concrete_name,
            "longitudinal_material_name": long_name,
            "model_fingerprint": model,
            "evidence_epoch_id": epoch,
            "concrete_fact_ref": concrete_fact_ref,
            "steel_fact_ref": steel_fact_ref,
        },
    )
    material = ColumnSectionMaterial(
        fck_mpa=fck_mpa,
        fcd_mpa=reviewed_concrete.fcd_mpa,
        fyd_mpa=reviewed_steel.fyd_mpa,
    )
    context = ColumnPmmMaterialContextBinding(
        component_id=component,
        section_id=section,
        material_name=concrete_name,
        material=material,
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        section_material_binding_ref=section_binding_ref,
        concrete_strength_source_refs=(concrete_fact_ref,),
        concrete_design_strength_review_refs=tuple(
            dict.fromkeys((*basis.basis_refs, *reviewed_concrete.review_refs))
        ),
        steel_design_strength_review_refs=tuple(
            dict.fromkeys((*basis.basis_refs, *reviewed_steel.review_refs, steel_fact_ref))
        ),
    )
    aggregate_ref = _stable_ref(
        "column-aggregate-basis:sha256:",
        {
            "aggregate_max_mm": basis.aggregate.aggregate_max_mm,
            "review_refs": list(basis.aggregate.review_refs),
            "basis_refs": list(basis.basis_refs),
        },
    )
    refs = tuple(
        dict.fromkeys(
            (
                *basis.basis_refs,
                *reviewed_concrete.review_refs,
                *reviewed_steel.review_refs,
                *basis.aggregate.review_refs,
                concrete_fact_ref,
                steel_fact_ref,
                section_binding_ref,
                context.binding_ref,
                aggregate_ref,
            )
        )
    )
    binding_ref = _stable_ref(
        "column-design-basis-binding:sha256:",
        {
            "component_id": component,
            "section_id": section,
            "concrete_material_name": concrete_name,
            "longitudinal_material_name": long_name,
            "material_context_ref": context.binding_ref,
            "aggregate_source_ref": aggregate_ref,
            "source_refs": list(refs),
        },
    )
    return BoundColumnDesignBasis(
        component_id=component,
        section_id=section,
        concrete_material_name=concrete_name,
        longitudinal_material_name=long_name,
        material_context=context,
        aggregate_max_mm=basis.aggregate.aggregate_max_mm,
        aggregate_source_ref=aggregate_ref,
        binding_ref=binding_ref,
        source_refs=refs,
    )


__all__ = [
    "BoundColumnDesignBasis",
    "COLUMN_DESIGN_BASIS_AUTHORITY",
    "COLUMN_DESIGN_BASIS_BINDING_AUTHORITY",
    "ColumnDesignBasisError",
    "ReviewedAggregateBasis",
    "ReviewedColumnDesignBasis",
    "ReviewedConcreteDesignStrength",
    "ReviewedLongitudinalSteelDesignStrength",
    "bind_reviewed_column_design_basis",
]
