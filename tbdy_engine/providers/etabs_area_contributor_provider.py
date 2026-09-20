"""Exact live ETABS Area contributor factual population for COLUMN-R1 A2/A3.

The provider composes existing typed OAPI owners and preserves factual surfaces
without deciding TS500 Eq.7.13 applicability. In particular, Area-object and
Area-property modifier vectors remain separate and no AreaObj slot is assigned
PropArea engineering meaning here. A3 extends the same population with exact
floor-diaphragm and wall pier/spandrel assignment facts; those facts remain
factual and do not themselves decide Eq.7.13 participation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping, Sequence

from tbdy_engine.etabs.oapi.area_contributors import (
    AreaDesignOrientation,
    AreaDiaphragmAssignmentFact,
    AreaPropertyFamilyProbeFact,
    AreaWallAssignmentFact,
    DiaphragmDefinitionFact,
    read_area_design_orientation_from_session,
    read_area_diaphragm_assignment_from_session,
    read_area_local_axes_from_session,
    read_area_material_overwrite_from_session,
    read_area_transformation_matrix_from_session,
    read_area_wall_assignments_from_session,
    read_deck_property_probe_from_session,
    read_diaphragm_definition_from_session,
    read_slab_property_probe_from_session,
)
from tbdy_engine.etabs.oapi.area_modifiers import (
    AreaModifierReadFact,
    AreaModifierSurface,
    get_area_modifiers_from_session,
)
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError, WallPropertyFact
from tbdy_engine.etabs.oapi.object_model import (
    read_area_names_from_session,
    read_area_property_assignment_from_session,
    read_wall_property_from_session,
)
from tbdy_engine.etabs.safety import EtabsVerifiedSession
from tbdy_engine.providers.etabs_frame_flexural_base_provider import (
    FrameFlexuralBaseCaptureSnapshot,
    FrameFlexuralBaseFactError,
    TABLE_BASIC_MATERIAL,
    TABLE_CONCRETE,
    _pick as _snapshot_pick,
    _row_ref as _snapshot_row_ref,
    _stress_to_mpa,
)


class EtabsAreaContributorProviderError(RuntimeError):
    """Raised when the exact A2/A3 factual population cannot be captured truthfully."""


class AreaPropertyFamily(StrEnum):
    NONE = "NONE"
    SLAB = "SLAB"
    WALL = "WALL"
    DECK = "DECK"
    UNRESOLVED = "UNRESOLVED"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsAreaContributorProviderError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(dict.fromkeys(_text(value, "source_ref") for value in values))
    if not result:
        raise EtabsAreaContributorProviderError("source_refs must not be empty")
    return result


@dataclass(frozen=True, slots=True)
class AreaPropertyFactualState:
    property_name: str
    family: AreaPropertyFamily
    family_type_code: int | None
    shell_type_code: int | None
    material_name: str | None
    thickness: float | None
    property_modifiers: AreaModifierReadFact
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "property_name", _text(self.property_name, "property_name")
        )
        if not isinstance(self.family, AreaPropertyFamily):
            raise TypeError("family must be AreaPropertyFamily")
        if not isinstance(self.property_modifiers, AreaModifierReadFact):
            raise TypeError("property_modifiers must be AreaModifierReadFact")
        if self.property_modifiers.surface is not AreaModifierSurface.AREA_PROPERTY:
            raise EtabsAreaContributorProviderError(
                "property_modifiers must come from AREA_PROPERTY surface"
            )
        if self.property_modifiers.target_name != self.property_name:
            raise EtabsAreaContributorProviderError(
                "property modifier target does not match property identity"
            )
        if not self.property_modifiers.success:
            raise EtabsAreaContributorProviderError(
                f"PropArea.GetModifiers failed for {self.property_name!r}"
            )
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


@dataclass(frozen=True, slots=True)
class AreaContributorFact:
    area_name: str
    orientation: AreaDesignOrientation
    property_name: str
    property_state: AreaPropertyFactualState | None
    local_axes_angle_degrees: float
    advanced_local_axes: bool
    transformation_matrix: tuple[float, ...]
    raw_material_overwrite_name: str
    object_modifiers: AreaModifierReadFact
    diaphragm_assignment: AreaDiaphragmAssignmentFact | None
    diaphragm_definition: DiaphragmDefinitionFact | None
    wall_assignment: AreaWallAssignmentFact | None
    model_fingerprint: str
    evidence_epoch_id: str
    session_provenance_ref: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "area_name", _text(self.area_name, "area_name"))
        if not isinstance(self.orientation, AreaDesignOrientation):
            raise TypeError("orientation must be AreaDesignOrientation")
        object.__setattr__(
            self, "property_name", _text(self.property_name, "property_name")
        )
        if self.property_name == "None":
            if self.property_state is not None:
                raise EtabsAreaContributorProviderError(
                    "unassigned Area property cannot have property_state"
                )
        else:
            if not isinstance(self.property_state, AreaPropertyFactualState):
                raise EtabsAreaContributorProviderError(
                    "assigned Area property requires typed property_state"
                )
            if self.property_state.property_name != self.property_name:
                raise EtabsAreaContributorProviderError(
                    "Area property assignment/state identity mismatch"
                )
        if len(tuple(self.transformation_matrix)) != 9:
            raise EtabsAreaContributorProviderError(
                "transformation_matrix must contain exactly 9 factual values"
            )
        if type(self.advanced_local_axes) is not bool:
            raise TypeError("advanced_local_axes must be bool")
        if not isinstance(self.object_modifiers, AreaModifierReadFact):
            raise TypeError("object_modifiers must be AreaModifierReadFact")
        if self.object_modifiers.surface is not AreaModifierSurface.AREA_OBJECT:
            raise EtabsAreaContributorProviderError(
                "object_modifiers must come from AREA_OBJECT surface"
            )
        if self.object_modifiers.target_name != self.area_name:
            raise EtabsAreaContributorProviderError(
                "AreaObj modifier target does not match area identity"
            )
        if not self.object_modifiers.success:
            raise EtabsAreaContributorProviderError(
                f"AreaObj.GetModifiers failed for {self.area_name!r}"
            )

        if self.orientation is AreaDesignOrientation.FLOOR:
            if not isinstance(self.diaphragm_assignment, AreaDiaphragmAssignmentFact):
                raise EtabsAreaContributorProviderError(
                    "Floor Area requires typed diaphragm assignment fact"
                )
            if self.diaphragm_assignment.area_name != self.area_name:
                raise EtabsAreaContributorProviderError(
                    "diaphragm assignment does not match Area identity"
                )
            if not self.diaphragm_assignment.success:
                raise EtabsAreaContributorProviderError(
                    "AreaObj.GetDiaphragm failed for Floor Area"
                )
            if self.diaphragm_assignment.assigned:
                if not isinstance(self.diaphragm_definition, DiaphragmDefinitionFact):
                    raise EtabsAreaContributorProviderError(
                        "assigned Floor diaphragm requires typed definition fact"
                    )
                if (
                    self.diaphragm_definition.diaphragm_name
                    != self.diaphragm_assignment.diaphragm_name
                ):
                    raise EtabsAreaContributorProviderError(
                        "diaphragm definition does not match Area assignment"
                    )
                if not self.diaphragm_definition.success:
                    raise EtabsAreaContributorProviderError(
                        "Diaphragm.GetDiaphragm failed for assigned Floor diaphragm"
                    )
            elif self.diaphragm_definition is not None:
                raise EtabsAreaContributorProviderError(
                    "unassigned Floor diaphragm cannot carry a definition fact"
                )
        elif self.diaphragm_assignment is not None or self.diaphragm_definition is not None:
            raise EtabsAreaContributorProviderError(
                "diaphragm facts are bounded to Floor Area contributors"
            )

        if self.orientation is AreaDesignOrientation.WALL:
            if not isinstance(self.wall_assignment, AreaWallAssignmentFact):
                raise EtabsAreaContributorProviderError(
                    "Wall Area requires typed pier/spandrel assignment fact"
                )
            if self.wall_assignment.area_name != self.area_name:
                raise EtabsAreaContributorProviderError(
                    "wall assignment does not match Area identity"
                )
            if not self.wall_assignment.success:
                raise EtabsAreaContributorProviderError(
                    "AreaObj.GetPier/GetSpandrel failed for Wall Area"
                )
        elif self.wall_assignment is not None:
            raise EtabsAreaContributorProviderError(
                "wall assignment fact is bounded to Wall Area contributors"
            )

        for name in (
            "model_fingerprint",
            "evidence_epoch_id",
            "session_provenance_ref",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "source_refs", _refs(self.source_refs))

    @property
    def semi_rigid_diaphragm_assigned(self) -> bool | None:
        if self.orientation is not AreaDesignOrientation.FLOOR:
            return None
        assert self.diaphragm_assignment is not None
        if not self.diaphragm_assignment.assigned:
            return False
        assert self.diaphragm_definition is not None
        return self.diaphragm_definition.semi_rigid

    @property
    def wall_assignment_role(self) -> str | None:
        if self.orientation is not AreaDesignOrientation.WALL:
            return None
        assert self.wall_assignment is not None
        if self.wall_assignment.assignment_conflict:
            return "CONFLICT"
        if self.wall_assignment.pier_assigned:
            return "PIER"
        if self.wall_assignment.spandrel_assigned:
            return "SPANDREL"
        return "OTHER"

    @property
    def default_local_axes_assignment_proven(self) -> bool:
        return not self.advanced_local_axes and self.local_axes_angle_degrees == 0.0




class AreaMaterialResolution(StrEnum):
    CONCRETE_PROVEN = "CONCRETE_PROVEN"
    BASIC_MECHANICAL_MISSING = "BASIC_MECHANICAL_MISSING"
    CONCRETE_DATA_MISSING = "CONCRETE_DATA_MISSING"
    BASIC_MECHANICAL_PROPERTIES_UNRESOLVED = (
        "BASIC_MECHANICAL_PROPERTIES_UNRESOLVED"
    )
    CONCRETE_DATA_UNRESOLVED = "CONCRETE_DATA_UNRESOLVED"


class AreaContributorScopeStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    NO_PROPERTY = "NO_PROPERTY"
    DECK_APPLICABILITY_UNRESOLVED = "DECK_APPLICABILITY_UNRESOLVED"
    PROPERTY_FAMILY_UNRESOLVED = "PROPERTY_FAMILY_UNRESOLVED"
    AREA_MATERIAL_IDENTITY_UNRESOLVED = "AREA_MATERIAL_IDENTITY_UNRESOLVED"
    MATERIAL_BASIC_MECHANICAL_MISSING = "MATERIAL_BASIC_MECHANICAL_MISSING"
    MATERIAL_CONCRETE_DATA_MISSING = "MATERIAL_CONCRETE_DATA_MISSING"
    MATERIAL_NOT_PROVEN_CONCRETE = "MATERIAL_NOT_PROVEN_CONCRETE"
    MATERIAL_BASIC_MECHANICAL_PROPERTIES_UNRESOLVED = (
        "MATERIAL_BASIC_MECHANICAL_PROPERTIES_UNRESOLVED"
    )
    MATERIAL_CONCRETE_DATA_UNRESOLVED = (
        "MATERIAL_CONCRETE_DATA_UNRESOLVED"
    )
    UNSUPPORTED_SHELL_FORMULATION = "UNSUPPORTED_SHELL_FORMULATION"
    MATERIAL_OVERWRITE_UNQUALIFIED = "MATERIAL_OVERWRITE_UNQUALIFIED"
    PROPERTY_GEOMETRY_UNRESOLVED = "PROPERTY_GEOMETRY_UNRESOLVED"


@dataclass(frozen=True, slots=True)
class AreaMaterialFactualFact:
    material_name: str
    resolution: AreaMaterialResolution
    basic_mechanical_row: Mapping[str, Any] | None
    concrete_data_row: Mapping[str, Any] | None
    factual_ec_mpa: Decimal | None
    factual_gc_mpa: Decimal | None
    concrete_fck_mpa: Decimal | None
    model_fingerprint: str
    evidence_epoch_id: str
    session_provenance_ref: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "material_name",
            _text(self.material_name, "material_name"),
        )
        if not isinstance(self.resolution, AreaMaterialResolution):
            raise TypeError("resolution must be AreaMaterialResolution")
        if self.basic_mechanical_row is not None:
            object.__setattr__(
                self,
                "basic_mechanical_row",
                dict(self.basic_mechanical_row),
            )
        if self.concrete_data_row is not None:
            object.__setattr__(
                self,
                "concrete_data_row",
                dict(self.concrete_data_row),
            )
        for field_name in (
            "factual_ec_mpa",
            "factual_gc_mpa",
            "concrete_fck_mpa",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, Decimal)
                or not value.is_finite()
                or value <= 0
            ):
                raise EtabsAreaContributorProviderError(
                    f"{field_name} must be positive finite Decimal or None"
                )
        if self.resolution is AreaMaterialResolution.CONCRETE_PROVEN:
            if (
                self.basic_mechanical_row is None
                or self.concrete_data_row is None
                or self.factual_ec_mpa is None
                or self.factual_gc_mpa is None
                or self.concrete_fck_mpa is None
            ):
                raise EtabsAreaContributorProviderError(
                    "CONCRETE_PROVEN requires exact Basic Mechanical E1/G12 "
                    "and Concrete Data facts"
                )
        elif self.concrete_fck_mpa is not None:
            raise EtabsAreaContributorProviderError(
                "non-concrete-proven Area material cannot carry fck"
            )
        for field_name in (
            "model_fingerprint",
            "evidence_epoch_id",
            "session_provenance_ref",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "source_refs", _refs(self.source_refs))

    @property
    def concrete_proven(self) -> bool:
        return self.resolution is AreaMaterialResolution.CONCRETE_PROVEN


@dataclass(frozen=True, slots=True)
class AreaContributorScopeFact:
    area_name: str
    property_name: str
    property_family: AreaPropertyFamily | None
    material_name: str | None
    status: AreaContributorScopeStatus
    reason: str
    model_fingerprint: str
    evidence_epoch_id: str
    session_provenance_ref: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "area_name", _text(self.area_name, "area_name"))
        object.__setattr__(
            self,
            "property_name",
            _text(self.property_name, "property_name"),
        )
        if self.property_family is not None and not isinstance(
            self.property_family,
            AreaPropertyFamily,
        ):
            raise TypeError(
                "property_family must be AreaPropertyFamily or None"
            )
        if self.material_name is not None:
            object.__setattr__(
                self,
                "material_name",
                _text(self.material_name, "material_name"),
            )
        if not isinstance(self.status, AreaContributorScopeStatus):
            raise TypeError("status must be AreaContributorScopeStatus")
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        for field_name in (
            "model_fingerprint",
            "evidence_epoch_id",
            "session_provenance_ref",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "source_refs", _refs(self.source_refs))

    @property
    def supported(self) -> bool:
        return self.status in {
            AreaContributorScopeStatus.SUPPORTED,
            AreaContributorScopeStatus.NO_PROPERTY,
        }

@dataclass(frozen=True, slots=True)
class AreaContributorPopulation:
    model_fingerprint: str
    evidence_epoch_id: str
    session_provenance_ref: str
    expected_area_names: tuple[str, ...]
    rows: tuple[AreaContributorFact, ...]
    source_refs: tuple[str, ...]
    scope_facts: tuple[AreaContributorScopeFact, ...] = ()
    material_facts: tuple[AreaMaterialFactualFact, ...] = ()
    supported_rows: tuple[AreaContributorFact, ...] = ()
    typed_out_of_slice_rows: tuple[AreaContributorScopeFact, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "model_fingerprint",
            "evidence_epoch_id",
            "session_provenance_ref",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        expected = tuple(sorted(_text(name, "expected_area_name") for name in self.expected_area_names))
        if len(expected) != len(set(expected)):
            raise EtabsAreaContributorProviderError(
                "duplicate expected Area object identity"
            )
        rows = tuple(sorted(self.rows, key=lambda item: item.area_name))
        if any(not isinstance(row, AreaContributorFact) for row in rows):
            raise TypeError("rows must contain AreaContributorFact")
        names = tuple(row.area_name for row in rows)
        if names != expected:
            raise EtabsAreaContributorProviderError(
                "captured Area population does not exactly match AreaObj.GetNameList"
            )
        if any(
            row.model_fingerprint != self.model_fingerprint
            or row.evidence_epoch_id != self.evidence_epoch_id
            or row.session_provenance_ref != self.session_provenance_ref
            for row in rows
        ):
            raise EtabsAreaContributorProviderError(
                "Area factual row model/epoch/session provenance mismatch"
            )
        scope_facts = tuple(
            sorted(self.scope_facts, key=lambda item: item.area_name)
        )
        material_facts = tuple(
            sorted(self.material_facts, key=lambda item: item.material_name)
        )
        supported_rows = tuple(
            sorted(self.supported_rows, key=lambda item: item.area_name)
        )
        typed_out = tuple(
            sorted(
                self.typed_out_of_slice_rows,
                key=lambda item: item.area_name,
            )
        )

        if scope_facts:
            if any(
                not isinstance(item, AreaContributorScopeFact)
                for item in scope_facts
            ):
                raise TypeError(
                    "scope_facts must contain AreaContributorScopeFact"
                )
            scope_names = tuple(item.area_name for item in scope_facts)
            if len(scope_names) != len(set(scope_names)):
                raise EtabsAreaContributorProviderError(
                    "duplicate Area scope identity"
                )
            if scope_names != expected:
                missing = tuple(sorted(set(expected) - set(scope_names)))
                orphan = tuple(sorted(set(scope_names) - set(expected)))
                raise EtabsAreaContributorProviderError(
                    "Area scope denominator is not exact; "
                    f"missing={missing!r}; orphan={orphan!r}"
                )

            if any(
                not isinstance(item, AreaContributorFact)
                for item in supported_rows
            ):
                raise TypeError(
                    "supported_rows must contain AreaContributorFact"
                )
            supported_names = tuple(
                item.area_name for item in supported_rows
            )
            if len(supported_names) != len(set(supported_names)):
                raise EtabsAreaContributorProviderError(
                    "duplicate supported Area identity"
                )

            if any(
                not isinstance(item, AreaContributorScopeFact)
                for item in typed_out
            ):
                raise TypeError(
                    "typed_out_of_slice_rows must contain AreaContributorScopeFact"
                )
            typed_names = tuple(item.area_name for item in typed_out)
            if len(typed_names) != len(set(typed_names)):
                raise EtabsAreaContributorProviderError(
                    "duplicate typed-out-of-slice Area identity"
                )
            overlap = tuple(
                sorted(set(supported_names) & set(typed_names))
            )
            if overlap:
                raise EtabsAreaContributorProviderError(
                    "Area supported/typed-out-of-slice overlap: "
                    f"{overlap!r}"
                )
            observed = tuple(
                sorted((*supported_names, *typed_names))
            )
            if observed != expected:
                missing = tuple(sorted(set(expected) - set(observed)))
                orphan = tuple(sorted(set(observed) - set(expected)))
                raise EtabsAreaContributorProviderError(
                    "Area supported + typed-out-of-slice partition is not exact; "
                    f"missing={missing!r}; orphan={orphan!r}"
                )

            scope_by_name = {
                item.area_name: item for item in scope_facts
            }
            if any(
                not scope_by_name[name].supported
                for name in supported_names
            ):
                raise EtabsAreaContributorProviderError(
                    "supported Area row has non-supported scope status"
                )
            if any(
                scope_by_name[name].supported
                for name in typed_names
            ):
                raise EtabsAreaContributorProviderError(
                    "typed-out-of-slice Area row has supported scope status"
                )

        material_names = tuple(
            item.material_name for item in material_facts
        )
        if len(material_names) != len(set(material_names)):
            raise EtabsAreaContributorProviderError(
                "duplicate Area material factual identity"
            )
        if any(
            item.model_fingerprint != self.model_fingerprint
            or item.evidence_epoch_id != self.evidence_epoch_id
            or item.session_provenance_ref != self.session_provenance_ref
            for item in (*scope_facts, *material_facts)
        ):
            raise EtabsAreaContributorProviderError(
                "Area scope/material model/epoch/session provenance mismatch"
            )

        object.__setattr__(self, "expected_area_names", expected)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "scope_facts", scope_facts)
        object.__setattr__(self, "material_facts", material_facts)
        object.__setattr__(self, "supported_rows", supported_rows)
        object.__setattr__(
            self,
            "typed_out_of_slice_rows",
            typed_out,
        )
        object.__setattr__(self, "source_refs", _refs(self.source_refs))

    @property
    def exact_partition_available(self) -> bool:
        return bool(self.scope_facts)

    @property
    def material_by_name(self) -> Mapping[str, AreaMaterialFactualFact]:
        return {
            item.material_name: item
            for item in self.material_facts
        }

    @property
    def scope_by_name(self) -> Mapping[str, AreaContributorScopeFact]:
        return {
            item.area_name: item
            for item in self.scope_facts
        }

    @property
    def advanced_local_axis_area_names(self) -> tuple[str, ...]:
        return tuple(row.area_name for row in self.rows if row.advanced_local_axes)

    @property
    def unresolved_property_area_names(self) -> tuple[str, ...]:
        return tuple(
            row.area_name
            for row in self.rows
            if row.property_state is not None
            and row.property_state.family is AreaPropertyFamily.UNRESOLVED
        )

    @property
    def conflicting_wall_assignment_area_names(self) -> tuple[str, ...]:
        return tuple(
            row.area_name for row in self.rows if row.wall_assignment_role == "CONFLICT"
        )


def _require_success(fact: object, *, api: str, target: str) -> None:
    if not bool(getattr(fact, "success", False)):
        code = getattr(fact, "return_code", None)
        if code is None:
            code = (
                getattr(fact, "pier_return_code", None),
                getattr(fact, "spandrel_return_code", None),
            )
        raise EtabsAreaContributorProviderError(
            f"{api} failed for {target!r}; return_code={code!r}"
        )


def _positive_floor_family(
    *,
    slab: AreaPropertyFamilyProbeFact,
    deck: AreaPropertyFamilyProbeFact,
) -> tuple[AreaPropertyFamily, AreaPropertyFamilyProbeFact | None]:
    successes = tuple(fact for fact in (slab, deck) if fact.success)
    if len(successes) > 1:
        raise EtabsAreaContributorProviderError(
            f"Area property {slab.property_name!r} is ambiguously positive for Slab and Deck"
        )
    if not successes:
        return AreaPropertyFamily.UNRESOLVED, None
    fact = successes[0]
    family = (
        AreaPropertyFamily.SLAB
        if fact.family == "SLAB"
        else AreaPropertyFamily.DECK
    )
    return family, fact


def _capture_property_state(
    session: EtabsVerifiedSession,
    *,
    property_name: str,
    orientation: AreaDesignOrientation,
) -> AreaPropertyFactualState:
    modifier_fact = get_area_modifiers_from_session(
        session,
        surface=AreaModifierSurface.AREA_PROPERTY,
        target_name=property_name,
    )
    _require_success(
        modifier_fact, api="PropArea.GetModifiers", target=property_name
    )

    refs: list[str] = [modifier_fact.evidence_ref]
    family = AreaPropertyFamily.UNRESOLVED
    family_type_code: int | None = None
    shell_type_code: int | None = None
    material_name: str | None = None
    thickness: float | None = None

    if orientation is AreaDesignOrientation.WALL:
        try:
            wall: WallPropertyFact = read_wall_property_from_session(
                session, property_name
            )
        except EtabsOAPIError as exc:
            refs.append(
                f"CSI:PropArea.GetWall:{property_name}:UNRESOLVED:{type(exc).__name__}"
            )
        else:
            family = AreaPropertyFamily.WALL
            family_type_code = wall.wall_type
            shell_type_code = wall.shell_type
            material_name = wall.material_name
            thickness = wall.thickness
            refs.append(
                f"CSI:PropArea.GetWall:{property_name}:{wall.wall_type}:{wall.shell_type}"
            )
    elif orientation is AreaDesignOrientation.FLOOR:
        slab = read_slab_property_probe_from_session(session, property_name)
        deck = read_deck_property_probe_from_session(session, property_name)
        refs.extend((slab.evidence_ref, deck.evidence_ref))
        family, positive = _positive_floor_family(slab=slab, deck=deck)
        if positive is not None:
            family_type_code = positive.family_type_code
            shell_type_code = positive.shell_type_code
            material_name = positive.material_name
            thickness = positive.thickness

    return AreaPropertyFactualState(
        property_name=property_name,
        family=family,
        family_type_code=family_type_code,
        shell_type_code=shell_type_code,
        material_name=material_name,
        thickness=thickness,
        property_modifiers=modifier_fact,
        source_refs=tuple(refs),
    )




def _exact_material_index(
    rows: Sequence[Mapping[str, Any]],
    *,
    label: str,
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        raw = _snapshot_pick(
            row,
            ("Material", "Name"),
            f"{label}[{index}] material identity",
            required=False,
        )
        if raw in (None, ""):
            raise EtabsAreaContributorProviderError(
                f"{label}[{index}] has no exact material identity"
            )
        name = _text(str(raw).strip(), "material_name")
        if name in result:
            raise EtabsAreaContributorProviderError(
                f"duplicate {label} material identity {name!r}"
            )
        result[name] = row
    return result


def _capture_area_material_facts(
    *,
    rows: Sequence[AreaContributorFact],
    material_snapshot: FrameFlexuralBaseCaptureSnapshot,
    model_fingerprint: str,
    evidence_epoch_id: str,
    session_provenance_ref: str,
) -> tuple[AreaMaterialFactualFact, ...]:
    if not isinstance(
        material_snapshot,
        FrameFlexuralBaseCaptureSnapshot,
    ):
        raise TypeError(
            "material_snapshot must be FrameFlexuralBaseCaptureSnapshot"
        )
    if (
        material_snapshot.session_provenance_ref
        != session_provenance_ref
    ):
        raise EtabsAreaContributorProviderError(
            "Area material snapshot session provenance mismatch"
        )

    basic_by_name = _exact_material_index(
        material_snapshot.basic_material_rows,
        label=TABLE_BASIC_MATERIAL,
    )
    concrete_by_name = _exact_material_index(
        material_snapshot.concrete_rows,
        label=TABLE_CONCRETE,
    )
    material_names = tuple(
        sorted(
            {
                row.property_state.material_name
                for row in rows
                if (
                    row.property_state is not None
                    and row.property_state.material_name
                    not in (None, "")
                )
            }
        )
    )

    facts: list[AreaMaterialFactualFact] = []
    for material_name in material_names:
        basic = basic_by_name.get(material_name)
        concrete = concrete_by_name.get(material_name)
        ec_mpa = None
        gc_mpa = None
        fck_mpa = None
        refs: list[str] = [
            session_provenance_ref,
            material_snapshot.ownership_proof_ref,
        ]
        if basic is not None:
            refs.append(
                _snapshot_row_ref(TABLE_BASIC_MATERIAL, basic)
            )
        if concrete is not None:
            refs.append(
                _snapshot_row_ref(TABLE_CONCRETE, concrete)
            )

        if basic is None:
            resolution = AreaMaterialResolution.BASIC_MECHANICAL_MISSING
        else:
            e_raw = _snapshot_pick(
                basic,
                ("E1", "Elastic Modulus", "Modulus of Elasticity", "E"),
                f"{material_name} E1",
                required=False,
            )
            g_raw = _snapshot_pick(
                basic,
                ("G12", "Shear Modulus", "G"),
                f"{material_name} G12",
                required=False,
            )
            if e_raw in (None, "") or g_raw in (None, ""):
                resolution = (
                    AreaMaterialResolution.BASIC_MECHANICAL_PROPERTIES_UNRESOLVED
                )
            else:
                try:
                    ec_candidate = _stress_to_mpa(
                        e_raw,
                        material_snapshot.present_force_unit,
                        material_snapshot.present_length_unit,
                        f"{material_name} E1",
                    )
                    gc_candidate = _stress_to_mpa(
                        g_raw,
                        material_snapshot.present_force_unit,
                        material_snapshot.present_length_unit,
                        f"{material_name} G12",
                    )
                except FrameFlexuralBaseFactError:
                    resolution = (
                        AreaMaterialResolution.BASIC_MECHANICAL_PROPERTIES_UNRESOLVED
                    )
                else:
                    if ec_candidate <= 0 or gc_candidate <= 0:
                        resolution = (
                            AreaMaterialResolution.BASIC_MECHANICAL_PROPERTIES_UNRESOLVED
                        )
                    else:
                        ec_mpa = ec_candidate
                        gc_mpa = gc_candidate
                        if concrete is None:
                            resolution = (
                                AreaMaterialResolution.CONCRETE_DATA_MISSING
                            )
                        else:
                            fc_raw = _snapshot_pick(
                                concrete,
                                ("Fc", "fck", "Concrete Strength"),
                                f"{material_name} Fc",
                                required=False,
                            )
                            if fc_raw in (None, ""):
                                resolution = (
                                    AreaMaterialResolution.CONCRETE_DATA_UNRESOLVED
                                )
                            else:
                                try:
                                    fck_candidate = _stress_to_mpa(
                                        fc_raw,
                                        material_snapshot.present_force_unit,
                                        material_snapshot.present_length_unit,
                                        f"{material_name} Fc",
                                    )
                                except FrameFlexuralBaseFactError:
                                    resolution = (
                                        AreaMaterialResolution.CONCRETE_DATA_UNRESOLVED
                                    )
                                else:
                                    if fck_candidate <= 0:
                                        resolution = (
                                            AreaMaterialResolution.CONCRETE_DATA_UNRESOLVED
                                        )
                                    else:
                                        fck_mpa = fck_candidate
                                        resolution = (
                                            AreaMaterialResolution.CONCRETE_PROVEN
                                        )

        facts.append(
            AreaMaterialFactualFact(
                material_name=material_name,
                resolution=resolution,
                basic_mechanical_row=basic,
                concrete_data_row=concrete,
                factual_ec_mpa=ec_mpa,
                factual_gc_mpa=gc_mpa,
                concrete_fck_mpa=fck_mpa,
                model_fingerprint=model_fingerprint,
                evidence_epoch_id=evidence_epoch_id,
                session_provenance_ref=session_provenance_ref,
                source_refs=tuple(refs),
            )
        )

    return tuple(sorted(facts, key=lambda item: item.material_name))


def _build_area_scope_facts(
    rows: Sequence[AreaContributorFact],
    material_facts: Sequence[AreaMaterialFactualFact],
) -> tuple[AreaContributorScopeFact, ...]:
    materials = {
        item.material_name: item
        for item in material_facts
    }
    result: list[AreaContributorScopeFact] = []

    for row in rows:
        state = row.property_state
        refs = list(row.source_refs)

        if (
            row.orientation is AreaDesignOrientation.NULL
            or row.property_name == "None"
        ):
            status = AreaContributorScopeStatus.NO_PROPERTY
            reason = (
                f"Area {row.area_name!r} has no assigned Area property; "
                "the existing canonical NULL/no-property Eq7.13 path remains applicable"
            )
            family = None
            material_name = None
        elif state is None:
            status = (
                AreaContributorScopeStatus.PROPERTY_FAMILY_UNRESOLVED
            )
            reason = (
                f"Area {row.area_name!r} assigned property "
                f"{row.property_name!r} has no exact factual property state"
            )
            family = None
            material_name = None
        else:
            family = state.family
            material_name = state.material_name
            refs.extend(state.source_refs)

            if family is AreaPropertyFamily.UNRESOLVED:
                status = (
                    AreaContributorScopeStatus.PROPERTY_FAMILY_UNRESOLVED
                )
                reason = (
                    f"Area {row.area_name!r} property "
                    f"{row.property_name!r} family is unresolved"
                )
            elif family is AreaPropertyFamily.DECK:
                status = (
                    AreaContributorScopeStatus.DECK_APPLICABILITY_UNRESOLVED
                )
                reason = (
                    f"Area {row.area_name!r} property "
                    f"{row.property_name!r} is exact DECK; "
                    "DECK is not automatically not-applicable and current "
                    "Eq7.13 Area applicability remains unresolved"
                )
            elif family not in {
                AreaPropertyFamily.WALL,
                AreaPropertyFamily.SLAB,
            }:
                status = (
                    AreaContributorScopeStatus.PROPERTY_FAMILY_UNRESOLVED
                )
                reason = (
                    f"Area {row.area_name!r} property family "
                    f"{family.value!r} is outside the supported simple WALL/SLAB slice"
                )
            elif state.shell_type_code not in {2, 3}:
                status = (
                    AreaContributorScopeStatus.UNSUPPORTED_SHELL_FORMULATION
                )
                reason = (
                    f"Area {row.area_name!r} shell type "
                    f"{state.shell_type_code!r} is outside the supported Eq7.13 slice"
                )
            elif (
                state.thickness is None
                or float(state.thickness) <= 0.0
            ):
                status = (
                    AreaContributorScopeStatus.PROPERTY_GEOMETRY_UNRESOLVED
                )
                reason = (
                    f"Area {row.area_name!r} has no positive simple-property thickness"
                )
            elif material_name in (None, ""):
                status = (
                    AreaContributorScopeStatus.AREA_MATERIAL_IDENTITY_UNRESOLVED
                )
                reason = (
                    f"Area {row.area_name!r} property "
                    f"{row.property_name!r} has no exact material identity"
                )
            elif row.raw_material_overwrite_name not in {
                "",
                "None",
                material_name,
            }:
                status = (
                    AreaContributorScopeStatus.MATERIAL_OVERWRITE_UNQUALIFIED
                )
                reason = (
                    f"Area {row.area_name!r} material overwrite "
                    f"{row.raw_material_overwrite_name!r} disagrees with "
                    f"property material {material_name!r}"
                )
            else:
                material = materials.get(material_name)
                if material is None:
                    status = (
                        AreaContributorScopeStatus.MATERIAL_BASIC_MECHANICAL_MISSING
                    )
                    reason = (
                        f"Area {row.area_name!r} material "
                        f"{material_name!r} has no same-epoch material fact"
                    )
                else:
                    refs.extend(material.source_refs)
                    if (
                        material.resolution
                        is AreaMaterialResolution.BASIC_MECHANICAL_MISSING
                    ):
                        status = (
                            AreaContributorScopeStatus.MATERIAL_BASIC_MECHANICAL_MISSING
                        )
                        reason = (
                            f"Area {row.area_name!r} material "
                            f"{material_name!r} has no exact same-epoch "
                            "Basic Mechanical row"
                        )
                    elif (
                        material.resolution
                        is AreaMaterialResolution.CONCRETE_DATA_MISSING
                    ):
                        status = (
                            AreaContributorScopeStatus.MATERIAL_CONCRETE_DATA_MISSING
                        )
                        reason = (
                            f"Area {row.area_name!r} material "
                            f"{material_name!r} has no exact same-epoch "
                            "Concrete Data row and is not proven concrete"
                        )
                    elif (
                        material.resolution
                        is AreaMaterialResolution.BASIC_MECHANICAL_PROPERTIES_UNRESOLVED
                    ):
                        status = (
                            AreaContributorScopeStatus.MATERIAL_BASIC_MECHANICAL_PROPERTIES_UNRESOLVED
                        )
                        reason = (
                            f"Area {row.area_name!r} material "
                            f"{material_name!r} exact same-epoch Basic Mechanical "
                            "E1/G12 facts are unresolved"
                        )
                    elif (
                        material.resolution
                        is AreaMaterialResolution.CONCRETE_DATA_UNRESOLVED
                    ):
                        status = (
                            AreaContributorScopeStatus.MATERIAL_CONCRETE_DATA_UNRESOLVED
                        )
                        reason = (
                            f"Area {row.area_name!r} material "
                            f"{material_name!r} exact same-epoch Concrete Data "
                            "Fc fact is unresolved"
                        )
                    elif not material.concrete_proven:
                        status = (
                            AreaContributorScopeStatus.MATERIAL_NOT_PROVEN_CONCRETE
                        )
                        reason = (
                            f"Area {row.area_name!r} material "
                            f"{material_name!r} is not proven concrete"
                        )
                    else:
                        status = AreaContributorScopeStatus.SUPPORTED
                        reason = (
                            f"Area {row.area_name!r} has exact supported "
                            f"{family.value} property/material factual basis"
                        )

        result.append(
            AreaContributorScopeFact(
                area_name=row.area_name,
                property_name=row.property_name,
                property_family=family,
                material_name=material_name,
                status=status,
                reason=reason,
                model_fingerprint=row.model_fingerprint,
                evidence_epoch_id=row.evidence_epoch_id,
                session_provenance_ref=row.session_provenance_ref,
                source_refs=tuple(dict.fromkeys(refs)),
            )
        )

    return tuple(sorted(result, key=lambda item: item.area_name))

def capture_area_contributor_population_from_session(
    session: EtabsVerifiedSession,
    *,
    model_fingerprint: str,
    evidence_epoch_id: str,
    session_provenance_ref: str,
    material_snapshot: FrameFlexuralBaseCaptureSnapshot | None = None,
) -> AreaContributorPopulation:
    """Capture the complete AreaObj factual population for one trusted epoch."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    model = _text(model_fingerprint, "model_fingerprint")
    epoch = _text(evidence_epoch_id, "evidence_epoch_id")
    provenance = _text(session_provenance_ref, "session_provenance_ref")

    try:
        names, _raw_names = read_area_names_from_session(session)
    except EtabsOAPIError as exc:
        raise EtabsAreaContributorProviderError(str(exc)) from exc
    expected = tuple(sorted(names))
    property_cache: dict[tuple[str, AreaDesignOrientation], AreaPropertyFactualState] = {}
    diaphragm_cache: dict[str, DiaphragmDefinitionFact] = {}
    rows: list[AreaContributorFact] = []
    population_refs: list[str] = [
        f"CSI:AreaObj.GetNameList:COUNT:{len(expected)}",
        provenance,
    ]

    for area_name in expected:
        try:
            assignment = read_area_property_assignment_from_session(session, area_name)
            orientation_fact = read_area_design_orientation_from_session(session, area_name)
            local_axes = read_area_local_axes_from_session(session, area_name)
            transform = read_area_transformation_matrix_from_session(session, area_name)
            overwrite = read_area_material_overwrite_from_session(session, area_name)
            object_modifiers = get_area_modifiers_from_session(
                session,
                surface=AreaModifierSurface.AREA_OBJECT,
                target_name=area_name,
            )
        except EtabsOAPIError as exc:
            raise EtabsAreaContributorProviderError(
                f"Area factual capture failed for {area_name!r}: {exc}"
            ) from exc

        _require_success(
            orientation_fact, api="AreaObj.GetDesignOrientation", target=area_name
        )
        _require_success(local_axes, api="AreaObj.GetLocalAxes", target=area_name)
        _require_success(
            transform, api="AreaObj.GetTransformationMatrix", target=area_name
        )
        _require_success(
            overwrite, api="AreaObj.GetMaterialOverwrite", target=area_name
        )
        _require_success(
            object_modifiers, api="AreaObj.GetModifiers", target=area_name
        )

        orientation = orientation_fact.orientation
        property_state: AreaPropertyFactualState | None = None
        if assignment.property_name != "None":
            key = (assignment.property_name, orientation)
            property_state = property_cache.get(key)
            if property_state is None:
                property_state = _capture_property_state(
                    session,
                    property_name=assignment.property_name,
                    orientation=orientation,
                )
                property_cache[key] = property_state

        diaphragm_assignment: AreaDiaphragmAssignmentFact | None = None
        diaphragm_definition: DiaphragmDefinitionFact | None = None
        wall_assignment: AreaWallAssignmentFact | None = None
        if orientation is AreaDesignOrientation.FLOOR:
            try:
                diaphragm_assignment = read_area_diaphragm_assignment_from_session(
                    session, area_name
                )
            except EtabsOAPIError as exc:
                raise EtabsAreaContributorProviderError(
                    f"Floor diaphragm factual capture failed for {area_name!r}: {exc}"
                ) from exc
            _require_success(
                diaphragm_assignment, api="AreaObj.GetDiaphragm", target=area_name
            )
            if diaphragm_assignment.assigned:
                diaphragm_definition = diaphragm_cache.get(
                    diaphragm_assignment.diaphragm_name
                )
                if diaphragm_definition is None:
                    try:
                        diaphragm_definition = read_diaphragm_definition_from_session(
                            session, diaphragm_assignment.diaphragm_name
                        )
                    except EtabsOAPIError as exc:
                        raise EtabsAreaContributorProviderError(
                            "assigned diaphragm definition factual capture failed for "
                            f"{diaphragm_assignment.diaphragm_name!r}: {exc}"
                        ) from exc
                    _require_success(
                        diaphragm_definition,
                        api="Diaphragm.GetDiaphragm",
                        target=diaphragm_assignment.diaphragm_name,
                    )
                    diaphragm_cache[diaphragm_assignment.diaphragm_name] = (
                        diaphragm_definition
                    )
        elif orientation is AreaDesignOrientation.WALL:
            try:
                wall_assignment = read_area_wall_assignments_from_session(
                    session, area_name
                )
            except EtabsOAPIError as exc:
                raise EtabsAreaContributorProviderError(
                    f"Wall assignment factual capture failed for {area_name!r}: {exc}"
                ) from exc
            _require_success(
                wall_assignment,
                api="AreaObj.GetPier/GetSpandrel",
                target=area_name,
            )

        refs = [
            f"CSI:AreaObj.GetProperty:{area_name}:{assignment.property_name}",
            orientation_fact.evidence_ref,
            local_axes.evidence_ref,
            transform.evidence_ref,
            overwrite.evidence_ref,
            object_modifiers.evidence_ref,
        ]
        if property_state is not None:
            refs.extend(property_state.source_refs)
        if diaphragm_assignment is not None:
            refs.append(diaphragm_assignment.evidence_ref)
        if diaphragm_definition is not None:
            refs.append(diaphragm_definition.evidence_ref)
        if wall_assignment is not None:
            refs.append(wall_assignment.evidence_ref)

        row = AreaContributorFact(
            area_name=area_name,
            orientation=orientation,
            property_name=assignment.property_name,
            property_state=property_state,
            local_axes_angle_degrees=local_axes.angle_degrees,
            advanced_local_axes=local_axes.advanced,
            transformation_matrix=transform.values,
            raw_material_overwrite_name=overwrite.raw_material_name,
            object_modifiers=object_modifiers,
            diaphragm_assignment=diaphragm_assignment,
            diaphragm_definition=diaphragm_definition,
            wall_assignment=wall_assignment,
            model_fingerprint=model,
            evidence_epoch_id=epoch,
            session_provenance_ref=provenance,
            source_refs=tuple(refs),
        )
        rows.append(row)
        population_refs.extend(row.source_refs)

    material_facts: tuple[AreaMaterialFactualFact, ...] = ()
    scope_facts: tuple[AreaContributorScopeFact, ...] = ()
    supported_rows: tuple[AreaContributorFact, ...] = ()
    typed_out_of_slice_rows: tuple[AreaContributorScopeFact, ...] = ()

    if material_snapshot is not None:
        material_facts = _capture_area_material_facts(
            rows=tuple(rows),
            material_snapshot=material_snapshot,
            model_fingerprint=model,
            evidence_epoch_id=epoch,
            session_provenance_ref=provenance,
        )
        scope_facts = _build_area_scope_facts(
            tuple(rows),
            material_facts,
        )
        scope_by_name = {
            item.area_name: item for item in scope_facts
        }
        supported_rows = tuple(
            row
            for row in rows
            if scope_by_name[row.area_name].supported
        )
        typed_out_of_slice_rows = tuple(
            item for item in scope_facts if not item.supported
        )
        for item in (*material_facts, *scope_facts):
            population_refs.extend(item.source_refs)

    return AreaContributorPopulation(
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        session_provenance_ref=provenance,
        expected_area_names=expected,
        rows=tuple(rows),
        source_refs=tuple(dict.fromkeys(population_refs)),
        scope_facts=scope_facts,
        material_facts=material_facts,
        supported_rows=supported_rows,
        typed_out_of_slice_rows=typed_out_of_slice_rows,
    )


__all__ = [
    "AreaContributorFact",
    "AreaContributorPopulation",
    "AreaContributorScopeFact",
    "AreaContributorScopeStatus",
    "AreaMaterialFactualFact",
    "AreaMaterialResolution",
    "AreaPropertyFactualState",
    "AreaPropertyFamily",
    "EtabsAreaContributorProviderError",
    "capture_area_contributor_population_from_session",
]
