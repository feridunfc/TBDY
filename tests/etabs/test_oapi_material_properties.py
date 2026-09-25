from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.material_properties as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


class _FakeSession:
    pass


class _PropMaterial:
    def __init__(self) -> None:
        self.calls = []
        self.raw = (30_000_000.0, 0.20, 1.0e-5, 12_500_000.0, 0)
        self.type_calls = []
        self.type_raw = (1, 0, 0)

    def GetMPIsotropic(self, name, temperature=0.0):
        self.calls.append((name, temperature))
        return self.raw

    def GetTypeOAPI(self, name):
        self.type_calls.append(name)
        return self.type_raw


@pytest.fixture
def runtime(monkeypatch):
    session = _FakeSession()
    prop_material = _PropMaterial()
    model = SimpleNamespace(PropMaterial=prop_material)

    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)

    def fake_read(_session, function, *, operation, timeout_seconds=30.0):
        assert _session is session
        assert operation in {
            "oapi_prop_material_get_mp_isotropic",
            "oapi_prop_material_get_type_oapi",
        }
        assert timeout_seconds > 0.0
        return function(object(), model)

    monkeypatch.setattr(subject, "_execute_verified_read", fake_read)
    return session, prop_material


def test_get_mp_isotropic_preserves_documented_named_outputs(runtime):
    session, prop_material = runtime

    fact = subject.get_isotropic_material_properties_from_session(
        session,
        material_name="C30",
        temperature=20.0,
    )

    assert prop_material.calls == [("C30", 20.0)]
    assert fact.success is True
    assert fact.material_name == "C30"
    assert fact.modulus_of_elasticity == 30_000_000.0
    assert fact.poisson_ratio == 0.20
    assert fact.thermal_coefficient == 1.0e-5
    assert fact.shear_modulus == 12_500_000.0
    assert fact.temperature == 20.0
    assert fact.evidence_ref.startswith(subject.ISOTROPIC_MATERIAL_EVIDENCE_PREFIX)


def test_get_mp_isotropic_preserves_nonzero_return_as_factual_failure(runtime):
    session, prop_material = runtime
    prop_material.raw = (30_000_000.0, 0.20, 1.0e-5, 12_500_000.0, 4)

    fact = subject.get_isotropic_material_properties_from_session(
        session,
        material_name="C30",
    )

    assert fact.return_code == 4
    assert fact.success is False


@pytest.mark.parametrize(
    "raw",
    [
        0,
        (30_000_000.0, 0.20, 1.0e-5, 12_500_000.0),
        (30_000_000.0, 0.20, 1.0e-5, 12_500_000.0, 0, 1),
        (30_000_000.0, 0.20, 1.0e-5, 0),
    ],
)
def test_get_mp_isotropic_rejects_unknown_python_abi_shapes(runtime, raw):
    session, prop_material = runtime
    prop_material.raw = raw

    with pytest.raises(EtabsOAPIError, match="ABI shape"):
        subject.get_isotropic_material_properties_from_session(
            session,
            material_name="C30",
        )


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("bad", [True, "1.0", float("nan"), float("inf")])
def test_get_mp_isotropic_rejects_nonfinite_or_non_numeric_outputs(
    runtime,
    index,
    bad,
):
    session, prop_material = runtime
    values = [30_000_000.0, 0.20, 1.0e-5, 12_500_000.0]
    values[index] = bad
    prop_material.raw = (*values, 0)

    with pytest.raises(EtabsOAPIError, match="finite numeric"):
        subject.get_isotropic_material_properties_from_session(
            session,
            material_name="C30",
        )


@pytest.mark.parametrize("bad", [True, "20", float("nan"), float("inf")])
def test_get_mp_isotropic_rejects_invalid_temperature(runtime, bad):
    session, _prop_material = runtime

    with pytest.raises(EtabsOAPIError, match="temperature"):
        subject.get_isotropic_material_properties_from_session(
            session,
            material_name="C30",
            temperature=bad,
        )


def test_get_mp_isotropic_requires_verified_session_type(monkeypatch):
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)

    with pytest.raises(TypeError, match="EtabsVerifiedSession"):
        subject.get_isotropic_material_properties_from_session(
            object(),
            material_name="C30",
        )


def test_get_mp_isotropic_rejects_noncanonical_name(runtime):
    session, _prop_material = runtime

    with pytest.raises(EtabsOAPIError, match="canonical"):
        subject.get_isotropic_material_properties_from_session(
            session,
            material_name=" C30 ",
        )



def test_get_type_oapi_source_proven_steel(runtime):
    session, prop_material = runtime
    prop_material.type_raw = (1, 0, 0)

    fact = subject.get_material_type_from_session(
        session,
        material_name="S355",
    )

    assert prop_material.type_calls == ["S355"]
    assert fact.success is True
    assert fact.material_name == "S355"
    assert fact.material_type_code == 1
    assert fact.symmetry_type_code == 0
    assert fact.is_steel is True
    assert fact.is_concrete is False
    assert fact.evidence_ref.startswith(
        subject.MATERIAL_TYPE_EVIDENCE_PREFIX
    )


def test_get_type_oapi_concrete_is_not_steel(runtime):
    session, prop_material = runtime
    prop_material.type_raw = (2, 0, 0)

    fact = subject.get_material_type_from_session(
        session,
        material_name="C35/45",
    )

    assert fact.success is True
    assert fact.is_concrete is True
    assert fact.is_steel is False


def test_get_type_oapi_nonzero_return_is_not_positive_type(runtime):
    session, prop_material = runtime
    prop_material.type_raw = (1, 0, 7)

    fact = subject.get_material_type_from_session(
        session,
        material_name="S355",
    )

    assert fact.success is False
    assert fact.is_steel is False


@pytest.mark.parametrize(
    "raw",
    (
        None,
        (),
        (1, 0),
        (1, 0, 0, 0),
        ("1", 0, 0),
        (1, "0", 0),
        (1, 0, "0"),
        (True, 0, 0),
    ),
)
def test_get_type_oapi_rejects_unknown_python_abi_shapes(
    runtime,
    raw,
):
    session, prop_material = runtime
    prop_material.type_raw = raw

    with pytest.raises(
        EtabsOAPIError,
        match="ABI shape",
    ):
        subject.get_material_type_from_session(
            session,
            material_name="S355",
        )
