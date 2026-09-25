from __future__ import annotations

from dataclasses import replace
import inspect
import math

import tbdy_engine.application.column_a19_effective_length as subject
from tbdy_engine.application.column_a18_end_restraint import (
    A18_AUTHORITY,
    A18_READY,
    A18EndRestraintMaterialization,
)
from tbdy_engine.application.column_local_sway_runtime import (
    STATUS_READY as A17_READY,
    ColumnLocalAxisSwayRuntime,
)
from tbdy_engine.design.columns.free_length_basis import (
    FREE_LENGTH_PROVEN,
    ColumnEndpointSupportResolution,
    ColumnFreeLengthResolution,
)
from tbdy_engine.design.columns.local_axis_sway_binding import (
    LOCAL_SWAY_PREVENTED,
    ColumnLocalAxisSwayBinding,
    LocalAxisSwayResult,
)
from tbdy_engine.design.columns.slenderness import SWAY_PREVENTED
from tbdy_engine.design.columns.sway_stability import (
    StorySwayStabilityResolution,
)


def _a18(end_tag: str, axis: str, alpha: float):
    suffix = f"{end_tag}:{axis}"
    return A18EndRestraintMaterialization(
        component_id="+4.50:C10:188",
        end_tag=end_tag,
        local_bending_axis=axis,
        disposition=A18_READY,
        alpha=alpha,
        numerator_column_i_over_l_m3=alpha,
        denominator_beam_i_over_l_m3=1.0,
        column_member_ids=("188",),
        beam_member_ids=(f"B-{suffix}",),
        source_refs=(
            A18_AUTHORITY,
            f"etabs-frame-release:sha256:{suffix}",
            f"A18:{suffix}",
        ),
    )


def _a18_rows():
    return (
        _a18("BOTTOM", "M2", 1.0),
        _a18("BOTTOM", "M3", 0.5),
        _a18("TOP", "M2", 3.0),
        _a18("TOP", "M3", 1.5),
    )


def _story(direction: str):
    return StorySwayStabilityResolution(
        story="+4.50",
        direction=direction,
        status="PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX",
        governing_phi=0.01,
        governing_load_basis="TEST_ONLY",
        load_results=(),
        missing_load_bases=(),
        source_refs=(f"TEST:{direction}",),
    )


def _local_sway():
    test_ref = (
        "TEST_ONLY:NON_DESIGN:NON_CANONICAL:"
        "NOT_TS500_PROOF:NOT_PROJECT_REVIEW"
    )

    m2 = LocalAxisSwayResult(
        axis="M2",
        status=LOCAL_SWAY_PREVENTED,
        sway_classification=SWAY_PREVENTED,
        contributing_global_directions=("X",),
        local_transverse_unit_xy=(1.0, 0.0),
        source_refs=(test_ref, "TEST:M2"),
    )

    m3 = LocalAxisSwayResult(
        axis="M3",
        status=LOCAL_SWAY_PREVENTED,
        sway_classification=SWAY_PREVENTED,
        contributing_global_directions=("Y",),
        local_transverse_unit_xy=(0.0, 1.0),
        source_refs=(test_ref, "TEST:M3"),
    )

    binding = ColumnLocalAxisSwayBinding(
        component_id="+4.50:C10:188",
        local_axis_angle_deg=0.0,
        m2=m2,
        m3=m3,
        source_refs=(test_ref,),
    )

    return ColumnLocalAxisSwayRuntime(
        component_id="+4.50:C10:188",
        story="+4.50",
        global_x=_story("X"),
        global_y=_story("Y"),
        local_binding=binding,
        status=A17_READY,
        source_refs=(test_ref,),
    )


def _support(end_tag: str):
    return ColumnEndpointSupportResolution(
        end_tag=end_tag,
        joint_unique_name=f"J-{end_tag}",
        status="PROVEN_HORIZONTAL_LATERAL_SUPPORT",
        proof_methods=("TEST_ONLY",),
        support_vectors_xy=((1.0, 0.0), (0.0, 1.0)),
        source_refs=(f"TEST:SUPPORT:{end_tag}",),
    )


def _free_length():
    return ColumnFreeLengthResolution(
        component_id="+4.50:C10:188",
        status=FREE_LENGTH_PROVEN,
        free_length_ln_mm=3800.0,
        factual_candidate_mm=3800.0,
        bottom_support=_support("BOTTOM"),
        top_support=_support("TOP"),
        source_refs=("TEST:FREE_LENGTH",),
    )


def _row(rows, axis):
    match = tuple(item for item in rows if item.local_bending_axis == axis)
    assert len(match) == 1
    return match[0]


def test_a19_propagates_source_bound_not_one_end_hinged_and_real_kernel_contract(
    monkeypatch,
):
    captured = []
    real = subject.evaluate_ts500_effective_length_factor

    def spy(basis):
        captured.append(basis)
        return real(basis)

    monkeypatch.setattr(
        subject,
        "evaluate_ts500_effective_length_factor",
        spy,
    )

    rows = subject.materialize_ts500_effective_lengths(
        component_id="+4.50:C10:188",
        a18_rows=_a18_rows(),
        local_sway=_local_sway(),
        free_length=_free_length(),
    )

    assert len(rows) == 2
    assert len(captured) == 2
    assert {item.axis for item in captured} == {"M2", "M3"}
    assert all(item.one_end_hinged is False for item in captured)

    m2 = _row(rows, "M2")
    m3 = _row(rows, "M3")

    assert m2.disposition == subject.A19_READY
    assert m3.disposition == subject.A19_READY

    assert m2.one_end_hinged is False
    assert m3.one_end_hinged is False

    # Independent axes prove there is no hard-coded k=1 fallback.
    assert math.isclose(m2.k, 0.90)
    assert math.isclose(m2.effective_length_lk_mm, 3420.0)

    assert math.isclose(m3.k, 0.80)
    assert math.isclose(m3.effective_length_lk_mm, 3040.0)

    assert m2.free_length_ln_mm == 3800.0
    assert m3.free_length_ln_mm == 3800.0

    assert m2.controlling_equation is None
    assert m3.controlling_equation is None

    assert subject.A19_ONE_END_HINGED_AUTHORITY in m2.source_refs
    assert subject.A19_ONE_END_HINGED_AUTHORITY in m3.source_refs


def test_a19_fails_closed_when_a18_ready_row_lacks_release_provenance():
    rows = list(_a18_rows())

    rows[0] = replace(
        rows[0],
        source_refs=(
            A18_AUTHORITY,
            "TEST:A18_WITHOUT_RELEASE_FACT",
        ),
    )

    result = subject.materialize_ts500_effective_lengths(
        component_id="+4.50:C10:188",
        a18_rows=tuple(rows),
        local_sway=_local_sway(),
        free_length=_free_length(),
    )

    m2 = _row(result, "M2")
    m3 = _row(result, "M3")

    assert m2.disposition == subject.A19_EXPLICIT_UNRESOLVED
    assert m2.one_end_hinged is None
    assert m2.k is None
    assert m2.effective_length_lk_mm is None
    assert m2.unresolved_reasons == (
        "A18_RELEASE_EVIDENCE_NOT_BOUND_FOR_ONE_END_HINGED:M2:BOTTOM",
    )

    # Axis independence is preserved.
    assert m3.disposition == subject.A19_READY


def test_a19_adapter_contains_no_stale_kernel_member_access():
    source = inspect.getsource(
        subject.materialize_ts500_effective_lengths
    )

    assert "factor.k" not in source
    assert "factor.controlling_equation" not in source
    assert "factor.effective_length_factor_k" in source

    assert "column_effective_length_mm(" in source
    assert "free_length_mm=float(ln)" in source
    assert "factor=factor" in source

    # Application does not manufacture equation provenance.
    assert "controlling_equation=None" in source
