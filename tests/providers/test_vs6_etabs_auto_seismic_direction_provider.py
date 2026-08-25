from types import MappingProxyType

import pytest

from tbdy_engine.design.columns.stability_action_basis import (
    StabilityActionSource,
    TS500_ACTION_E,
)
from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.providers.etabs_auto_seismic_direction_provider import (
    EtabsAutoSeismicDirectionEvidence,
    EtabsAutoSeismicDirectionProviderError,
    EtabsAutoSeismicDirectionRow,
    bind_etabs_seismic_action_directions,
)


def _source(case_name: str, pattern_name: str) -> StabilityActionSource:
    return StabilityActionSource(
        case_name=case_name,
        pattern_name=pattern_name,
        source_pattern_type="QUAKE",
        action_role=TS500_ACTION_E,
        case_scale_factor=1.0,
        source_refs=(f"FACT:{case_name}",),
    )


def _row(name: str, *, x=False, xp=False, xm=False, y=False, yp=False, ym=False):
    flags = MappingProxyType({
        "XDir": x,
        "XDirPlusE": xp,
        "XDirMinusE": xm,
        "YDir": y,
        "YDirPlusE": yp,
        "YDirMinusE": ym,
    })
    return EtabsAutoSeismicDirectionRow(
        pattern_name=name,
        flags=flags,
        raw_row={"Name": name},
    )


def _evidence(*rows):
    return EtabsAutoSeismicDirectionEvidence(
        field_keys=("Name", "XDir", "XDirPlusE", "XDirMinusE", "YDir", "YDirPlusE", "YDirMinusE"),
        rows=tuple(rows),
        runtime_capture_status=RuntimeCaptureStatus.FULL,
        return_code=0,
        row_count_reported=len(rows),
        selected_signature_reason="test",
    )


def test_direction_binding_uses_exact_pattern_identity_and_flags_not_case_names():
    result = bind_etabs_seismic_action_directions(
        (
            _source("case-that-says-Y", "P_A"),
            _source("case-that-says-X", "P_B"),
        ),
        _evidence(
            _row("P_A", x=True),
            _row("P_B", y=True),
        ),
    )
    assert result.status == "PROVEN_ETABS_SEISMIC_DIRECTION_BINDING"
    assert [(item.case_name, item.pattern_name, item.direction) for item in result.bindings] == [
        ("case-that-says-Y", "P_A", "X"),
        ("case-that-says-X", "P_B", "Y"),
    ]
    assert result.as_dict()["case_names_used_for_direction_inference"] is False


def test_eccentric_direction_flags_bind_to_parent_axis_but_are_preserved():
    result = bind_etabs_seismic_action_directions(
        (_source("A", "PXE"), _source("B", "PYM")),
        _evidence(_row("PXE", xp=True), _row("PYM", ym=True)),
    )
    assert result.status == "PROVEN_ETABS_SEISMIC_DIRECTION_BINDING"
    assert result.bindings[0].direction == "X"
    assert result.bindings[0].selected_flag_names == ("XDirPlusE",)
    assert result.bindings[1].direction == "Y"
    assert result.bindings[1].selected_flag_names == ("YDirMinusE",)


def test_missing_or_ambiguous_direction_evidence_blocks_fail_closed():
    missing = bind_etabs_seismic_action_directions(
        (_source("A", "PX"), _source("B", "PY")),
        _evidence(_row("PX", x=True)),
    )
    assert missing.status == "BLOCKED_ETABS_SEISMIC_DIRECTION_MISSING_PATTERN_ROW"
    assert missing.missing_pattern_names == ("PY",)

    ambiguous = bind_etabs_seismic_action_directions(
        (_source("A", "PX"), _source("B", "PY")),
        _evidence(_row("PX", x=True, y=True), _row("PY", y=True)),
    )
    assert ambiguous.status == "BLOCKED_ETABS_SEISMIC_DIRECTION_AMBIGUOUS_FLAGS"
    assert ambiguous.ambiguous_pattern_names == ("PX",)


def test_duplicate_rows_and_noncanonical_names_fail_closed():
    with pytest.raises(EtabsAutoSeismicDirectionProviderError, match="canonical"):
        EtabsAutoSeismicDirectionRow(
            pattern_name=" PX ",
            flags={
                "XDir": True,
                "XDirPlusE": False,
                "XDirMinusE": False,
                "YDir": False,
                "YDirPlusE": False,
                "YDirMinusE": False,
            },
            raw_row={"Name": " PX "},
        )


def test_binding_requires_both_horizontal_axes_for_complete_resolution():
    result = bind_etabs_seismic_action_directions(
        (_source("A", "P1"), _source("B", "P2")),
        _evidence(_row("P1", x=True), _row("P2", x=True)),
    )
    assert result.status == "BLOCKED_ETABS_SEISMIC_DIRECTION_INCOMPLETE_AXES"
