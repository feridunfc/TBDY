from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.area_contributors as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


class _FakeSession:
    pass


class _AreaObj:
    def GetDesignOrientation(self, name):
        return [2, 0]

    def GetLocalAxes(self, name):
        return [15.0, False, 0]

    def GetTransformationMatrix(self, name):
        return [(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0), 0]

    def GetMaterialOverwrite(self, name):
        return ["None", 0]

    def GetDiaphragm(self, name):
        return ["D1", 0]

    def GetPier(self, name):
        return ["P1", 0]

    def GetSpandrel(self, name):
        return ["None", 0]


class _Diaphragm:
    def GetDiaphragm(self, name):
        return [True, 0]


class _PropArea:
    def __init__(self):
        self.slab = [0, 2, "C35/45", 0.15, 65280, "", "guid", 0]
        self.deck = [0, 0, None, 0.0, 0, None, None, 1]

    def GetSlab(self, name):
        return self.slab

    def GetDeck(self, name):
        return self.deck


@pytest.fixture
def runtime(monkeypatch):
    session = _FakeSession()
    model = SimpleNamespace(
        AreaObj=_AreaObj(),
        PropArea=_PropArea(),
        Diaphragm=_Diaphragm(),
    )
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)

    def fake_read(_session, function, *, operation, timeout_seconds=30.0):
        assert operation.startswith("oapi_")
        return function(object(), model)

    monkeypatch.setattr(subject, "_execute_verified_read", fake_read)
    return session, model


def test_runtime_r1_shapes_decode_without_engineering_meaning(runtime):
    session, _ = runtime

    orientation = subject.read_area_design_orientation_from_session(session, "25")
    axes = subject.read_area_local_axes_from_session(session, "25")
    matrix = subject.read_area_transformation_matrix_from_session(session, "25")
    overwrite = subject.read_area_material_overwrite_from_session(session, "25")
    diaphragm = subject.read_area_diaphragm_assignment_from_session(session, "25")
    diaphragm_definition = subject.read_diaphragm_definition_from_session(session, "D1")
    wall = subject.read_area_wall_assignments_from_session(session, "25")
    slab = subject.read_slab_property_probe_from_session(session, "Slab_d=15")

    assert orientation.orientation is subject.AreaDesignOrientation.FLOOR
    assert orientation.return_code == 0
    assert axes.angle_degrees == 15.0
    assert axes.advanced is False
    assert matrix.values == (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    assert overwrite.raw_material_name == "None"
    assert diaphragm.assigned is True
    assert diaphragm.diaphragm_name == "D1"
    assert diaphragm_definition.success is True
    assert diaphragm_definition.semi_rigid is True
    assert wall.success is True
    assert wall.pier_assigned is True
    assert wall.spandrel_assigned is False
    assert wall.assignment_conflict is False
    assert slab.success is True
    assert slab.family == "SLAB"
    assert slab.family_type_code == 0
    assert slab.shell_type_code == subject.AreaShellType.SHELL_THICK
    assert slab.material_name == "C35/45"
    assert slab.thickness == 0.15


def test_nonmatching_property_family_probe_preserves_failure(runtime):
    session, _ = runtime
    deck = subject.read_deck_property_probe_from_session(session, "Slab_d=15")

    assert deck.success is False
    assert deck.return_code == 1
    assert deck.family_type_code is None
    assert deck.shell_type_code is None
    assert deck.material_name is None
    assert deck.thickness is None


def test_none_diaphragm_assignment_is_preserved_not_promoted(runtime):
    session, model = runtime
    model.AreaObj.GetDiaphragm = lambda _name: ["None", 0]

    fact = subject.read_area_diaphragm_assignment_from_session(session, "25")

    assert fact.success is True
    assert fact.assigned is False
    assert fact.diaphragm_name == "None"


def test_wall_assignment_conflict_is_explicit(runtime):
    session, model = runtime
    model.AreaObj.GetSpandrel = lambda _name: ["S1", 0]

    fact = subject.read_area_wall_assignments_from_session(session, "25")

    assert fact.success is True
    assert fact.pier_assigned is True
    assert fact.spandrel_assigned is True
    assert fact.assignment_conflict is True


@pytest.mark.parametrize(
    ("method", "raw"),
    [
        ("GetDesignOrientation", [2]),
        ("GetLocalAxes", [0.0, 0, 0]),
        ("GetTransformationMatrix", [(1.0,) * 8, 0]),
        ("GetMaterialOverwrite", [None, 0]),
        ("GetDiaphragm", ["D1"]),
        ("GetPier", ["P1"]),
        ("GetSpandrel", ["None"]),
    ],
)
def test_area_fact_abi_fails_closed(runtime, method, raw):
    session, model = runtime
    setattr(model.AreaObj, method, lambda _name, value=raw: value)

    if method in {"GetPier", "GetSpandrel"}:
        call = subject.read_area_wall_assignments_from_session
    else:
        call = {
            "GetDesignOrientation": subject.read_area_design_orientation_from_session,
            "GetLocalAxes": subject.read_area_local_axes_from_session,
            "GetTransformationMatrix": subject.read_area_transformation_matrix_from_session,
            "GetMaterialOverwrite": subject.read_area_material_overwrite_from_session,
            "GetDiaphragm": subject.read_area_diaphragm_assignment_from_session,
        }[method]

    with pytest.raises(EtabsOAPIError):
        call(session, "25")


def test_diaphragm_definition_abi_and_boolean_fail_closed(runtime):
    session, model = runtime
    model.Diaphragm.GetDiaphragm = lambda _name: [1, 0]
    with pytest.raises(EtabsOAPIError, match="non-boolean"):
        subject.read_diaphragm_definition_from_session(session, "D1")

    model.Diaphragm.GetDiaphragm = lambda _name: [True]
    with pytest.raises(EtabsOAPIError, match="unsupported Python ABI shape"):
        subject.read_diaphragm_definition_from_session(session, "D1")


def test_unknown_orientation_code_is_not_promoted(runtime):
    session, model = runtime
    model.AreaObj.GetDesignOrientation = lambda _name: [99, 0]

    with pytest.raises(EtabsOAPIError, match="unsupported eAreaDesignOrientation"):
        subject.read_area_design_orientation_from_session(session, "25")


def test_successful_layered_probe_keeps_material_nullable(runtime):
    session, model = runtime
    model.PropArea.slab = [0, 6, None, 0.0, 0, "", "layered-guid", 0]

    fact = subject.read_slab_property_probe_from_session(session, "LayeredSlab")

    assert fact.success is True
    assert fact.shell_type_code == subject.AreaShellType.LAYERED
    assert fact.material_name is None
