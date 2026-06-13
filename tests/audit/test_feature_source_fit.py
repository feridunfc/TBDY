from tbdy_engine.audit.etabs_table_fit import EtabsTableFitAuditor
from tbdy_engine.audit.models import AuditStatus
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.providers.fake_etabs import FakeEtabsProvider


def _auditor(tables):
    return EtabsTableFitAuditor.from_provider(load_contracts(), FakeEtabsProvider(tables=tables))


def test_feature_source_fit_resolvable_when_table_and_field_alias_exist():
    auditor = _auditor({
        "Frame Section Property Definitions - Concrete Rectangular": [{"SectionName": "B40x70", "Depth": 0.7, "Width": 0.4}],
    })
    reports = {r.feature_name: r for r in auditor.feature_source_fit()}
    assert reports["beam_width_mm"].status == AuditStatus.RESOLVABLE
    assert reports["beam_width_mm"].matched_column == "Width"
    assert reports["beam_width_mm"].source_kind == "etabs_table"


def test_feature_source_fit_missing_when_table_missing():
    reports = {r.feature_name: r for r in _auditor({}).feature_source_fit()}
    assert reports["beam_width_mm"].status == AuditStatus.MISSING
    assert reports["beam_width_mm"].table_key == "frame_section_properties"


def test_feature_source_fit_partial_when_column_missing():
    auditor = _auditor({"Frame Section Property Definitions - Concrete Rectangular": [{"SectionName": "B40x70", "Depth": 0.7}]})
    reports = {r.feature_name: r for r in auditor.feature_source_fit()}
    assert reports["beam_width_mm"].status == AuditStatus.PARTIAL
    assert "Width" in reports["beam_width_mm"].missing_columns


def test_computed_feature_reports_custom_resolver_and_required_inputs():
    reports = {r.feature_name: r for r in _auditor({}).feature_source_fit()}
    report = reports["beam_As_top_engine_selected_mm2"]
    assert report.source_kind == "computed"
    assert report.status == AuditStatus.RESOLVABLE
    assert report.custom_resolver
    assert report.unit == "mm2"
    assert isinstance(report.required_inputs, tuple)


def test_missing_required_sources_report_lists_tables_and_columns():
    report = _auditor({"Frame Section Property Definitions - Concrete Rectangular": [{"SectionName": "B40x70", "Depth": 0.7}]}).missing_required_sources()
    payload = report.as_dict()
    assert any(item["feature_name"] == "beam_label" for item in payload["missing_tables"])
    assert any(item["feature_name"] == "beam_width_mm" for item in payload["missing_columns"])
