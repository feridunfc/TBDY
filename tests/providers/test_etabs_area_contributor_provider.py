from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.providers.etabs_area_contributor_provider as subject
from tbdy_engine.etabs.oapi.area_contributors import (
    AreaDesignOrientation,
    AreaDesignOrientationFact,
    AreaLocalAxesFact,
    AreaMaterialOverwriteFact,
    AreaPropertyFamilyProbeFact,
    AreaTransformationMatrixFact,
)
from tbdy_engine.etabs.oapi.area_modifiers import (
    AreaModifierReadFact,
    AreaModifierSurface,
    AreaModifierVector,
)


class _FakeSession:
    pass


def _modifier(surface, target, value=1.0):
    return AreaModifierReadFact(
        surface=surface,
        target_name=target,
        modifiers=AreaModifierVector.from_sequence([value] * 10),
        return_code=0,
    )


@pytest.fixture
def factual_runtime(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)
    monkeypatch.setattr(
        subject,
        "read_area_names_from_session",
        lambda _session: (("A-W", "A-F", "A-N"), object()),
    )
    properties = {"A-W": "Wall40", "A-F": "Slab15", "A-N": "None"}
    orientations = {
        "A-W": AreaDesignOrientation.WALL,
        "A-F": AreaDesignOrientation.FLOOR,
        "A-N": AreaDesignOrientation.NULL,
    }

    monkeypatch.setattr(
        subject,
        "read_area_property_assignment_from_session",
        lambda _session, name: SimpleNamespace(property_name=properties[name]),
    )
    monkeypatch.setattr(
        subject,
        "read_area_design_orientation_from_session",
        lambda _session, name: AreaDesignOrientationFact(
            area_name=name,
            orientation_code=int(orientations[name]),
            return_code=0,
        ),
    )
    monkeypatch.setattr(
        subject,
        "read_area_local_axes_from_session",
        lambda _session, name: AreaLocalAxesFact(
            area_name=name,
            angle_degrees=0.0,
            advanced=False,
            return_code=0,
        ),
    )
    monkeypatch.setattr(
        subject,
        "read_area_transformation_matrix_from_session",
        lambda _session, name: AreaTransformationMatrixFact(
            area_name=name,
            values=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            return_code=0,
        ),
    )
    monkeypatch.setattr(
        subject,
        "read_area_material_overwrite_from_session",
        lambda _session, name: AreaMaterialOverwriteFact(
            area_name=name,
            raw_material_name="None",
            return_code=0,
        ),
    )

    def modifiers(_session, *, surface, target_name):
        return _modifier(surface, target_name, 1.0 if surface is AreaModifierSurface.AREA_OBJECT else 0.5)

    monkeypatch.setattr(subject, "get_area_modifiers_from_session", modifiers)
    monkeypatch.setattr(
        subject,
        "read_wall_property_from_session",
        lambda _session, name: SimpleNamespace(
            wall_type=1,
            shell_type=2,
            material_name="C35/45",
            thickness=0.40,
        ),
    )
    monkeypatch.setattr(
        subject,
        "read_slab_property_probe_from_session",
        lambda _session, name: AreaPropertyFamilyProbeFact(
            property_name=name,
            family="SLAB",
            family_type_code=0,
            shell_type_code=2,
            material_name="C35/45",
            thickness=0.15,
            return_code=0,
        ),
    )
    monkeypatch.setattr(
        subject,
        "read_deck_property_probe_from_session",
        lambda _session, name: AreaPropertyFamilyProbeFact(
            property_name=name,
            family="DECK",
            family_type_code=None,
            shell_type_code=None,
            material_name=None,
            thickness=None,
            return_code=1,
        ),
    )
    return session


def test_complete_population_preserves_object_and_property_facts(factual_runtime):
    population = subject.capture_area_contributor_population_from_session(
        factual_runtime,
        model_fingerprint="model-1",
        evidence_epoch_id="epoch-1",
        session_provenance_ref="session-1",
    )

    assert population.expected_area_names == ("A-F", "A-N", "A-W")
    assert tuple(row.area_name for row in population.rows) == population.expected_area_names
    wall = next(row for row in population.rows if row.area_name == "A-W")
    floor = next(row for row in population.rows if row.area_name == "A-F")
    null = next(row for row in population.rows if row.area_name == "A-N")

    assert wall.property_state.family is subject.AreaPropertyFamily.WALL
    assert floor.property_state.family is subject.AreaPropertyFamily.SLAB
    assert floor.property_state.shell_type_code == 2
    assert null.property_state is None
    assert null.property_name == "None"

    assert wall.object_modifiers.surface is AreaModifierSurface.AREA_OBJECT
    assert wall.property_state.property_modifiers.surface is AreaModifierSurface.AREA_PROPERTY
    assert wall.object_modifiers.modifiers.as_tuple() == (1.0,) * 10
    assert wall.property_state.property_modifiers.modifiers.as_tuple() == (0.5,) * 10
    assert population.advanced_local_axis_area_names == ()
    assert population.unresolved_property_area_names == ()


def test_floor_property_with_no_positive_family_is_explicit_unresolved(
    factual_runtime, monkeypatch
):
    monkeypatch.setattr(
        subject,
        "read_slab_property_probe_from_session",
        lambda _session, name: AreaPropertyFamilyProbeFact(
            property_name=name,
            family="SLAB",
            family_type_code=None,
            shell_type_code=None,
            material_name=None,
            thickness=None,
            return_code=1,
        ),
    )

    population = subject.capture_area_contributor_population_from_session(
        factual_runtime,
        model_fingerprint="model-1",
        evidence_epoch_id="epoch-1",
        session_provenance_ref="session-1",
    )

    assert population.unresolved_property_area_names == ("A-F",)


def test_ambiguous_floor_property_family_fails_closed(factual_runtime, monkeypatch):
    monkeypatch.setattr(
        subject,
        "read_deck_property_probe_from_session",
        lambda _session, name: AreaPropertyFamilyProbeFact(
            property_name=name,
            family="DECK",
            family_type_code=2,
            shell_type_code=3,
            material_name="S355",
            thickness=0.0875,
            return_code=0,
        ),
    )

    with pytest.raises(
        subject.EtabsAreaContributorProviderError,
        match="ambiguously positive",
    ):
        subject.capture_area_contributor_population_from_session(
            factual_runtime,
            model_fingerprint="model-1",
            evidence_epoch_id="epoch-1",
            session_provenance_ref="session-1",
        )


def test_advanced_local_axis_is_preserved_not_interpreted(
    factual_runtime, monkeypatch
):
    original = subject.read_area_local_axes_from_session

    def axes(_session, name):
        if name == "A-W":
            return AreaLocalAxesFact(
                area_name=name,
                angle_degrees=22.5,
                advanced=True,
                return_code=0,
            )
        return original(_session, name)

    monkeypatch.setattr(subject, "read_area_local_axes_from_session", axes)

    population = subject.capture_area_contributor_population_from_session(
        factual_runtime,
        model_fingerprint="model-1",
        evidence_epoch_id="epoch-1",
        session_provenance_ref="session-1",
    )

    assert population.advanced_local_axis_area_names == ("A-W",)
    wall = next(row for row in population.rows if row.area_name == "A-W")
    assert wall.local_axes_angle_degrees == 22.5


def test_nonzero_object_modifier_read_blocks_exact_population(
    factual_runtime, monkeypatch
):
    def modifiers(_session, *, surface, target_name):
        return AreaModifierReadFact(
            surface=surface,
            target_name=target_name,
            modifiers=AreaModifierVector.from_sequence([1.0] * 10),
            return_code=7 if surface is AreaModifierSurface.AREA_OBJECT and target_name == "A-W" else 0,
        )

    monkeypatch.setattr(subject, "get_area_modifiers_from_session", modifiers)

    with pytest.raises(
        subject.EtabsAreaContributorProviderError,
        match="AreaObj.GetModifiers failed",
    ):
        subject.capture_area_contributor_population_from_session(
            factual_runtime,
            model_fingerprint="model-1",
            evidence_epoch_id="epoch-1",
            session_provenance_ref="session-1",
        )
