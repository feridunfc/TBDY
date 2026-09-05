from __future__ import annotations

from decimal import Decimal
import inspect
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tbdy_engine.analysis_basis import frame_gross_flexural_basis as basis
from tbdy_engine.analysis_basis.frame_gross_flexural_basis import (
    FrameFlexuralAxis,
    FrameFlexuralBaseContinuityEvidence,
    FrameGrossFlexuralBasisError,
    _build_continuity_from_facts,
    _build_from_continuity,
    build_frame_gross_flexural_basis_evidence,
    capture_frame_flexural_base_continuity_evidence,
    derive_rectangular_gross_inertia,
)
from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierSurface,
    FrameModifierVector,
)
from tbdy_engine.integration import etabs_analysis_state_mutation as b4b_module
from tbdy_engine.integration import etabs_analysis_state_revalidation as revalidation_module
from tbdy_engine.integration.etabs_analysis_execution import AnalysisExecutionResult
from tbdy_engine.integration.etabs_analysis_state_mutation import (
    AnalysisStateMutationResult,
)
from tbdy_engine.integration.etabs_scratch_lifecycle import OwnedScratchContext
from tbdy_engine.integration.live_etabs_acquisition_context import (
    TrustedLiveAcquisitionContext,
)
from tbdy_engine.providers import etabs_frame_flexural_base_provider as provider
from tbdy_engine.providers.etabs_frame_flexural_base_provider import (
    FrameFlexuralBaseFact,
    FrameFlexuralBaseFactError,
)
from tbdy_engine.regulatory.ts500_concrete_elastic_modulus import (
    Ts500EcComparisonStatus,
    compare_etabs_ec_to_ts500_table_3_2,
)


def _base_fact(
    *,
    component: str = "F1",
    section: str = "R30X50",
    material: str = "C25",
    ec: str = "30000",
    fck: str = "25",
    t2: str = "300",
    t3: str = "500",
    source: str = "source:1",
    ownership: str = "scratch:1",
    acquisition: str = "acq:1",
    session: str = "session:1",
    event: str = "1" * 32,
) -> FrameFlexuralBaseFact:
    rows = tuple((f"T{i}", {"i": i}) for i in range(5))
    refs = tuple(f"row:{i}" for i in range(5))
    return provider._issue_frame_flexural_base_fact(
        component_unique_name=component,
        assigned_section_name=section,
        material_name=material,
        t2_mm=Decimal(t2),
        t3_mm=Decimal(t3),
        concrete_fck_mpa=Decimal(fck),
        etabs_ec_mpa=Decimal(ec),
        source_model_ref=source,
        ownership_proof_ref=ownership,
        acquisition_context_ref=acquisition,
        session_provenance_ref=session,
        capture_event_ref=provider.FRAME_FLEXURAL_BASE_CAPTURE_EVENT_PREFIX + event,
        present_force_unit=3,
        present_length_unit=4,
        source_rows=rows,
        source_refs=refs,
    )


def _post_like(pre: FrameFlexuralBaseFact, **changes) -> FrameFlexuralBaseFact:
    values = {
        "component": pre.component_unique_name,
        "section": pre.assigned_section_name,
        "material": pre.material_name,
        "ec": str(pre.etabs_ec_mpa),
        "fck": str(pre.concrete_fck_mpa),
        "t2": str(pre.t2_mm),
        "t3": str(pre.t3_mm),
        "source": pre.source_model_ref,
        "ownership": pre.ownership_proof_ref,
        "acquisition": "acq:post",
        "session": "session:post",
        "event": "2" * 32,
    }
    values.update(changes)
    return _base_fact(**values)


def _modifier(
    surface: FrameModifierSurface,
    target: str,
    *,
    i2: float = 1.0,
    i3: float = 1.0,
):
    vector = FrameModifierVector(
        1.0,
        1.0,
        1.0,
        1.0,
        i2,
        i3,
        1.0,
        1.0,
    )
    after = SimpleNamespace(
        success=True,
        modifiers=vector,
        evidence_ref=f"after:{surface.value}:{target}",
    )
    return SimpleNamespace(
        surface=surface,
        target_name=target,
        setter=SimpleNamespace(success=True),
        after=after,
    )


def _lineage(
    pre: FrameFlexuralBaseFact,
    *,
    section: str | None = None,
    object_i2: float = 1.0,
    object_i3: float = 1.0,
    property_i2: float = 1.0,
    property_i3: float = 1.0,
    include_object: bool = True,
    include_property: bool = True,
    qualified: bool = True,
    wrong_state: bool = False,
    commit_pre: bool = True,
    retain_pre_post_revalidation: bool = True,
    revalidation_matched: bool = True,
):
    state = SimpleNamespace(
        identity_ref="analysis-state:sha256:" + "a" * 64,
        source_model_ref="source:1",
        state_basis_refs=(pre.evidence_ref,) if commit_pre else (),
    )
    target_section = section or pre.assigned_section_name
    mutations = []
    if include_property:
        mutations.append(
            _modifier(
                FrameModifierSurface.FRAME_SECTION_PROPERTY,
                target_section,
                i2=property_i2,
                i3=property_i3,
            )
        )
    if include_object:
        mutations.append(
            _modifier(
                FrameModifierSurface.FRAME_OBJECT,
                pre.component_unique_name,
                i2=object_i2,
                i3=object_i3,
            )
        )

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
    qstate = (
        SimpleNamespace(
            identity_ref="analysis-state:sha256:" + "c" * 64,
            source_model_ref="source:1",
            state_basis_refs=state.state_basis_refs,
        )
        if wrong_state
        else state
    )
    qualification = SimpleNamespace(
        qualified=qualified,
        analysis_state=qstate,
        analysis_result=result,
        qualification_ref="qualification:1",
    )
    current_state = SimpleNamespace(
        identity_ref=state.identity_ref,
        source_model_ref=state.source_model_ref,
        state_basis_refs=(
            state.state_basis_refs
            if retain_pre_post_revalidation
            else ()
        ),
    )
    revalidation = SimpleNamespace(
        matched_exact=revalidation_matched,
        current_analysis_state=current_state,
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


def _continuity(
    pre: FrameFlexuralBaseFact,
    post: FrameFlexuralBaseFact | None = None,
    **lineage_kwargs,
):
    post = post or _post_like(pre)
    owned, b4b, b5 = _lineage(pre, **lineage_kwargs)
    continuity = _build_continuity_from_facts(
        owned_scratch=owned,
        pre_fact=pre,
        post_fact=post,
        established_state=b4b,
        execution_result=b5,
    )
    return continuity, owned, b4b, b5


def _build(
    pre: FrameFlexuralBaseFact,
    post: FrameFlexuralBaseFact | None = None,
    **lineage_kwargs,
):
    continuity, owned, b4b, b5 = _continuity(
        pre,
        post,
        **lineage_kwargs,
    )
    return _build_from_continuity(
        owned_scratch=owned,
        continuity=continuity,
        axis=FrameFlexuralAxis.LOCAL_2_M2,
        established_state=b4b,
        execution_result=b5,
    )


def test_matching_ec_gross_rectangle_continuity_and_unit_surfaces_is_positive():
    evidence = _build(_base_fact())
    assert evidence.ts500_ec_comparison.status is Ts500EcComparisonStatus.MATCH
    assert evidence.gross_i_axis_mm4 == Decimal("3125000000")
    assert evidence.property_axis_modifier == 1.0
    assert evidence.object_axis_modifier == 1.0
    assert evidence.base_state_continuity.status.value == "BASE_STATE_CONTINUITY_PROVEN"


def test_continuity_compares_semantics_not_capture_hash_identity():
    pre = _base_fact(acquisition="acq:pre", session="session:pre", event="1" * 32)
    post = _post_like(pre, acquisition="acq:post", session="session:post", event="2" * 32)
    continuity, *_ = _continuity(pre, post)
    assert pre.evidence_ref != post.evidence_ref
    assert pre.capture_event_ref != post.capture_event_ref
    assert pre.semantic_state_ref == post.semantic_state_ref
    assert continuity.semantic_state_ref == pre.semantic_state_ref


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


@pytest.mark.parametrize(
    "kwargs",
    [{"include_property": False}, {"include_object": False}],
)
def test_missing_either_modifier_surface_fails_closed(kwargs):
    with pytest.raises(FrameGrossFlexuralBasisError, match="modifier census"):
        _build(_base_fact(), **kwargs)


def test_wrong_section_assignment_fails_closed_against_property_surface():
    pre = _base_fact(section="R30X50")
    with pytest.raises(FrameGrossFlexuralBasisError, match="modifier census"):
        _build(pre, section="OTHER")


def test_wrong_analysis_state_identity_fails_closed():
    with pytest.raises(FrameGrossFlexuralBasisError, match="not qualified"):
        _build(_base_fact(), wrong_state=True)


def test_unqualified_analysis_result_fails_closed():
    with pytest.raises(FrameGrossFlexuralBasisError, match="not qualified"):
        _build(_base_fact(), qualified=False)


def test_b5_post_analysis_modifier_revalidation_is_required():
    with pytest.raises(FrameGrossFlexuralBasisError, match="revalidate"):
        _build(_base_fact(), revalidation_matched=False)


def test_pre_capture_must_be_committed_into_b4b_analysis_state_identity():
    pre = _base_fact()
    post = _post_like(pre)
    owned, b4b, b5 = _lineage(pre, commit_pre=False)
    with pytest.raises(FrameGrossFlexuralBasisError, match="PRE frame-base capture"):
        _build_continuity_from_facts(
            owned_scratch=owned,
            pre_fact=pre,
            post_fact=post,
            established_state=b4b,
            execution_result=b5,
        )


def test_b5_revalidation_must_preserve_pre_state_basis_commitment():
    pre = _base_fact()
    post = _post_like(pre)
    owned, b4b, b5 = _lineage(
        pre,
        retain_pre_post_revalidation=False,
    )
    with pytest.raises(FrameGrossFlexuralBasisError, match="lost the PRE"):
        _build_continuity_from_facts(
            owned_scratch=owned,
            pre_fact=pre,
            post_fact=post,
            established_state=b4b,
            execution_result=b5,
        )


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"ec": "29999"}, "etabs_ec_mpa"),
        ({"t2": "301"}, "t2_mm"),
        ({"t3": "501"}, "t3_mm"),
        ({"material": "C30"}, "material_name"),
        ({"section": "R35X50"}, "assigned_section_name"),
    ],
)
def test_pre_post_base_semantic_mismatch_fails_closed(changes, field):
    pre = _base_fact()
    post = _post_like(pre, **changes)
    with pytest.raises(FrameGrossFlexuralBasisError, match=field):
        _continuity(pre, post)


def test_pre_post_source_model_mismatch_fails_closed():
    pre = _base_fact()
    post = _post_like(pre, source="source:2")
    with pytest.raises(FrameGrossFlexuralBasisError, match="source_model_ref"):
        _continuity(pre, post)


def test_pre_post_ownership_proof_mismatch_fails_closed():
    pre = _base_fact()
    post = _post_like(pre, ownership="scratch:2")
    with pytest.raises(FrameGrossFlexuralBasisError, match="ownership_proof_ref"):
        _continuity(pre, post)


def test_post_only_capture_has_no_supported_positive_basis_path():
    assert not hasattr(basis, "capture_frame_gross_flexural_basis_evidence")
    signature = inspect.signature(build_frame_gross_flexural_basis_evidence)
    assert "continuity" in signature.parameters
    assert "base_fact" not in signature.parameters
    assert "post_fact" not in signature.parameters


def test_continuity_public_path_does_not_accept_caller_injected_post_fact():
    signature = inspect.signature(capture_frame_flexural_base_continuity_evidence)
    assert "pre_fact" in signature.parameters
    assert "post_fact" not in signature.parameters


def test_frame_flexural_base_fact_direct_public_construction_is_blocked():
    with pytest.raises(TypeError, match="provider-issued only"):
        FrameFlexuralBaseFact(
            component_unique_name="F1",
            assigned_section_name="R30X50",
            material_name="C25",
            section_semantics=provider.SUPPORTED_FRAME_SECTION_SEMANTICS,
            t2_mm=Decimal("300"),
            t3_mm=Decimal("500"),
            concrete_fck_mpa=Decimal("25"),
            etabs_ec_mpa=Decimal("30000"),
            source_model_ref="source:1",
            ownership_proof_ref="scratch:1",
            acquisition_context_ref="acq:1",
            session_provenance_ref="session:1",
            capture_event_ref=provider.FRAME_FLEXURAL_BASE_CAPTURE_EVENT_PREFIX + "1" * 32,
            present_force_unit=3,
            present_length_unit=4,
            source_rows=tuple((f"T{i}", {"i": i}) for i in range(5)),
            source_refs=tuple(f"row:{i}" for i in range(5)),
        )


def test_continuity_direct_public_construction_is_blocked():
    pre = _base_fact()
    post = _post_like(pre)
    with pytest.raises(TypeError, match="factory-created only"):
        FrameFlexuralBaseContinuityEvidence(
            pre_fact=pre,
            post_fact=post,
            semantic_state_ref=pre.semantic_state_ref,
            parent_analysis_state_ref="state:1",
            parent_analysis_result_ref="result:1",
            ownership_proof_ref="scratch:1",
            source_model_ref="source:1",
            source_refs=("source:1",),
        )


def test_b4b_exposes_opaque_additional_state_basis_commitment_seam():
    signature = inspect.signature(b4b_module.establish_frame_modifier_analysis_state)
    assert "additional_state_basis_refs" in signature.parameters


def test_revalidation_preserves_complete_original_state_basis_population():
    source = inspect.getsource(revalidation_module.revalidate_frame_modifier_analysis_state)
    assert "state_basis_refs=established_state.analysis_state_identity.state_basis_refs" in source


def test_ts500_unknown_concrete_class_is_unresolved_not_interpolated():
    comparison = compare_etabs_ec_to_ts500_table_3_2(
        concrete_fck_mpa=Decimal("32"),
        factual_etabs_ec_mpa=Decimal("32000"),
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
    monkeypatch.setattr(
        provider,
        "reread_verified_session_identity",
        lambda session: identity,
    )
    monkeypatch.setattr(
        provider,
        "read_verified_unit_snapshot",
        lambda session: units,
    )
    monkeypatch.setattr(
        provider,
        "_rows",
        lambda ctx, table: tuple(tables[table]),
    )
    return context, owned


def _valid_tables():
    return {
        provider.TABLE_FRAME_ASSIGNMENTS: [
            {"UniqueName": "F1", "SectProp": "R30X50"}
        ],
        provider.TABLE_RECTANGULAR: [
            {
                "Name": "R30X50",
                "t2": 300,
                "t3": 500,
                "Material": "C25",
            }
        ],
        provider.TABLE_FRAME_SECTION_SUMMARY: [
            {
                "Name": "R30X50",
                "Material": "C25",
                "Shape": "Concrete Rectangular",
            }
        ],
        provider.TABLE_BASIC_MATERIAL: [
            {"Material": "C25", "E1": 30000}
        ],
        provider.TABLE_CONCRETE: [
            {"Material": "C25", "Fc": 25}
        ],
    }


def test_live_factual_path_binds_assignment_material_ec_units_and_event(monkeypatch):
    context, owned = _provider_context(monkeypatch, _valid_tables())
    fact = provider.capture_frame_flexural_base_fact(
        context=context,
        owned_scratch=owned,
        component_unique_name="F1",
    )
    assert fact.assigned_section_name == "R30X50"
    assert fact.material_name == "C25"
    assert fact.etabs_ec_mpa == Decimal("30000")
    assert fact.concrete_fck_mpa == Decimal("25")
    assert fact.section_semantics == provider.SUPPORTED_FRAME_SECTION_SEMANTICS
    assert fact.capture_event_ref.startswith(
        provider.FRAME_FLEXURAL_BASE_CAPTURE_EVENT_PREFIX
    )


def test_two_canonical_provider_captures_have_same_semantics_but_distinct_events(monkeypatch):
    context, owned = _provider_context(monkeypatch, _valid_tables())
    pre = provider.capture_frame_flexural_base_fact(
        context=context,
        owned_scratch=owned,
        component_unique_name="F1",
    )
    post = provider.capture_frame_flexural_base_fact(
        context=context,
        owned_scratch=owned,
        component_unique_name="F1",
    )
    assert pre.semantic_state_ref == post.semantic_state_ref
    assert pre.capture_event_ref != post.capture_event_ref
    assert pre.evidence_ref != post.evidence_ref


def test_public_continuity_path_captures_post_from_canonical_provider(monkeypatch):
    pre = _base_fact()
    post = _post_like(pre)
    owned, b4b, b5 = _lineage(pre)
    context = Mock(spec=TrustedLiveAcquisitionContext)
    context.source_model_identity = owned.source_model_identity
    context.verified_session = object()
    captured = []

    def _capture(*, context, owned_scratch, component_unique_name):
        captured.append((context, owned_scratch, component_unique_name))
        return post

    monkeypatch.setattr(
        basis,
        "capture_frame_flexural_base_fact",
        _capture,
    )
    continuity = capture_frame_flexural_base_continuity_evidence(
        context=context,
        owned_scratch=owned,
        pre_fact=pre,
        established_state=b4b,
        execution_result=b5,
    )
    assert continuity.pre_fact is pre
    assert continuity.post_fact is post
    assert captured == [(context, owned, "F1")]


def test_wrong_material_binding_fails_closed(monkeypatch):
    tables = _valid_tables()
    tables[provider.TABLE_RECTANGULAR][0]["Material"] = "C30"
    context, owned = _provider_context(monkeypatch, tables)
    with pytest.raises(FrameFlexuralBaseFactError, match="material disagrees"):
        provider.capture_frame_flexural_base_fact(
            context=context,
            owned_scratch=owned,
            component_unique_name="F1",
        )


def test_missing_e1_fails_closed(monkeypatch):
    tables = _valid_tables()
    del tables[provider.TABLE_BASIC_MATERIAL][0]["E1"]
    context, owned = _provider_context(monkeypatch, tables)
    with pytest.raises(FrameFlexuralBaseFactError, match="E1"):
        provider.capture_frame_flexural_base_fact(
            context=context,
            owned_scratch=owned,
            component_unique_name="F1",
        )


def test_wrong_section_assignment_fails_closed_at_rectangle_join(monkeypatch):
    tables = _valid_tables()
    tables[provider.TABLE_FRAME_ASSIGNMENTS][0]["SectProp"] = "MISSING"
    context, owned = _provider_context(monkeypatch, tables)
    with pytest.raises(FrameFlexuralBaseFactError, match="rectangular section"):
        provider.capture_frame_flexural_base_fact(
            context=context,
            owned_scratch=owned,
            component_unique_name="F1",
        )


def test_unsupported_nonprismatic_section_fails_closed(monkeypatch):
    tables = _valid_tables()
    tables[provider.TABLE_FRAME_SECTION_SUMMARY][0]["Shape"] = "Nonprismatic"
    context, owned = _provider_context(monkeypatch, tables)
    with pytest.raises(FrameFlexuralBaseFactError, match="not the supported"):
        provider.capture_frame_flexural_base_fact(
            context=context,
            owned_scratch=owned,
            component_unique_name="F1",
        )
