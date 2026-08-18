from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

import tbdy_engine.features.used_rc_material_population as m0_module
from tbdy_engine.etabs.safety import (
    EtabsCapabilitySnapshot,
    EtabsSessionIdentity,
    EtabsUnitSnapshot,
    EtabsVerifiedSession,
)
from tbdy_engine.features.etabs_com_attach import (
    ATTACH_STATUS_ATTACHED,
    STRATEGY_COMTYPES_HELPER_GET_OBJECT_PROCESS,
    EtabsAttachResult,
)
from tbdy_engine.features.used_rc_material_population import (
    ConcreteStrengthFactStatus,
    MaterialApiFact,
    MaterialPopulationReadiness,
    MaterialPopulationSources,
    MaterialSourceContractResolutionError,
    MaterialUnitContext,
    MaterialUsageStatus,
    WallPropertyFact,
    build_used_rc_material_population,
    canonical_material_population_json,
    read_material_population_sources_from_verified_session,
)
from tbdy_engine.features.wall_inventory import build_wall_inventory


MODEL = "MODEL::M0"
CONCRETE = "STEEL-C777::OPAQUE"
NON_CONCRETE = "CONC-C999::OPAQUE"

FRAME_SUMMARY = (
    {"UniqueName": "B-1", "Type": "Beam", "Story": "S1", "Label": "B1"},
    {"UniqueName": "B-2", "Type": "Beam", "Story": "S2", "Label": "B2"},
    {"UniqueName": "C-1", "Type": "Column", "Story": "S1", "Label": "C1"},
    {"UniqueName": "C-2", "Type": "Column", "Story": "S2", "Label": "C2"},
    {"UniqueName": "BR-1", "Type": "Brace", "Story": "S1", "Label": "BR1"},
)
FRAME_ASSIGNMENTS = (
    {"UniqueName": "B-1", "SectProp": "SEC-B", "Story": "S1", "Label": "B1"},
    {"UniqueName": "B-2", "SectProp": "SEC-B", "Story": "S2", "Label": "B2"},
    {"UniqueName": "C-1", "SectProp": "SEC-C", "Story": "S1", "Label": "C1"},
    {"UniqueName": "C-2", "SectProp": "SEC-S", "Story": "S2", "Label": "C2"},
)
FRAME_SECTIONS = (
    {"Name": "SEC-B", "Material": CONCRETE, "Shape": "Anything"},
    {"Name": "SEC-C", "Material": CONCRETE, "Shape": "AnythingElse"},
    {"Name": "SEC-S", "Material": NON_CONCRETE, "Shape": "Opaque"},
)


def _wall_inventory(*, unique: str = "A-W1", prop: str = "WP-1", model: str = MODEL):
    return build_wall_inventory(
        model_fingerprint=model,
        area_assignment_rows=[
            {
                "UniqueName": unique,
                "Story": "S1",
                "Label": "W1",
                "SectionProperty": prop,
                "PropertyType": "Wall",
            }
        ],
        wall_property_rows=[
            {"Name": prop, "Material": "TABLE-MATERIAL-IS-NOT-M0-AUTHORITY", "Thickness": 0.3}
        ],
        pier_assignment_rows=[],
    )


def _unit_context(*, force: int = 4, length: int = 6):
    return MaterialUnitContext(
        present_force_unit_code=force,
        present_length_unit_code=length,
        source_api="GetPresentUnits_2",
        raw_present_units=(force, length, 2, 0),
    )


def _sources(
    *,
    summary=FRAME_SUMMARY,
    assignments=FRAME_ASSIGNMENTS,
    sections=FRAME_SECTIONS,
    wall=None,
    wall_facts=None,
    material_facts=None,
    unit_context=None,
    summary_available=True,
    assignment_available=True,
    section_available=True,
):
    wall = wall or _wall_inventory()
    if wall_facts is None:
        wall_facts = (
            WallPropertyFact(
                etabs_area_unique_name="A-W1",
                assigned_area_property="WP-1",
                wall_property_type_code=1,
                shell_type_code=1,
                material_name=CONCRETE,
                thickness_raw=0.3,
            ),
        )
    if material_facts is None:
        material_facts = (
            MaterialApiFact(
                material_name=CONCRETE,
                material_type_code=2,
                raw_fc=32000.0,
                type_raw_result=(2, 0, 0),
                concrete_raw_result=(32000.0, False, 0.0, 1, 1, 0.002, 0.004, 0.0, 0.0, 0.0, 0),
            ),
            MaterialApiFact(
                material_name=NON_CONCRETE,
                material_type_code=1,
                type_raw_result=(1, 0, 0),
            ),
        )
    return MaterialPopulationSources(
        frame_summary_rows=summary,
        frame_assignment_rows=assignments,
        frame_section_material_rows=sections,
        wall_inventory=wall,
        wall_property_facts=wall_facts,
        material_facts=material_facts,
        unit_context=_unit_context() if unit_context is None else unit_context,
        frame_summary_available=summary_available,
        frame_assignment_available=assignment_available,
        frame_section_material_available=section_available,
    )


def _build(**kwargs):
    return build_used_rc_material_population(
        model_fingerprint=MODEL,
        sources=_sources(**kwargs),
    )


def _reconciliation(population, domain):
    return next(row for row in population.reconciliations if row.domain == domain)


def _usage(population, identity):
    return next(row for row in population.usages if row.component_identity == identity)


def test_complete_beam_column_wall_population_reconciles_exactly():
    population = _build()
    assert population.readiness is MaterialPopulationReadiness.COMPLETE

    beam = _reconciliation(population, "Beam")
    assert beam.expected_identities == ("B-1", "B-2")
    assert beam.actual_identities == ("B-1", "B-2")
    assert beam.missing_identities == ()
    assert beam.unexpected_identities == ()
    assert beam.duplicate_identities == ()
    assert (beam.expected_count, beam.resolved_concrete, beam.proven_non_concrete, beam.unresolved, beam.actual_count) == (2, 2, 0, 0, 2)
    assert beam.reconciled and beam.complete

    column = _reconciliation(population, "Column")
    assert column.expected_identities == ("C-1", "C-2")
    assert column.actual_identities == ("C-1", "C-2")
    assert (column.expected_count, column.resolved_concrete, column.proven_non_concrete, column.unresolved, column.actual_count) == (2, 1, 1, 0, 2)
    assert column.reconciled and column.complete

    wall = _reconciliation(population, "Wall")
    assert wall.expected_identities == ("A-W1",)
    assert wall.actual_identities == ("A-W1",)
    assert (wall.expected_count, wall.resolved_concrete, wall.proven_non_concrete, wall.unresolved, wall.actual_count) == (1, 1, 0, 0, 1)
    assert wall.reconciled and wall.complete


def test_reconciliation_expected_population_is_independent_of_emitted_usage(monkeypatch):
    original = m0_module._frame_usages

    def drop_one_expected_usage(fingerprint, sources, material_facts, frame_population):
        rows = original(fingerprint, sources, material_facts, frame_population)
        return [row for row in rows if row.component_identity != "B-1"]

    monkeypatch.setattr(m0_module, "_frame_usages", drop_one_expected_usage)
    population = _build()
    beam = _reconciliation(population, "Beam")

    assert beam.expected_identities == ("B-1", "B-2")
    assert beam.actual_identities == ("B-2",)
    assert beam.missing_identities == ("B-1",)
    assert beam.expected_count == 2
    assert beam.actual_count == 1
    assert not beam.reconciled
    assert not beam.complete
    assert population.readiness is MaterialPopulationReadiness.PARTIAL


def test_many_usages_of_same_material_deduplicate_to_one_definition_and_keep_references():
    population = _build()
    assert len(population.used_material_definitions) == 2
    concrete = next(x for x in population.used_material_definitions if x.material_name == CONCRETE)
    assert concrete.is_concrete
    assert {x.component_identity for x in concrete.usage_references} == {"B-1", "B-2", "C-1", "A-W1"}
    assert {x.component_type for x in concrete.usage_references} == {"Beam", "Column", "Wall"}
    assert all(x.assigned_property for x in concrete.usage_references)
    assert all(x.source_references for x in concrete.usage_references)


def test_material_name_is_opaque_and_type_and_strength_are_not_parsed_from_it():
    population = _build()
    concrete = next(x for x in population.used_material_definitions if x.material_name == CONCRETE)
    other = next(x for x in population.used_material_definitions if x.material_name == NON_CONCRETE)
    assert concrete.material_type_code == 2
    assert concrete.canonical_fck_mpa == pytest.approx(32.0)
    assert other.material_type_code == 1
    assert not other.is_concrete
    assert _usage(population, "C-2").status is MaterialUsageStatus.PROVEN_NON_CONCRETE


def test_proven_non_concrete_material_is_separately_accounted():
    population = _build()
    usage = _usage(population, "C-2")
    assert usage.status is MaterialUsageStatus.PROVEN_NON_CONCRETE
    column = _reconciliation(population, "Column")
    assert column.proven_non_concrete == 1
    definition = next(x for x in population.used_material_definitions if x.material_name == NON_CONCRETE)
    assert definition.concrete_strength_status is ConcreteStrengthFactStatus.NOT_APPLICABLE
    assert definition.raw_fc is None
    assert definition.canonical_fck_mpa is None


def test_missing_exact_section_assignment_is_unresolved_and_retained():
    assignments = tuple(row for row in FRAME_ASSIGNMENTS if row["UniqueName"] != "B-1")
    population = _build(assignments=assignments)
    usage = _usage(population, "B-1")
    assert usage.status is MaterialUsageStatus.UNRESOLVED
    assert {d.code for d in usage.diagnostics} == {"FRAME_SECTION_ASSIGNMENT_MISSING"}
    beam = _reconciliation(population, "Beam")
    assert beam.expected_count == 2 and beam.actual_count == 2 and beam.unresolved == 1
    assert beam.reconciled
    assert not beam.complete
    assert population.readiness is MaterialPopulationReadiness.PARTIAL


def test_missing_material_identity_is_unresolved_and_retained():
    sections = tuple(
        {k: v for k, v in row.items() if k != "Material"} if row["Name"] == "SEC-B" else row
        for row in FRAME_SECTIONS
    )
    population = _build(sections=sections)
    assert _usage(population, "B-1").status is MaterialUsageStatus.UNRESOLVED
    assert _usage(population, "B-2").status is MaterialUsageStatus.UNRESOLVED
    assert {d.code for d in _usage(population, "B-1").diagnostics} == {"FRAME_MATERIAL_IDENTITY_MISSING"}


def test_missing_material_type_fact_is_unresolved():
    facts = (MaterialApiFact(material_name=NON_CONCRETE, material_type_code=1),)
    population = _build(material_facts=facts)
    assert _usage(population, "B-1").status is MaterialUsageStatus.UNRESOLVED
    assert _usage(population, "A-W1").status is MaterialUsageStatus.UNRESOLVED


def test_conflicting_exact_frame_assignment_is_unresolved():
    assignments = FRAME_ASSIGNMENTS + (
        {"UniqueName": "B-1", "SectProp": "OTHER", "Story": "S1", "Label": "B1"},
    )
    population = _build(assignments=assignments)
    usage = _usage(population, "B-1")
    assert usage.status is MaterialUsageStatus.UNRESOLVED
    assert {d.code for d in usage.diagnostics} == {"FRAME_SECTION_ASSIGNMENT_AMBIGUOUS"}
    assert len(usage.source_references) == 3


def test_duplicate_frame_object_identity_is_detected_without_double_counting_object():
    summary = FRAME_SUMMARY + (dict(FRAME_SUMMARY[0]),)
    population = _build(summary=summary)
    b1 = _usage(population, "B-1")
    assert b1.status is MaterialUsageStatus.UNRESOLVED
    assert {d.code for d in b1.diagnostics} == {"DUPLICATE_OBJECT_IDENTITY"}
    beam = _reconciliation(population, "Beam")
    assert beam.expected_identities == ("B-1", "B-2")
    assert beam.actual_identities == ("B-1", "B-2")
    assert beam.duplicate_identities == ()
    assert beam.expected_count == 2
    assert beam.unresolved == 1
    assert beam.reconciled and not beam.complete


def test_missing_frame_type_is_retained_as_population_uncertainty_and_prevents_complete():
    summary = tuple(
        {k: v for k, v in row.items() if k != "Type"} if row["UniqueName"] == "B-1" else row
        for row in FRAME_SUMMARY
    )
    population = _build(summary=summary)
    usage = _usage(population, "B-1")
    assert usage.component_type == "Frame"
    assert usage.status is MaterialUsageStatus.UNRESOLVED
    assert {d.code for d in usage.diagnostics} == {"FRAME_COMPONENT_TYPE_MISSING"}
    assert _reconciliation(population, "Beam").expected_identities == ("B-2",)
    assert population.readiness is MaterialPopulationReadiness.PARTIAL


def test_conflicting_frame_type_is_retained_as_population_uncertainty_and_prevents_complete():
    summary = FRAME_SUMMARY + (
        {"UniqueName": "B-1", "Type": "Column", "Story": "S1", "Label": "B1"},
    )
    population = _build(summary=summary)
    usage = _usage(population, "B-1")
    assert usage.component_type == "Frame"
    assert usage.status is MaterialUsageStatus.UNRESOLVED
    assert {d.code for d in usage.diagnostics} == {"FRAME_COMPONENT_TYPE_CONFLICT"}
    assert "B-1" not in _reconciliation(population, "Beam").expected_identities
    assert "B-1" not in _reconciliation(population, "Column").expected_identities
    assert population.readiness is MaterialPopulationReadiness.PARTIAL


def test_unrecognized_frame_type_is_not_guessed_from_name_section_or_geometry():
    summary = tuple(
        ({**row, "Type": "Girder"} if row["UniqueName"] == "B-1" else row)
        for row in FRAME_SUMMARY
    )
    population = _build(summary=summary)
    usage = _usage(population, "B-1")
    assert usage.component_type == "Frame"
    assert usage.status is MaterialUsageStatus.UNRESOLVED
    assert {d.code for d in usage.diagnostics} == {"FRAME_COMPONENT_TYPE_UNRECOGNIZED"}
    assert population.readiness is MaterialPopulationReadiness.PARTIAL


def test_proven_brace_is_positively_excluded_with_factual_provenance_without_blocking():
    population = _build()
    assert all(row.component_identity != "BR-1" for row in population.usages)
    exclusions = [
        diagnostic
        for diagnostic in population.diagnostics
        if diagnostic.code == "FRAME_NON_TARGET_POSITIVELY_EXCLUDED"
        and diagnostic.component_identity == "BR-1"
    ]
    assert len(exclusions) == 1
    exclusion = exclusions[0]
    assert exclusion.details["raw_type"] == "brace"
    assert exclusion.details["source_table"] == "Frame Assignments - Summary"
    assert exclusion.details["source_references"]
    assert population.readiness is MaterialPopulationReadiness.COMPLETE


def test_layered_wall_without_layer_material_source_is_unresolved_even_if_name_is_present():
    wall_fact = WallPropertyFact(
        etabs_area_unique_name="A-W1",
        assigned_area_property="WP-1",
        wall_property_type_code=1,
        shell_type_code=6,
        material_name=CONCRETE,
        thickness_raw=0.3,
    )
    population = _build(wall_facts=(wall_fact,))
    usage = _usage(population, "A-W1")
    assert usage.status is MaterialUsageStatus.UNRESOLVED
    assert {d.code for d in usage.diagnostics} == {"LAYERED_WALL_MATERIAL_SOURCE_UNAVAILABLE"}
    wall = _reconciliation(population, "Wall")
    assert wall.expected_count == 1 and wall.actual_count == 1 and wall.unresolved == 1


@pytest.mark.parametrize(
    "unit_context,raw_fc,expected",
    [
        (_unit_context(force=4, length=6), 32000.0, 32.0),
        (_unit_context(force=3, length=4), 32.0, 32.0),
    ],
)
def test_fc_normalization_uses_explicit_unit_context_only(unit_context, raw_fc, expected):
    facts = (
        MaterialApiFact(material_name=CONCRETE, material_type_code=2, raw_fc=raw_fc),
        MaterialApiFact(material_name=NON_CONCRETE, material_type_code=1),
    )
    population = _build(material_facts=facts, unit_context=unit_context)
    concrete = next(x for x in population.used_material_definitions if x.is_concrete)
    assert concrete.raw_fc == raw_fc
    assert concrete.canonical_fck_mpa == pytest.approx(expected)
    assert concrete.concrete_strength_status is ConcreteStrengthFactStatus.RESOLVED


def test_unresolved_unit_context_cannot_produce_canonical_fck():
    sources = _sources()
    sources = MaterialPopulationSources(
        frame_summary_rows=sources.frame_summary_rows,
        frame_assignment_rows=sources.frame_assignment_rows,
        frame_section_material_rows=sources.frame_section_material_rows,
        wall_inventory=sources.wall_inventory,
        wall_property_facts=sources.wall_property_facts,
        material_facts=sources.material_facts,
        unit_context=MaterialUnitContext(4, 6, None, None),
    )
    population = build_used_rc_material_population(model_fingerprint=MODEL, sources=sources)
    concrete = next(x for x in population.used_material_definitions if x.is_concrete)
    assert concrete.raw_fc == 32000.0
    assert concrete.canonical_fck_mpa is None
    assert concrete.concrete_strength_status is ConcreteStrengthFactStatus.UNRESOLVED
    assert population.readiness is MaterialPopulationReadiness.PARTIAL


def test_raw_fc_is_preserved_without_magnitude_interpretation():
    raw = 43123.5
    facts = (
        MaterialApiFact(material_name=CONCRETE, material_type_code=2, raw_fc=raw),
        MaterialApiFact(material_name=NON_CONCRETE, material_type_code=1),
    )
    population = _build(material_facts=facts)
    concrete = next(x for x in population.used_material_definitions if x.is_concrete)
    assert concrete.raw_fc == raw
    assert concrete.canonical_fck_mpa == pytest.approx(raw * 0.001)


def test_reorder_invariance_for_all_factual_sources():
    a = _build()
    b = _build(
        summary=tuple(reversed(FRAME_SUMMARY)),
        assignments=tuple(reversed(FRAME_ASSIGNMENTS)),
        sections=tuple(reversed(FRAME_SECTIONS)),
        wall_facts=tuple(reversed(_sources().wall_property_facts)),
        material_facts=tuple(reversed(_sources().material_facts)),
    )
    assert canonical_material_population_json(a) == canonical_material_population_json(b)


def test_reorder_invariance_with_conflicting_type_and_positive_exclusion():
    summary = FRAME_SUMMARY + (
        {"UniqueName": "B-1", "Type": "Column", "Story": "S1", "Label": "B1"},
    )
    a = _build(summary=summary)
    b = _build(summary=tuple(reversed(summary)))
    assert canonical_material_population_json(a) == canonical_material_population_json(b)
    assert a.readiness is MaterialPopulationReadiness.PARTIAL


def test_wall_inventory_is_not_mutated_by_material_population_builder():
    wall = _wall_inventory()
    before = deepcopy(wall.as_dict())
    build_used_rc_material_population(model_fingerprint=MODEL, sources=_sources(wall=wall))
    assert wall.as_dict() == before


def test_unavailable_frame_source_blocks_readiness_instead_of_claiming_complete():
    population = _build(assignments=(), assignment_available=False)
    assert population.readiness is MaterialPopulationReadiness.BLOCKED
    assert _reconciliation(population, "Beam").unresolved == 2
    assert _reconciliation(population, "Column").unresolved == 2


def test_new_m0_source_contains_no_material_engineering_authority():
    source = (
        Path(__file__).resolve().parents[2]
        / "tbdy_engine"
        / "features"
        / "used_rc_material_population.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "P" + "ASS",
        "F" + "AIL",
        "2" + "5.0",
        "C" + "25/30",
        "Minimal" + "CheckEngine",
        "checks" + ".engine",
        "material " + "adequacy",
    )
    upper = source.upper()
    for token in forbidden:
        assert token.upper() not in upper


class FakeDatabaseTables:
    def __init__(self, tables):
        self.tables = tables
        self.calls = []

    def GetTableForDisplayArray(self, table_key, *args):
        self.calls.append(table_key)
        rows = self.tables[table_key]
        columns = tuple(dict.fromkeys(key for row in rows for key in row))
        return {"columns": columns, "rows": rows}


class FakeAreaObj:
    def __init__(self, assignments):
        self.assignments = assignments
        self.calls = []

    def GetProperty(self, unique):
        self.calls.append(unique)
        return self.assignments[unique], 0


class FakePropArea:
    def __init__(self, properties):
        self.properties = properties
        self.calls = []

    def GetWall(self, prop):
        self.calls.append(prop)
        return (*self.properties[prop], 0)


class FakePropMaterial:
    def __init__(self, material_types, concrete_fc):
        self.material_types = material_types
        self.concrete_fc = concrete_fc
        self.type_calls = []
        self.concrete_calls = []

    def GetTypeOAPI(self, name):
        self.type_calls.append(name)
        return self.material_types[name], 0, 0

    def GetOConcrete_1(self, name):
        self.concrete_calls.append(name)
        fc = self.concrete_fc[name]
        return fc, False, 0.0, 1, 1, 0.002, 0.004, 0.0, 0.0, 0


class FakeSap:
    def __init__(self):
        self.DatabaseTables = FakeDatabaseTables(
            {
                "Frame Assignments - Summary": list(FRAME_SUMMARY),
                "Frame Assignments - Section Properties": list(FRAME_ASSIGNMENTS),
                "Frame Section Property Definitions - Summary": list(FRAME_SECTIONS),
            }
        )
        self.AreaObj = FakeAreaObj({"A-W1": "WP-1"})
        self.PropArea = FakePropArea({"WP-1": (1, 1, CONCRETE, 0.3, 0, "", "GUID")})
        self.PropMaterial = FakePropMaterial(
            {CONCRETE: 2, NON_CONCRETE: 1},
            {CONCRETE: 32000.0},
        )


def _verified_session(
    sap,
    *,
    model_fingerprint=None,
    model_fingerprint_source="UNAVAILABLE_FROM_CONSUMED_API",
):
    attach = EtabsAttachResult(
        status=ATTACH_STATUS_ATTACHED,
        strategy=STRATEGY_COMTYPES_HELPER_GET_OBJECT_PROCESS,
        etabs_object=object(),
        sap_model=sap,
        attempts=(),
    )
    identity = EtabsSessionIdentity(
        process_id=None,
        attach_strategy=STRATEGY_COMTYPES_HELPER_GET_OBJECT_PROCESS,
        program_api_version=2.3,
        program_name="ETABS",
        program_version="23.2.0",
        program_level="Ultimate",
        internal_program_version=23.2,
        model_full_path=r"C:\tmp\MODEL.EDB",
        model_fingerprint=model_fingerprint,
        model_fingerprint_source=model_fingerprint_source,
        model_locked=True,
        units=EtabsUnitSnapshot(
            present_units=6,
            database_units=6,
            present_force_unit=4,
            present_length_unit=6,
            present_temperature_unit=2,
            database_force_unit=4,
            database_length_unit=6,
            database_temperature_unit=2,
            present_units_api="GetPresentUnits_2",
            database_units_api="GetDatabaseUnits_2",
        ),
    )
    return EtabsVerifiedSession(attach, identity, EtabsCapabilitySnapshot())


def test_direct_reader_requires_verified_session_contract():
    with pytest.raises(TypeError):
        read_material_population_sources_from_verified_session(
            session=object(),
            wall_inventory=_wall_inventory(),
        )


def test_direct_reader_blocks_before_any_etabs_read_when_model_binding_contract_is_unresolved():
    sap = FakeSap()
    session = _verified_session(sap)
    wall = _wall_inventory()

    with pytest.raises(MaterialSourceContractResolutionError) as exc_info:
        read_material_population_sources_from_verified_session(
            session=session,
            wall_inventory=wall,
        )

    exc = exc_info.value
    assert exc.verdict == "NEEDS_SOURCE_CONTRACT_RESOLUTION"
    assert exc.details["session_model_full_path"] == r"C:\tmp\MODEL.EDB"
    assert exc.details["session_model_fingerprint"] is None
    assert exc.details["session_model_fingerprint_source"] == "UNAVAILABLE_FROM_CONSUMED_API"
    assert exc.details["wall_inventory_model_fingerprint"] == MODEL
    assert "minimum_missing_binding" in exc.details
    assert sap.DatabaseTables.calls == []
    assert sap.AreaObj.calls == []
    assert sap.PropArea.calls == []
    assert sap.PropMaterial.type_calls == []
    assert sap.PropMaterial.concrete_calls == []


def test_unrelated_nonempty_session_fingerprint_is_not_treated_as_wall_inventory_binding():
    sap = FakeSap()
    session = _verified_session(
        sap,
        model_fingerprint=MODEL,
        model_fingerprint_source="SOME_OTHER_IDENTITY_SEMANTIC",
    )

    with pytest.raises(MaterialSourceContractResolutionError):
        read_material_population_sources_from_verified_session(
            session=session,
            wall_inventory=_wall_inventory(),
        )

    assert sap.DatabaseTables.calls == []


def test_cross_model_wall_inventory_never_silently_executes_while_binding_contract_is_unresolved():
    sap = FakeSap()
    session = _verified_session(sap)
    other_wall = _wall_inventory(model="MODEL::OTHER")

    with pytest.raises(MaterialSourceContractResolutionError) as exc_info:
        read_material_population_sources_from_verified_session(
            session=session,
            wall_inventory=other_wall,
        )

    assert exc_info.value.details["wall_inventory_model_fingerprint"] == "MODEL::OTHER"
    assert sap.DatabaseTables.calls == []
