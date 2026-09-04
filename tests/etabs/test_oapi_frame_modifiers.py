from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.frame_modifiers as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


class _FakeSession:
    def __init__(self) -> None:
        self._gateway_session = object()


class _Container:
    def __init__(self) -> None:
        self.get_result = ([1.0] * 8, 0)
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
    frame = _Container()
    prop = _Container()
    model = SimpleNamespace(FrameObj=frame, PropFrame=prop)

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
    return session, frame, prop


def _vector(*, i22=1.0, i33=1.0):
    return subject.FrameModifierVector(
        area=1.0,
        shear_area_local_2=1.0,
        shear_area_local_3=1.0,
        torsional_constant=1.0,
        inertia_local_2=i22,
        inertia_local_3=i33,
        mass=1.0,
        weight=1.0,
    )


def test_vector_preserves_exact_documented_frame_order():
    vector = _vector(i22=0.35, i33=0.40)
    assert vector.as_tuple() == (1.0, 1.0, 1.0, 1.0, 0.35, 0.40, 1.0, 1.0)


@pytest.mark.parametrize("bad", [(), (1.0,) * 7, (1.0,) * 9])
def test_vector_requires_exactly_eight_values(bad):
    with pytest.raises(EtabsOAPIError, match="exactly 8"):
        subject.FrameModifierVector.from_sequence(bad)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "1.0"])
def test_vector_rejects_nonfinite_or_non_numeric_values(bad):
    values = [1.0] * 8
    values[4] = bad
    with pytest.raises(EtabsOAPIError):
        subject.FrameModifierVector.from_sequence(values)


@pytest.mark.parametrize(
    ("surface", "attribute"),
    [
        (subject.FrameModifierSurface.FRAME_OBJECT, "FrameObj"),
        (subject.FrameModifierSurface.FRAME_SECTION_PROPERTY, "PropFrame"),
    ],
)
def test_get_modifiers_decodes_one_vector_plus_return_code(runtime, surface, attribute):
    session, frame, prop = runtime
    container = frame if attribute == "FrameObj" else prop
    container.get_result = ([1.0, 1.0, 1.0, 1.0, 0.25, 0.30, 1.0, 1.0], 0)

    fact = subject.get_frame_modifiers_from_session(
        session,
        surface=surface,
        target_name="F1" if surface is subject.FrameModifierSurface.FRAME_OBJECT else "C40x40",
    )

    assert fact.success is True
    assert fact.modifiers.inertia_local_2 == 0.25
    assert fact.modifiers.inertia_local_3 == 0.30
    assert fact.evidence_ref.startswith(subject.FRAME_MODIFIER_EVIDENCE_PREFIX)


def test_get_modifiers_preserves_nonzero_as_factual_failure(runtime):
    session, frame, _ = runtime
    frame.get_result = ([1.0] * 8, 7)

    fact = subject.get_frame_modifiers_from_session(
        session,
        surface=subject.FrameModifierSurface.FRAME_OBJECT,
        target_name="F1",
    )

    assert fact.return_code == 7
    assert fact.success is False


@pytest.mark.parametrize(
    "raw",
    [
        0,
        ([1.0] * 8,),
        ([1.0] * 8, 0, 1),
        ([1.0] * 7, 0),
        ("not-a-vector", 0),
    ],
)
def test_get_modifiers_rejects_unknown_python_abi_shapes(runtime, raw):
    session, frame, _ = runtime
    frame.get_result = raw
    with pytest.raises(EtabsOAPIError, match="ABI shape"):
        subject.get_frame_modifiers_from_session(
            session,
            surface=subject.FrameModifierSurface.FRAME_OBJECT,
            target_name="F1",
        )


def test_frame_object_set_is_exact_object_target_only(runtime):
    session, frame, _ = runtime
    requested = _vector(i22=0.25, i33=0.30)

    fact = subject.set_frame_modifiers_from_session(
        session,
        surface=subject.FrameModifierSurface.FRAME_OBJECT,
        target_name="F1",
        modifiers=requested,
    )

    assert fact.success is True
    assert frame.set_calls == [("F1", requested.as_list(), 0)]


def test_prop_frame_set_has_no_group_or_selection_target(runtime):
    session, _, prop = runtime
    requested = _vector(i22=0.25, i33=0.30)

    fact = subject.set_frame_modifiers_from_session(
        session,
        surface=subject.FrameModifierSurface.FRAME_SECTION_PROPERTY,
        target_name="C40x40",
        modifiers=requested,
    )

    assert fact.success is True
    assert prop.set_calls == [("C40x40", requested.as_list())]


def test_set_decoder_accepts_reflected_byref_vector_only_when_exact(runtime):
    session, _, prop = runtime
    requested = _vector(i22=0.25, i33=0.30)
    prop.set_result = (requested.as_list(), 0)

    fact = subject.set_frame_modifiers_from_session(
        session,
        surface=subject.FrameModifierSurface.FRAME_SECTION_PROPERTY,
        target_name="C40x40",
        modifiers=requested,
    )

    assert fact.return_code == 0


def test_set_decoder_rejects_unknown_reflected_payload(runtime):
    session, _, prop = runtime
    requested = _vector(i22=0.25, i33=0.30)
    prop.set_result = ([9.0] * 8, 0)

    with pytest.raises(EtabsOAPIError, match="reflected ByRef"):
        subject.set_frame_modifiers_from_session(
            session,
            surface=subject.FrameModifierSurface.FRAME_SECTION_PROPERTY,
            target_name="C40x40",
            modifiers=requested,
        )


def test_surface_types_are_never_collapsed(runtime):
    session, frame, prop = runtime
    subject.get_frame_modifiers_from_session(
        session,
        surface=subject.FrameModifierSurface.FRAME_OBJECT,
        target_name="F1",
    )
    subject.get_frame_modifiers_from_session(
        session,
        surface=subject.FrameModifierSurface.FRAME_SECTION_PROPERTY,
        target_name="C40x40",
    )
    assert frame.get_calls == ["F1"]
    assert prop.get_calls == ["C40x40"]
