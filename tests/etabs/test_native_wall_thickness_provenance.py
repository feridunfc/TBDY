"""Q1P native wall provenance; every ETABS surface is an offline fixture."""
from dataclasses import replace
from decimal import Decimal
import json
import ntpath
from types import SimpleNamespace

import pytest

from test_oapi_material_properties import runtime as material_runtime
import tbdy_engine.etabs.oapi.object_model as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.providers.etabs_frame_flexural_base_provider import (
    _qualified_quantity, FrameFlexuralBaseFactError,
)


@pytest.fixture
def wall_runtime(material_runtime, monkeypatch):
    session, material = material_runtime
    model = material.model
    application = SimpleNamespace(GetOAPIVersionNumber=lambda: 2.014)
    forbidden = []

    class ForbiddenSurface:
        def __getattr__(self, name):
            forbidden.append(name)
            raise AssertionError(f"Forbidden ETABS access: {name}")

    class WallSurface(ForbiddenSurface):
        raw = (1, 2, "C35/45", .4, 0, "", "fixture-guid", 0)

        def __init__(self):
            self.calls = []
            self.after_getter = lambda: None

        def GetWall(self, property_name):
            self.calls.append(property_name)
            model.events.append("GetWall")
            self.after_getter()
            return self.raw

    wall = WallSurface()
    model.PropArea = wall
    model.DatabaseTables = ForbiddenSurface()
    model.Analyze = ForbiddenSurface()
    model.DesignConcrete = ForbiddenSurface()
    model.File = ForbiddenSurface()
    def forbidden_setter(*args, **kwargs):
        forbidden.append("SetPresentUnits")
        raise AssertionError("No setters")
    model.SetPresentUnits = forbidden_setter
    model.directory = r"C:\synthetic\owned_scratch"
    model.filename = "current-scratch.EDB"
    # Cached source path and units deliberately differ from the active scratch.
    session.identity = replace(session.identity, units=replace(
        session.identity.units, present_units=6, present_force_unit=4))
    monkeypatch.setattr(subject, "EtabsVerifiedSession", type(session))
    dispatches = []
    def read(_session, function, *, operation, timeout_seconds=30.0):
        assert _session is session and operation == "oapi_prop_area_get_wall"
        dispatches.append(operation)
        return function(application, model)
    monkeypatch.setattr(subject, "_execute_verified_read", read)
    return SimpleNamespace(session=session, model=model, application=application,
                           wall=wall, forbidden=forbidden, dispatches=dispatches)


def acquire(runtime):
    return subject.read_wall_property_from_session(runtime.session, "Wall40")


def test_exact_missing_binding_failure_with_raw_thickness_present(wall_runtime):
    fact = replace(acquire(wall_runtime), unit_provenance=())
    assert fact.thickness == .4 and fact.raw_response[3] == .4
    with pytest.raises(EtabsOAPIError, match="^UNIT_UNQUALIFIED:MISSING_OR_DUPLICATE_OUTPUT_BINDING$"):
        fact.source_unit_for("Thickness", "L")


@pytest.mark.parametrize("present,triplet", [(10, (3, 6, 2, 0)), (6, (4, 6, 2, 0))])
def test_real_seam_qualifies_fresh_scratch_and_present_without_raw_changes(wall_runtime, present, triplet):
    r = wall_runtime
    r.model.present, r.model.triplet = present, triplet
    r.model.events.clear()
    fact = acquire(r)
    p = fact.source_unit_for("Thickness", "L")
    assert r.wall.calls == ["Wall40"] and len(r.dispatches) == 1
    index = r.model.events.index("GetWall")
    for side in [r.model.events[:index], r.model.events[index + 1:]]:
        assert side.count("GetModelFilename") == 1
        assert side.count("GetPresentUnits_2") == 1
    assert fact.raw_response == r.wall.raw and fact.thickness == r.wall.raw[3]
    assert len(fact.unit_provenance) == 1 and p.output_key == "Thickness"
    assert p.source_unit == "m" and p.dimension == "L"
    assert fact.source_model_ref == ntpath.normcase(ntpath.join(r.model.directory, r.model.filename))
    assert fact.source_model_ref != r.session.identity.model_full_path
    assert p.source_model_ref == fact.source_model_ref
    assert p.session_ref == fact.session_ref == "etabs-session:pid:16664"
    assert p.capture_ref == fact.capture_ref and p.raw_response_ref == fact.raw_response_ref
    assert p.authority_ref == subject._WALL_THICKNESS_AUTHORITY_REF
    assert p.authority_version == subject._WALL_THICKNESS_AUTHORITY_VERSION
    assert "Q1N" not in p.authority_ref and "PROJECT_REVIEWED" in p.authority_version
    states = [json.loads(p.unit_state_before), json.loads(p.unit_state_after)]
    assert all(s["active_identity"]["units"]["present_units"] == present for s in states)
    assert all(s["active_identity"]["units"]["database_force_unit"] == 4 for s in states)
    assert states[0] == states[1] and p.qualification == "QUALIFIED"
    assert _qualified_quantity(fact.thickness, p, "L") == Decimal("400")
    assert not r.forbidden


@pytest.mark.parametrize("after", [False, True])
@pytest.mark.parametrize("failure", ["missing", "exception", "units", "path"])
def test_missing_observation_fails_closed_at_exact_side(wall_runtime, monkeypatch, after, failure):
    r = wall_runtime
    original = subject.read_session_identity
    def observe(*args, **kwargs):
        if bool(r.wall.calls) == after:
            if failure == "exception":
                raise RuntimeError("fixture observation unavailable")
            if failure == "missing":
                return None
            result = original(*args, **kwargs)
            return replace(result, **({"units": None} if failure == "units" else {"model_full_path": ""}))
        return original(*args, **kwargs)
    monkeypatch.setattr(subject, "read_session_identity", observe)
    with pytest.raises(EtabsOAPIError, match="UNIT_UNQUALIFIED"):
        acquire(r)
    assert len(r.wall.calls) == int(after)
    assert len(r.dispatches) == 1 and not r.forbidden


@pytest.mark.parametrize("change", ["units", "model", "session", "gateway", "version", "api"])
def test_drift_fails_closed_after_single_call(wall_runtime, change):
    r = wall_runtime
    def drift():
        if change == "units":
            r.model.present, r.model.triplet = 6, (4, 6, 2, 0)
        elif change == "model":
            r.model.filename = "foreign.EDB"
        elif change == "session":
            r.session.identity = replace(r.session.identity, process_id=99)
        elif change == "gateway":
            r.session._gateway_session = object()
        elif change == "version":
            r.model.GetVersion = lambda: ("24.0.0", 0., 0)
        else:
            r.application.GetOAPIVersionNumber = lambda: 3.0
    r.wall.after_getter = drift
    with pytest.raises(EtabsOAPIError, match="UNIT_UNQUALIFIED"):
        acquire(r)
    assert r.wall.calls == ["Wall40"] and not r.forbidden


@pytest.mark.parametrize("change", ["version", "api", "pid", "gateway", "relative_path"])
def test_invalid_anchor_or_compatibility_blocks_before_call(wall_runtime, change):
    r = wall_runtime
    if change == "version":
        r.model.GetVersion = lambda: ("24.0.0", 0., 0)
    elif change == "api":
        r.application.GetOAPIVersionNumber = lambda: 3.0
    elif change == "pid":
        r.session.identity = replace(r.session.identity, process_id=None)
    elif change == "gateway":
        r.session._gateway_session = None
    else:
        r.model.directory = "relative"
    with pytest.raises(EtabsOAPIError, match="UNIT_UNQUALIFIED"):
        acquire(r)
    assert not r.wall.calls and not r.forbidden


@pytest.mark.parametrize("present,triplet", [(9, (4, 4, 2, 0)), (7, (4, 5, 2, 0)),
                                            (10, (3, 4, 2, 0)), (10, (3, 6, 2, 1))])
def test_unverified_present_units_do_not_borrow_database_or_converter_support(wall_runtime, present, triplet):
    r = wall_runtime
    r.model.present, r.model.triplet = present, triplet
    with pytest.raises(EtabsOAPIError, match="UNIT_UNQUALIFIED"):
        acquire(r)
    assert not r.wall.calls and not r.forbidden


def test_unknown_length_decoder_fails_closed_even_with_fixture_observation_status(wall_runtime, monkeypatch):
    original = subject.read_session_identity
    def observe(*args, **kwargs):
        identity = original(*args, **kwargs)
        return replace(identity, units=replace(identity.units, present_length_unit=99))
    monkeypatch.setattr(subject, "read_session_identity", observe)
    with pytest.raises(EtabsOAPIError, match="UNSUPPORTED_PRESENT_LENGTH_UNIT"):
        acquire(wall_runtime)
    assert not wall_runtime.wall.calls


@pytest.mark.parametrize("raw", [
    (1, 2, "C35/45", .4, 0, "", "guid", 4),
    (1, 2, "C35/45", .4, 0, "", "guid"),
    (1, 6, "C35/45", .4, 0, "", "guid", 0),
    (1, 2, "C35/45", None, 0, "", "guid", 0),
    (1, 2, "C35/45", True, 0, "", "guid", 0),
    (1, 2, "C35/45", float("nan"), 0, "", "guid", 0),
    (1, 2, "C35/45", float("inf"), 0, "", "guid", 0),
    (1, 2, "C35/45", 0., 0, "", "guid", 0),
    (1, 2, "C35/45", -.4, 0, "", "guid", 0),
    (1, 2, "C35/45", .4, 0, "", "guid", None),
    (1, 2, "C35/45"), 0,
])
def test_native_or_thickness_failure_observes_after_without_retry(wall_runtime, raw):
    r = wall_runtime
    r.wall.raw = raw
    r.model.events.clear()
    with pytest.raises(EtabsOAPIError):
        acquire(r)
    assert r.wall.calls == ["Wall40"]
    assert r.model.events.count("GetPresentUnits_2") == 2
    assert not r.forbidden


def test_native_exception_remains_primary_when_after_observation_also_fails(wall_runtime):
    r = wall_runtime
    r.wall.raw = 0
    r.wall.after_getter = lambda: setattr(r.model, "triplet", None)
    with pytest.raises(EtabsOAPIError, match="failed/raw=0") as error:
        acquire(r)
    assert error.value.__notes__ and "After GetWall observation failed" in error.value.__notes__[0]
    assert r.wall.calls == ["Wall40"]


@pytest.mark.parametrize("field,value", [
    ("source_call", "SapModel.PropArea.GetSlab"), ("subject_key", "OtherWall"),
    ("output_key", "OtherOutput"), ("dimension", "L4"),
    ("source_model_ref", "foreign-model"), ("session_ref", "foreign-session"),
    ("capture_ref", "foreign-capture"), ("raw_response_ref", "foreign-raw"),
    ("return_code", 1), ("authority_ref", None),
    ("authority_kind", "REPORT_DEFAULT"), ("unit_state_after", "foreign-state"),
])
def test_foreign_or_invalid_provenance_is_rejected(wall_runtime, field, value):
    fact = acquire(wall_runtime)
    altered = replace(fact, unit_provenance=(replace(fact.unit_provenance[0], **{field: value}),))
    with pytest.raises(EtabsOAPIError, match="UNIT_UNQUALIFIED"):
        altered.source_unit_for("Thickness", "L")


@pytest.mark.parametrize("duplicate", [False, True])
def test_missing_or_duplicate_binding_is_rejected(wall_runtime, duplicate):
    fact = acquire(wall_runtime)
    altered = replace(fact, unit_provenance=fact.unit_provenance * 2 if duplicate else ())
    with pytest.raises(EtabsOAPIError, match="MISSING_OR_DUPLICATE_OUTPUT_BINDING"):
        altered.source_unit_for("Thickness", "L")


def test_inapplicable_flag_is_not_broadened(wall_runtime):
    fact = replace(acquire(wall_runtime), thickness_applicable=False)
    with pytest.raises(EtabsOAPIError, match="WALL_THICKNESS_UNAVAILABLE_OR_INAPPLICABLE"):
        fact.source_unit_for("Thickness", "L")


def test_unknown_unit_token_is_rejected_by_existing_converter(wall_runtime):
    fact = acquire(wall_runtime)
    binding = replace(fact.unit_provenance[0], source_unit="unknown")
    with pytest.raises(FrameFlexuralBaseFactError, match="UNKNOWN_OR_WRONG_DIMENSION_UNIT"):
        _qualified_quantity(fact.thickness, binding, "L")


def test_preserved_anomalous_raw_value_is_never_corrected(wall_runtime):
    r = wall_runtime
    r.wall.raw = (*r.wall.raw[:3], .0004, *r.wall.raw[4:])
    fact = acquire(r)
    assert fact.thickness == .0004 and fact.raw_response == r.wall.raw
    assert _qualified_quantity(fact.thickness, fact.source_unit_for("Thickness", "L"), "L") == Decimal(".4")
    stripped = replace(fact, unit_provenance=())
    assert stripped.raw_response_ref == fact.raw_response_ref
    assert stripped.evidence_ref != fact.evidence_ref


def test_no_extra_unit_or_lifecycle_framework_added():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(subject.read_wall_property_from_session))
    forbidden = {"SetPresentUnits", "RunAnalysis", "StartDesign", "Save", "OpenFile",
                 "SaveAs", "GetAllFieldsInTable", "GetTableForDisplayArray",
                 "attach_verified_to_running_etabs"}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attributes & forbidden
    assert not any(name.startswith("Set") for name in attributes)
