from tbdy_engine.design.columns.stability_stiffness_basis import (
    AssignedFrameBendingModifierEvidence,
    STATUS_BLOCKED_GLOBAL_PROOF,
    STATUS_REANALYSIS_REQUIRED,
    assess_ts500_eq713_stiffness_basis,
)


def _evidence(section, kind, i2, i3):
    return AssignedFrameBendingModifierEvidence(
        section_name=section,
        member_kind=kind,
        i2_modifier=i2,
        i3_modifier=i3,
        source_refs=(f"ETABS:{section}",),
    )


def test_nonunit_assigned_column_modifier_requires_reanalysis():
    result = assess_ts500_eq713_stiffness_basis((
        _evidence("Column_80x80", "COLUMN", 0.7, 0.7),
    ))
    assert result.status == STATUS_REANALYSIS_REQUIRED
    assert result.reanalysis_required is True
    assert result.proves_uncracked is False
    assert [item.section_name for item in result.nonunit_sections] == ["Column_80x80"]


def test_nonunit_assigned_beam_modifier_also_requires_reanalysis():
    result = assess_ts500_eq713_stiffness_basis((
        _evidence("Column_80x80", "COLUMN", 1.0, 1.0),
        _evidence("B60x70", "BEAM", 0.35, 0.35),
    ))
    assert result.status == STATUS_REANALYSIS_REQUIRED
    assert result.reanalysis_required is True
    assert {item.section_name for item in result.nonunit_sections} == {"B60x70"}


def test_unit_frame_modifiers_do_not_overclaim_global_uncracked_basis():
    result = assess_ts500_eq713_stiffness_basis((
        _evidence("Column_80x80", "COLUMN", 1.0, 1.0),
        _evidence("B60x70", "BEAM", 1.0, 1.0),
    ))
    assert result.status == STATUS_BLOCKED_GLOBAL_PROOF
    assert result.reanalysis_required is False
    assert result.proves_uncracked is False
    assert result.nonunit_sections == ()


def test_duplicate_section_identity_fails_closed():
    try:
        assess_ts500_eq713_stiffness_basis((
            _evidence("Column_80x80", "COLUMN", 0.7, 0.7),
            _evidence("Column_80x80", "COLUMN", 0.7, 0.7),
        ))
    except ValueError as exc:
        assert "duplicate member_kind/section_name" in str(exc)
    else:
        raise AssertionError("duplicate evidence must fail closed")
