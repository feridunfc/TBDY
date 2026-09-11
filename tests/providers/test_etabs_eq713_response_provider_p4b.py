from __future__ import annotations

import tbdy_engine.providers.etabs_eq713_response_provider as provider
from tbdy_engine.etabs.oapi.eq713_response_results import (
    AreaStrainShellResponseFact,
    AreaStrainShellResponseRow,
)


class _FakeSession:
    pass


def _fact(area: str, case: str) -> AreaStrainShellResponseFact:
    row = AreaStrainShellResponseRow(
        object_name=area,
        element_name=f"E-{area}",
        point_element_name="P1",
        load_case=case,
        step_type="",
        step_number=0.0,
        e11_top=0.001,
        e22_top=0.002,
        g12_top=0.003,
        emax_top=0.0,
        emin_top=0.0,
        eangle_top=0.0,
        evm_top=0.0,
        e11_bottom=-0.001,
        e22_bottom=-0.002,
        g12_bottom=-0.003,
        emax_bottom=0.0,
        emin_bottom=0.0,
        eangle_bottom=0.0,
        evm_bottom=0.0,
        g13_avg=0.004,
        g23_avg=0.005,
        gmax_avg=0.0,
        gangle_avg=0.0,
    )
    return AreaStrainShellResponseFact(area, case, (row,), 0)


def test_area_response_population_uses_strain_only_and_binds_exact_lineage(monkeypatch) -> None:
    monkeypatch.setattr(provider, "EtabsVerifiedSession", _FakeSession)
    calls = []

    def read(_session, *, area_name, case_name):
        calls.append((area_name, case_name))
        return _fact(area_name, case_name)

    monkeypatch.setattr(provider, "read_area_strain_shell_response_from_session", read)

    population = provider.capture_eq713_response_population_from_session(
        _FakeSession(),
        model_fingerprint="model:1",
        evidence_epoch_id="epoch:1",
        analysis_result_ref="analysis-result:g1",
        execution_proof_ref="b5-proof:g1",
        case_names=("EQX", "EQY"),
        area_names=("A1",),
        case_scope_refs=("qualified-static:X", "qualified-static:Y"),
    )

    assert calls == [("A1", "EQX"), ("A1", "EQY")]
    assert population.model_fingerprint == "model:1"
    assert population.evidence_epoch_id == "epoch:1"
    assert population.analysis_result_ref == "analysis-result:g1"
    assert population.execution_proof_ref == "b5-proof:g1"
    assert population.case_names == ("EQX", "EQY")
    assert population.area_names == ("A1",)
    assert population.frame_results == ()
    assert population.area_results == ()
    assert tuple((fact.area_name, fact.case_name) for fact in population.area_strain_results) == (
        ("A1", "EQX"),
        ("A1", "EQY"),
    )
    assert "qualified-static:X" in population.source_refs
    assert "qualified-static:Y" in population.source_refs
    assert all(fact.evidence_ref in population.source_refs for fact in population.area_strain_results)
    assert population.evidence_ref.startswith("eq713-response-population:sha256:")
