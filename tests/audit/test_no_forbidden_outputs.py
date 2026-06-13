import inspect

from tbdy_engine.audit import EtabsTableFitAuditor
from tbdy_engine.audit.models import EtabsTableInventory
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.providers.fake_etabs import FakeEtabsProvider


def test_audit_models_reject_checkresult_ok_fail_and_pass_rule():
    for bad in ["CheckResult", "'OK'", "'FAIL'", "pass_rule"]:
        try:
            EtabsTableInventory(
                actual_table_name=bad,
                canonical_table_key=None,
                matched_by="none",
                available_columns=(),
                row_count=0,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"forbidden payload accepted: {bad}")


def test_audit_output_has_no_forbidden_decision_payloads():
    auditor = EtabsTableFitAuditor.from_provider(load_contracts(), FakeEtabsProvider(tables={"Unmatched Table": [{"Column": 1}]}))
    text = repr([row.as_dict() for row in auditor.table_inventory()])
    assert "CheckResult" not in text
    assert "'OK'" not in text and '"OK"' not in text
    assert "'FAIL'" not in text and '"FAIL"' not in text
    assert "pass_rule" not in text


def test_audit_modules_do_not_import_forbidden_runtime_paths():
    import tbdy_engine.audit.etabs_table_fit as module

    source = inspect.getsource(module)
    forbidden = ["CheckEngine", "runner_v2", "runtime", "archx"]
    assert not any(token in source for token in forbidden)
