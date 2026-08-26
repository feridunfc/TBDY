from types import SimpleNamespace

import pytest

import tbdy_engine.features.column_design_rebar_evidence as evidence_module
from tbdy_engine.features.column_design_rebar_evidence import (
    ColumnDesignRebarEvidenceError,
    ColumnDesignRebarIdentity,
    STATUS_BLOCKED,
    STATUS_NO_DATA,
    build_column_design_rebar_evidence,
    capture_live_column_design_rebar_evidence,
    resolve_etabs_required_rebar,
)
from tbdy_engine.regulatory.units import UNIT_M, UNIT_MM

IDENTITY = ColumnDesignRebarIdentity(component_id="+0.00:C2:236", story="+0.00", object_name="C2", label="C2", unique_name="236", section_identity="C80x80")


def _row(*, area=7000.0, location=0.0, option=2, combo="ULS_1", ratio=0.0, frame="C2"):
    return {"FrameName": frame, "MyOption": option, "Location": location, "PMMCombo": combo, "PMMArea": area, "PMMRatio": ratio, "ErrorSummary": "", "WarningSummary": ""}


def _bundle(rows, *, unit=UNIT_MM, model="model:1"):
    return build_column_design_rebar_evidence(model_fingerprint=model, identity=IDENTITY, rows=rows, source_length_unit=unit, unit_provenance_refs=("CSI:GetPresentUnits_2",))


def _resolve(bundle, *, model="model:1", component=IDENTITY.component_id, section=IDENTITY.section_identity):
    return resolve_etabs_required_rebar(bundle, expected_model_fingerprint=model, expected_component_id=component, expected_section_identity=section)


def test_exact_identity_population_and_max_required_area_are_preserved():
    bundle = _bundle((_row(area=6800.0), _row(area=7200.0, location=4.45, combo="ULS_7")))
    result = _resolve(bundle)
    assert len(bundle.rows) == 2
    assert result.authority == "ETABS_REQUIRED_REBAR"
    assert result.required_as_mm2 == pytest.approx(7200.0)
    assert result.governing_combinations == ("ULS_7",)
    assert len(result.governing_source_row_ids) == 1


def test_source_length_unit_is_explicitly_squared_for_area_conversion():
    result = _resolve(_bundle((_row(area=0.0072, location=4.45),), unit=UNIT_M))
    assert result.required_as_mm2 == pytest.approx(7200.0)
    assert result.governing_locations_mm == pytest.approx((4450.0,))


def test_check_ratio_and_check_rows_never_become_required_rebar_authority():
    a = _resolve(_bundle((_row(area=7000.0, ratio=0.01), _row(area=999999.0, option=1, ratio=9.9))))
    b = _resolve(_bundle((_row(area=7000.0, ratio=999.0), _row(area=1.0, option=1, ratio=0.1))))
    assert a.required_as_mm2 == b.required_as_mm2 == pytest.approx(7000.0)
    assert a.authority == b.authority == "ETABS_REQUIRED_REBAR"


def test_missing_design_population_fails_closed_as_no_data():
    result = _resolve(_bundle((_row(area=1.0, option=1, ratio=0.5),)))
    assert result.status == STATUS_NO_DATA
    assert not result.resolved


@pytest.mark.parametrize(("model", "component", "section"), [("other", IDENTITY.component_id, IDENTITY.section_identity), ("model:1", "other", IDENTITY.section_identity), ("model:1", IDENTITY.component_id, "other")])
def test_stale_or_identity_mismatch_fails_closed(model, component, section):
    result = _resolve(_bundle((_row(),)), model=model, component=component, section=section)
    assert result.status == STATUS_BLOCKED
    assert result.authority == "NOT_SELECTED"


def test_epoch_is_deterministic_and_population_order_independent():
    a = _row(area=6800.0)
    b = _row(area=7200.0, location=4.45, combo="ULS_7")
    assert _bundle((a, b)).evidence_epoch_id == _bundle((b, a)).evidence_epoch_id


def test_direct_api_capture_preserves_present_units_without_mutation(monkeypatch):
    snapshots = [SimpleNamespace(present_units_api="GetPresentUnits_2", present_units=8, present_force_unit=4, present_length_unit=6, present_temperature_unit=2), SimpleNamespace(present_units_api="GetPresentUnits_2", present_units=8, present_force_unit=4, present_length_unit=6, present_temperature_unit=2)]
    monkeypatch.setattr(evidence_module, "read_etabs_unit_snapshot", lambda sap: snapshots.pop(0))
    class DesignConcrete:
        def GetSummaryResultsColumn(self, name):
            assert name == "C2"
            return (2, ["C2", "C2"], [2, 2], [0.0, 4.45], ["ULS_1", "ULS_7"], [0.0068, 0.0072], [0.0, 0.0], ["", ""], [0.0, 0.0], ["", ""], [0.0, 0.0], ["", ""], ["", ""], 0)
    bundle = capture_live_column_design_rebar_evidence(sap_model=SimpleNamespace(DesignConcrete=DesignConcrete()), model_fingerprint="model:1", identity=IDENTITY)
    assert bundle.source_length_unit == UNIT_M
    assert _resolve(bundle).required_as_mm2 == pytest.approx(7200.0)
    assert "present_length_unit=m" in bundle.unit_provenance_refs


def test_direct_api_capture_rejects_unresolved_source_unit(monkeypatch):
    snapshot = SimpleNamespace(present_units_api="GetPresentUnits_2", present_units=99, present_force_unit=99, present_length_unit=99, present_temperature_unit=2)
    monkeypatch.setattr(evidence_module, "read_etabs_unit_snapshot", lambda sap: snapshot)
    with pytest.raises(Exception, match="present length unit"):
        capture_live_column_design_rebar_evidence(sap_model=SimpleNamespace(DesignConcrete=object()), model_fingerprint="model:1", identity=IDENTITY)


def test_wrong_frame_identity_is_rejected_before_resolution():
    with pytest.raises(ColumnDesignRebarEvidenceError, match="FrameName"):
        _bundle((_row(frame="OTHER"),))
