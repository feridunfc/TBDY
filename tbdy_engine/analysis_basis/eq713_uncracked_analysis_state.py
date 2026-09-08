"""TS 500 Eq. 7.13 whole-system uncracked analysis-state authority.

Pure engineering authority only: no ETABS acquisition, mutation, analysis, or
lifecycle ownership lives here.  Same-epoch factual callers must prove gross
geometry/material and mode participation before a mutation target can exist.
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

TS500_EQ713_UNCRACKED_ANALYSIS_STATE_CONTRACT = "TS500_EQ713_UNCRACKED_ANALYSIS_STATE_V1"
TS500_EQ713_SOURCE_REF = "TS500_2000_7_6_2_1_EQ_7_13"
AREA_PROPERTY_MODIFIER_SOURCE_REF = "CSI:PropArea.GetModifiers:10_SLOT_SEMANTICS"
AREA_OBJECT_UNITY_NEUTRALITY_CONTRACT = "AREA_OBJECT_MODIFIER_VECTOR_ALL_UNITY_IS_COMPOSITION_NEUTRAL_V1"


class Eq713AnalysisBasisError(RuntimeError):
    pass


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


_AREA_SLOT = {
    AreaStiffnessMode.F11: 0, AreaStiffnessMode.F22: 1,
    AreaStiffnessMode.F12: 2, AreaStiffnessMode.M11: 3,
    AreaStiffnessMode.M22: 4, AreaStiffnessMode.M12: 5,
    AreaStiffnessMode.V13: 6, AreaStiffnessMode.V23: 7,
}
_FRAME_SLOT = {
    FrameStiffnessMode.AXIAL: 0, FrameStiffnessMode.SHEAR_2: 1,
    FrameStiffnessMode.SHEAR_3: 2, FrameStiffnessMode.TORSION: 3,
    FrameStiffnessMode.FLEXURE_2: 4, FrameStiffnessMode.FLEXURE_3: 5,
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


def _vector(values: Sequence[object], length: int, label: str) -> tuple[Decimal, ...]:
    result = tuple(_decimal(v, f"{label}[{i}]") for i, v in enumerate(values))
    if len(result) != length:
        raise Eq713AnalysisBasisError(f"{label} must contain exactly {length} values")
    return result


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(dict.fromkeys(v for v in values if isinstance(v, str) and v.strip()))
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
        return self.ec_status is Ts500EcComparisonStatus.MATCH and self.gc_status is Ts500EcComparisonStatus.MATCH


def build_concrete_uncracked_material_basis(*, material_name: str, fck_mpa: object,
        factual_ec_mpa: object, factual_gc_mpa: object,
        source_refs: Sequence[str]) -> ConcreteUncrackedMaterialBasis:
    ec = compare_etabs_ec_to_ts500_table_3_2(
        concrete_fck_mpa=fck_mpa, factual_etabs_ec_mpa=factual_ec_mpa
    )
    if ec.required_ts500_ec_mpa is None:
        return ConcreteUncrackedMaterialBasis(
            material_name, ec.fck_mpa, ec.factual_etabs_ec_mpa,
            _decimal(factual_gc_mpa, "factual_gc_mpa"), None, None,
            ec.status, Ts500EcComparisonStatus.UNRESOLVED,
            _refs((*source_refs, *ec.source_refs)),
        )
    gc = compare_etabs_gc_to_ts500_eq_3_3(
        required_ts500_ec_mpa=ec.required_ts500_ec_mpa,
        factual_etabs_gc_mpa=factual_gc_mpa,
    )
    return ConcreteUncrackedMaterialBasis(
        material_name, ec.fck_mpa, ec.factual_etabs_ec_mpa,
        gc.factual_etabs_gc_mpa, ec.required_ts500_ec_mpa,
        gc.required_ts500_gc_mpa, ec.status, gc.status,
        _refs((*source_refs, *ec.source_refs, *gc.source_refs)),
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
    def build(cls, *, area_name: str, property_name: str, category: AreaCategory,
            formulation: AreaFormulation, is_concrete: bool,
            gross_geometry_proven: bool, thickness_proven: bool,
            homogeneous_simple_property: bool, material_overwrite_qualified: bool,
            thickness_overwrite_qualified: bool, property_modifiers: Sequence[object],
            object_modifiers: Sequence[object],
            material_basis: ConcreteUncrackedMaterialBasis | None,
            semi_rigid_diaphragm_participation: bool | None = None,
            wall_role: WallRole | None = None,
            default_wall_local_axes_proven: bool | None = None,
            plate_participation: bool | None = None,
            transverse_shear_participation: bool | None = None,
            source_refs: Sequence[str]) -> "AreaGrossBasePropertyEvidence":
        return cls(
            area_name, property_name, category, formulation, bool(is_concrete),
            bool(gross_geometry_proven), bool(thickness_proven),
            bool(homogeneous_simple_property), bool(material_overwrite_qualified),
            bool(thickness_overwrite_qualified),
            _vector(property_modifiers, 10, "property_modifiers"),
            _vector(object_modifiers, 10, "object_modifiers"), material_basis,
            semi_rigid_diaphragm_participation, wall_role,
            default_wall_local_axes_proven, plate_participation,
            transverse_shear_participation, _refs(source_refs),
        )

    @property
    def object_modifiers_unity(self) -> bool:
        return all(v == Decimal("1") for v in self.object_modifiers)

    @property
    def gross_base_qualified(self) -> bool:
        if self.category is AreaCategory.NULL or not self.is_concrete:
            return True
        return all((self.gross_geometry_proven, self.thickness_proven,
                    self.homogeneous_simple_property,
                    self.material_overwrite_qualified,
                    self.thickness_overwrite_qualified)) and self.material_basis is not None and self.material_basis.qualified


@dataclass(frozen=True, slots=True)
class AreaEq713TargetDisposition:
    area_name: str
    mode_dispositions: tuple[ModeDisposition, ...]
    target_property_modifiers: tuple[Decimal, ...] | None
    blocked_reasons: tuple[str, ...]
    source_refs: tuple[str, ...]

    @property
    def qualified(self) -> bool:
        return not self.blocked_reasons

    @property
    def applicable(self) -> bool:
        return any(r.disposition is ContributorDisposition.TARGETED_UNCRACKED for r in self.mode_dispositions)


def _all_area(fact: AreaGrossBasePropertyEvidence, disposition: ContributorDisposition,
              reason: str, *, target: tuple[Decimal, ...] | None = None) -> AreaEq713TargetDisposition:
    refs = _refs((*fact.source_refs, TS500_EQ713_SOURCE_REF, AREA_PROPERTY_MODIFIER_SOURCE_REF))
    rows = tuple(ModeDisposition(m, disposition, reason, refs) for m in AreaStiffnessMode)
    blocked = (reason,) if disposition is ContributorDisposition.BLOCKED_UNSUPPORTED else ()
    return AreaEq713TargetDisposition(fact.area_name, rows, target, blocked, refs)


def build_area_eq713_target(fact: AreaGrossBasePropertyEvidence) -> AreaEq713TargetDisposition:
    refs = _refs((*fact.source_refs, TS500_EQ713_SOURCE_REF, AREA_PROPERTY_MODIFIER_SOURCE_REF))
    if fact.category is AreaCategory.NULL:
        return _all_area(fact, ContributorDisposition.PROVEN_NOT_APPLICABLE,
                         "Null/no-property Area has no shell-section stiffness target")
    if not fact.object_modifiers_unity:
        return _all_area(fact, ContributorDisposition.BLOCKED_UNSUPPORTED,
                         "non-unity AreaObj modifier vector has no independently proven slot semantics")
    if not fact.is_concrete:
        return _all_area(fact, ContributorDisposition.PROVEN_NOT_APPLICABLE,
                         "TS500 concrete cracking normalization is not applied to non-concrete Area property")
    if not fact.gross_base_qualified:
        reasons = []
        if not fact.gross_geometry_proven: reasons.append("gross geometry not proven")
        if not fact.thickness_proven: reasons.append("gross thickness not proven")
        if not fact.homogeneous_simple_property: reasons.append("unsupported layered/equivalent/composite property")
        if not fact.material_overwrite_qualified: reasons.append("material overwrite not qualified")
        if not fact.thickness_overwrite_qualified: reasons.append("thickness overwrite not qualified")
        if fact.material_basis is None: reasons.append("concrete Ec/Gc material basis missing")
        elif not fact.material_basis.qualified: reasons.append("concrete Ec/Gc does not match the required TS500 uncracked elastic basis")
        return _all_area(fact, ContributorDisposition.BLOCKED_UNSUPPORTED, "; ".join(reasons))
    if fact.formulation not in {AreaFormulation.SHELL_THICK, AreaFormulation.MEMBRANE}:
        return _all_area(fact, ContributorDisposition.BLOCKED_UNSUPPORTED, "unsupported Area formulation")

    dispositions: dict[AreaStiffnessMode, ModeDisposition] = {}
    target = list(fact.property_modifiers)

    def mark(modes, disposition, reason, normalize=False):
        for mode in modes:
            if normalize: target[_AREA_SLOT[mode]] = Decimal("1")
            dispositions[mode] = ModeDisposition(mode, disposition, reason, refs)

    in_plane = (AreaStiffnessMode.F11, AreaStiffnessMode.F22, AreaStiffnessMode.F12)
    plate = (AreaStiffnessMode.M11, AreaStiffnessMode.M22, AreaStiffnessMode.M12)
    transverse = (AreaStiffnessMode.V13, AreaStiffnessMode.V23)

    if fact.category is AreaCategory.FLOOR:
        if fact.semi_rigid_diaphragm_participation is not True:
            return _all_area(fact, ContributorDisposition.BLOCKED_UNSUPPORTED,
                             "floor in-plane Eq7.13 participation is not positively established as semi-rigid diaphragm response")
        mark(in_plane, ContributorDisposition.TARGETED_UNCRACKED,
             "participating concrete semi-rigid diaphragm in-plane normal/shear stiffness", True)
        if fact.formulation is AreaFormulation.MEMBRANE:
            mark((*plate, *transverse), ContributorDisposition.PROVEN_NOT_APPLICABLE,
                 "Membrane formulation has no plate-bending/transverse-shear mechanism")
        else:
            if fact.plate_participation is True:
                mark(plate, ContributorDisposition.TARGETED_UNCRACKED, "positively established participating plate response", True)
            elif fact.plate_participation is False:
                mark(plate, ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE, "plate response positively excluded from Eq7.13 displacement response")
            else:
                mark(plate, ContributorDisposition.BLOCKED_UNSUPPORTED, "plate participation in Eq7.13 displacement response is unresolved")
            if fact.transverse_shear_participation is True:
                mark(transverse, ContributorDisposition.TARGETED_UNCRACKED, "positively established participating thick-shell transverse shear", True)
            elif fact.transverse_shear_participation is False:
                mark(transverse, ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE, "transverse shear positively excluded from Eq7.13 displacement response")
            else:
                mark(transverse, ContributorDisposition.BLOCKED_UNSUPPORTED, "transverse-shear participation in Eq7.13 displacement response is unresolved")
    elif fact.category is AreaCategory.WALL:
        if fact.wall_role not in {WallRole.PIER, WallRole.SPANDREL}:
            return _all_area(fact, ContributorDisposition.BLOCKED_UNSUPPORTED, "wall pier/spandrel role is not positively established")
        if fact.default_wall_local_axes_proven is not True:
            return _all_area(fact, ContributorDisposition.BLOCKED_UNSUPPORTED, "wall local-axis mapping is not positively established")
        flex = AreaStiffnessMode.F22 if fact.wall_role is WallRole.PIER else AreaStiffnessMode.F11
        other = AreaStiffnessMode.F11 if flex is AreaStiffnessMode.F22 else AreaStiffnessMode.F22
        mark((flex, AreaStiffnessMode.F12), ContributorDisposition.TARGETED_UNCRACKED,
             f"{fact.wall_role.value.lower()} in-plane flexure plus participating wall in-plane shear", True)
        mark((other,), ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE,
             "other local membrane-normal family is not the established wall flexural mode")
        if fact.plate_participation is True:
            mark(plate, ContributorDisposition.TARGETED_UNCRACKED, "positively established participating wall out-of-plane bending", True)
        elif fact.plate_participation is False:
            mark(plate, ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE, "wall out-of-plane bending positively excluded from Eq7.13 response")
        else:
            mark(plate, ContributorDisposition.BLOCKED_UNSUPPORTED, "wall out-of-plane participation is unresolved")
        if fact.transverse_shear_participation is True:
            mark(transverse, ContributorDisposition.TARGETED_UNCRACKED, "positively established participating wall transverse shear", True)
        elif fact.transverse_shear_participation is False:
            mark(transverse, ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE, "wall transverse shear positively excluded from Eq7.13 response")
        else:
            mark(transverse, ContributorDisposition.BLOCKED_UNSUPPORTED, "wall transverse-shear participation is unresolved")
    else:
        return _all_area(fact, ContributorDisposition.BLOCKED_UNSUPPORTED, "unsupported Area category")

    rows = tuple(dispositions[m] for m in AreaStiffnessMode)
    blocked = tuple(dict.fromkeys(r.reason for r in rows if r.disposition is ContributorDisposition.BLOCKED_UNSUPPORTED))
    return AreaEq713TargetDisposition(
        fact.area_name, rows, tuple(target) if not blocked else None, blocked, refs
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

    @property
    def applicable(self) -> bool:
        return any(r.disposition is ContributorDisposition.TARGETED_UNCRACKED for r in self.mode_dispositions)


def audit_frame_eq713_modes(*, component_uid: str, property_modifiers: Sequence[object],
        object_modifiers: Sequence[object],
        participation: Mapping[FrameStiffnessMode, bool | None],
        material_basis: ConcreteUncrackedMaterialBasis,
        source_refs: Sequence[str]) -> FrameModeAuditDisposition:
    prop = _vector(property_modifiers, 8, "frame_property_modifiers")
    obj = _vector(object_modifiers, 8, "frame_object_modifiers")
    refs = _refs((*source_refs, TS500_EQ713_SOURCE_REF))
    rows, blocked = [], []
    for mode in FrameStiffnessMode:
        participates = participation.get(mode)
        if participates is None:
            disposition = ContributorDisposition.BLOCKED_UNSUPPORTED
            reason = f"{mode.value} participation in Eq7.13 Delta_i is unresolved"
            blocked.append(reason)
        elif not participates:
            disposition = ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE
            reason = f"{mode.value} positively excluded from Eq7.13 Delta_i response"
        elif not material_basis.qualified:
            disposition = ContributorDisposition.BLOCKED_UNSUPPORTED
            reason = "concrete Ec/Gc material basis is not qualified"
            blocked.append(reason)
        else:
            effective = prop[_FRAME_SLOT[mode]] * obj[_FRAME_SLOT[mode]]
            disposition = ContributorDisposition.TARGETED_UNCRACKED
            reason = f"participating {mode.value} effective modifier={effective}; gross target is effective modifier 1 on a qualified gross material/geometry basis"
        rows.append(ModeDisposition(mode, disposition, reason, refs))
    return FrameModeAuditDisposition(component_uid, tuple(rows), tuple(dict.fromkeys(blocked)), refs)


@dataclass(frozen=True, slots=True)
class Eq713PopulationDisposition:
    area_rows: tuple[AreaEq713TargetDisposition, ...]
    frame_rows: tuple[FrameModeAuditDisposition, ...]

    @property
    def expected_applicable_contributors(self) -> tuple[str, ...]:
        values = [f"AREA:{r.area_name}" for r in self.area_rows if r.applicable]
        values.extend(f"FRAME:{r.component_uid}" for r in self.frame_rows if r.applicable)
        return tuple(sorted(values))

    @property
    def qualified_contributors(self) -> tuple[str, ...]:
        values = [f"AREA:{r.area_name}" for r in self.area_rows if r.applicable and r.qualified]
        values.extend(f"FRAME:{r.component_uid}" for r in self.frame_rows if r.applicable and r.qualified)
        return tuple(sorted(values))

    @property
    def positive(self) -> bool:
        return all(r.qualified for r in self.area_rows) and all(r.qualified for r in self.frame_rows) and self.expected_applicable_contributors == self.qualified_contributors


__all__ = [
    "AREA_OBJECT_UNITY_NEUTRALITY_CONTRACT", "AREA_PROPERTY_MODIFIER_SOURCE_REF",
    "TS500_EQ713_SOURCE_REF", "TS500_EQ713_UNCRACKED_ANALYSIS_STATE_CONTRACT",
    "AreaCategory", "AreaEq713TargetDisposition", "AreaFormulation",
    "AreaGrossBasePropertyEvidence", "AreaStiffnessMode",
    "ConcreteUncrackedMaterialBasis", "ContributorDisposition",
    "Eq713AnalysisBasisError", "Eq713PopulationDisposition",
    "FrameModeAuditDisposition", "FrameStiffnessMode", "ModeDisposition", "WallRole",
    "audit_frame_eq713_modes", "build_area_eq713_target",
    "build_concrete_uncracked_material_basis",
]
