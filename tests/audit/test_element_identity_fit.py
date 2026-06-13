from tbdy_engine.audit.etabs_table_fit import EtabsTableFitAuditor
from tbdy_engine.audit.models import AuditStatus
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.providers.fake_etabs import FakeEtabsProvider


def test_element_identity_fit_maps_common_identity_columns():
    provider = FakeEtabsProvider(tables={
        "Frame Assignments - Summary": [{"UniqueName": "B1", "Label": "B1", "Story": "S1", "Section": "B40x70"}],
        "Pier Forces": [{"Pier": "P1", "Story": "S1", "Output Case": "EX"}],
    })
    reports = {r.element_type: r for r in EtabsTableFitAuditor.from_provider(load_contracts(), provider).element_identity_fit()}
    assert reports["beam"].status == AuditStatus.MATCHED
    assert reports["beam"].identity_mapping["story"] == "Story"
    assert reports["beam"].identity_mapping["section"] == "Section"


def test_missing_identity_field_produces_partial_or_missing():
    provider = FakeEtabsProvider(tables={"Frame Assignments - Summary": [{"Story": "S1"}]})
    reports = {r.element_type: r for r in EtabsTableFitAuditor.from_provider(load_contracts(), provider).element_identity_fit()}
    assert reports["beam"].status in {AuditStatus.PARTIAL, AuditStatus.MISSING}
    assert reports["beam"].diagnostics


def test_coverage_expected_source_remains_present_for_missing_feature():
    auditor = EtabsTableFitAuditor.from_provider(load_contracts(), FakeEtabsProvider(tables={}))
    source = auditor.coverage_expected_source_for_feature("beam_width_mm")
    assert source.source_kind.value == "etabs_table"
    assert source.table_key == "frame_section_properties"
    assert source.field_aliases
