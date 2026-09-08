"""TS 500 Eq. 7.13 whole-system uncracked analysis-state authority.

This module is deliberately bounded to engineering target selection.  It does
not acquire ETABS facts, mutate ETABS, run analysis, or create a second B4B/B5
owner.  Inputs must already be factual, same-epoch evidence.

Canonical law:
- the governing Delta_i comes from one coherent participating structural state;
- every concrete section-stiffness mode participating in that response is on an
  uncracked/gross elastic basis;
- participation is mode-specific;
- non-participating modes, mass, and weight are preserved;
- unresolved gross geometry/material/formulation fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Mapping, Sequence

from tbdy_engine.regulatory.ts500_concrete_elastic_modulus import (
    Ts500EcComparisonStatus,
    compare_etabs_ec_to_ts500_table_3_2,
    compare_etabs_gc_to_ts500_eq_3_3,
)

TS500_EQ713_UNCRACKED_ANALYSIS_STATE_CONTRACT = (
    "TS500_EQ713_UNCRACKED_ANALYSIS_STATE_V1"
)
TS500_EQ713_SOURCE_REF = "TS500_2000_7_6_2_1_EQ_7_13"
AREA_PROPERTY_MODIFIER_SOURCE_REF = "CSI:PropArea.GetModifiers:10_SLOT_SEMANTICS"
AREA_OBJECT_UNITY_NEUTRALITY_CONTRACT = (
    "AREA_OBJECT_MODIFIER_VECTOR_ALL_UNITY_IS_COMPOSITION_NEUTRAL_V1"
)


class Eq713AnalysisBasisError(RuntimeError):
    """Raised when an Eq. 7.13 target would require unsupported inference."""


class ContributorDisposition(StrEnum):
    TARGETED_UNCRACKED = "TARGETED_UNCRACKED"
    PROVEN_NON_PARTICIPATING_MODE = "PROVEN_NON_PARTICIPATING_MODE"
    PROVEN_NOT_APPLICABLE = "PROVEN_NOT_APPLICABLE"
    BLOCKED_UNSUPPORTED = "BLOCKED_UNSUPPORTED"


class AreaCategory(StrEnum):
    FLOOR = "FLOOR"
    WALL = "WALL"
    NULL = "NULL"


class AreaFormulation(StrEnum):
    SHELL_THICK = "SHELL_THICK"
    MEMBRANE = "MEMBRANE"
    OTHER = "OTHER"


class WallRole(StrEnum):
    PIER = "PIER"
    SPANDREL = "SPANDREL"
    OTHER = "OTHER"


class AreaStiffnessMode(StrEnum):
    F11 = "F11_MEMBRANE_NORMAL"
    F22 = "F22_MEMBRANE_NORMAL"
    F12 = "F12_MEMBRANE_SHEAR"
    M11 = "M11_PLATE_BENDING"
    M22 = "M22_PLATE_BENDING"
    M12 = "M12_PLATE_TWISTING"
    V13 = "V13_TRANSVERSE_SHEAR"
    V23 = "V23_TRANSVERSE_SHEAR"


class FrameStiffnessMode(StrEnum):
    AXIAL = "AXIAL"
    SHEAR_2 = "SHEAR_2"
    SHEAR_3 = "SHEAR_3"
    TORSION = "TORSION"
    FLEXURE_2 = "FLEXURE_2"
    FLEXURE_3 = "FLEXURE_3"


_AREA_SLOT_BY_MODE: dict[AreaStiffnessMode, int] = {
    AreaStiffnessMode.F11: 0,
    AreaStiffnessMode.F22: 1,
    AreaStiffnessMode.F12: 2,
    AreaStiffnessMode.M11: 3,
    AreaStiffnessMode.M22: 4,
    AreaStiffnessMode.M12: 5,
    AreaStiffnessMode.V13: 6,
    AreaStiffnessMode.V23: 7,
}

_FRAME_SLOT_BY_MODE: dict[FrameStiffnessMode, int] = {
    FrameStiffnessMode.AXIAL: 0,
    FrameStiffnessMode.SHEAR_2: 1,
    FrameStiffnessMode.SHEAR_3: 2,
    FrameStiffnessMode.TORSION: 3,
    FrameStiffnessMode.FLEXURE_2: 4,
    FrameStiffnessMode.FLEXURE_3: 5,
}


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise Eq713AnalysisBasisError(f"{label} must be numeric")
    try:
        result = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise Eq713AnalysisBasisError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise Eq713AnalysisBasisError(f"{label} must be finite")
    return result


def _vector(values: Sequence[object], *, length: int, label: str) -> tuple[Decimal, ...]:
    result = tuple(_decimal(value, f"{label}[{index}]") for index, value in enumerate(values))
    if len(result) != length:
        raise Eq713AnalysisBasisError(
            f"{label} must contain exactly {length} values; observed={len(result)}"
        )
    return result


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(dict.fromkeys(value for value in values if isinstance(value, str) and value.strip()))
    if not result:
        raise Eq713AnalysisBasisError("source_refs must not be empty")
    return result


@dataclass(frozen=True, slots=True)
class ConcreteUncrackedMaterialBasis:
    material_name: str
    fck_mpa: Decimal
    factual_ec_mpa: Decimal
    factual_gc_mpa: Decimal
    required_ec_mpa: Decimal | None
    required_gc_mpa: Decimal | None
    ec_status: Ts500EcComparisonStatus
    gc_status: Ts500EcComparisonStatus
    source_refs: tuple[str, ...]

    @property
    def qualified(self) -> bool:
        return (
            self.ec_status is Ts500EcComparisonStatus.MATCH
            and self.gc_status is Ts500EcComparisonStatus.MATCH
        )


def build_concrete_uncracked_material_basis(
    *,
    material_name: str,
    fck_mpa: object,
    factual_ec_mpa: object,
    factual_gc_mpa: object,
    source_refs: Sequence[str],
) -> ConcreteUncrackedMaterialBasis:
    ec = compare_etabs_ec_to_ts500_table_3_2(
        concrete_fck_mpa=fck_mpa,
        factual_etabs_ec_mpa=factual_ec_mpa,
    )
    if ec.required_ts500_ec_mpa is None:
        return ConcreteUncrackedMaterialBasis(
            material_name=material_name,
            fck_mpa=ec.fck_mpa,
            factual_ec_mpa=ec.factual_etabs_ec_mpa,
            factual_gc_mpa=_decimal(factual_gc_mpa, "factual_gc_mpa"),
            required_ec_mpa=None,
            required_gc_mpa=None,
            ec_status=ec.status,
            gc_status=Ts500EcComparisonStatus.UNRESOLVED,
            source_refs=_refs((*source_refs, *ec.source_refs)),
        )
    gc = compare_etabs_gc_to_ts500_eq_3_3(
        required_ts500_ec_mpa=ec.required_ts500_ec_mpa,
        factual_etabs_gc_mpa=factual_gc_mpa,
    )
    return ConcreteUncrackedMaterialBasis(
        material_name=material_name,
        fck_mpa=ec.fck_mpa,
        factual_ec_mpa=ec.factual_etabs_ec_mpa,
        factual_gc_mpa=gc.factual_etabs_gc_mpa,
        required_ec_mpa=ec.required_ts500_ec_mpa,
        required_gc_mpa=gc.required_ts500_gc_mpa,
        ec_status=ec.status,
        gc_status=gc.status,
        source_refs=_refs((*source_refs, *ec.source_refs, *gc.source_refs)),
    )


@dataclass(frozen=True, slots=True)
class ModeDisposition:
    mode: AreaStiffnessMode | FrameStiffnessMode
    disposition: ContributorDisposition
    reason: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AreaGrossBasePropertyEvidence:
    area_name: str
    property_name: str
    category: AreaCategory
    formulation: AreaFormulation
    is_concrete: bool
    gross_geometry_proven: bool
    thickness_proven: bool
    homogeneous_simple_property: bool
    material_overwrite_qualified: bool
    thickness_overwrite_qualified: bool
    property_modifiers: tuple[Decimal, ...]
    object_modifiers: tuple[Decimal, ...]
    material_basis: ConcreteUncrackedMaterialBasis | None
    semi_rigid_diaphragm_participation: bool | None
    wall_role: WallRole | None
    default_wall_local_axes_proven: bool | None
    plate_participation: bool | None
    transverse_shear_participation: bool | None
    source_refs: tuple[str, ...]

    @classmethod
    def build(
        cls,
        *,
        area_name: str,
        property_name: str,
        category: AreaCategory,
        formulation: AreaFormulation,
        is_concrete: bool,
        gross_geometry_proven: bool,
        thickness_proven: bool,
        homogeneous_simple_property: bool,
        material_overwrite_qualified: bool,
        thickness_overwrite_qualified: bool,
        property_modifiers: Sequence[object],
        object_modifiers: Sequence[object],
        material_basis: ConcreteUncrackedMaterialBasis | None,
        semi_rigid_diaphragm_participation: bool | None = None,
        wall_role: WallRole | None = None,
        default_wall_local_axes_proven: bool | None = None,
        plate_participation: bool | None = None,
        transverse_shear_participation: bool | None = None,
        source_refs: Sequence[str],
    ) -> "AreaGrossBasePropertyEvidence":
        return cls(
            area_name=area_name,
            property_name=property_name,
            category=category,
            formulation=formulation,
            is_concrete=bool(is_concrete),
            gross_geometry_proven=bool(gross_geometry_proven),
            thickness_proven=bool(thickness_proven),
            homogeneous_simple_property=bool(homogeneous_simple_property),
            material_overwrite_qualified=bool(material_overwrite_qualified),
            thickness_overwrite_qualified=bool(thickness_overwrite_qualified),
            property_modifiers=_vector(property_modifiers, length=10, label="property_modifiers"),
            object_modifiers=_vector(object_modifiers, length=10, label="object_modifiers"),
            material_basis=material_basis,
            semi_rigid_diaphragm_participation=semi_rigid_diaphragm_participation,
            wall_role=wall_role,
            default_wall_local_axes_proven=default_wall_local_axes_proven,
            plate_participation=plate_participation,
            transverse_shear_participation=transverse_shear_participation,
            source_refs=_refs(source_refs),
        )

    @property
    def object_modifier_vector_is_unity(self) -> bool:
        return all(value == Decimal("1") for value in self.object_modifiers)

    @property
    def gross_base_qualified(self) -> bool:
        if self.category is AreaCategory.NULL:
            return True
        if not self.is_concrete:
            return True
        return (
            self.gross_geometry_proven
            and self.thickness_proven
            and self.homogeneous_simple_property
            and self.material_overwrite_qualified
            and self.thickness_overwrite_qualified
            and self.material_basis is not None
            and self.material_basis.qualified
        )


@dataclass(frozen=True, slots=True)
class AreaEq713TargetDisposition:
    area_name: str
    mode_dispositions: tuple[ModeDisposition, ...]
    target_property_modifiers: tuple[Decimal, ...] | None
    blocked_reasons: tuple[str, ...]
    source_refs: tuple[str, ...]

    @property
    def qualified(self) -> bool:
        return not self.blocked_reasons and all(
            item.disposition is not ContributorDisposition.BLOCKED_UNSUPPORTED
            for item in self.mode_dispositions
        )


def _blocked_all_area_modes(
    fact: AreaGrossBasePropertyEvidence, reason: str
) -> AreaEq713TargetDisposition:
    refs = _refs((*fact.source_refs, TS500_EQ713_SOURCE_REF))
    return AreaEq713TargetDisposition(
        area_name=fact.area_name,
        mode_dispositions=tuple(
            ModeDisposition(
                mode=mode,
                disposition=ContributorDisposition.BLOCKED_UNSUPPORTED,
                reason=reason,
                source_refs=refs,
            )
            for mode in AreaStiffnessMode
        ),
        target_property_modifiers=None,
        blocked_reasons=(reason,),
        source_refs=refs,
    )


def build_area_eq713_target(
    fact: AreaGrossBasePropertyEvidence,
) -> AreaEq713TargetDisposition:
    """Build only source-supported changes; unresolved participation fails closed."""
    refs = _refs((*fact.source_refs, TS500_EQ713_SOURCE_REF, AREA_PROPERTY_MODIFIER_SOURCE_REF))
    if fact.category is AreaCategory.NULL:
        return AreaEq713TargetDisposition(
            area_name=fact.area_name,
            mode_dispositions=tuple(
                ModeDisposition(
                    mode=mode,
                    disposition=ContributorDisposition.PROVEN_NOT_APPLICABLE,
                    reason="Null/no-property Area has no shell-section stiffness target",
                    source_refs=refs,
                )
                for mode in AreaStiffnessMode
            ),
            target_property_modifiers=None,
            blocked_reasons=(),
            source_refs=refs,
        )
    if not fact.object_modifier_vector_is_unity:
        return _blocked_all_area_modes(
            fact,
            "non-unity AreaObj modifier vector has no independently proven slot semantics",
        )
    if not fact.is_concrete:
        return AreaEq713TargetDisposition(
            area_name=fact.area_name,
            mode_dispositions=tuple(
                ModeDisposition(
                    mode=mode,
                    disposition=ContributorDisposition.PROVEN_NOT_APPLICABLE,
                    reason="TS500 concrete cracking normalization is not applied to non-concrete Area property",
                    source_refs=refs,
                )
                for mode in AreaStiffnessMode
            ),
            target_property_modifiers=None,
            blocked_reasons=(),
            source_refs=refs,
        )
    if not fact.gross_base_qualified:
        reasons: list[str] = []
        if not fact.gross_geometry_proven:
            reasons.append("gross geometry not proven")
        if not fact.thickness_proven:
            reasons.append("gross thickness not proven")
        if not fact.homogeneous_simple_property:
            reasons.append("property is layered/equivalent/composite or otherwise unsupported")
        if not fact.material_overwrite_qualified:
            reasons.append("material overwrite not qualified")
        if not fact.thickness_overwrite_qualified:
            reasons.append("thickness overwrite not qualified")
        if fact.material_basis is None:
            reasons.append("concrete Ec/Gc material basis missing")
        elif not fact.material_basis.qualified:
            reasons.append(
                "concrete Ec/Gc does not match the required TS500 uncracked elastic basis"
            )
        return _blocked_all_area_modes(fact, "; ".join(reasons))
    if fact.formulation not in {AreaFormulation.SHELL_THICK, AreaFormulation.MEMBRANE}:
        return _blocked_all_area_modes(fact, "unsupported Area formulation")

    dispositions: dict[AreaStiffnessMode, ModeDisposition] = {}
    target = list(fact.property_modifiers)

    def mark_target(*modes: AreaStiffnessMode, reason: str) -> None:
        for mode in modes:
            target[_AREA_SLOT_BY_MODE[mode]] = Decimal("1")
            dispositions[mode] = ModeDisposition(
                mode=mode,
                disposition=ContributorDisposition.TARGETED_UNCRACKED,
                reason=reason,
                source_refs=refs,
            )

    def mark_nonparticipating(*modes: AreaStiffnessMode, reason: str) -> None:
        for mode in modes:
            dispositions[mode] = ModeDisposition(
                mode=mode,
                disposition=ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE,
                reason=reason,
                source_refs=refs,
            )

    def mark_not_applicable(*modes: AreaStiffnessMode, reason: str) -> None:
        for mode in modes:
            dispositions[mode] = ModeDisposition(
                mode=mode,
                disposition=ContributorDisposition.PROVEN_NOT_APPLICABLE,
                reason=reason,
                source_refs=refs,
            )

    def mark_blocked(*modes: AreaStiffnessMode, reason: str) -> None:
        for mode in modes:
            dispositions[mode] = ModeDisposition(
                mode=mode,
                disposition=ContributorDisposition.BLOCKED_UNSUPPORTED,
                reason=reason,
                source_refs=refs,
            )

    if fact.category is AreaCategory.FLOOR:
        if fact.semi_rigid_diaphragm_participation is not True:
            return _blocked_all_area_modes(
                fact,
                "floor in-plane Eq7.13 participation is not positively established as semi-rigid diaphragm response",
            )
        mark_target(
            AreaStiffnessMode.F11,
            AreaStiffnessMode.F22,
            AreaStiffnessMode.F12,
            reason="participating concrete semi-rigid diaphragm in-plane normal/shear stiffness",
        )
        if fact.formulation is AreaFormulation.MEMBRANE:
            mark_not_applicable(
                AreaStiffnessMode.M11,
                AreaStiffnessMode.M22,
                AreaStiffnessMode.M12,
                AreaStiffnessMode.V13,
                AreaStiffnessMode.V23,
                reason="Membrane formulation has no plate-bending/transverse-shear mechanism",
            )
        else:
            plate_modes = (
                AreaStiffnessMode.M11,
                AreaStiffnessMode.M22,
                AreaStiffnessMode.M12,
            )
            if fact.plate_participation is True:
                mark_target(*plate_modes, reason="positively established participating plate response")
            elif fact.plate_participation is False:
                mark_nonparticipating(*plate_modes, reason="plate response positively excluded from Eq7.13 displacement response")
            else:
                mark_blocked(*plate_modes, reason="plate participation in Eq7.13 displacement response is unresolved")
            shear_modes = (AreaStiffnessMode.V13, AreaStiffnessMode.V23)
            if fact.transverse_shear_participation is True:
                mark_target(*shear_modes, reason="positively established participating thick-shell transverse shear")
            elif fact.transverse_shear_participation is False:
                mark_nonparticipating(*shear_modes, reason="transverse shear positively excluded from Eq7.13 displacement response")
            else:
                mark_blocked(*shear_modes, reason="transverse-shear participation in Eq7.13 displacement response is unresolved")
    elif fact.category is AreaCategory.WALL:
        if fact.wall_role not in {WallRole.PIER, WallRole.SPANDREL}:
            return _blocked_all_area_modes(fact, "wall pier/spandrel role is not positively established")
        if fact.default_wall_local_axes_proven is not True:
            return _blocked_all_area_modes(fact, "wall local-axis mapping is not positively established")
        normal_mode = (
            AreaStiffnessMode.F22
            if fact.wall_role is WallRole.PIER
            else AreaStiffnessMode.F11
        )
        other_normal = (
            AreaStiffnessMode.F11
            if normal_mode is AreaStiffnessMode.F22
            else AreaStiffnessMode.F22
        )
        mark_target(normal_mode, reason=f"{fact.wall_role.value.lower()} in-plane flexure")
        mark_target(AreaStiffnessMode.F12, reason="participating wall in-plane shear")
        mark_nonparticipating(other_normal, reason="other local membrane-normal family is not the established wall flexural mode")
        plate_modes = (
            AreaStiffnessMode.M11,
            AreaStiffnessMode.M22,
            AreaStiffnessMode.M12,
        )
        if fact.plate_participation is True:
            mark_target(*plate_modes, reason="positively established participating wall out-of-plane bending")
        elif fact.plate_participation is False:
            mark_nonparticipating(*plate_modes, reason="wall out-of-plane bending positively excluded from Eq7.13 response")
        else:
            mark_blocked(*plate_modes, reason="wall out-of-plane participation is unresolved")
        shear_modes = (AreaStiffnessMode.V13, AreaStiffnessMode.V23)
        if fact.transverse_shear_participation is True:
            mark_target(*shear_modes, reason="positively established participating wall transverse shear")
        elif fact.transverse_shear_participation is False:
            mark_nonparticipating(*shear_modes, reason="wall transverse shear positively excluded from Eq7.13 response")
        else:
            mark_blocked(*shear_modes, reason="wall transverse-shear participation is unresolved")
    else:
        return _blocked_all_area_modes(fact, "unsupported Area category")

    ordered = tuple(dispositions[mode] for mode in AreaStiffnessMode)
    blocked = tuple(item.reason for item in ordered if item.disposition is ContributorDisposition.BLOCKED_UNSUPPORTED)
    return AreaEq713TargetDisposition(
        area_name=fact.area_name,
        mode_dispositions=ordered,
        target_property_modifiers=tuple(target) if not blocked else None,
        blocked_reasons=tuple(dict.fromkeys(blocked)),
        source_refs=refs,
    )


@dataclass(frozen=True, slots=True)
class FrameModeAuditDisposition:
    component_uid: str
    mode_dispositions: tuple[ModeDisposition, ...]
    blocked_reasons: tuple[str, ...]
    source_refs: tuple[str, ...]

    @property
    def qualified(self) -> bool:
        return not self.blocked_reasons


def audit_frame_eq713_modes(
    *,
    component_uid: str,
    property_modifiers: Sequence[object],
    object_modifiers: Sequence[object],
    participation: Mapping[FrameStiffnessMode, bool | None],
    material_basis: ConcreteUncrackedMaterialBasis,
    source_refs: Sequence[str],
) -> FrameModeAuditDisposition:
    """Audit documented frame stiffness modes without inventing participation."""
    prop = _vector(property_modifiers, length=8, label="frame_property_modifiers")
    obj = _vector(object_modifiers, length=8, label="frame_object_modifiers")
    refs = _refs((*source_refs, TS500_EQ713_SOURCE_REF))
    rows: list[ModeDisposition] = []
    blocked: list[str] = []
    for mode in FrameStiffnessMode:
        participates = participation.get(mode)
        if participates is None:
            reason = f"{mode.value} participation in Eq7.13 Delta_i is unresolved"
            disposition = ContributorDisposition.BLOCKED_UNSUPPORTED
            blocked.append(reason)
        elif participates is False:
            reason = f"{mode.value} positively excluded from Eq7.13 Delta_i response"
            disposition = ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE
        elif not material_basis.qualified:
            reason = "concrete Ec/Gc material basis is not qualified"
            disposition = ContributorDisposition.BLOCKED_UNSUPPORTED
            blocked.append(reason)
        else:
            effective = prop[_FRAME_SLOT_BY_MODE[mode]] * obj[_FRAME_SLOT_BY_MODE[mode]]
            reason = (
                f"participating {mode.value} effective modifier={effective}; "
                "gross target is effective modifier 1 with gross material/geometry basis"
            )
            disposition = ContributorDisposition.TARGETED_UNCRACKED
        rows.append(
            ModeDisposition(
                mode=mode,
                disposition=disposition,
                reason=reason,
                source_refs=refs,
            )
        )
    return FrameModeAuditDisposition(
        component_uid=component_uid,
        mode_dispositions=tuple(rows),
        blocked_reasons=tuple(dict.fromkeys(blocked)),
        source_refs=refs,
    )


@dataclass(frozen=True, slots=True)
class Eq713PopulationDisposition:
    area_rows: tuple[AreaEq713TargetDisposition, ...]
    frame_rows: tuple[FrameModeAuditDisposition, ...]

    @property
    def expected_applicable_contributors(self) -> tuple[str, ...]:
        values: list[str] = []
        for row in self.area_rows:
            if any(
                item.disposition is ContributorDisposition.TARGETED_UNCRACKED
                for item in row.mode_dispositions
            ):
                values.append(f"AREA:{row.area_name}")
        for row in self.frame_rows:
            if any(
                item.disposition is ContributorDisposition.TARGETED_UNCRACKED
                for item in row.mode_dispositions
            ):
                values.append(f"FRAME:{row.component_uid}")
        return tuple(sorted(values))

    @property
    def qualified_contributors(self) -> tuple[str, ...]:
        values = [f"AREA:{row.area_name}" for row in self.area_rows if row.qualified]
        values.extend(f"FRAME:{row.component_uid}" for row in self.frame_rows if row.qualified)
        return tuple(sorted(values))

    @property
    def positive(self) -> bool:
        return (
            all(row.qualified for row in self.area_rows)
            and all(row.qualified for row in self.frame_rows)
            and self.expected_applicable_contributors == self.qualified_contributors
        )


__all__ = [
    "AREA_OBJECT_UNITY_NEUTRALITY_CONTRACT",
    "AREA_PROPERTY_MODIFIER_SOURCE_REF",
    "TS500_EQ713_SOURCE_REF",
    "TS500_EQ713_UNCRACKED_ANALYSIS_STATE_CONTRACT",
    "AreaCategory",
    "AreaEq713TargetDisposition",
    "AreaFormulation",
    "AreaGrossBasePropertyEvidence",
    "AreaStiffnessMode",
    "ConcreteUncrackedMaterialBasis",
    "ContributorDisposition",
    "Eq713AnalysisBasisError",
    "Eq713PopulationDisposition",
    "FrameModeAuditDisposition",
    "FrameStiffnessMode",
    "ModeDisposition",
    "WallRole",
    "audit_frame_eq713_modes",
    "build_area_eq713_target",
    "build_concrete_uncracked_material_basis",
]
