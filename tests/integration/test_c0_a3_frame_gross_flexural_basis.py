from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tbdy_engine.analysis_basis.frame_gross_flexural_basis import (
    FrameFlexuralAxis,
    FrameGrossFlexuralBasisError,
    _build_from_fact,
    derive_rectangular_gross_inertia,
)
from tbdy_engine.etabs.oapi.frame_modifiers import FrameModifierSurface, FrameModifierVector
from tbdy_engine.integration.etabs_analysis_execution import AnalysisExecutionResult
from tbdy_engine.integration.etabs_analysis_state_mutation import AnalysisStateMutationResult
from tbdy_engine.integration.etabs_scratch_lifecycle import OwnedScratchContext
from tbdy_engine.integration.live_etabs_acquisition_context import TrustedLiveAcquisitionContext
from tbdy_engine.providers import etabs_frame_flexural_base_provider as provider
from tbdy_engine.providers.etabs_frame_flexural_base_provider import FrameFlexuralBaseFact, FrameFlexuralBaseFactError
from tbdy_engine.regulatory.ts500_concrete_elastic_modulus import (
    Ts500EcComparisonStatus,
    compare_etabs_ec_to_ts500_table_3_2,
)


def _base_fact(*, section: str = "R30X50", material: str = "C25", ec: str = "30000", fck: str = "25") -> FrameFlexuralBaseFact:
    rows = tuple((f"T{i}", {"i": i}) for i in range(5))
    refs = tuple(f"row:{i}" for i in range(5))
    return FrameFlexuralBaseFact(
        component_unique_name="F1",
        assigned_section_name=section,
        material_name=material,
        t2_mm=Decimal("300"),
        t3_mm=Decimal("500"),
        concrete_fck_mpa=Decimal(fck),
        etabs_ec_mpa=Decimal(ec),
        source_model_ref="source:1",
        ownership_proof_ref="scratch:1",
        acquisition_context_ref="acq:1",
        session_provenance_ref="session:1",
        present_force_unit=3,
        present_length_unit=4,
        source_rows=rows,
        source_refs=refs,
    )


def _modifier(surface: FrameModifierSurface, target: str, *, i2: float = 1.0, i3: float = 1.0):
    vector = FrameModifierVector(1.0, 1.0, 1.0, 1.0, i2, i3, 1.0, 1.0)
    after = SimpleNamespace(success=True, modifiers=vector, evidence_ref=f"after:{surface.value}:{target}")
    return SimpleNamespace(
        surface=surface,
        target_name=target,
        setter=SimpleNamespace(success=True),
        after=after,
    )


def _lineage(*, section: str = "R30X50", object_i2: float = 1.0, object_i3: float = 1.0,
             property_i2: float = 1.0, property_i3: float = 1.0,
             include_object: bool = True, include_property: bool = True,
             qualified: bool = True, wrong_state: bool = False):
    state = SimpleNamespace(identity_ref="analysis-state:sha256:" + "a" * 64, source_model_ref="source:1")
    mutations = []
    if include_property:
        mutations.append(_modifier(FrameModifierSurface.FRAME_SECTION_PROPERTY, section, i2=property_i2, i3=property_i3))
    if include_object:
        mutations.append(_modifier(FrameModifierSurface.FRAME_OBJECT, "F1", i2=object_i2, i3=object_i3))
    b4b = Mock(spec=AnalysisStateMutationResult)
    b4b.analysis_state_identity = state
    b4b.mutation_manifest = SimpleNamespace(
        ownership_proof_ref="scratch:1",
        manifest_ref="mutation:1",
        mutations=tuple(mutations),
    )
    result = SimpleNamespace(
        identity_ref="analysis-result:sha256:" + "b" * 64,
        source_model_ref="source:1",
        parent_analysis_state_ref=state.identity_ref,
    )
    qstate = SimpleNamespace(identity_ref="analysis-state:sha256:" + "c" * 64, source_model_ref="source:1") if wrong_state else state
    qualification = SimpleNamespace(
        qualified=qualified,
        analysis_state=qstate,
        analysis_result=result,
        qualification_ref="qualification:1",
    )
    revalidation = SimpleNamespace(
        matched_exact=True,
        current_analysis_state=state,
        comparison=SimpleNamespace(comparison_ref="state-comparison:1"),
    )
    manifest = SimpleNamespace(
        state_revalidation=revalidation,
        ownership_proof_ref="scratch:1",
        source_model_ref="source:1",
        manifest_ref="execution-manifest:1",
    )
    b5 = Mock(spec=AnalysisExecutionResult)
    b5.analysis_result_identity = result
    b5.qualification = qualification
    b5.manifest = manifest
    owned = Mock(spec=OwnedScratchContext)
    owned.ownership_proof_ref = "scratch:1"
    owned.source_model_identity = SimpleNamespace(source_model_ref="source:1")
    return owned, b4b, b5


def _build(base: FrameFlexuralBaseFact, **kwargs):
    owned, b4b, b5 = _lineage(section=base.assigned_section_name, **kwargs)
    return _build_from_fact(
        owned_scratch=owned,
        base_fact=base,
        axis=FrameFlexuralAxis.LOCAL_2_M2,
        established_state=b4b,
        execution_result=b5,
    )


def test_matching_ec_gross_rectangle_and_both_unit_surfaces_is_positive():
    evidence = _build(_base_fact())
    assert evidence.ts500_ec_comparison.status is Ts500EcComparisonStatus.MATCH
    assert evidence.gross_i_axis_mm4 == Decimal("3125000000")
    assert evidence.property_axis_modifier == 1.0
    assert evidence.object_axis_modifier == 1.0


def test_gross_rectangular_local_axis_mapping_is_exact():
    gross = derive_rectangular_gross_inertia(_base_fact())
    assert gross.i22_mm4 == Decimal("3125000000")
    assert gross.i33_mm4 == Decimal("1125000000")


def test_ec_mismatch_fails_closed():
    with pytest.raises(FrameGrossFlexuralBasisError, match="Ec"):
        _build(_base_fact(ec="29999"))


def test_property_modifier_nonunit_fails_closed():
    with pytest.raises(FrameGrossFlexuralBasisError, match="section-property"):
        _build(_base_fact(), property_i2=0.5)


def test_object_modifier_nonunit_fails_closed():
    with pytest.raises(FrameGrossFlexuralBasisError, match="frame-object"):
        _build(_base_fact(), object_i2=0.5)


@pytest.mark.parametrize("kwargs", [{"include_property": False}, {"include_object": False}])
def test_missing_either_modifier_surface_fails_closed(kwargs):
    with pytest.raises(FrameGrossFlexuralBasisError, match="modifier census"):
        _build(_base_fact(), **kwargs)


def test_wrong_section_assignment_fails_closed_against_property_surface():
    base = _base_fact(section="R30X50")
    owned, b4b, b5 = _lineage(section="OTHER")
    with pytest.raises(FrameGrossFlexuralBasisError, match="modifier census"):
        _build_from_fact(
            owned_scratch=owned,
            base_fact=base,
            axis=FrameFlexuralAxis.LOCAL_2_M2,
            established_state=b4b,
            execution_result=b5,
        )


def test_wrong_analysis_state_identity_fails_closed():
    with pytest.raises(FrameGrossFlexuralBasisError, match="not qualified"):
        _build(_base_fact(), wrong_state=True)


def test_unqualified_analysis_result_fails_closed():
    with pytest.raises(FrameGrossFlexuralBasisError, match="not qualified"):
        _build(_base_fact(), qualified=False)


def test_ts500_unknown_concrete_class_is_unresolved_not_interpolated():
    comparison = compare_etabs_ec_to_ts500_table_3_2(
        concrete_fck_mpa=Decimal("32"), factual_etabs_ec_mpa=Decimal("32000")
    )
    assert comparison.status is Ts500EcComparisonStatus.UNRESOLVED
    assert comparison.required_ts500_ec_mpa is None


def _provider_context(monkeypatch, tables):
    context = Mock(spec=TrustedLiveAcquisitionContext)
    owned = Mock(spec=OwnedScratchContext)
    source = SimpleNamespace(source_model_ref="source:1")
    context.source_model_identity = source
    context.acquisition_context_ref = "acq:1"
    context.session_provenance_ref = "session:1"
    context.verified_session = object()
    owned.source_model_identity = source
    owned.ownership_proof_ref = "scratch:1"
    owned.scratch_path = r"C:\scratch.edb"
    identity = SimpleNamespace(model_full_path=r"C:\scratch.edb")
    units = SimpleNamespace(present_force_unit=3, present_length_unit=4)
    monkeypatch.setattr(provider, "reread_verified_session_identity", lambda session: identity)
    monkeypatch.setattr(provider, "read_verified_unit_snapshot", lambda session: units)
    monkeypatch.setattr(provider, "_rows", lambda ctx, table: tuple(tables[table]))
    return context, owned


def _valid_tables():
    return {
        provider.TABLE_FRAME_ASSIGNMENTS: [{"UniqueName": "F1", "SectProp": "R30X50"}],
        provider.TABLE_RECTANGULAR: [{"Name": "R30X50", "t2": 300, "t3": 500, "Material": "C25"}],
        provider.TABLE_FRAME_SECTION_SUMMARY: [{"Name": "R30X50", "Material": "C25", "Shape": "Concrete Rectangular"}],
        provider.TABLE_BASIC_MATERIAL: [{"Material": "C25", "E1": 30000}],
        provider.TABLE_CONCRETE: [{"Material": "C25", "Fc": 25}],
    }


def test_live_factual_path_binds_assignment_material_ec_and_units(monkeypatch):
    context, owned = _provider_context(monkeypatch, _valid_tables())
    fact = provider.capture_frame_flexural_base_fact(
        context=context, owned_scratch=owned, component_unique_name="F1"
    )
    assert fact.assigned_section_name == "R30X50"
    assert fact.material_name == "C25"
    assert fact.etabs_ec_mpa == Decimal("30000")
    assert fact.concrete_fck_mpa == Decimal("25")


def test_wrong_material_binding_fails_closed(monkeypatch):
    tables = _valid_tables()
    tables[provider.TABLE_RECTANGULAR][0]["Material"] = "C30"
    context, owned = _provider_context(monkeypatch, tables)
    with pytest.raises(FrameFlexuralBaseFactError, match="material disagrees"):
        provider.capture_frame_flexural_base_fact(context=context, owned_scratch=owned, component_unique_name="F1")


def test_missing_e1_fails_closed(monkeypatch):
    tables = _valid_tables()
    del tables[provider.TABLE_BASIC_MATERIAL][0]["E1"]
    context, owned = _provider_context(monkeypatch, tables)
    with pytest.raises(FrameFlexuralBaseFactError, match="E1"):
        provider.capture_frame_flexural_base_fact(context=context, owned_scratch=owned, component_unique_name="F1")


def test_wrong_section_assignment_fails_closed_at_rectangle_join(monkeypatch):
    tables = _valid_tables()
    tables[provider.TABLE_FRAME_ASSIGNMENTS][0]["SectProp"] = "MISSING"
    context, owned = _provider_context(monkeypatch, tables)
    with pytest.raises(FrameFlexuralBaseFactError, match="rectangular section"):
        provider.capture_frame_flexural_base_fact(context=context, owned_scratch=owned, component_unique_name="F1")


def test_unsupported_nonprismatic_section_fails_closed(monkeypatch):
    tables = _valid_tables()
    tables[provider.TABLE_FRAME_SECTION_SUMMARY][0]["Shape"] = "Nonprismatic"
    context, owned = _provider_context(monkeypatch, tables)
    with pytest.raises(FrameFlexuralBaseFactError, match="not the supported"):
        provider.capture_frame_flexural_base_fact(context=context, owned_scratch=owned, component_unique_name="F1")
