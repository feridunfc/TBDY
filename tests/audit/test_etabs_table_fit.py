from tbdy_engine.audit.etabs_table_fit import EtabsTableFitAuditor
from tbdy_engine.audit.models import AuditStatus
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.providers.fake_etabs import FakeEtabsProvider


def test_provider_table_inventory_lists_actual_tables_and_columns():
    provider = FakeEtabsProvider(tables={
        "Frame Assignments - Summary": [{"Frame": "B1", "Story": "S1", "Section": "B40x70"}],
        "Unmatched ETABS Table": [{"SomeColumn": 1}],
    })
    auditor = EtabsTableFitAuditor.from_provider(load_contracts(), provider)
    inventory = {row.actual_table_name: row for row in auditor.table_inventory()}
    assert inventory["Frame Assignments - Summary"].canonical_table_key == "frame_assignments"
    assert inventory["Frame Assignments - Summary"].matched_by == "alias"
    assert "Frame" in inventory["Frame Assignments - Summary"].available_columns
    assert inventory["Unmatched ETABS Table"].matched_by == "none"


def test_table_registry_missing_table_produces_missing_fit():
    provider = FakeEtabsProvider(tables={})
    reports = {r.table_key: r for r in EtabsTableFitAuditor.from_provider(load_contracts(), provider).table_contract_fit()}
    assert reports["frame_assignments"].status == AuditStatus.MISSING
    assert reports["frame_assignments"].missing_columns


def test_required_column_aliases_are_matched_and_missing_column_is_partial():
    provider = FakeEtabsProvider(tables={
        "Frame Section Property Definitions - Concrete Rectangular": [{"SectionName": "B40x70", "Depth": 0.7, "Width": 0.4}],
        "Frame Assignments - Summary": [{"Frame": "B1", "Story": "S1"}],
    })
    reports = {r.table_key: r for r in EtabsTableFitAuditor.from_provider(load_contracts(), provider).table_contract_fit()}
    assert reports["frame_section_properties"].status == AuditStatus.MATCHED
    assert set(reports["frame_section_properties"].matched_columns) >= {"SectionName", "Depth", "Width"}
    assert reports["frame_assignments"].status == AuditStatus.PARTIAL
    assert "DesignSect" in reports["frame_assignments"].missing_columns


def test_table_headers_report_lists_headers_and_samples_and_writes_file(tmp_path):
    provider = FakeEtabsProvider(tables={
        "Frame Assignments - Summary": [
            {"Frame": "B1", "Story": "S1", "Section": "B40x70"},
        ]
    })
    auditor = EtabsTableFitAuditor.from_provider(load_contracts(), provider)
    headers = {r.actual_table_name: r for r in auditor.table_headers_report()}
    assert headers["Frame Assignments - Summary"].available_columns == ("Frame", "Story", "Section")
    assert headers["Frame Assignments - Summary"].sample_rows[0]["Frame"] == "B1"
    auditor.write_deep_fit_reports(tmp_path)
    assert (tmp_path / "table_headers_report.json").exists()
