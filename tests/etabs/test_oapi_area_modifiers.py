from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.area_modifiers as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


class _FakeSession:
    def __init__(self) -> None:
        self._gateway_session = object()


class _Container:
    def __init__(self) -> None:
        self.get_result = ([1.0] * 10, 0)
        self.set_result = 0
        self.get_calls = []
        self.set_calls = []

    def GetModifiers(self, name):
        self.get_calls.append(name)
        return self.get_result

    def SetModifiers(self, *args):
        self.set_calls.append(args)
        return self.set_result


@pytest.fixture
def runtime(monkeypatch):
    session = _FakeSession()
    area = _Container()
    prop = _Container()
    model = SimpleNamespace(AreaObj=area, PropArea=prop)

    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)

    def fake_read(_session, function, *, operation, timeout_seconds=30.0):
        assert operation
        assert timeout_seconds > 0
        return function(object(), model)

    def fake_mutation(
        gateway_session,
        function,
        *,
        operation,
        timeout_seconds=30.0,
        _transport_key=None,
    ):
        assert gateway_session is session._gateway_session
        assert operation
        assert timeout_seconds > 0
        assert _transport_key is subject._B4T_MUTATION_TRANSPORT_KEY
        return function(model)

    monkeypatch.setattr(subject, "_execute_verified_read", fake_read)
    monkeypatch.setattr(subject, "_execute_bounded_model_mutation", fake_mutation)
    return session, area, prop


def _vector(value=1.0):
    return subject.AreaModifierVector.from_sequence([value] * 10)


def test_vector_preserves_exact_ten_index_payload():
    vector = subject.AreaModifierVector.from_sequence(
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    )
    assert vector.as_tuple() == tuple(float(i) for i in range(1, 11))
    assert vector.property_slot(
        subject.AreaPropertyModifierSlot.BENDING_M22
    ) == 5.0


@pytest.mark.parametrize("bad", [(), (1.0,) * 9, (1.0,) * 11])
def test_vector_requires_exactly_ten_values(bad):
    with pytest.raises(EtabsOAPIError, match="exactly 10"):
        subject.AreaModifierVector.from_sequence(bad)


@pytest.mark.parametrize(
    "bad",
    [float("nan"), float("inf"), float("-inf"), True, "1.0"],
)
def test_vector_rejects_nonfinite_or_non_numeric_values(bad):
    values = [1.0] * 10
    values[4] = bad
    with pytest.raises(EtabsOAPIError):
        subject.AreaModifierVector.from_sequence(values)


@pytest.mark.parametrize(
    ("surface", "target"),
    [
        (subject.AreaModifierSurface.AREA_OBJECT, "A1"),
        (subject.AreaModifierSurface.AREA_PROPERTY, "Slab_d=15"),
    ],
)
def test_get_modifiers_decodes_live_r1_shape(runtime, surface, target):
    session, area, prop = runtime
    container = area if surface is subject.AreaModifierSurface.AREA_OBJECT else prop
    container.get_result = (
        [1.0, 1.0, 1.0, 0.25, 0.30, 0.35, 1.0, 1.0, 1.0, 1.0],
        0,
    )

    fact = subject.get_area_modifiers_from_session(
        session,
        surface=surface,
        target_name=target,
    )

    assert fact.success is True
    assert fact.modifiers.as_tuple()[3:6] == (0.25, 0.30, 0.35)
    assert fact.evidence_ref.startswith(subject.AREA_MODIFIER_EVIDENCE_PREFIX)


def test_get_preserves_nonzero_return_as_factual_failure(runtime):
    session, area, _ = runtime
    area.get_result = ([1.0] * 10, 7)

    fact = subject.get_area_modifiers_from_session(
        session,
        surface=subject.AreaModifierSurface.AREA_OBJECT,
        target_name="A1",
    )

    assert fact.return_code == 7
    assert fact.success is False


@pytest.mark.parametrize(
    "raw",
    [
        0,
        ([1.0] * 10,),
        ([1.0] * 10, 0, 1),
        ([1.0] * 9, 0),
        ([1.0] * 10, [2.0] * 10, 0),
        ("not-a-vector", 0),
    ],
)
def test_get_rejects_unsupported_or_ambiguous_abi(runtime, raw):
    session, area, _ = runtime
    area.get_result = raw

    with pytest.raises(EtabsOAPIError, match="ABI shape"):
        subject.get_area_modifiers_from_session(
            session,
            surface=subject.AreaModifierSurface.AREA_OBJECT,
            target_name="A1",
        )


def test_area_object_set_uses_explicit_objects_item_type(runtime):
    session, area, _ = runtime
    requested = _vector(0.5)

    fact = subject.set_area_modifiers_from_session(
        session,
        surface=subject.AreaModifierSurface.AREA_OBJECT,
        target_name="A1",
        modifiers=requested,
    )

    assert fact.success is True
    assert area.set_calls == [("A1", requested.as_list(), 0)]


def test_area_property_set_has_no_item_type(runtime):
    session, _, prop = runtime
    requested = _vector(0.5)

    fact = subject.set_area_modifiers_from_session(
        session,
        surface=subject.AreaModifierSurface.AREA_PROPERTY,
        target_name="Slab_d=15",
        modifiers=requested,
    )

    assert fact.success is True
    assert prop.set_calls == [("Slab_d=15", requested.as_list())]


def test_set_preserves_nonzero_return_as_factual_failure(runtime):
    session, _, prop = runtime
    prop.set_result = 9
    requested = _vector(0.5)

    fact = subject.set_area_modifiers_from_session(
        session,
        surface=subject.AreaModifierSurface.AREA_PROPERTY,
        target_name="Slab_d=15",
        modifiers=requested,
    )

    assert fact.return_code == 9
    assert fact.success is False


def test_set_accepts_exact_reflected_byref_vector(runtime):
    session, _, prop = runtime
    requested = _vector(0.5)
    prop.set_result = (requested.as_list(), 0)

    fact = subject.set_area_modifiers_from_session(
        session,
        surface=subject.AreaModifierSurface.AREA_PROPERTY,
        target_name="Slab_d=15",
        modifiers=requested,
    )

    assert fact.success is True


@pytest.mark.parametrize(
    "raw",
    [
        ([9.0] * 10, 0),
        ([1.0] * 9, 0),
        ([0.5] * 10, [0.5] * 10, 0),
        ("unexpected", 0),
        (0, 1),
    ],
)
def test_set_rejects_invalid_reflected_payload(runtime, raw):
    session, _, prop = runtime
    requested = _vector(0.5)
    prop.set_result = raw

    with pytest.raises(EtabsOAPIError):
        subject.set_area_modifiers_from_session(
            session,
            surface=subject.AreaModifierSurface.AREA_PROPERTY,
            target_name="Slab_d=15",
            modifiers=requested,
        )


def test_surface_types_never_collapse(runtime):
    session, area, prop = runtime

    subject.get_area_modifiers_from_session(
        session,
        surface=subject.AreaModifierSurface.AREA_OBJECT,
        target_name="A1",
    )
    subject.get_area_modifiers_from_session(
        session,
        surface=subject.AreaModifierSurface.AREA_PROPERTY,
        target_name="Slab_d=15",
    )

    assert area.get_calls == ["A1"]
    assert prop.get_calls == ["Slab_d=15"]
