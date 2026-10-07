"""Q1P wall-to-existing Area conversion; no population or live acceptance."""
from dataclasses import replace
from decimal import Decimal

import pytest

from test_native_wall_thickness_provenance import wall_runtime, material_runtime
from unit_contract_fixtures import wall as synthetic_wall
import tbdy_engine.etabs.oapi.object_model as raw_owner
import tbdy_engine.providers.etabs_area_contributor_provider as consumer
from tbdy_engine.etabs.oapi.area_contributors import AreaDesignOrientation
from tbdy_engine.etabs.oapi.area_modifiers import (
    AreaModifierReadFact, AreaModifierSurface, AreaModifierVector,
)
from tbdy_engine.providers.etabs_frame_flexural_base_provider import _qualified_quantity


@pytest.fixture
def area_consumer(monkeypatch):
    def modifiers(session, *, surface, target_name):
        assert surface is AreaModifierSurface.AREA_PROPERTY
        return AreaModifierReadFact(
            surface=surface, target_name=target_name,
            modifiers=AreaModifierVector.from_sequence([1.] * 10), return_code=0,
        )
    monkeypatch.setattr(consumer, "get_area_modifiers_from_session", modifiers)


def capture(session):
    return consumer._capture_property_state(
        session, property_name="Wall40", orientation=AreaDesignOrientation.WALL,
    )


def test_real_getter_to_unchanged_area_consumer_converts_fixture_metres(wall_runtime, area_consumer, monkeypatch):
    conversions = []
    actual = consumer._qualified_quantity
    def record(value, binding, dimension):
        result = actual(value, binding, dimension)
        conversions.append((value, binding.output_key, binding.source_unit, dimension, result))
        return result
    monkeypatch.setattr(consumer, "_qualified_quantity", record)
    result = capture(wall_runtime.session)
    assert result.wall_source_fact.raw_response == wall_runtime.wall.raw
    assert result.raw_thickness == result.wall_source_fact.thickness == .4
    assert conversions == [(.4, "Thickness", "m", "L", Decimal("400"))]
    assert result.thickness == .4
    binding = result.wall_source_fact.source_unit_for("Thickness", "L")
    assert binding.evidence_ref in result.source_refs
    assert wall_runtime.wall.calls == ["Wall40"] and not wall_runtime.forbidden


def test_displayed_raw_thickness_without_binding_is_not_promoted(wall_runtime, area_consumer, monkeypatch):
    raw = replace(raw_owner.read_wall_property_from_session(wall_runtime.session, "Wall40"),
                  unit_provenance=())
    monkeypatch.setattr(consumer, "read_wall_property_from_session", lambda *args: raw)
    state = capture(wall_runtime.session)
    assert state.thickness is None and state.raw_thickness == .4
    assert any("UNIT_UNQUALIFIED:MISSING_OR_DUPLICATE_OUTPUT_BINDING" in ref for ref in state.source_refs)


@pytest.mark.parametrize("unit,value", [("mm", 400.), ("cm", 40.), ("m", .4)])
def test_existing_converter_supported_length_tokens_are_independent_synthetic_evidence(
    wall_runtime, area_consumer, monkeypatch, unit, value,
):
    # Explicit synthetic authority only: this does not extend live safety/decoder
    # qualification of mm/cm or claim that a native acquisition supplied them.
    fact = synthetic_wall("Wall40", thickness=value, unit=unit)
    monkeypatch.setattr(consumer, "read_wall_property_from_session", lambda *args: fact)
    p = fact.source_unit_for("Thickness", "L")
    assert p.authority_ref == "fixture:independent-units"
    assert _qualified_quantity(value, p, "L") == Decimal("400")
    state = capture(wall_runtime.session)
    assert state.thickness == .4 and state.raw_thickness == value
    assert state.wall_source_fact.raw_response == fact.raw_response
    assert not wall_runtime.wall.calls


def test_failure_does_not_repair_any_material_or_population_context(wall_runtime, area_consumer):
    wall_runtime.wall.raw = (1, 6, "C35/45", .4, 0, "", "guid", 0)
    state = capture(wall_runtime.session)
    assert state.thickness is None
    assert any("GetWall:Wall40:UNRESOLVED" in ref for ref in state.source_refs)
    assert wall_runtime.wall.calls == ["Wall40"] and not wall_runtime.forbidden
