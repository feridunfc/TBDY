"""Exact live ETABS Area contributor factual population for COLUMN-R1 A2.

The provider composes existing typed OAPI owners and preserves factual surfaces
without deciding TS500 Eq.7.13 applicability.  In particular, Area-object and
Area-property modifier vectors remain separate and no AreaObj slot is assigned
PropArea engineering meaning here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Sequence

from tbdy_engine.etabs.oapi.area_contributors import (
    AreaDesignOrientation,
    AreaPropertyFamilyProbeFact,
    read_area_design_orientation_from_session,
    read_area_local_axes_from_session,
    read_area_material_overwrite_from_session,
    read_area_transformation_matrix_from_session,
    read_deck_property_probe_from_session,
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


class EtabsAreaContributorProviderError(RuntimeError):
    """Raised when the exact A2 factual population cannot be captured truthfully."""


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
        for name in (
            "model_fingerprint",
            "evidence_epoch_id",
            "session_provenance_ref",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


@dataclass(frozen=True, slots=True)
class AreaContributorPopulation:
    model_fingerprint: str
    evidence_epoch_id: str
    session_provenance_ref: str
    expected_area_names: tuple[str, ...]
    rows: tuple[AreaContributorFact, ...]
    source_refs: tuple[str, ...]

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
        object.__setattr__(self, "expected_area_names", expected)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "source_refs", _refs(self.source_refs))

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


def _require_success(fact: object, *, api: str, target: str) -> None:
    if not bool(getattr(fact, "success", False)):
        code = getattr(fact, "return_code", None)
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


def capture_area_contributor_population_from_session(
    session: EtabsVerifiedSession,
    *,
    model_fingerprint: str,
    evidence_epoch_id: str,
    session_provenance_ref: str,
) -> AreaContributorPopulation:
    """Capture the complete AreaObj factual population for one trusted epoch.

    This function intentionally does not return an Eq.7.13 expected contributor
    set.  It supplies the exact facts from which the existing engineering layer
    must later derive that set.
    """
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
            model_fingerprint=model,
            evidence_epoch_id=epoch,
            session_provenance_ref=provenance,
            source_refs=tuple(refs),
        )
        rows.append(row)
        population_refs.extend(row.source_refs)

    return AreaContributorPopulation(
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        session_provenance_ref=provenance,
        expected_area_names=expected,
        rows=tuple(rows),
        source_refs=tuple(dict.fromkeys(population_refs)),
    )


__all__ = [
    "AreaContributorFact",
    "AreaContributorPopulation",
    "AreaPropertyFactualState",
    "AreaPropertyFamily",
    "EtabsAreaContributorProviderError",
    "capture_area_contributor_population_from_session",
]
