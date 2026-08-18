"""Authoritative used reinforced-concrete material population facts.

The slice is intentionally narrow: exact Beam/Column source population,
structural-wall candidates, exact material identity/type, and explicit-unit Fc
normalization. It contains no material engineering decision.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import StrEnum
import hashlib
import json
import math
from typing import Any

from tbdy_engine.etabs.safety import EtabsVerifiedSession, process_local_acquisition_lock
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED
from tbdy_engine.features.live_etabs_geometry_probe import read_live_etabs_table_for_geometry
from tbdy_engine.features.wall_inventory import WallInventory, WallInventoryStatus


_FRAME_SUMMARY = "Frame Assignments - Summary"
_FRAME_ASSIGNMENTS = "Frame Assignments - Section Properties"
_FRAME_SECTIONS = "Frame Section Property Definitions - Summary"
_FRAME_TYPES = frozenset({"beam", "column"})
_POSITIVELY_EXCLUDED_FRAME_TYPES = frozenset({"brace", "null"})
_KNOWN_MATERIAL_TYPES = frozenset(range(1, 9))
_CONCRETE_TYPE = 2
_SPECIFIED_WALL = 1
_LAYERED_SHELL = 6
_NON_BLOCKING_DIAGNOSTICS = frozenset({"FRAME_NON_TARGET_POSITIVELY_EXCLUDED"})

# ETABS eForce -> N and eLength -> mm. The factor is selected only from
# explicitly captured GetPresentUnits_2 enum values.
_FORCE_TO_N = {1: 4.4482216152605, 2: 4448.2216152605, 3: 1.0, 4: 1000.0, 5: 9.80665, 6: 9806.65}
_LENGTH_TO_MM = {1: 25.4, 2: 304.8, 3: 0.001, 4: 1.0, 5: 10.0, 6: 1000.0}


class MaterialUsageStatus(StrEnum):
    RESOLVED_CONCRETE_USAGE = "RESOLVED_CONCRETE_USAGE"
    PROVEN_NON_CONCRETE = "PROVEN_NON_CONCRETE"
    UNRESOLVED = "UNRESOLVED"


class MaterialPopulationReadiness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


class ConcreteStrengthFactStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MaterialSourceContractResolutionError(RuntimeError):
    """Closed-gate signal for an unresolved M0 factual source binding."""

    verdict = "NEEDS_SOURCE_CONTRACT_RESOLUTION"

    def __init__(self, message: str, *, details: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.details = dict(details)


@dataclass(frozen=True, slots=True)
class MaterialPopulationDiagnostic:
    code: str
    message: str
    domain: str | None = None
    component_identity: str | None = None
    material_name: str | None = None
    source_api: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MaterialUnitContext:
    present_force_unit_code: int | None
    present_length_unit_code: int | None
    source_api: str | None
    raw_present_units: Any = None

    @property
    def stress_factor_to_mpa(self) -> float | None:
        force = _FORCE_TO_N.get(self.present_force_unit_code)
        length = _LENGTH_TO_MM.get(self.present_length_unit_code)
        return None if force is None or length is None else force / (length * length)

    @property
    def supported(self) -> bool:
        return self.source_api == "GetPresentUnits_2" and self.stress_factor_to_mpa is not None


@dataclass(frozen=True, slots=True)
class WallPropertyFact:
    etabs_area_unique_name: str
    assigned_area_property: str | None
    wall_property_type_code: int | None
    shell_type_code: int | None
    material_name: str | None
    thickness_raw: Any
    area_property_raw_result: Any = None
    wall_property_raw_result: Any = None
    diagnostic_code: str | None = None

    def __post_init__(self) -> None:
        unique = _id(self.etabs_area_unique_name)
        if unique is None:
            raise ValueError("WallPropertyFact requires exact ETABS area UniqueName")
        object.__setattr__(self, "etabs_area_unique_name", unique)
        object.__setattr__(self, "assigned_area_property", _id(self.assigned_area_property))
        object.__setattr__(self, "material_name", _id(self.material_name))

    @property
    def layered(self) -> bool:
        return self.shell_type_code == _LAYERED_SHELL


@dataclass(frozen=True, slots=True)
class MaterialApiFact:
    material_name: str
    material_type_code: int | None
    symmetry_type_code: int | None = None
    raw_fc: Any = None
    type_raw_result: Any = None
    concrete_raw_result: Any = None
    diagnostic_code: str | None = None

    def __post_init__(self) -> None:
        name = _id(self.material_name)
        if name is None:
            raise ValueError("MaterialApiFact requires exact material name")
        object.__setattr__(self, "material_name", name)

    @property
    def type_known(self) -> bool:
        return self.material_type_code in _KNOWN_MATERIAL_TYPES

    @property
    def concrete(self) -> bool:
        return self.material_type_code == _CONCRETE_TYPE


@dataclass(frozen=True, slots=True)
class MaterialPopulationSources:
    frame_summary_rows: tuple[Mapping[str, Any], ...]
    frame_assignment_rows: tuple[Mapping[str, Any], ...]
    frame_section_material_rows: tuple[Mapping[str, Any], ...]
    wall_inventory: WallInventory
    wall_property_facts: tuple[WallPropertyFact, ...]
    material_facts: tuple[MaterialApiFact, ...]
    unit_context: MaterialUnitContext | None
    frame_summary_available: bool = True
    frame_assignment_available: bool = True
    frame_section_material_available: bool = True
    source_diagnostics: tuple[MaterialPopulationDiagnostic, ...] = ()

    def __init__(
        self, *, frame_summary_rows: Sequence[Mapping[str, Any]],
        frame_assignment_rows: Sequence[Mapping[str, Any]],
        frame_section_material_rows: Sequence[Mapping[str, Any]],
        wall_inventory: WallInventory, wall_property_facts: Sequence[WallPropertyFact],
        material_facts: Sequence[MaterialApiFact], unit_context: MaterialUnitContext | None,
        frame_summary_available: bool = True, frame_assignment_available: bool = True,
        frame_section_material_available: bool = True,
        source_diagnostics: Sequence[MaterialPopulationDiagnostic] = (),
    ) -> None:
        if not isinstance(wall_inventory, WallInventory):
            raise TypeError("wall_inventory must be WallInventory")
        object.__setattr__(self, "frame_summary_rows", tuple(dict(x) for x in frame_summary_rows))
        object.__setattr__(self, "frame_assignment_rows", tuple(dict(x) for x in frame_assignment_rows))
        object.__setattr__(self, "frame_section_material_rows", tuple(dict(x) for x in frame_section_material_rows))
        object.__setattr__(self, "wall_inventory", wall_inventory)
        object.__setattr__(self, "wall_property_facts", tuple(wall_property_facts))
        object.__setattr__(self, "material_facts", tuple(material_facts))
        object.__setattr__(self, "unit_context", unit_context)
        object.__setattr__(self, "frame_summary_available", bool(frame_summary_available))
        object.__setattr__(self, "frame_assignment_available", bool(frame_assignment_available))
        object.__setattr__(self, "frame_section_material_available", bool(frame_section_material_available))
        object.__setattr__(self, "source_diagnostics", tuple(source_diagnostics))


@dataclass(frozen=True, slots=True)
class MaterialUsageReference:
    usage_id: str
    component_type: str
    component_identity: str | None
    story: str | None
    label: str | None
    assigned_property: str | None
    material_name: str | None
    material_type_code: int | None
    status: MaterialUsageStatus
    source_references: tuple[Mapping[str, Any], ...]
    diagnostics: tuple[MaterialPopulationDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", MaterialUsageStatus(self.status))
        object.__setattr__(self, "source_references", tuple(dict(x) for x in self.source_references))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return self.component_type, self.component_identity or self.usage_id, self.usage_id


@dataclass(frozen=True, slots=True)
class UsedMaterialDefinition:
    material_id: str
    model_fingerprint: str
    material_name: str
    material_type_code: int
    is_concrete: bool
    raw_fc: Any
    canonical_fck_mpa: float | None
    concrete_strength_status: ConcreteStrengthFactStatus
    unit_context: MaterialUnitContext | None
    usage_references: tuple[MaterialUsageReference, ...]
    diagnostics: tuple[MaterialPopulationDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class MaterialDomainReconciliation:
    domain: str
    expected_identities: tuple[str, ...]
    actual_identities: tuple[str, ...]
    missing_identities: tuple[str, ...]
    unexpected_identities: tuple[str, ...]
    duplicate_identities: tuple[str, ...]
    expected_count: int
    resolved_concrete: int
    proven_non_concrete: int
    unresolved: int
    actual_count: int
    source_available: bool
    reconciled: bool

    @property
    def expected(self) -> int:
        """Compatibility alias for the pre-intervention M0 field."""
        return self.expected_count

    @property
    def complete(self) -> bool:
        return self.source_available and self.reconciled and self.unresolved == 0


@dataclass(frozen=True, slots=True)
class UsedRcMaterialPopulation:
    model_fingerprint: str
    usages: tuple[MaterialUsageReference, ...]
    used_material_definitions: tuple[UsedMaterialDefinition, ...]
    reconciliations: tuple[MaterialDomainReconciliation, ...]
    readiness: MaterialPopulationReadiness
    diagnostics: tuple[MaterialPopulationDiagnostic, ...]

    @property
    def used_concrete_material_definitions(self) -> tuple[UsedMaterialDefinition, ...]:
        return tuple(x for x in self.used_material_definitions if x.is_concrete)

    def as_dict(self) -> dict[str, Any]:
        return {
            "inventory_contract": "USED_RC_MATERIAL_POPULATION_M0",
            "model_fingerprint": self.model_fingerprint,
            "readiness": self.readiness.value,
            "usage_count": len(self.usages),
            "used_material_definition_count": len(self.used_material_definitions),
            "used_concrete_material_definition_count": len(self.used_concrete_material_definitions),
            "usages": [_plain(x) for x in self.usages],
            "used_material_definitions": [_plain(x) for x in self.used_material_definitions],
            "reconciliations": [_plain(x) | {"complete": x.complete} for x in self.reconciliations],
            "diagnostics": [_plain(x) for x in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class _FramePopulationAccounting:
    expected_beam_identities: tuple[str, ...]
    expected_column_identities: tuple[str, ...]
    target_groups: tuple[tuple[str, str, tuple[Mapping[str, Any], ...]], ...]
    uncertainty_usages: tuple[MaterialUsageReference, ...]
    diagnostics: tuple[MaterialPopulationDiagnostic, ...]


def build_used_rc_material_population(
    *, model_fingerprint: str, sources: MaterialPopulationSources
) -> UsedRcMaterialPopulation:
    """Build the deterministic factual inventory from already-read source facts."""
    fingerprint = _text(model_fingerprint)
    if not fingerprint:
        raise ValueError("model_fingerprint is required")
    if sources.wall_inventory.model_fingerprint != fingerprint:
        raise ValueError("WallInventory model fingerprint does not match population model")

    material_facts, duplicate_material_names = _unique_material_facts(sources.material_facts)
    diagnostics = list(sources.source_diagnostics)
    diagnostics.extend(
        MaterialPopulationDiagnostic(
            code="MATERIAL_API_FACT_AMBIGUOUS",
            message="Repeated factual API records exist for exact material identity",
            material_name=name,
        )
        for name in duplicate_material_names
    )

    frame_population = _frame_population_accounting(fingerprint, sources.frame_summary_rows)
    diagnostics.extend(frame_population.diagnostics)

    frame_usages = _frame_usages(fingerprint, sources, material_facts, frame_population)
    wall_usages = _wall_usages(sources, material_facts)
    usages = tuple(sorted((*frame_usages, *wall_usages), key=lambda x: x.sort_key))

    usage_id_counts = Counter(x.usage_id for x in usages)
    duplicate_usage_ids = tuple(sorted(key for key, count in usage_id_counts.items() if count > 1))
    diagnostics.extend(
        MaterialPopulationDiagnostic(
            code="DUPLICATE_MATERIAL_USAGE_IDENTITY",
            message="Emitted MaterialUsageReference identity is duplicated",
            component_identity=usage_id,
            details={"usage_id": usage_id},
        )
        for usage_id in duplicate_usage_ids
    )

    definitions = _material_definitions(
        fingerprint, usages, material_facts, sources.unit_context
    )
    wall_expected = _wall_expected_identities(sources.wall_inventory)
    expected_by_domain = {
        "Beam": frame_population.expected_beam_identities,
        "Column": frame_population.expected_column_identities,
        "Wall": wall_expected,
    }
    reconciliations = tuple(
        _reconcile(
            domain,
            expected_by_domain[domain],
            usages,
            source_available=(
                sources.frame_summary_available if domain in {"Beam", "Column"} else True
            ),
        )
        for domain in ("Beam", "Column", "Wall")
    )

    source_blocked = not (
        sources.frame_summary_available
        and sources.frame_assignment_available
        and sources.frame_section_material_available
    )
    unresolved_usage = any(x.status is MaterialUsageStatus.UNRESOLVED for x in usages)
    unresolved_fc = any(
        x.is_concrete and x.concrete_strength_status is not ConcreteStrengthFactStatus.RESOLVED
        for x in definitions
    )
    domain_incomplete = any(not x.complete for x in reconciliations)
    blocking_diagnostic = any(x.code not in _NON_BLOCKING_DIAGNOSTICS for x in diagnostics)

    if source_blocked:
        readiness = MaterialPopulationReadiness.BLOCKED
    elif unresolved_usage or unresolved_fc or domain_incomplete or blocking_diagnostic:
        readiness = MaterialPopulationReadiness.PARTIAL
    else:
        readiness = MaterialPopulationReadiness.COMPLETE

    if readiness is MaterialPopulationReadiness.COMPLETE and (
        unresolved_usage or unresolved_fc or domain_incomplete or blocking_diagnostic
    ):
        raise ValueError("Complete inventory cannot contain unresolved facts")

    return UsedRcMaterialPopulation(
        model_fingerprint=fingerprint,
        usages=usages,
        used_material_definitions=definitions,
        reconciliations=reconciliations,
        readiness=readiness,
        diagnostics=tuple(sorted(diagnostics, key=_diagnostic_sort_key)),
    )


def canonical_material_population_json(population: UsedRcMaterialPopulation) -> str:
    return json.dumps(
        population.as_dict(), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ) + "\n"


def read_material_population_sources_from_verified_session(
    *, session: EtabsVerifiedSession, wall_inventory: WallInventory
) -> MaterialPopulationSources:
    """Read exact sources through an already verified exact-model session.

    This reader intentionally blocks before any ETABS factual acquisition
    until WallInventory carries an identity that is explicitly comparable to
    EtabsVerifiedSession identity by an accepted source contract.
    """
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    if session.attach_result.status != ATTACH_STATUS_ATTACHED:
        raise ValueError("Verified ETABS session is not attached")
    if session.attach_result.sap_model is None or not _text(session.identity.model_full_path):
        raise ValueError("Verified ETABS session does not expose the verified model")
    if not isinstance(wall_inventory, WallInventory):
        raise TypeError("wall_inventory must be WallInventory")

    _require_wall_inventory_session_binding(session, wall_inventory)

    sap_model = session.attach_result.sap_model
    with process_local_acquisition_lock():
        summary = read_live_etabs_table_for_geometry(sap_model.DatabaseTables, _FRAME_SUMMARY)
        assignments = read_live_etabs_table_for_geometry(sap_model.DatabaseTables, _FRAME_ASSIGNMENTS)
        sections = read_live_etabs_table_for_geometry(sap_model.DatabaseTables, _FRAME_SECTIONS)

        source_diags = tuple(
            MaterialPopulationDiagnostic(
                code=f"{role}_SOURCE_UNAVAILABLE",
                message="Required exact factual frame source is unavailable",
                source_api="DatabaseTables.GetTableForDisplayArray",
                details={"table": result.table_key, "source_status": result.status, "message": result.message},
            )
            for role, result in (
                ("FRAME_POPULATION", summary),
                ("FRAME_ASSIGNMENT", assignments),
                ("FRAME_SECTION_MATERIAL", sections),
            )
            if result.status != "FETCHED"
        )

        wall_facts = tuple(
            _read_wall_fact(sap_model, record)
            for record in wall_inventory.records
            if record.classification_status is WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE
        )
        names = _exact_used_material_names(
            summary.rows, assignments.rows, sections.rows, wall_facts
        )
        material_facts = tuple(_read_material_fact(sap_model, name) for name in sorted(names))

    units = session.identity.units
    unit_context = MaterialUnitContext(
        present_force_unit_code=_int(units.present_force_unit),
        present_length_unit_code=_int(units.present_length_unit),
        source_api=units.present_units_api,
        raw_present_units=units.present_units,
    )
    return MaterialPopulationSources(
        frame_summary_rows=summary.rows,
        frame_assignment_rows=assignments.rows,
        frame_section_material_rows=sections.rows,
        wall_inventory=wall_inventory,
        wall_property_facts=wall_facts,
        material_facts=material_facts,
        unit_context=unit_context,
        frame_summary_available=summary.status == "FETCHED",
        frame_assignment_available=assignments.status == "FETCHED",
        frame_section_material_available=sections.status == "FETCHED",
        source_diagnostics=source_diags,
    )


def build_used_rc_material_population_from_verified_session(
    *, session: EtabsVerifiedSession, wall_inventory: WallInventory
) -> UsedRcMaterialPopulation:
    return build_used_rc_material_population(
        model_fingerprint=wall_inventory.model_fingerprint,
        sources=read_material_population_sources_from_verified_session(
            session=session, wall_inventory=wall_inventory
        ),
    )


def _require_wall_inventory_session_binding(
    session: EtabsVerifiedSession, wall_inventory: WallInventory
) -> None:
    identity = session.identity
    raise MaterialSourceContractResolutionError(
        "WallInventory and EtabsVerifiedSession do not expose an existing "
        "directly comparable model-binding identity contract; live material "
        "acquisition is blocked before any ETABS read.",
        details={
            "session_model_full_path": identity.model_full_path,
            "session_model_fingerprint": identity.model_fingerprint,
            "session_model_fingerprint_source": identity.model_fingerprint_source,
            "wall_inventory_model_fingerprint": wall_inventory.model_fingerprint,
            "wall_inventory_source_contract_status": dict(wall_inventory.source_contract_status),
            "minimum_missing_binding": (
                "An explicit accepted source contract binding WallInventory to the same "
                "exact verified EtabsVerifiedSession model identity."
            ),
            "forbidden_inference_not_used": [
                "model_full_path_hash",
                "unrelated_fingerprint_equality",
                "manufactured_session_fingerprint",
            ],
        },
    )


def _frame_population_accounting(
    fingerprint: str, rows: Sequence[Mapping[str, Any]]
) -> _FramePopulationAccounting:
    grouped: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    anonymous: list[Mapping[str, Any]] = []
    for raw in sorted((dict(x) for x in rows), key=_canonical):
        unique = _id(raw.get("UniqueName"))
        if unique is None:
            anonymous.append(raw)
        else:
            grouped[unique].append(raw)

    expected: dict[str, set[str]] = {"Beam": set(), "Column": set()}
    target_groups: list[tuple[str, str, tuple[Mapping[str, Any], ...]]] = []
    uncertainty: list[MaterialUsageReference] = []
    diagnostics: list[MaterialPopulationDiagnostic] = []

    for unique, grouped_rows in sorted(grouped.items()):
        exact_rows = tuple(grouped_rows)
        tokens = {_frame_type_token(row.get("Type")) for row in exact_rows}
        if len(tokens) == 1:
            token = next(iter(tokens))
            if token in _FRAME_TYPES:
                domain = "Beam" if token == "beam" else "Column"
                expected[domain].add(unique)
                target_groups.append((domain, unique, exact_rows))
                continue
            if token in _POSITIVELY_EXCLUDED_FRAME_TYPES:
                diagnostics.append(_frame_exclusion_diagnostic(unique, token, exact_rows))
                continue

        code = _frame_type_uncertainty_code(tokens)
        uncertainty.append(_unresolved(
            f"frame-population:{_sha(fingerprint + chr(31) + unique)}",
            "Frame",
            unique,
            _one(exact_rows, "Story"),
            _one(exact_rows, "Label"),
            None,
            None,
            tuple(_ref(_FRAME_SUMMARY, row) for row in exact_rows),
            code,
            _frame_type_uncertainty_message(code),
        ))

    for position, row in enumerate(anonymous):
        token = _frame_type_token(row.get("Type"))
        refs = (_ref(_FRAME_SUMMARY, row),)
        if token in _FRAME_TYPES:
            domain = "Beam" if token == "beam" else "Column"
            digest = _sha(f"{fingerprint}\x1f{domain}\x1f{_canonical(row)}\x1f{position}")
            uncertainty.append(_unresolved(
                f"frame-anonymous:{digest}",
                domain,
                None,
                _id(row.get("Story")),
                _id(row.get("Label")),
                None,
                None,
                refs,
                "FRAME_OBJECT_IDENTITY_MISSING",
                "Beam/Column population row has no exact string UniqueName",
            ))
        elif token in _POSITIVELY_EXCLUDED_FRAME_TYPES:
            diagnostics.append(_frame_exclusion_diagnostic(None, token, (row,)))
        else:
            code = _frame_type_uncertainty_code({token})
            digest = _sha(f"{fingerprint}\x1fFrame\x1f{_canonical(row)}\x1f{position}")
            uncertainty.append(_unresolved(
                f"frame-anonymous:{digest}",
                "Frame",
                None,
                _id(row.get("Story")),
                _id(row.get("Label")),
                None,
                None,
                refs,
                code,
                _frame_type_uncertainty_message(code),
            ))

    return _FramePopulationAccounting(
        expected_beam_identities=tuple(sorted(expected["Beam"])),
        expected_column_identities=tuple(sorted(expected["Column"])),
        target_groups=tuple(sorted(target_groups, key=lambda item: (item[0], item[1]))),
        uncertainty_usages=tuple(sorted(uncertainty, key=lambda item: item.sort_key)),
        diagnostics=tuple(sorted(diagnostics, key=_diagnostic_sort_key)),
    )


def _frame_exclusion_diagnostic(
    unique: str | None, token: str, rows: Sequence[Mapping[str, Any]]
) -> MaterialPopulationDiagnostic:
    return MaterialPopulationDiagnostic(
        code="FRAME_NON_TARGET_POSITIVELY_EXCLUDED",
        message="Authoritative frame population proves a non-target frame type",
        domain="Frame",
        component_identity=unique,
        source_api="DatabaseTables.GetTableForDisplayArray",
        details={
            "raw_type": token,
            "source_table": _FRAME_SUMMARY,
            "source_references": [_plain(_ref(_FRAME_SUMMARY, row)) for row in rows],
        },
    )


def _frame_type_uncertainty_code(tokens: set[str | None]) -> str:
    if tokens == {None}:
        return "FRAME_COMPONENT_TYPE_MISSING"
    if len(tokens) > 1:
        return "FRAME_COMPONENT_TYPE_CONFLICT"
    return "FRAME_COMPONENT_TYPE_UNRECOGNIZED"


def _frame_type_uncertainty_message(code: str) -> str:
    return {
        "FRAME_COMPONENT_TYPE_MISSING": "Authoritative frame population row has no explicit component Type",
        "FRAME_COMPONENT_TYPE_CONFLICT": "Authoritative frame population rows conflict on component Type",
        "FRAME_COMPONENT_TYPE_UNRECOGNIZED": "Authoritative frame population Type is not an accepted target or positive exclusion",
    }[code]


def _frame_usages(
    fingerprint: str,
    sources: MaterialPopulationSources,
    material_facts: Mapping[str, MaterialApiFact],
    frame_population: _FramePopulationAccounting,
) -> list[MaterialUsageReference]:
    if not sources.frame_summary_available:
        return list(frame_population.uncertainty_usages)

    assignments = _index(sources.frame_assignment_rows, "UniqueName")
    sections = _index(sources.frame_section_material_rows, "Name")
    result: list[MaterialUsageReference] = list(frame_population.uncertainty_usages)

    for domain, unique, rows in frame_population.target_groups:
        usage_id = _frame_usage_id(fingerprint, domain, unique)
        if len(rows) != 1:
            result.append(_unresolved(
                usage_id,
                domain,
                unique,
                _one(rows, "Story"),
                _one(rows, "Label"),
                None,
                None,
                tuple(_ref(_FRAME_SUMMARY, x) for x in rows),
                "DUPLICATE_OBJECT_IDENTITY",
                "Authoritative frame population repeats exact object identity",
            ))
            continue
        result.append(_resolve_frame(
            fingerprint, domain, unique, rows[0], assignments, sections, material_facts
        ))
    return result


def _resolve_frame(
    fingerprint: str, domain: str, unique: str, summary: Mapping[str, Any],
    assignments: Mapping[str, tuple[Mapping[str, Any], ...]],
    sections: Mapping[str, tuple[Mapping[str, Any], ...]],
    material_facts: Mapping[str, MaterialApiFact],
) -> MaterialUsageReference:
    usage_id = _frame_usage_id(fingerprint, domain, unique)
    story, label = _id(summary.get("Story")), _id(summary.get("Label"))
    refs = [_ref(_FRAME_SUMMARY, summary)]
    matches = assignments.get(unique, ())
    if len(matches) != 1:
        refs.extend(_ref(_FRAME_ASSIGNMENTS, x) for x in matches)
        return _unresolved(
            usage_id, domain, unique, story, label, None, None, tuple(refs),
            "FRAME_SECTION_ASSIGNMENT_MISSING" if not matches else "FRAME_SECTION_ASSIGNMENT_AMBIGUOUS",
            "Exact frame object-to-section dependency is unresolved",
        )
    assignment = matches[0]
    refs.append(_ref(_FRAME_ASSIGNMENTS, assignment))
    story, label = story or _id(assignment.get("Story")), label or _id(assignment.get("Label"))
    section = _id(assignment.get("SectProp"))
    if section is None:
        return _unresolved(
            usage_id, domain, unique, story, label, None, None, tuple(refs),
            "FRAME_SECTION_VALUE_MISSING", "Exact frame assignment has no section/property identity",
        )

    section_rows = sections.get(section, ())
    if len(section_rows) != 1:
        refs.extend(_ref(_FRAME_SECTIONS, x) for x in section_rows)
        return _unresolved(
            usage_id, domain, unique, story, label, section, None, tuple(refs),
            "FRAME_SECTION_DEFINITION_MISSING" if not section_rows else "FRAME_SECTION_DEFINITION_AMBIGUOUS",
            "Exact frame section-to-material dependency is unresolved",
        )
    section_row = section_rows[0]
    refs.append(_ref(_FRAME_SECTIONS, section_row))
    material = _id(section_row.get("Material"))
    if material is None:
        return _unresolved(
            usage_id, domain, unique, story, label, section, None, tuple(refs),
            "FRAME_MATERIAL_IDENTITY_MISSING", "Exact frame section row has no material identity",
        )

    fact = material_facts.get(material)
    if fact is None or not fact.type_known:
        return _unresolved(
            usage_id, domain, unique, story, label, section, material, tuple(refs),
            "MATERIAL_TYPE_UNRESOLVED", "Exact material identity has no supported factual type",
        )
    refs.append({"source_api": "PropMaterial.GetTypeOAPI", "material_name": material, "raw_result": fact.type_raw_result})
    return MaterialUsageReference(
        usage_id, domain, unique, story, label, section, material, fact.material_type_code,
        MaterialUsageStatus.RESOLVED_CONCRETE_USAGE if fact.concrete else MaterialUsageStatus.PROVEN_NON_CONCRETE,
        tuple(refs),
    )


def _wall_usages(
    sources: MaterialPopulationSources, material_facts: Mapping[str, MaterialApiFact]
) -> list[MaterialUsageReference]:
    candidates = tuple(
        x for x in sources.wall_inventory.records
        if x.classification_status is WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE
    )
    facts: defaultdict[str, list[WallPropertyFact]] = defaultdict(list)
    for fact in sources.wall_property_facts:
        facts[fact.etabs_area_unique_name].append(fact)

    result: list[MaterialUsageReference] = []
    for record in sorted(candidates, key=lambda x: x.inventory_record_id):
        unique = _id(record.etabs_area_unique_name)
        refs = tuple(
            {"source_family": x.source_family, "row_digest": x.row_digest, "area_row_token": x.area_row_token, "row": dict(x.row)}
            for x in record.source_row_references
        )
        if unique is None:
            result.append(_unresolved(
                record.inventory_record_id, "Wall", None, record.story, record.area_label,
                record.assigned_area_property, None, refs,
                "WALL_EXACT_IDENTITY_MISSING", "Structural wall candidate has no exact ETABS UniqueName",
            ))
            continue
        wall_facts = tuple(facts.get(unique, ()))
        if len(wall_facts) != 1:
            result.append(_unresolved(
                record.inventory_record_id, "Wall", unique, record.story, record.area_label,
                record.assigned_area_property, None, refs,
                "WALL_PROPERTY_API_FACT_MISSING" if not wall_facts else "WALL_PROPERTY_API_FACT_AMBIGUOUS",
                "Exact structural wall property API fact is unresolved",
            ))
            continue

        fact = wall_facts[0]
        refs = refs + (
            {"source_api": "AreaObj.GetProperty", "unique_name": unique, "raw_result": fact.area_property_raw_result},
            {"source_api": "PropArea.GetWall", "property": fact.assigned_area_property, "raw_result": fact.wall_property_raw_result},
        )
        if fact.diagnostic_code is not None:
            result.append(_unresolved(
                record.inventory_record_id, "Wall", unique, record.story, record.area_label,
                fact.assigned_area_property, None, refs, fact.diagnostic_code,
                "Exact structural wall property dependency is unresolved",
            ))
        elif fact.assigned_area_property != _id(record.assigned_area_property):
            result.append(_unresolved(
                record.inventory_record_id, "Wall", unique, record.story, record.area_label,
                fact.assigned_area_property, None, refs, "WALL_PROPERTY_IDENTITY_CONFLICT",
                "API property does not exactly match WallInventory property",
            ))
        elif fact.layered:
            result.append(_unresolved(
                record.inventory_record_id, "Wall", unique, record.story, record.area_label,
                fact.assigned_area_property, None, refs, "LAYERED_WALL_MATERIAL_SOURCE_UNAVAILABLE",
                "Layered wall material is not resolved from GetWall MatProp",
            ))
        elif fact.wall_property_type_code != _SPECIFIED_WALL:
            result.append(_unresolved(
                record.inventory_record_id, "Wall", unique, record.story, record.area_label,
                fact.assigned_area_property, None, refs, "WALL_PROPERTY_FORM_UNRESOLVED",
                "Wall property does not prove one specified material identity",
            ))
        elif fact.material_name is None:
            result.append(_unresolved(
                record.inventory_record_id, "Wall", unique, record.story, record.area_label,
                fact.assigned_area_property, None, refs, "WALL_MATERIAL_IDENTITY_MISSING",
                "Specified non-layered wall property has no material identity",
            ))
        else:
            material_fact = material_facts.get(fact.material_name)
            if material_fact is None or not material_fact.type_known:
                result.append(_unresolved(
                    record.inventory_record_id, "Wall", unique, record.story, record.area_label,
                    fact.assigned_area_property, fact.material_name, refs, "MATERIAL_TYPE_UNRESOLVED",
                    "Exact wall material identity has no supported factual type",
                ))
            else:
                result.append(MaterialUsageReference(
                    record.inventory_record_id, "Wall", unique, record.story, record.area_label,
                    fact.assigned_area_property, fact.material_name, material_fact.material_type_code,
                    MaterialUsageStatus.RESOLVED_CONCRETE_USAGE if material_fact.concrete else MaterialUsageStatus.PROVEN_NON_CONCRETE,
                    refs + ({"source_api": "PropMaterial.GetTypeOAPI", "material_name": fact.material_name, "raw_result": material_fact.type_raw_result},),
                ))
    return result


def _wall_expected_identities(wall_inventory: WallInventory) -> tuple[str, ...]:
    identities: list[str] = []
    for record in wall_inventory.records:
        if record.classification_status is not WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE:
            continue
        unique = _id(record.etabs_area_unique_name)
        identities.append(unique if unique is not None else record.inventory_record_id)
    return tuple(sorted(identities))


def _material_definitions(
    fingerprint: str, usages: Sequence[MaterialUsageReference],
    facts: Mapping[str, MaterialApiFact], unit_context: MaterialUnitContext | None,
) -> tuple[UsedMaterialDefinition, ...]:
    grouped: defaultdict[str, list[MaterialUsageReference]] = defaultdict(list)
    for usage in usages:
        if usage.status is not MaterialUsageStatus.UNRESOLVED and usage.material_name is not None:
            grouped[usage.material_name].append(usage)

    result = []
    for name, material_usages in sorted(grouped.items()):
        fact = facts[name]
        diagnostics: tuple[MaterialPopulationDiagnostic, ...] = ()
        if fact.concrete:
            parsed = _finite(fact.raw_fc)
            factor = None if unit_context is None or not unit_context.supported else unit_context.stress_factor_to_mpa
            normalized = None if parsed is None or factor is None else parsed * factor
            if normalized is not None and math.isfinite(normalized):
                strength_status = ConcreteStrengthFactStatus.RESOLVED
            else:
                normalized = None
                strength_status = ConcreteStrengthFactStatus.UNRESOLVED
                diagnostics = (MaterialPopulationDiagnostic(
                    code="CONCRETE_FC_FACT_UNRESOLVED" if parsed is None else "CONCRETE_FC_UNIT_CONTEXT_UNRESOLVED",
                    message="Concrete raw Fc or its explicit unit context is unresolved",
                    material_name=name,
                    source_api="PropMaterial.GetOConcrete_1",
                ),)
            raw_fc = fact.raw_fc
        else:
            raw_fc, normalized = None, None
            strength_status = ConcreteStrengthFactStatus.NOT_APPLICABLE

        result.append(UsedMaterialDefinition(
            material_id=f"material:{_sha(fingerprint + chr(31) + name)}",
            model_fingerprint=fingerprint,
            material_name=name,
            material_type_code=int(fact.material_type_code),
            is_concrete=fact.concrete,
            raw_fc=raw_fc,
            canonical_fck_mpa=normalized,
            concrete_strength_status=strength_status,
            unit_context=unit_context if fact.concrete else None,
            usage_references=tuple(sorted(material_usages, key=lambda x: x.sort_key)),
            diagnostics=diagnostics,
        ))
    return tuple(result)


def _reconcile(
    domain: str,
    expected_identities: Sequence[str],
    usages: Sequence[MaterialUsageReference],
    *,
    source_available: bool,
) -> MaterialDomainReconciliation:
    expected = tuple(sorted(str(x) for x in expected_identities))
    expected_set = set(expected)
    rows = tuple(x for x in usages if x.component_type == domain)
    actual_values = tuple(_usage_population_identity(x) for x in rows)
    actual_counts = Counter(actual_values)
    actual_set = set(actual_values)
    duplicates = tuple(sorted(identity for identity, count in actual_counts.items() if count > 1))
    missing = tuple(sorted(expected_set - actual_set))
    unexpected = tuple(sorted(actual_set - expected_set))
    counts = Counter(x.status for x in rows)
    concrete = counts[MaterialUsageStatus.RESOLVED_CONCRETE_USAGE]
    non_concrete = counts[MaterialUsageStatus.PROVEN_NON_CONCRETE]
    unresolved = counts[MaterialUsageStatus.UNRESOLVED]
    actual_count = len(rows)
    terminal_count = concrete + non_concrete + unresolved
    reconciled = (
        not missing
        and not unexpected
        and not duplicates
        and actual_count == len(expected)
        and terminal_count == actual_count
    )
    return MaterialDomainReconciliation(
        domain=domain,
        expected_identities=expected,
        actual_identities=tuple(sorted(actual_values)),
        missing_identities=missing,
        unexpected_identities=unexpected,
        duplicate_identities=duplicates,
        expected_count=len(expected),
        resolved_concrete=concrete,
        proven_non_concrete=non_concrete,
        unresolved=unresolved,
        actual_count=actual_count,
        source_available=source_available,
        reconciled=reconciled,
    )


def _usage_population_identity(usage: MaterialUsageReference) -> str:
    return usage.component_identity or usage.usage_id


def _exact_used_material_names(
    summary_rows: Sequence[Mapping[str, Any]], assignment_rows: Sequence[Mapping[str, Any]],
    section_rows: Sequence[Mapping[str, Any]], wall_facts: Sequence[WallPropertyFact],
) -> frozenset[str]:
    assignments, sections = _index(assignment_rows, "UniqueName"), _index(section_rows, "Name")
    grouped: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in summary_rows:
        unique = _id(row.get("UniqueName"))
        if unique is not None:
            grouped[unique].append(dict(row))

    names: set[str] = set()
    for unique, rows in grouped.items():
        tokens = {_frame_type_token(row.get("Type")) for row in rows}
        if len(tokens) != 1 or next(iter(tokens)) not in _FRAME_TYPES:
            continue
        if len(rows) != 1 or len(assignments.get(unique, ())) != 1:
            continue
        section = _id(assignments[unique][0].get("SectProp"))
        if section is None or len(sections.get(section, ())) != 1:
            continue
        material = _id(sections[section][0].get("Material"))
        if material is not None:
            names.add(material)

    for fact in wall_facts:
        if (
            fact.diagnostic_code is None and not fact.layered
            and fact.wall_property_type_code == _SPECIFIED_WALL and fact.material_name is not None
        ):
            names.add(fact.material_name)
    return frozenset(names)


def _read_wall_fact(sap_model: Any, record: Any) -> WallPropertyFact:
    unique = _id(record.etabs_area_unique_name)
    if unique is None:
        raise ValueError("Structural wall candidate lacks exact ETABS UniqueName")
    try:
        area_raw = sap_model.AreaObj.GetProperty(unique)
        area_values, area_ret = _api_result(area_raw, 1)
    except Exception as exc:
        return WallPropertyFact(unique, None, None, None, None, None, {"error": str(exc)}, None, "AREA_PROPERTY_API_READ_ERROR")
    prop = _id(area_values[0]) if area_values else None
    if area_ret not in (None, 0) or prop is None:
        return WallPropertyFact(unique, prop, None, None, None, None, area_raw, None, "AREA_PROPERTY_API_RESULT_UNRESOLVED")

    try:
        wall_raw = sap_model.PropArea.GetWall(prop)
        wall_values, wall_ret = _api_result(wall_raw, 7)
    except Exception as exc:
        return WallPropertyFact(unique, prop, None, None, None, None, area_raw, {"error": str(exc)}, "WALL_PROPERTY_API_READ_ERROR")
    wall_type = _int(wall_values[0]) if len(wall_values) > 0 else None
    shell_type = _int(wall_values[1]) if len(wall_values) > 1 else None
    material = _id(wall_values[2]) if len(wall_values) > 2 else None
    thickness = wall_values[3] if len(wall_values) > 3 else None
    diagnostic = None if wall_ret in (None, 0) and len(wall_values) >= 4 else "WALL_PROPERTY_API_RESULT_UNRESOLVED"
    if shell_type == _LAYERED_SHELL:
        material = None
    return WallPropertyFact(unique, prop, wall_type, shell_type, material, thickness, area_raw, wall_raw, diagnostic)


def _read_material_fact(sap_model: Any, name: str) -> MaterialApiFact:
    try:
        type_raw = sap_model.PropMaterial.GetTypeOAPI(name)
        values, ret = _api_result(type_raw, 2)
    except Exception as exc:
        return MaterialApiFact(name, None, type_raw_result={"error": str(exc)}, diagnostic_code="MATERIAL_TYPE_API_READ_ERROR")
    mat_type = _int(values[0]) if values else None
    symmetry = _int(values[1]) if len(values) > 1 else None
    if ret not in (None, 0) or mat_type not in _KNOWN_MATERIAL_TYPES:
        return MaterialApiFact(name, mat_type, symmetry, type_raw_result=type_raw, diagnostic_code="MATERIAL_TYPE_API_RESULT_UNRESOLVED")
    if mat_type != _CONCRETE_TYPE:
        return MaterialApiFact(name, mat_type, symmetry, type_raw_result=type_raw)

    try:
        concrete_raw = sap_model.PropMaterial.GetOConcrete_1(name)
        concrete_values, concrete_ret = _api_result(concrete_raw, 10)
    except Exception as exc:
        return MaterialApiFact(
            name, mat_type, symmetry, type_raw_result=type_raw,
            concrete_raw_result={"error": str(exc)}, diagnostic_code="CONCRETE_API_READ_ERROR",
        )
    raw_fc = concrete_values[0] if concrete_values else None
    diagnostic = None if concrete_ret in (None, 0) and concrete_values else "CONCRETE_API_RESULT_UNRESOLVED"
    return MaterialApiFact(name, mat_type, symmetry, raw_fc, type_raw, concrete_raw, diagnostic)


def _unique_material_facts(
    facts: Sequence[MaterialApiFact],
) -> tuple[dict[str, MaterialApiFact], tuple[str, ...]]:
    grouped: defaultdict[str, list[MaterialApiFact]] = defaultdict(list)
    for fact in facts:
        grouped[fact.material_name].append(fact)
    return (
        {name: rows[0] for name, rows in grouped.items() if len(rows) == 1},
        tuple(sorted(name for name, rows in grouped.items() if len(rows) != 1)),
    )


def _index(rows: Sequence[Mapping[str, Any]] | Any, key: str) -> dict[str, tuple[Mapping[str, Any], ...]]:
    grouped: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = dict(raw)
        identity = _id(row.get(key))
        if identity is not None:
            grouped[identity].append(row)
    return {key_: tuple(sorted(value, key=_canonical)) for key_, value in grouped.items()}


def _unresolved(
    usage_id: str, component_type: str, component_identity: str | None,
    story: str | None, label: str | None, prop: str | None, material: str | None,
    refs: tuple[Mapping[str, Any], ...], code: str, message: str,
) -> MaterialUsageReference:
    return MaterialUsageReference(
        usage_id, component_type, component_identity, story, label, prop, material, None,
        MaterialUsageStatus.UNRESOLVED, refs,
        (MaterialPopulationDiagnostic(code, message, component_type, component_identity, material),),
    )


def _api_result(raw: Any, outputs: int) -> tuple[tuple[Any, ...], int | None]:
    values = list(raw) if isinstance(raw, (tuple, list)) else []
    if not values:
        return (), _int(raw) if isinstance(raw, int) else None
    ret = None
    if len(values) > outputs and _int(values[-1]) is not None:
        ret = _int(values.pop())
    return tuple(values[:outputs]), ret


def _frame_type_token(value: Any) -> str | None:
    text = _id(value)
    return None if text is None else text.casefold()


def _frame_usage_id(fingerprint: str, domain: str, unique: str) -> str:
    return f"frame:{_sha(chr(31).join((fingerprint, domain, unique)))}"


def _ref(table: str, row: Mapping[str, Any]) -> Mapping[str, Any]:
    return {"source_table": table, "row_digest": _sha(_canonical(row)), "row": dict(row)}


def _one(rows: Sequence[Mapping[str, Any]], key: str) -> str | None:
    values = {_id(x.get(key)) for x in rows} - {None}
    return next(iter(values)) if len(values) == 1 else None


def _id(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    candidate = getattr(value, "value", None)
    if isinstance(candidate, int) and not isinstance(candidate, bool):
        return candidate
    try:
        return int(value)
    except Exception:
        return None


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _canonical(row: Mapping[str, Any]) -> str:
    return json.dumps(
        _plain(dict(row)), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"), default=str,
    )


def _diagnostic_sort_key(value: MaterialPopulationDiagnostic) -> tuple[str, str, str, str]:
    return (
        value.code,
        value.domain or "",
        value.component_identity or "",
        value.material_name or "",
    )


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return _plain(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(x) for x in value]
    enum_value = getattr(value, "value", None)
    if enum_value is not None and not isinstance(value, (str, int, float, bool)):
        return _plain(enum_value)
    return value


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "ConcreteStrengthFactStatus",
    "MaterialApiFact",
    "MaterialDomainReconciliation",
    "MaterialPopulationDiagnostic",
    "MaterialPopulationReadiness",
    "MaterialPopulationSources",
    "MaterialSourceContractResolutionError",
    "MaterialUnitContext",
    "MaterialUsageReference",
    "MaterialUsageStatus",
    "UsedMaterialDefinition",
    "UsedRcMaterialPopulation",
    "WallPropertyFact",
    "build_used_rc_material_population",
    "build_used_rc_material_population_from_verified_session",
    "canonical_material_population_json",
    "read_material_population_sources_from_verified_session",
]
