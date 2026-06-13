from tbdy_engine.audit.etabs_table_fit import EtabsTableFitAuditor
from tbdy_engine.audit.models import AuditStatus
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.providers.fake_etabs import FakeEtabsProvider


def test_combo_family_fit_maps_known_combo_names():
    provider = FakeEtabsProvider(tables={
        "Element Forces - Beams": [
            {"UniqueName": "B1", "Output Case": "CAP_X_1", "P": 0, "V2": 1, "M3": 2},
        ]
    })
    reports = EtabsTableFitAuditor.from_provider(load_contracts(), provider).combo_family_fit()
    assert reports
    assert reports[0].matched_combo_family == "CAPACITY_X"
    assert reports[0].status == AuditStatus.MATCHED


def test_unknown_combo_produces_diagnostic():
    provider = FakeEtabsProvider(tables={"Element Forces - Beams": [{"Output Case": "MYSTERY_CASE"}]})
    reports = EtabsTableFitAuditor.from_provider(load_contracts(), provider).combo_family_fit()
    assert reports[0].status == AuditStatus.UNKNOWN
    assert reports[0].diagnostics


def test_displacement_combo_used_for_reinforcement_source_is_forbidden():
    provider = FakeEtabsProvider(tables={
        "Concrete Beam Design Summary": [{"Frame": "B1", "Story": "S1", "Station": 0, "TopArea": 10, "BotArea": 10, "DesignCombo": "DISP_X_1"}]
    })
    reports = EtabsTableFitAuditor.from_provider(load_contracts(), provider).combo_family_fit()
    assert reports
    assert reports[0].matched_combo_family == "DISP_X"
    assert reports[0].status == AuditStatus.FORBIDDEN_FOR_PURPOSE
