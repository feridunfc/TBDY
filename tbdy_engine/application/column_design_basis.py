"""Explicit reviewed project/material design basis for the Column product path.

This is a production dependency, not a request-DTO engineering-truth surface.
It binds reviewed design strengths, aggregate size, optional transverse-steel /
ductility applicability, and optional source-bound numerical review policy to
exact product composition before existing authorities consume them.

Factual ``fck`` and reinforcement material names remain source-owned. Reviewed
``fcd``/``fyd``/``fywk``/``fywd`` are never derived here. Material-name
applicability is exact; absent transverse review facts remain explicit blockers
for A36 without invalidating the already-qualified longitudinal path. Story-
translation tolerance is an optional reviewed numerical equality basis only;
absence remains unresolved upstream of A17 and no numeric default is
manufactured here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Sequence

from tbdy_engine.design.columns.column_pmm_assessment import ColumnPmmMaterialContextBinding
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial
from tbdy_engine.design.columns.story_relative_translation import ReviewedStoryTranslationTolerance
from tbdy_engine.features.used_rc_material_population import (
    MaterialUsageReference,
    UsedMaterialDefinition,
)
from tbdy_engine.providers.etabs_column_rebar_intent_provider import (
    EtabsColumnRebarIntentEvidence,
)
from tbdy_engine.regulatory.contracts import (
    ApplicabilityBinding,
    ApplicabilityState,
)


COLUMN_DESIGN_BASIS_AUTHORITY = "REVIEWED_PROJECT_COLUMN_DESIGN_BASIS"
COLUMN_DESIGN_BASIS_BINDING_AUTHORITY = "COLUMN_DESIGN_BASIS_FACTUAL_MATERIAL_BINDING"
COLUMN_STORY_TRANSLATION_TOLERANCE_BASIS_VERSION = "COLUMN_STORY_TRANSLATION_TOLERANCE_V1"

COLUMN_ROUTE_C_W_ACTION_FAMILY = "W"
COLUMN_ROUTE_C_SUPPORTED_PATH = "COLUMN/ROUTE_C"
COLUMN_ROUTE_C_W_APPLICABILITY_BASIS_VERSION = (
    "COLUMN_ROUTE_C_W_APPLICABILITY_V1"
)
COLUMN_ROUTE_C_W_APPLICABILITY_BINDING_ID = (
    "column-r1-route-c-w-applicability-v1"
)


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


def _optional_refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{label} must be a sequence")
    return tuple(sorted({_text(value, label) for value in values}))


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
class ReviewedTransverseSteelDesignStrength:
    """Reviewed A36 steel basis bound later to factual ``MatPropConfine`` identity."""

    material_name: str
    fywk_mpa: float
    fywd_mpa: float
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "material_name", _text(self.material_name, "transverse_steel.material_name"))
        object.__setattr__(self, "fywk_mpa", _positive(self.fywk_mpa, "transverse_steel.fywk_mpa"))
        object.__setattr__(self, "fywd_mpa", _positive(self.fywd_mpa, "transverse_steel.fywd_mpa"))
        object.__setattr__(
            self,
            "review_refs",
            _refs(self.review_refs, "transverse_steel.review_ref"),
        )


@dataclass(frozen=True, slots=True)
class ReviewedAggregateBasis:
    aggregate_max_mm: float
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "aggregate_max_mm", _positive(self.aggregate_max_mm, "aggregate_max_mm"))
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "aggregate.review_ref"))


@dataclass(frozen=True, slots=True)
class ReviewedActionFamilyApplicability:
    """Reviewed applicability for the bounded Route-C W action family."""

    state: ApplicabilityState
    review_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    action_family: str = COLUMN_ROUTE_C_W_ACTION_FAMILY
    supported_path: str = COLUMN_ROUTE_C_SUPPORTED_PATH
    basis_version: str = COLUMN_ROUTE_C_W_APPLICABILITY_BASIS_VERSION

    def __post_init__(self) -> None:
        if not isinstance(
            self.state,
            ApplicabilityState,
        ):
            raise TypeError(
                "state must be ApplicabilityState"
            )

        if (
            self.action_family
            != COLUMN_ROUTE_C_W_ACTION_FAMILY
        ):
            raise ColumnDesignBasisError(
                "reviewed action-family applicability "
                "must target W"
            )

        if (
            self.supported_path
            != COLUMN_ROUTE_C_SUPPORTED_PATH
        ):
            raise ColumnDesignBasisError(
                "reviewed W applicability must target "
                "COLUMN/ROUTE_C"
            )

        if (
            self.basis_version
            != COLUMN_ROUTE_C_W_APPLICABILITY_BASIS_VERSION
        ):
            raise ColumnDesignBasisError(
                "unsupported W applicability basis version"
            )

        object.__setattr__(
            self,
            "review_refs",
            _refs(
                self.review_refs,
                "route_c_w_applicability.review_ref",
            ),
        )

        object.__setattr__(
            self,
            "source_refs",
            _refs(
                self.source_refs,
                "route_c_w_applicability.source_ref",
            ),
        )


def _evaluate_route_c_w_applicability(
    value: object,
) -> ApplicabilityState:
    if not isinstance(
        value,
        ReviewedActionFamilyApplicability,
    ):
        raise TypeError(
            "Route-C W applicability input must be "
            "ReviewedActionFamilyApplicability"
        )

    return value.state


COLUMN_ROUTE_C_W_APPLICABILITY_BINDING = (
    ApplicabilityBinding(
        binding_id=(
            COLUMN_ROUTE_C_W_APPLICABILITY_BINDING_ID
        ),
        input_type=ReviewedActionFamilyApplicability,
        evaluator=_evaluate_route_c_w_applicability,
    )
)


@dataclass(frozen=True, slots=True)
class ReviewedColumnDesignBasis:
    concrete_strengths: tuple[ReviewedConcreteDesignStrength, ...]
    longitudinal_steel_strengths: tuple[ReviewedLongitudinalSteelDesignStrength, ...]
    aggregate: ReviewedAggregateBasis
    basis_refs: tuple[str, ...]
    story_translation_tolerance: ReviewedStoryTranslationTolerance | None = None
    authority: str = COLUMN_DESIGN_BASIS_AUTHORITY
    transverse_steel_strengths: tuple[ReviewedTransverseSteelDesignStrength, ...] = ()
    high_ductility_applies: bool | None = None
    limited_ductility_applies: bool | None = None
    transverse_policy_refs: tuple[str, ...] = ()
    route_c_w_applicability: ReviewedActionFamilyApplicability | None = None

    def __post_init__(self) -> None:
        concrete = tuple(self.concrete_strengths)
        steel = tuple(self.longitudinal_steel_strengths)
        transverse = tuple(self.transverse_steel_strengths)
        if not concrete or not all(isinstance(item, ReviewedConcreteDesignStrength) for item in concrete):
            raise ColumnDesignBasisError("concrete_strengths must contain reviewed concrete basis entries")
        if not steel or not all(isinstance(item, ReviewedLongitudinalSteelDesignStrength) for item in steel):
            raise ColumnDesignBasisError("longitudinal_steel_strengths must contain reviewed steel basis entries")
        if not all(isinstance(item, ReviewedTransverseSteelDesignStrength) for item in transverse):
            raise ColumnDesignBasisError(
                "transverse_steel_strengths must contain reviewed transverse steel basis entries"
            )
        if len({item.material_name for item in concrete}) != len(concrete):
            raise ColumnDesignBasisError("reviewed concrete material applicability must be unique")
        if len({item.material_name for item in steel}) != len(steel):
            raise ColumnDesignBasisError("reviewed longitudinal steel material applicability must be unique")
        if len({item.material_name for item in transverse}) != len(transverse):
            raise ColumnDesignBasisError("reviewed transverse steel material applicability must be unique")
        if not isinstance(self.aggregate, ReviewedAggregateBasis):
            raise TypeError("aggregate must be ReviewedAggregateBasis")
        if self.story_translation_tolerance is not None and not isinstance(
            self.story_translation_tolerance, ReviewedStoryTranslationTolerance
        ):
            raise TypeError(
                "story_translation_tolerance must be ReviewedStoryTranslationTolerance or None"
            )
        if (
            self.route_c_w_applicability is not None
            and not isinstance(
                self.route_c_w_applicability,
                ReviewedActionFamilyApplicability,
            )
        ):
            raise TypeError(
                "route_c_w_applicability must be "
                "ReviewedActionFamilyApplicability or None"
            )

        for name in ("high_ductility_applies", "limited_ductility_applies"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise TypeError(f"{name} must be bool or None")
        if self.high_ductility_applies is True and self.limited_ductility_applies is True:
            raise ColumnDesignBasisError("HIGH and LIMITED ductility cannot both apply")
        policy_refs = _optional_refs(self.transverse_policy_refs, "transverse_policy_ref")
        if (
            self.high_ductility_applies is not None
            or self.limited_ductility_applies is not None
        ) and not policy_refs:
            raise ColumnDesignBasisError(
                "reviewed ductility/applicability facts require transverse_policy_refs"
            )
        if self.authority != COLUMN_DESIGN_BASIS_AUTHORITY:
            raise ColumnDesignBasisError("unsupported Column design-basis authority")
        object.__setattr__(self, "concrete_strengths", tuple(sorted(concrete, key=lambda item: item.material_name)))
        object.__setattr__(self, "longitudinal_steel_strengths", tuple(sorted(steel, key=lambda item: item.material_name)))
        object.__setattr__(self, "transverse_steel_strengths", tuple(sorted(transverse, key=lambda item: item.material_name)))
        object.__setattr__(self, "transverse_policy_refs", policy_refs)
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
class BoundColumnActionFamilyApplicability:
    """Project/model/epoch-bound reviewed Route-C W applicability."""

    action_family: str
    supported_path: str
    state: ApplicabilityState
    project_id: str
    model_fingerprint: str
    evidence_epoch_id: str
    basis_version: str
    applicability_binding_id: str
    binding_ref: str
    evidence_ref: str
    review_refs: tuple[str, ...]
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.action_family
            != COLUMN_ROUTE_C_W_ACTION_FAMILY
        ):
            raise ColumnDesignBasisError(
                "bound action family must be W"
            )

        if (
            self.supported_path
            != COLUMN_ROUTE_C_SUPPORTED_PATH
        ):
            raise ColumnDesignBasisError(
                "bound applicability path must be "
                "COLUMN/ROUTE_C"
            )

        if not isinstance(
            self.state,
            ApplicabilityState,
        ):
            raise TypeError(
                "state must be ApplicabilityState"
            )

        if (
            self.basis_version
            != COLUMN_ROUTE_C_W_APPLICABILITY_BASIS_VERSION
        ):
            raise ColumnDesignBasisError(
                "unsupported bound W applicability basis version"
            )

        if (
            self.applicability_binding_id
            != COLUMN_ROUTE_C_W_APPLICABILITY_BINDING_ID
        ):
            raise ColumnDesignBasisError(
                "unsupported W applicability binding"
            )

        object.__setattr__(
            self,
            "project_id",
            _text(
                self.project_id,
                "project_id",
            ),
        )

        object.__setattr__(
            self,
            "model_fingerprint",
            _text(
                self.model_fingerprint,
                "model_fingerprint",
            ),
        )

        object.__setattr__(
            self,
            "evidence_epoch_id",
            _text(
                self.evidence_epoch_id,
                "evidence_epoch_id",
            ),
        )

        object.__setattr__(
            self,
            "binding_ref",
            _text(
                self.binding_ref,
                "binding_ref",
            ),
        )

        object.__setattr__(
            self,
            "evidence_ref",
            _text(
                self.evidence_ref,
                "evidence_ref",
            ),
        )

        object.__setattr__(
            self,
            "review_refs",
            _refs(
                self.review_refs,
                "bound_route_c_w.review_ref",
            ),
        )

        object.__setattr__(
            self,
            "source_refs",
            _refs(
                self.source_refs,
                "bound_route_c_w.source_ref",
            ),
        )


def bind_reviewed_route_c_w_applicability(
    basis: ReviewedColumnDesignBasis,
    *,
    project_id: str,
    model_fingerprint: str,
    evidence_epoch_id: str,
) -> BoundColumnActionFamilyApplicability | None:
    """Bind reviewed W applicability to project/model/epoch identity."""

    if not isinstance(
        basis,
        ReviewedColumnDesignBasis,
    ):
        raise TypeError(
            "basis must be ReviewedColumnDesignBasis"
        )

    reviewed = basis.route_c_w_applicability

    if reviewed is None:
        return None

    project = _text(
        project_id,
        "project_id",
    )

    model = _text(
        model_fingerprint,
        "model_fingerprint",
    )

    epoch = _text(
        evidence_epoch_id,
        "evidence_epoch_id",
    )

    state = (
        COLUMN_ROUTE_C_W_APPLICABILITY_BINDING
        .evaluator(reviewed)
    )

    binding_ref = _stable_ref(
        "column-route-c-w-applicability-binding:sha256:",
        {
            "project_id": project,
            "model_fingerprint": model,
            "evidence_epoch_id": epoch,
            "action_family": reviewed.action_family,
            "supported_path": reviewed.supported_path,
            "state": state.value,
            "basis_version": reviewed.basis_version,
            "applicability_binding_id": (
                COLUMN_ROUTE_C_W_APPLICABILITY_BINDING
                .binding_id
            ),
            "basis_refs": list(
                basis.basis_refs
            ),
            "review_refs": list(
                reviewed.review_refs
            ),
            "source_refs": list(
                reviewed.source_refs
            ),
        },
    )

    evidence_ref = (
        "COLUMN_ROUTE_C_GQW_APPLICABILITY:"
        f"{state.value}:"
        f"{binding_ref}"
    )

    source_refs = tuple(
        dict.fromkeys(
            (
                *basis.basis_refs,
                *reviewed.review_refs,
                *reviewed.source_refs,
                binding_ref,
                evidence_ref,
            )
        )
    )

    return BoundColumnActionFamilyApplicability(
        action_family=reviewed.action_family,
        supported_path=reviewed.supported_path,
        state=state,
        project_id=project,
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        basis_version=reviewed.basis_version,
        applicability_binding_id=(
            COLUMN_ROUTE_C_W_APPLICABILITY_BINDING
            .binding_id
        ),
        binding_ref=binding_ref,
        evidence_ref=evidence_ref,
        review_refs=reviewed.review_refs,
        source_refs=source_refs,
    )


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
    transverse_material_name: str | None = None
    transverse_fywk_mpa: float | None = None
    transverse_fywd_mpa: float | None = None
    high_ductility_applies: bool | None = None
    limited_ductility_applies: bool | None = None
    transverse_basis_refs: tuple[str, ...] = ()
    transverse_basis_blockers: tuple[str, ...] = ()


def bind_reviewed_column_design_basis(
    basis: ReviewedColumnDesignBasis,
    *,
    component_id: str,
    section_id: str,
    factual_concrete_usage: MaterialUsageReference,
    factual_concrete_definition: UsedMaterialDefinition,
    factual_rebar_intent: EtabsColumnRebarIntentEvidence,
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
    if not isinstance(factual_rebar_intent, EtabsColumnRebarIntentEvidence):
        raise TypeError("factual_rebar_intent must be EtabsColumnRebarIntentEvidence")

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
    if factual_rebar_intent.section_name != section:
        raise ColumnDesignBasisError("rebar intent section differs from target Column section")
    long_name = _text(factual_rebar_intent.mat_prop_long, "rebar_intent.mat_prop_long")
    transverse_name = _text(
        factual_rebar_intent.mat_prop_confine,
        "rebar_intent.mat_prop_confine",
    )

    reviewed_concrete = basis.concrete_for(concrete_name)
    reviewed_steel = basis.steel_for(long_name)

    concrete_fact_ref = (
        f"ETABS:UsedRcMaterialPopulation:{factual_concrete_usage.usage_id}:"
        f"{factual_concrete_definition.material_id}:{concrete_name}:fck={fck_mpa:.12g}MPa"
    )
    steel_fact_ref = f"ETABS:PropFrame.GetRebarColumn:{section}:MatPropLong={long_name}"
    transverse_fact_ref = (
        f"ETABS:PropFrame.GetRebarColumn:{section}:MatPropConfine={transverse_name}"
    )

    transverse_matches = tuple(
        item
        for item in basis.transverse_steel_strengths
        if item.material_name == transverse_name
    )
    transverse_blockers: list[str] = []
    transverse_review_refs: tuple[str, ...] = ()
    transverse_fywk_mpa = None
    transverse_fywd_mpa = None
    if len(transverse_matches) == 1:
        reviewed_transverse = transverse_matches[0]
        transverse_fywk_mpa = reviewed_transverse.fywk_mpa
        transverse_fywd_mpa = reviewed_transverse.fywd_mpa
        transverse_review_refs = tuple(reviewed_transverse.review_refs)
    elif not basis.transverse_steel_strengths:
        transverse_blockers.append("TRANSVERSE_STEEL_DESIGN_BASIS_NOT_REVIEWED")
    else:
        transverse_blockers.append(
            f"TRANSVERSE_STEEL_MATERIAL_APPLICABILITY_MISMATCH:{transverse_name}"
        )

    if basis.high_ductility_applies is None and basis.limited_ductility_applies is None:
        transverse_blockers.append("COLUMN_DUCTILITY_APPLICABILITY_NOT_REVIEWED")

    section_binding_ref = _stable_ref(
        "column-section-material-binding:sha256:",
        {
            "component_id": component,
            "section_id": section,
            "usage_id": factual_concrete_usage.usage_id,
            "material_id": factual_concrete_definition.material_id,
            "concrete_material_name": concrete_name,
            "longitudinal_material_name": long_name,
            "transverse_material_name": transverse_name,
            "model_fingerprint": model,
            "evidence_epoch_id": epoch,
            "concrete_fact_ref": concrete_fact_ref,
            "steel_fact_ref": steel_fact_ref,
            "transverse_fact_ref": transverse_fact_ref,
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
    transverse_basis_refs = tuple(
        dict.fromkeys(
            (
                *basis.basis_refs,
                *transverse_review_refs,
                *basis.transverse_policy_refs,
                transverse_fact_ref,
            )
        )
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
                transverse_fact_ref,
                *transverse_review_refs,
                *basis.transverse_policy_refs,
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
            "transverse_material_name": transverse_name,
            "transverse_fywk_mpa": transverse_fywk_mpa,
            "transverse_fywd_mpa": transverse_fywd_mpa,
            "high_ductility_applies": basis.high_ductility_applies,
            "limited_ductility_applies": basis.limited_ductility_applies,
            "transverse_basis_blockers": tuple(transverse_blockers),
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
        transverse_material_name=transverse_name,
        transverse_fywk_mpa=transverse_fywk_mpa,
        transverse_fywd_mpa=transverse_fywd_mpa,
        high_ductility_applies=basis.high_ductility_applies,
        limited_ductility_applies=basis.limited_ductility_applies,
        transverse_basis_refs=transverse_basis_refs,
        transverse_basis_blockers=tuple(transverse_blockers),
    )


__all__ = [
    "BoundColumnActionFamilyApplicability",
    "BoundColumnDesignBasis",
    "COLUMN_ROUTE_C_SUPPORTED_PATH",
    "COLUMN_ROUTE_C_W_ACTION_FAMILY",
    "COLUMN_ROUTE_C_W_APPLICABILITY_BASIS_VERSION",
    "COLUMN_ROUTE_C_W_APPLICABILITY_BINDING",
    "COLUMN_ROUTE_C_W_APPLICABILITY_BINDING_ID",
    "COLUMN_DESIGN_BASIS_AUTHORITY",
    "COLUMN_DESIGN_BASIS_BINDING_AUTHORITY",
    "COLUMN_STORY_TRANSLATION_TOLERANCE_BASIS_VERSION",
    "ColumnDesignBasisError",
    "ReviewedActionFamilyApplicability",
    "ReviewedAggregateBasis",
    "ReviewedColumnDesignBasis",
    "ReviewedConcreteDesignStrength",
    "ReviewedLongitudinalSteelDesignStrength",
    "ReviewedTransverseSteelDesignStrength",
    "bind_reviewed_column_design_basis",
    "bind_reviewed_route_c_w_applicability",
]
