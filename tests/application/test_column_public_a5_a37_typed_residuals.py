from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_public_a5 as a5
from tbdy_engine.etabs.oapi.frame_modifiers import FrameModifierVector
from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (
    ContributorDisposition,
    FrameModeAuditDisposition,
    FrameStiffnessMode,
    ModeDisposition,
)
from tbdy_engine.etabs.oapi.line_springs import (
    LineSpringPropertyUniverseFact,
)
from tbdy_engine.providers.etabs_frame_eq713_population_provider import (
    FrameEq713ObjectTypeFact,
    FrameEq713ObjectTypeResolution,
    FrameEq713ScopeFact,
    FrameEq713ScopeStatus,
    TABLE_FRAME_ASSIGNMENTS_SUMMARY,
)


def _scope(
    name: str,
    *,
    status=FrameEq713ScopeStatus.OUT_OF_SLICE_FACTUAL_SCOPE_UNRESOLVED,
    section=None,
    shape=None,
    material=None,
    role=None,
):
    return FrameEq713ScopeFact(
        frame_name=name,
        assigned_section_name=section,
        shape=shape,
        material_name=material,
        member_role=role,
        scope_status=status,
        reason=f"legacy-scope-reason:{name}",
        source_refs=(f"scope:{name}",),
    )


def _type(name: str, raw: str | None):
    return FrameEq713ObjectTypeFact(
        frame_name=name,
        raw_frame_type=raw,
        normalized_frame_type=None if raw is None else raw.upper(),
        resolution=(
            FrameEq713ObjectTypeResolution.UNRESOLVED
            if raw is None
            else FrameEq713ObjectTypeResolution.RESOLVED
        ),
        source_table=TABLE_FRAME_ASSIGNMENTS_SUMMARY,
        source_column=None if raw is None else "FrameType",
        source_row=None if raw is None else {"UniqueName": name, "FrameType": raw},
        join_identity=name,
        resolution_reason="missing" if raw is None else "resolved",
        source_refs=(f"type:{name}",),
    )


def _assert_all_blocked(disposition):
    assert tuple(row.mode for row in disposition.mode_dispositions) == tuple(
        FrameStiffnessMode
    )
    assert all(
        row.disposition is ContributorDisposition.BLOCKED_UNSUPPORTED
        for row in disposition.mode_dispositions
    )
    assert all(
        row.disposition is not ContributorDisposition.PROVEN_NOT_APPLICABLE
        for row in disposition.mode_dispositions
    )


def test_null_raw_type_alone_never_becomes_proven_not_applicable():
    disposition = a5._typed_out_of_slice_frame_disposition(
        _scope("NULL-1"),
        _type("NULL-1", "Null"),
        None,
    )

    _assert_all_blocked(disposition)
    reason = disposition.blocked_reasons[0]
    assert "line-spring" in reason
    assert "not proven" in reason
    assert any("Line_Springs" in ref for ref in disposition.source_refs)


def test_brace_is_not_coerced_to_beam_or_declared_not_applicable():
    disposition = a5._typed_out_of_slice_frame_disposition(
        _scope(
            "BRACE-1",
            status=FrameEq713ScopeStatus.OUT_OF_SLICE_ROLE_UNRESOLVED,
        ),
        _type("BRACE-1", "Brace"),
        None,
    )

    _assert_all_blocked(disposition)
    reason = disposition.blocked_reasons[0]
    assert "BRACE is a factual frame type" in reason
    assert "not a not-applicable label" in reason
    assert "inferring BRACE as BEAM" not in reason


def test_steel_generic_facts_do_not_manufacture_concrete_authority():
    structural = SimpleNamespace(
        frame_name="760",
        assigned_section_name="HE160A",
        shape="Steel I/Wide Flange",
        material_name="S355",
        source_refs=("section:HE160A", "material:S355", "modifier:760"),
    )
    original = a5.FrameEq713ResidualStructuralFact
    a5.FrameEq713ResidualStructuralFact = SimpleNamespace
    try:
        disposition = a5._typed_out_of_slice_frame_disposition(
            _scope(
                "760",
                status=FrameEq713ScopeStatus.OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL,
                section="HE160A",
                shape="Steel I/Wide Flange",
                material="S355",
                role="BEAM",
            ),
            _type("760", "Beam"),
            structural,
        )
    finally:
        a5.FrameEq713ResidualStructuralFact = original

    _assert_all_blocked(disposition)
    reason = disposition.blocked_reasons[0]
    assert "material-neutral normalization contract" in reason
    assert "concrete-only" in reason
    assert "non-participating" not in reason


def test_unresolved_frame_type_is_explicitly_blocked():
    disposition = a5._typed_out_of_slice_frame_disposition(
        _scope("UNKNOWN-1"),
        _type("UNKNOWN-1", None),
        None,
    )
    _assert_all_blocked(disposition)
    assert "factual Frame type is unresolved" in disposition.blocked_reasons[0]


def test_legacy_synthetic_population_without_a37_type_fields_uses_compatibility_path():
    scope = _scope(
        "LEGACY-STEEL",
        status=FrameEq713ScopeStatus.OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL,
        section="HE160A",
        shape="Steel I/Wide Flange",
        material="S355",
        role="BEAM",
    )
    frame_population = SimpleNamespace(
        expected_frame_names=("LEGACY-STEEL",),
        rows=(),
        out_of_slice_rows=(scope,),
    )
    area_population = SimpleNamespace(
        expected_area_names=(),
        rows=(),
    )

    whole, _ = a5._build_a3(
        frame_population=frame_population,
        area_population=area_population,
        topology=SimpleNamespace(columns=()),
    )

    assert tuple(row.component_uid for row in whole.frame_rows) == (
        "LEGACY-STEEL",
    )
    row = whole.frame_rows[0]
    assert all(
        item.disposition is ContributorDisposition.BLOCKED_UNSUPPORTED
        for item in row.mode_dispositions
    )

def test_998_equivalent_a3_frame_disposition_accounting_has_no_missing_identity():
    supported = tuple(
        FrameModeAuditDisposition(
            component_uid=f"RC-{index:03d}",
            mode_dispositions=tuple(
                ModeDisposition(
                    mode,
                    ContributorDisposition.TARGETED_UNCRACKED,
                    "synthetic supported mode",
                    (f"supported:{index}",),
                )
                for mode in FrameStiffnessMode
            ),
            blocked_reasons=(),
            source_refs=(f"supported:{index}",),
        )
        for index in range(918)
    )

    null_rows = tuple(
        a5._typed_out_of_slice_frame_disposition(
            _scope(f"NULL-{index:03d}"),
            _type(f"NULL-{index:03d}", "Null"),
            None,
        )
        for index in range(68)
    )
    brace_rows = tuple(
        a5._typed_out_of_slice_frame_disposition(
            _scope(
                f"BRACE-{index:03d}",
                status=FrameEq713ScopeStatus.OUT_OF_SLICE_ROLE_UNRESOLVED,
            ),
            _type(f"BRACE-{index:03d}", "Brace"),
            None,
        )
        for index in range(4)
    )
    steel_rows = tuple(
        a5._typed_out_of_slice_frame_disposition(
            _scope(
                f"STEEL-{index:03d}",
                status=FrameEq713ScopeStatus.OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL,
                section="HE160A",
                shape="Steel I/Wide Flange",
                material="S355",
                role="BEAM",
            ),
            _type(f"STEEL-{index:03d}", "Beam"),
            None,
        )
        for index in range(8)
    )

    rows = (*supported, *null_rows, *brace_rows, *steel_rows)
    names = tuple(row.component_uid for row in rows)
    assert len(rows) == 998
    assert len(set(names)) == 998



def _line_spring_universe(
    *names: str,
    return_code: int = 0,
):
    return LineSpringPropertyUniverseFact(
        property_names=tuple(names),
        reported_count=len(names),
        return_code=return_code,
    )


def test_null_with_empty_model_line_spring_universe_is_proven_not_applicable():
    universe = _line_spring_universe()

    disposition = a5._typed_out_of_slice_frame_disposition(
        _scope("NULL-EMPTY"),
        _type("NULL-EMPTY", "Null"),
        None,
        universe,
    )

    assert disposition.blocked_reasons == ()
    assert tuple(
        item.mode
        for item in disposition.mode_dispositions
    ) == tuple(FrameStiffnessMode)

    assert all(
        item.disposition
        is ContributorDisposition.PROVEN_NOT_APPLICABLE
        for item in disposition.mode_dispositions
    )

    assert universe.evidence_ref in disposition.source_refs
    assert (
        "PropLineSpring property universe is successfully proven empty"
        in disposition.mode_dispositions[0].reason
    )


def test_null_with_defined_model_line_spring_property_remains_blocked():
    universe = _line_spring_universe("LS-1")

    disposition = a5._typed_out_of_slice_frame_disposition(
        _scope("NULL-WITH-SPRING-UNIVERSE"),
        _type("NULL-WITH-SPRING-UNIVERSE", "Null"),
        None,
        universe,
    )

    _assert_all_blocked(disposition)
    assert universe.evidence_ref in disposition.source_refs


def test_null_with_nonzero_line_spring_universe_read_remains_blocked():
    universe = _line_spring_universe(
        return_code=7,
    )

    disposition = a5._typed_out_of_slice_frame_disposition(
        _scope("NULL-UNRESOLVED-SPRING-UNIVERSE"),
        _type(
            "NULL-UNRESOLVED-SPRING-UNIVERSE",
            "Null",
        ),
        None,
        universe,
    )

    _assert_all_blocked(disposition)


def test_null_with_frame_section_assignment_remains_blocked_even_if_spring_universe_empty():
    universe = _line_spring_universe()

    disposition = a5._typed_out_of_slice_frame_disposition(
        _scope(
            "NULL-WITH-SECTION",
            section="SEC-1",
        ),
        _type("NULL-WITH-SECTION", "Null"),
        None,
        universe,
    )

    _assert_all_blocked(disposition)



def _source_proven_steel_structural(
    name: str,
    *,
    property_values=(1.0,) * 8,
    object_values=(1.0,) * 8,
):
    return SimpleNamespace(
        frame_name=name,
        assigned_section_name=(
            "DN40"
            if "BRACE" in name
            else "HE160A"
        ),
        shape=(
            "Steel Pipe"
            if "BRACE" in name
            else "Steel I/Wide Flange"
        ),
        material_name="S355",
        material_type=SimpleNamespace(
            material_name="S355",
            success=True,
            is_steel=True,
            evidence_ref="material-type:S355",
        ),
        property_modifiers=SimpleNamespace(
            modifiers=FrameModifierVector.from_sequence(
                property_values
            ),
        ),
        object_modifiers=SimpleNamespace(
            modifiers=FrameModifierVector.from_sequence(
                object_values
            ),
        ),
        source_refs=(
            f"structural:{name}",
            "material-type:S355",
        ),
    )


@pytest.mark.parametrize(
    (
        "name",
        "raw_type",
        "status",
        "role",
        "section",
        "shape",
    ),
    (
        (
            "STEEL-BEAM",
            "Beam",
            FrameEq713ScopeStatus.OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL,
            "BEAM",
            "HE160A",
            "Steel I/Wide Flange",
        ),
        (
            "BRACE-STEEL",
            "Brace",
            FrameEq713ScopeStatus.OUT_OF_SLICE_ROLE_UNRESOLVED,
            None,
            "DN40",
            "Steel Pipe",
        ),
    ),
)
def test_source_proven_steel_frame_closes_concrete_normalization(
    name,
    raw_type,
    status,
    role,
    section,
    shape,
):
    structural = (
        _source_proven_steel_structural(
            name
        )
    )

    original = (
        a5.FrameEq713ResidualStructuralFact
    )

    a5.FrameEq713ResidualStructuralFact = (
        SimpleNamespace
    )

    try:
        disposition = (
            a5._typed_out_of_slice_frame_disposition(
                _scope(
                    name,
                    status=status,
                    section=section,
                    shape=shape,
                    material="S355",
                    role=role,
                ),
                _type(
                    name,
                    raw_type,
                ),
                structural,
            )
        )
    finally:
        a5.FrameEq713ResidualStructuralFact = (
            original
        )

    assert disposition.blocked_reasons == ()

    assert tuple(
        item.mode
        for item in disposition.mode_dispositions
    ) == tuple(FrameStiffnessMode)

    assert all(
        item.disposition
        is ContributorDisposition.PROVEN_NOT_APPLICABLE
        for item in disposition.mode_dispositions
    )

    reason = (
        disposition
        .mode_dispositions[0]
        .reason
    )

    assert (
        "TS500 concrete cracking normalization "
        "is not applied"
        in reason
    )

    assert "End releases" in reason

    assert (
        "material-type:S355"
        in disposition.source_refs
    )


@pytest.mark.parametrize(
    (
        "property_values",
        "object_values",
    ),
    (
        (
            (
                0.5, 1.0, 1.0, 1.0,
                1.0, 1.0, 1.0, 1.0,
            ),
            (1.0,) * 8,
        ),
        (
            (1.0,) * 8,
            (
                1.0, 1.0, 1.0, 1.0,
                0.5, 1.0, 1.0, 1.0,
            ),
        ),
    ),
)
def test_source_proven_steel_frame_with_nonunity_modifier_remains_blocked(
    property_values,
    object_values,
):
    structural = (
        _source_proven_steel_structural(
            "STEEL-NONUNITY",
            property_values=property_values,
            object_values=object_values,
        )
    )

    original = (
        a5.FrameEq713ResidualStructuralFact
    )

    a5.FrameEq713ResidualStructuralFact = (
        SimpleNamespace
    )

    try:
        disposition = (
            a5._typed_out_of_slice_frame_disposition(
                _scope(
                    "STEEL-NONUNITY",
                    status=FrameEq713ScopeStatus.OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL,
                    section="HE160A",
                    shape="Steel I/Wide Flange",
                    material="S355",
                    role="BEAM",
                ),
                _type(
                    "STEEL-NONUNITY",
                    "Beam",
                ),
                structural,
            )
        )
    finally:
        a5.FrameEq713ResidualStructuralFact = (
            original
        )

    _assert_all_blocked(disposition)

    assert (
        "not both unity"
        in disposition.blocked_reasons[0]
    )


def test_unproven_material_type_does_not_close_steel_named_frame():
    structural = (
        _source_proven_steel_structural(
            "STEEL-UNPROVEN"
        )
    )

    structural.material_type = (
        SimpleNamespace(
            material_name="S355",
            success=False,
            is_steel=False,
            evidence_ref=(
                "material-type:S355:failed"
            ),
        )
    )

    original = (
        a5.FrameEq713ResidualStructuralFact
    )

    a5.FrameEq713ResidualStructuralFact = (
        SimpleNamespace
    )

    try:
        disposition = (
            a5._typed_out_of_slice_frame_disposition(
                _scope(
                    "STEEL-UNPROVEN",
                    status=FrameEq713ScopeStatus.OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL,
                    section="HE160A",
                    shape="Steel I/Wide Flange",
                    material="S355",
                    role="BEAM",
                ),
                _type(
                    "STEEL-UNPROVEN",
                    "Beam",
                ),
                structural,
            )
        )
    finally:
        a5.FrameEq713ResidualStructuralFact = (
            original
        )

    _assert_all_blocked(disposition)
