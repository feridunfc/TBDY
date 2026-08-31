from __future__ import annotations

from dataclasses import dataclass

import pytest

import etabs_gateway.connection as gateway_connection

from tbdy_engine.engine.unit_context import attach_unit_context
from tbdy_engine.etabs.safety import (
    AnalysisReadiness,
    CapabilityState,
    DatabaseTablesReadTransaction,
    EtabsCapabilityError,
    EtabsIdentityMismatchError,
    EtabsSafetyError,
    EtabsSafetyErrorCode,
    EtabsStateRestoreError,
    EtabsStateVerificationError,
    ResultsSetupReadTransaction,
    RuntimeCaptureStatus,
    _decode_database_selected_names,
    attach_verified_to_running_etabs,
    classify_capture_status,
    read_analysis_readiness,
    read_capability_snapshot,
    read_etabs_unit_snapshot,
)
from tbdy_engine.features.etabs_com_attach import (
    STRATEGY_COMTYPES_HELPER_GET_OBJECT_PROCESS,
    attach_to_running_etabs,
)
from tbdy_engine.providers.etabs_display_table_fetcher import (
    fetch_display_table,
    fetch_display_table_for_output,
    select_output_for_display,
)


class FakeAnalyze:
    def __init__(self, statuses=None):
        self.statuses = statuses or {"DEAD": 4, "MODAL": 1}

    def GetCaseStatus(self):
        names = list(self.statuses)
        values = [self.statuses[name] for name in names]
        return len(names), names, values, 0


class FakeSap:
    def __init__(self, model_path=r"C:\tmp\B-BLOK_Revised.EDB"):
        self.model_path = model_path
        self.set_present_units_calls = 0
        self.Analyze = FakeAnalyze()
        self.DatabaseTables = None
        self.Results = None
        self.LoadCases = None
        self.RespCombo = None

    def GetModelFilename(self, include_path=True):
        return self.model_path if include_path else self.model_path.rsplit("\\", 1)[-1]

    def GetModelFilepath(self):
        return self.model_path.rsplit("\\", 1)[0]

    def GetVersion(self):
        return "22.7.0", 22.7, 0

    def GetProgramInfo(self):
        return "ETABS", "22.7.0", "Ultimate", 0

    def GetModelIsLocked(self):
        return True

    def GetPresentUnits(self):
        return 6

    def GetDatabaseUnits(self):
        return 9

    def GetPresentUnits_2(self):
        return 3, 6, 2, 0

    def GetDatabaseUnits_2(self):
        return 4, 7, 2, 0

    def SetPresentUnits(self, value):
        self.set_present_units_calls += 1
        raise AssertionError("canonical acquisition must not call SetPresentUnits")


class FakeEtabsObject:
    def __init__(self, sap):
        self.SapModel = sap

    def GetOAPIVersionNumber(self):
        return 2.3


class FakeHelper:
    def __init__(self, process_object):
        self.process_object = process_object
        self.process_calls = []
        self.get_object_calls = []

    def GetObjectProcess(self, prog_id, pid):
        self.process_calls.append((prog_id, pid))
        return self.process_object

    def GetObject(self, prog_id):
        self.get_object_calls.append(prog_id)
        return self.process_object


class FailingProcessHelper(FakeHelper):
    def GetObjectProcess(self, prog_id, pid):
        self.process_calls.append((prog_id, pid))
        raise RuntimeError(f"PID {pid} not attachable")


class UnsupportedProcessHelper:
    def __init__(self, process_object):
        self.process_object = process_object
        self.get_object_calls = []

    def GetObject(self, prog_id):
        self.get_object_calls.append(prog_id)
        return self.process_object


class FakeComtypesClient:
    def __init__(self, etabs_object, *, helper=None):
        self.etabs_object = etabs_object
        self.helper = helper or FakeHelper(etabs_object)
        self.active_calls = []
        self.create_calls = []

    def CreateObject(self, prog_id):
        self.create_calls.append(prog_id)
        return self.helper

    def GetActiveObject(self, prog_id):
        self.active_calls.append(prog_id)
        return self.etabs_object


class FailingWin32:
    def GetActiveObject(self, prog_id):
        raise RuntimeError(prog_id)


class FailingComtypesClient:
    def __init__(self):
        self.active_calls = []
        self.create_calls = []

    def GetActiveObject(self, prog_id):
        self.active_calls.append(prog_id)
        raise RuntimeError("fake active-object failure")

    def CreateObject(self, prog_id):
        self.create_calls.append(prog_id)
        raise RuntimeError("fake helper failure")


class WouldSucceedWin32:
    def __init__(self, etabs_object):
        self.etabs_object = etabs_object
        self.calls = []

    def GetActiveObject(self, prog_id):
        self.calls.append(prog_id)
        return self.etabs_object


def test_exact_target_identity_accepted():
    sap = FakeSap()
    client = FakeComtypesClient(FakeEtabsObject(sap))
    session = attach_verified_to_running_etabs(
        r"C:\tmp\B-BLOK_Revised.EDB",
        comtypes_client=client,
        win32com_client=FailingWin32(),
    )
    assert session.identity.model_full_path == r"C:\tmp\B-BLOK_Revised.EDB"
    assert session.identity.model_locked is True
    assert session.identity.program_version == "22.7.0"
    session.close()


def test_wrong_model_is_hard_failure_with_stable_code():
    sap = FakeSap(r"C:\tmp\WRONG.EDB")
    client = FakeComtypesClient(FakeEtabsObject(sap))
    with pytest.raises(EtabsIdentityMismatchError) as caught:
        attach_verified_to_running_etabs(
            r"C:\tmp\B-BLOK_Revised.EDB",
            comtypes_client=client,
            win32com_client=FailingWin32(),
        )
    assert caught.value.code is EtabsSafetyErrorCode.ATTACHED_MODEL_MISMATCH




def test_fake_compatibility_attach_cannot_fall_through_to_real_win32(
    monkeypatch: pytest.MonkeyPatch,
):
    sap = FakeSap()
    fake_client = FakeComtypesClient(FakeEtabsObject(sap))
    real_runtime = WouldSucceedWin32(FakeEtabsObject(FakeSap(r"C:\\tmp\\REAL.EDB")))
    real_loader_hits = []

    def load_real_win32():
        real_loader_hits.append("win32com.client")
        return real_runtime

    monkeypatch.setattr(gateway_connection, "_load_win32com_client", load_real_win32)

    result = attach_to_running_etabs(comtypes_client=fake_client)

    assert result.status == "ATTACHED"
    assert result.strategy == "comtypes_get_active_object_etabs_api_object"
    assert fake_client.active_calls == ["CSI.ETABS.API.ETABSObject"]
    assert real_loader_hits == []
    assert real_runtime.calls == []


def test_fake_compatibility_attach_failure_has_no_real_win32_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_client = FailingComtypesClient()
    real_runtime = WouldSucceedWin32(FakeEtabsObject(FakeSap(r"C:\\tmp\\REAL.EDB")))
    real_loader_hits = []

    def load_real_win32():
        real_loader_hits.append("win32com.client")
        return real_runtime

    monkeypatch.setattr(gateway_connection, "_load_win32com_client", load_real_win32)

    result = attach_to_running_etabs(comtypes_client=fake_client)

    assert result.status == "FAILED"
    assert result.strategy is None
    assert real_loader_hits == []
    assert real_runtime.calls == []


def test_pid_attach_is_preferred_when_requested():
    sap = FakeSap()
    etabs = FakeEtabsObject(sap)
    helper = FakeHelper(etabs)
    client = FakeComtypesClient(etabs, helper=helper)
    result = attach_to_running_etabs(
        pid=4321,
        allow_pid_fallback=False,
        comtypes_client=client,
        win32com_client=FailingWin32(),
    )
    assert result.strategy == STRATEGY_COMTYPES_HELPER_GET_OBJECT_PROCESS
    assert helper.process_calls[0][1] == 4321
    assert client.active_calls == []


def test_pid_verified_session_records_pid_only_for_exact_process_strategy():
    sap = FakeSap()
    etabs = FakeEtabsObject(sap)
    client = FakeComtypesClient(etabs)
    session = attach_verified_to_running_etabs(
        r"C:\tmp\B-BLOK_Revised.EDB",
        pid=77,
        comtypes_client=client,
        win32com_client=FailingWin32(),
    )
    assert session.identity.process_id == 77
    assert session.capabilities.pid_attach is CapabilityState.SUPPORTED
    session.close()


def test_callable_pid_failure_is_hard_failure_without_generic_fallback():
    sap = FakeSap()
    etabs = FakeEtabsObject(sap)
    helper = FailingProcessHelper(etabs)
    client = FakeComtypesClient(etabs, helper=helper)

    with pytest.raises(EtabsSafetyError) as caught:
        attach_verified_to_running_etabs(
            r"C:\tmp\B-BLOK_Revised.EDB",
            pid=991,
            comtypes_client=client,
            win32com_client=FailingWin32(),
        )

    assert caught.value.code is EtabsSafetyErrorCode.PID_ATTACH_FAILED
    assert client.active_calls == []


def test_callable_pid_failure_fallback_requires_explicit_opt_in_and_verifies_target():
    sap = FakeSap()
    etabs = FakeEtabsObject(sap)
    helper = FailingProcessHelper(etabs)
    client = FakeComtypesClient(etabs, helper=helper)

    session = attach_verified_to_running_etabs(
        r"C:\tmp\B-BLOK_Revised.EDB",
        pid=991,
        allow_pid_fallback=True,
        comtypes_client=client,
        win32com_client=FailingWin32(),
    )

    assert session.identity.process_id is None
    assert client.active_calls
    assert session.diagnostics[0]["code"] == EtabsSafetyErrorCode.PID_ATTACH_FAILED.value
    assert session.diagnostics[0]["compatibility_opt_in"] is True
    session.close()


def test_unsupported_pid_api_may_use_bounded_verified_fallback():
    sap = FakeSap()
    etabs = FakeEtabsObject(sap)
    helper = UnsupportedProcessHelper(etabs)
    client = FakeComtypesClient(etabs, helper=helper)

    session = attach_verified_to_running_etabs(
        r"C:\tmp\B-BLOK_Revised.EDB",
        pid=992,
        comtypes_client=client,
        win32com_client=FailingWin32(),
    )

    assert session.identity.process_id is None
    assert session.capabilities.pid_attach is CapabilityState.UNSUPPORTED
    assert session.diagnostics[0]["code"] == EtabsSafetyErrorCode.PID_ATTACH_UNSUPPORTED.value
    session.close()


def test_pid_fallback_still_rejects_wrong_model():
    sap = FakeSap(r"C:\tmp\WRONG.EDB")
    etabs = FakeEtabsObject(sap)
    helper = UnsupportedProcessHelper(etabs)
    client = FakeComtypesClient(etabs, helper=helper)
    with pytest.raises(EtabsIdentityMismatchError) as caught:
        attach_verified_to_running_etabs(
            r"C:\tmp\B-BLOK_Revised.EDB",
            pid=993,
            comtypes_client=client,
            win32com_client=FailingWin32(),
        )
    assert caught.value.code is EtabsSafetyErrorCode.ATTACHED_MODEL_MISMATCH


def test_fallback_attach_is_identity_verified():
    sap = FakeSap()
    client = FakeComtypesClient(FakeEtabsObject(sap))
    session = attach_verified_to_running_etabs(
        r"c:\TMP\B-BLOK_Revised.EDB",
        comtypes_client=client,
        win32com_client=FailingWin32(),
    )
    assert session.identity.process_id is None
    assert session.identity.model_full_path.lower().endswith("b-blok_revised.edb")
    session.close()


def test_present_units_are_never_changed_by_canonical_unit_read():
    sap = FakeSap()
    units = read_etabs_unit_snapshot(sap)
    assert sap.set_present_units_calls == 0
    assert units.present_units == 6
    assert units.database_units == 9
    assert units.present_force_unit == 3
    assert units.database_force_unit == 4


def test_missing_unit_provenance_has_stable_diagnostic_code():
    class NoUnits:
        pass

    units = read_etabs_unit_snapshot(NoUnits())
    assert units.present_units_api is None
    assert units.database_units_api is None
    assert {
        item["error_code"] for item in units.diagnostics
    } == {EtabsSafetyErrorCode.UNIT_PROVENANCE_UNAVAILABLE.value}


@dataclass
class FakeContext:
    design_basis: dict
    unit_system: dict | None = None


def test_attach_unit_context_is_read_only_by_default():
    sap = FakeSap()
    ctx = FakeContext(design_basis={})
    attach_unit_context(ctx, sap)
    assert sap.set_present_units_calls == 0
    assert ctx.unit_system["set_present_units_attempted"] is False
    assert ctx.unit_system["etabs_unit_provenance"]["present_units"] == 6
    assert ctx.unit_system["etabs_unit_provenance"]["database_units"] == 9


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (1, AnalysisReadiness.ANALYSIS_NOT_RUN),
        (2, AnalysisReadiness.ANALYSIS_COULD_NOT_START),
        (3, AnalysisReadiness.ANALYSIS_INCOMPLETE),
        (4, AnalysisReadiness.ANALYSIS_FINISHED),
    ],
)
def test_analysis_status_mapping_is_factual(code, expected):
    sap = FakeSap()
    sap.Analyze = FakeAnalyze({"CASE": code})
    status = read_analysis_readiness(sap, "CASE")
    assert status.readiness is expected
    assert status.error_code is None
    assert "CURRENT" not in status.readiness.value


def test_unknown_analysis_status_exposes_stable_code():
    sap = FakeSap()
    sap.Analyze = FakeAnalyze({"CASE": 99})
    status = read_analysis_readiness(sap, "CASE")
    assert status.readiness is AnalysisReadiness.ANALYSIS_UNKNOWN
    assert status.error_code is EtabsSafetyErrorCode.ANALYSIS_STATUS_UNKNOWN


def test_incomplete_database_selection_capability_fails_before_mutation():
    class IncompleteDB:
        def __init__(self):
            self.setter_calls = 0

        def SetLoadCasesSelectedForDisplay(self, names):
            self.setter_calls += 1
            return 0

        def SetLoadCombinationsSelectedForDisplay(self, names):
            self.setter_calls += 1
            return 0

    db = IncompleteDB()
    with pytest.raises(EtabsCapabilityError) as caught:
        with DatabaseTablesReadTransaction(db):
            pass
    assert caught.value.code is EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED
    assert db.setter_calls == 0


class FakeDatabaseTables:
    def __init__(self):
        self.cases = ["OLD_CASE"]
        self.combos = ["OLD_COMBO"]
        self.patterns = ["DEAD"]
        self.fail_combo_target = True
        self.fail_restore_combo = False
        self.table_call_arg_counts = []
        self.selection_seen_by_fetch = []
        self.case_set_calls = []
        self.combo_set_calls = []

    def GetLoadCasesSelectedForDisplay(self):
        return len(self.cases), list(self.cases), 0

    def SetLoadCasesSelectedForDisplay(self, names):
        names = list(names)
        self.case_set_calls.append(tuple(names))
        self.cases = names
        return 0

    def GetLoadCombinationsSelectedForDisplay(self):
        return len(self.combos), list(self.combos), 0

    def SetLoadCombinationsSelectedForDisplay(self, names):
        names = list(names)
        self.combo_set_calls.append(tuple(names))
        if self.fail_restore_combo and names == ["OLD_COMBO"]:
            return 1
        if self.fail_combo_target and names not in ([], ["OLD_COMBO"]):
            return 1
        self.combos = names
        return 0

    def GetLoadPatternsSelectedForDisplay(self):
        return len(self.patterns), list(self.patterns), 0

    def SetLoadPatternsSelectedForDisplay(self, names):
        self.patterns = list(names)
        return 0

    def GetOutputOptionsForDisplay(self):
        return False, 0.0, 0.0, 0.0, True, 1, 12, True, 1, 12, 2, 2, 2, 2, 2, 0

    def SetOutputOptionsForDisplay(self, *args):
        return 0

    def GetTableForDisplayArray(self, *args):
        self.selection_seen_by_fetch.append((tuple(self.cases), tuple(self.combos)))
        self.table_call_arg_counts.append(len(args))
        if len(args) != 3:
            raise TypeError("fake supports only legacy 3-arg shape")
        return {
            "return_code": 0,
            "field_keys": ["Story", "OutputCase"],
            "number_records": 1,
            "table_data": ["L1", "CASE_X"],
        }


class FakeEtabs23PaddedDatabaseTables(FakeDatabaseTables):
    """Reproduce ETABS 23.2 count + old-capacity SAFEARRAY padding."""

    def __init__(self):
        super().__init__()
        self.cases = [
            "Modal", "RSX", "RSY", "LC_DL", "LC_SDL", "LC_WDL", "LC_LL", "LC_DDL",
            "LC_S", "LC_T", "LC_H", "LC_HE", "LC_EQX", "LC_EQY", "EDZ", "~ChineseX",
            "~ChineseY", "~StaticRSX", "~Static+EccRSX", "~Static-EccRSX", "~StaticRSY",
            "~Static+EccRSY", "~Static-EccRSY",
        ]
        self.combos = ["ENV_GRAV", "ENV_UNC", "ENV_CRK", "ENV_D"]
        self.case_capacity = len(self.cases)
        self.combo_capacity = len(self.combos)
        self.original_combos = tuple(self.combos)

    @staticmethod
    def _padded(names, capacity):
        payload = tuple(list(names) + [None] * (capacity - len(names)))
        return [len(names), payload, 0]

    def GetLoadCasesSelectedForDisplay(self):
        return self._padded(self.cases, self.case_capacity)

    def SetLoadCasesSelectedForDisplay(self, names):
        names = list(names)
        self.case_set_calls.append(tuple(names))
        self.cases = names
        return [tuple(names), 0]

    def GetLoadCombinationsSelectedForDisplay(self):
        return self._padded(self.combos, self.combo_capacity)

    def SetLoadCombinationsSelectedForDisplay(self, names):
        names = list(names)
        self.combo_set_calls.append(tuple(names))
        if self.fail_combo_target and names != list(self.original_combos):
            return [tuple(names), 1]
        self.combos = names
        return [tuple(names), 0]


def test_count_aware_getter_decodes_only_authoritative_prefix():
    raw = [1, ("LC_DL", None, None, None), 0]
    assert _decode_database_selected_names(
        raw,
        "GetLoadCasesSelectedForDisplay",
        error_code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
    ) == ("LC_DL",)


def test_count_aware_getter_ignores_none_padding_after_count():
    raw = [2, ("ENV_GRAV", "ENV_UNC", None, None, None), 0]
    assert _decode_database_selected_names(
        raw,
        "GetLoadCombinationsSelectedForDisplay",
        error_code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
    ) == ("ENV_GRAV", "ENV_UNC")


def test_count_aware_getter_nonzero_return_fails_closed():
    with pytest.raises(EtabsCapabilityError) as caught:
        _decode_database_selected_names(
            [0, (None, None), 1],
            "GetLoadCasesSelectedForDisplay",
            error_code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
        )
    assert caught.value.code is EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED
    assert caught.value.details["api_return_code"] == 1


def test_count_aware_getter_count_greater_than_payload_fails_closed():
    with pytest.raises(EtabsCapabilityError) as caught:
        _decode_database_selected_names(
            [2, ("LC_DL",), 0],
            "GetLoadCasesSelectedForDisplay",
            error_code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
        )
    assert caught.value.code is EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED


def test_count_aware_getter_requires_integer_count():
    with pytest.raises(EtabsCapabilityError) as caught:
        _decode_database_selected_names(
            [1.0, ("LC_DL",), 0],
            "GetLoadCasesSelectedForDisplay",
            error_code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
        )
    assert caught.value.code is EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED


def test_count_aware_getter_non_string_inside_authoritative_prefix_fails_closed():
    with pytest.raises(EtabsCapabilityError) as caught:
        _decode_database_selected_names(
            [2, ("LC_DL", None, "IGNORED_TAIL"), 0],
            "GetLoadCasesSelectedForDisplay",
            error_code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
        )
    assert caught.value.code is EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED


def test_live_padded_singleton_case_shape_verifies_exactly_and_preserves_combos():
    db = FakeEtabs23PaddedDatabaseTables()
    original_cases = tuple(db.cases)
    original_combos = tuple(db.combos)
    db.fail_combo_target = True
    with DatabaseTablesReadTransaction(db) as tx:
        selected = tx.select_output("LC_DL")
        assert tuple(db.cases) == ("LC_DL",)
        assert tuple(db.combos) == original_combos
        assert db.GetLoadCasesSelectedForDisplay()[1][1] is None
        assert selected["target_kind"] == "case"
        assert selected["target_name"] == "LC_DL"
        assert selected["temporary_cases_exact"] == ["LC_DL"]
        assert selected["temporary_combos_exact"] == list(original_combos)
        assert selected["opposite_domain_preserved"] is True
        assert selected["temporary_state_verified_exact"] is True
        assert selected["selection_scope"] == "VERIFIED_SUPERSET_SELECTION"
        assert selected["target_only_capture_claimed"] is False
        case_diag = next(
            item for item in tx.diagnostics if item.get("phase") == "temporary_selection_case"
        )
        assert case_diag["temporary_cases_verified_exact"] is True
        assert case_diag["temporary_combos_verified_exact"] is True
    assert tuple(db.cases) == original_cases
    assert tuple(db.combos) == original_combos


def test_live_padded_singleton_combo_shape_verifies_exactly_and_preserves_cases():
    db = FakeEtabs23PaddedDatabaseTables()
    original_cases = tuple(db.cases)
    original_combos = tuple(db.combos)
    db.fail_combo_target = False
    with DatabaseTablesReadTransaction(db) as tx:
        selected = tx.select_output("ENV_GRAV")
        assert tuple(db.cases) == original_cases
        assert tuple(db.combos) == ("ENV_GRAV",)
        assert db.GetLoadCombinationsSelectedForDisplay()[1][1] is None
        assert selected["target_kind"] == "combo"
        assert selected["temporary_cases_exact"] == list(original_cases)
        assert selected["temporary_combos_exact"] == ["ENV_GRAV"]
        assert selected["opposite_domain_preserved"] is True
        combo_diag = next(
            item for item in tx.diagnostics if item.get("phase") == "temporary_selection_combo"
        )
        assert combo_diag["temporary_cases_verified_exact"] is True
        assert combo_diag["temporary_combos_verified_exact"] is True
    assert tuple(db.cases) == original_cases
    assert tuple(db.combos) == original_combos


def test_database_transaction_restores_state_on_success():
    db = FakeDatabaseTables()
    with DatabaseTablesReadTransaction(db) as tx:
        selected = tx.select_output("CASE_X")
        assert selected["display_selection_success"] is True
        assert selected["temporary_state_verified_exact"] is True
        assert db.cases == ["CASE_X"]
        assert db.combos == ["OLD_COMBO"]
    assert db.cases == ["OLD_CASE"]
    assert db.combos == ["OLD_COMBO"]


def test_database_transaction_restores_state_when_fetch_raises():
    db = FakeDatabaseTables()
    with pytest.raises(RuntimeError, match="fetch exploded"):
        with DatabaseTablesReadTransaction(db) as tx:
            tx.select_output("CASE_X")
            raise RuntimeError("fetch exploded")
    assert db.cases == ["OLD_CASE"]
    assert db.combos == ["OLD_COMBO"]


def test_restore_failure_invalidates_acquisition_with_stable_code():
    db = FakeDatabaseTables()
    db.fail_restore_combo = True
    with pytest.raises(EtabsStateRestoreError) as caught:
        with DatabaseTablesReadTransaction(db) as tx:
            tx.select_output("CASE_X")
    assert caught.value.code is EtabsSafetyErrorCode.STATE_RESTORE_FAILED


def test_restore_mismatch_remains_hard_failure():
    class RestoreMismatchDB(FakeDatabaseTables):
        def __init__(self):
            super().__init__()
            self.fail_combo_target = False

        def SetLoadCombinationsSelectedForDisplay(self, names):
            names = list(names)
            self.combo_set_calls.append(tuple(names))
            if names == ["OLD_COMBO"] and self.combos != ["OLD_COMBO"]:
                return 0
            self.combos = names
            return 0

    db = RestoreMismatchDB()
    with pytest.raises(EtabsStateRestoreError) as caught:
        with DatabaseTablesReadTransaction(db) as tx:
            tx.select_output("COMBO_X")
    assert caught.value.code is EtabsSafetyErrorCode.STATE_RESTORE_VERIFY_FAILED


def test_standalone_selection_fails_closed_without_mutation():
    db = FakeDatabaseTables()
    diagnostic = select_output_for_display(db, "CASE_X")
    assert diagnostic["display_selection_success"] is False
    assert diagnostic["display_selection_attempted"] is False
    assert db.cases == ["OLD_CASE"]
    assert db.combos == ["OLD_COMBO"]


def test_case_fetch_preserves_snapshot_combos_as_verified_superset():
    db = FakeDatabaseTables()
    result = fetch_display_table_for_output(
        db,
        "Story Drifts",
        preferred_output_case="CASE_X",
    )
    assert db.selection_seen_by_fetch
    assert set(db.selection_seen_by_fetch) == {(("CASE_X",), ("OLD_COMBO",))}
    assert result.display_selection["temporary_cases_exact"] == ["CASE_X"]
    assert result.display_selection["temporary_combos_exact"] == ["OLD_COMBO"]
    assert result.display_selection["opposite_domain_preserved"] is True
    assert result.display_selection["selection_scope"] == "VERIFIED_SUPERSET_SELECTION"
    assert db.cases == ["OLD_CASE"]
    assert db.combos == ["OLD_COMBO"]


def test_combo_fetch_preserves_snapshot_cases_as_verified_superset():
    db = FakeDatabaseTables()
    db.fail_combo_target = False
    result = fetch_display_table_for_output(
        db,
        "Base Reactions",
        preferred_output_case="COMBO_X",
    )
    assert db.selection_seen_by_fetch
    assert set(db.selection_seen_by_fetch) == {(("OLD_CASE",), ("COMBO_X",))}
    assert result.display_selection["temporary_cases_exact"] == ["OLD_CASE"]
    assert result.display_selection["temporary_combos_exact"] == ["COMBO_X"]
    assert result.display_selection["opposite_domain_preserved"] is True
    assert db.cases == ["OLD_CASE"]
    assert db.combos == ["OLD_COMBO"]


def test_temporary_selection_verify_mismatch_fails_before_fetch_and_restores():
    class LyingDB(FakeDatabaseTables):
        def __init__(self):
            super().__init__()
            self.table_calls = 0

        def SetLoadCombinationsSelectedForDisplay(self, names):
            names = list(names)
            self.combo_set_calls.append(tuple(names))
            if names == ["OLD_COMBO"]:
                self.combos = names
                return 0
            return 0

        def SetLoadCasesSelectedForDisplay(self, names):
            names = list(names)
            self.case_set_calls.append(tuple(names))
            if names == ["OLD_CASE"]:
                self.cases = names
                return 0
            return 0

        def GetTableForDisplayArray(self, *args):
            self.table_calls += 1
            return super().GetTableForDisplayArray(*args)

    db = LyingDB()
    with pytest.raises(EtabsStateVerificationError) as caught:
        fetch_display_table_for_output(db, "Story Drifts", preferred_output_case="X")
    assert caught.value.code is EtabsSafetyErrorCode.TEMPORARY_STATE_VERIFY_FAILED
    assert db.table_calls == 0
    assert db.cases == ["OLD_CASE"]
    assert db.combos == ["OLD_COMBO"]


def test_opposite_domain_is_never_deliberately_cleared_in_normal_selection():
    case_db = FakeDatabaseTables()
    with DatabaseTablesReadTransaction(case_db) as tx:
        tx.select_output("CASE_X")
    assert () not in case_db.case_set_calls
    assert () not in case_db.combo_set_calls

    combo_db = FakeDatabaseTables()
    combo_db.fail_combo_target = False
    with DatabaseTablesReadTransaction(combo_db) as tx:
        tx.select_output("COMBO_X")
    assert () not in combo_db.case_set_calls
    assert () not in combo_db.combo_set_calls


def test_mixed_outputcase_full_table_is_not_filtered_by_acquisition():
    class MixedOutputCaseDB(FakeDatabaseTables):
        def __init__(self):
            super().__init__()
            self.fail_combo_target = False

        def GetTableForDisplayArray(self, *args):
            self.selection_seen_by_fetch.append((tuple(self.cases), tuple(self.combos)))
            self.table_call_arg_counts.append(len(args))
            if len(args) != 3:
                raise TypeError("fake supports only legacy 3-arg shape")
            return {
                "return_code": 0,
                "field_keys": ["OutputCase", "FX"],
                "number_records": 2,
                "table_data": ["OLD_CASE", "1.0", "COMBO_X", "2.0"],
            }

    db = MixedOutputCaseDB()
    result = fetch_display_table_for_output(
        db,
        "Base Reactions",
        preferred_output_case="COMBO_X",
    )
    assert result.capture_status is RuntimeCaptureStatus.FULL
    assert [row["OutputCase"] for row in result.parsed.rows] == ["OLD_CASE", "COMBO_X"]
    assert result.display_selection["target_only_capture_claimed"] is False
    assert result.display_selection["selection_scope"] == "VERIFIED_SUPERSET_SELECTION"


def test_safe_display_fetch_restores_and_preserves_signature_compatibility():
    db = FakeDatabaseTables()
    result = fetch_display_table_for_output(
        db,
        "Story Drifts",
        preferred_output_case="CASE_X",
    )
    assert result.selected_signature["signature_name"] == "sig_3_group_field_key"
    assert db.table_call_arg_counts[:4] == [7, 7, 6, 3]
    assert result.capture_status is RuntimeCaptureStatus.FULL
    assert result.display_selection["display_selection_success"] is True
    assert db.cases == ["OLD_CASE"]
    assert db.combos == ["OLD_COMBO"]
    assert any(item.get("phase") == "restore_verify" for item in result.state_diagnostics)


def test_display_fetch_sampling_cannot_claim_full():
    class TwoRowDB:
        def GetTableForDisplayArray(self, *args):
            return {
                "return_code": 0,
                "field_keys": ["Story", "OutputCase"],
                "number_records": 2,
                "table_data": ["L1", "C1", "L2", "C1"],
            }

    result = fetch_display_table(TwoRowDB(), "Story Drifts", max_rows=1)
    assert result.capture_status is RuntimeCaptureStatus.SAMPLED


def test_full_and_partial_capture_semantics():
    assert classify_capture_status(
        return_code=0,
        row_count_reported=2,
        row_count_captured=2,
        header_count=3,
        flat_payload_length=6,
    ) is RuntimeCaptureStatus.FULL
    assert classify_capture_status(
        return_code=0,
        row_count_reported=2,
        row_count_captured=1,
        header_count=3,
        flat_payload_length=3,
    ) is RuntimeCaptureStatus.PARTIAL


def test_zero_row_zero_schema_response_is_not_full():
    assert classify_capture_status(
        return_code=0,
        row_count_reported=0,
        row_count_captured=0,
        header_count=0,
        flat_payload_length=0,
    ) is RuntimeCaptureStatus.UNKNOWN


def test_known_schema_legitimate_empty_table_may_be_full():
    assert classify_capture_status(
        return_code=0,
        row_count_reported=0,
        row_count_captured=0,
        header_count=2,
        flat_payload_length=0,
    ) is RuntimeCaptureStatus.FULL


def test_missing_success_return_code_cannot_be_full():
    assert classify_capture_status(
        return_code=None,
        row_count_reported=0,
        row_count_captured=0,
        header_count=2,
        flat_payload_length=0,
    ) is RuntimeCaptureStatus.UNKNOWN


def test_capture_status_five_state_contract_unchanged():
    assert classify_capture_status(
        return_code=0,
        row_count_reported=1,
        row_count_captured=1,
        header_count=2,
        flat_payload_length=2,
    ) is RuntimeCaptureStatus.FULL
    assert classify_capture_status(
        return_code=0,
        row_count_reported=2,
        row_count_captured=1,
        header_count=2,
        flat_payload_length=2,
    ) is RuntimeCaptureStatus.PARTIAL
    assert classify_capture_status(
        return_code=0,
        row_count_reported=2,
        row_count_captured=1,
        header_count=2,
        flat_payload_length=2,
        max_rows=1,
    ) is RuntimeCaptureStatus.SAMPLED
    assert classify_capture_status(
        return_code=0,
        row_count_reported=2,
        row_count_captured=1,
        header_count=2,
        flat_payload_length=2,
        explicitly_truncated=True,
    ) is RuntimeCaptureStatus.TRUNCATED
    assert classify_capture_status(
        return_code=1,
        row_count_reported=0,
        row_count_captured=0,
        header_count=2,
        flat_payload_length=0,
    ) is RuntimeCaptureStatus.UNKNOWN


class FakeNameList:
    def __init__(self, names):
        self.names = list(names)

    def GetNameList(self):
        return len(self.names), list(self.names), 0


class FakeResultsSetup:
    def __init__(self):
        self.case_flags = {"DEAD": True, "MODAL": False}
        self.combo_flags = {"COMB": True}
        self.mutation_calls = 0

    def GetCaseSelectedForOutput(self, name):
        return self.case_flags[name], 0

    def SetCaseSelectedForOutput(self, name, selected=True):
        self.mutation_calls += 1
        self.case_flags[name] = bool(selected)
        return 0

    def GetComboSelectedForOutput(self, name):
        return self.combo_flags[name], 0

    def SetComboSelectedForOutput(self, name, selected=True):
        self.mutation_calls += 1
        self.combo_flags[name] = bool(selected)
        return 0

    def DeselectAllCasesAndCombosForOutput(self):
        self.mutation_calls += 1
        for name in self.case_flags:
            self.case_flags[name] = False
        for name in self.combo_flags:
            self.combo_flags[name] = False
        return 0


class FakeResults:
    def __init__(self, setup):
        self.Setup = setup


def test_results_setup_is_independent_and_reversible():
    sap = FakeSap()
    setup = FakeResultsSetup()
    sap.Results = FakeResults(setup)
    sap.LoadCases = FakeNameList(["DEAD", "MODAL"])
    sap.RespCombo = FakeNameList(["COMB"])
    before_cases = dict(setup.case_flags)
    before_combos = dict(setup.combo_flags)
    with ResultsSetupReadTransaction(sap) as tx:
        tx.select_case("MODAL")
        assert setup.case_flags == {"DEAD": False, "MODAL": True}
        assert setup.combo_flags == {"COMB": False}
    assert setup.case_flags == before_cases
    assert setup.combo_flags == before_combos


def test_results_setter_without_matching_getter_fails_before_mutation():
    class SetOnlyResultsSetup:
        def __init__(self):
            self.mutations = 0

        def SetCaseSelectedForOutput(self, name, selected=True):
            self.mutations += 1
            return 0

        def GetComboSelectedForOutput(self, name):
            return False, 0

        def SetComboSelectedForOutput(self, name, selected=True):
            self.mutations += 1
            return 0

        def DeselectAllCasesAndCombosForOutput(self):
            self.mutations += 1
            return 0

    sap = FakeSap()
    setup = SetOnlyResultsSetup()
    sap.Results = FakeResults(setup)
    sap.LoadCases = FakeNameList(["DEAD"])
    sap.RespCombo = FakeNameList(["COMB"])

    with pytest.raises(EtabsCapabilityError) as caught:
        with ResultsSetupReadTransaction(sap):
            pass

    assert caught.value.code is EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED
    assert setup.mutations == 0


def test_capability_snapshot_splits_getters_and_setters_independently():
    class PartialSetup:
        def GetCaseSelectedForOutput(self, name):
            return False, 0

        def SetComboSelectedForOutput(self, name, selected=True):
            return 0

    class PartialDB:
        def GetLoadCasesSelectedForDisplay(self):
            return 0, [], 0

        def SetLoadCombinationsSelectedForDisplay(self, names):
            return 0

    sap = FakeSap()
    sap.Results = FakeResults(PartialSetup())
    sap.DatabaseTables = PartialDB()
    caps = read_capability_snapshot(sap)

    assert caps.results_case_selection_get is CapabilityState.SUPPORTED
    assert caps.results_case_selection_set is CapabilityState.UNSUPPORTED
    assert caps.results_combo_selection_get is CapabilityState.UNSUPPORTED
    assert caps.results_combo_selection_set is CapabilityState.SUPPORTED
    assert caps.database_case_selection_get is CapabilityState.SUPPORTED
    assert caps.database_case_selection_set is CapabilityState.UNSUPPORTED
    assert caps.database_combo_selection_get is CapabilityState.UNSUPPORTED
    assert caps.database_combo_selection_set is CapabilityState.SUPPORTED


def test_capability_snapshot_keeps_unknown_pid_explicit():
    sap = FakeSap()
    caps = read_capability_snapshot(sap)
    assert caps.pid_attach is CapabilityState.UNKNOWN
    assert caps.present_units_2 is CapabilityState.SUPPORTED
    assert caps.database_units_2 is CapabilityState.SUPPORTED
    assert caps.case_status is CapabilityState.SUPPORTED


def test_stable_error_code_contract_contains_required_codes():
    required = {
        "ATTACH_FAILED",
        "PID_ATTACH_UNSUPPORTED",
        "PID_ATTACH_FAILED",
        "ATTACHED_MODEL_MISMATCH",
        "SESSION_IDENTITY_UNAVAILABLE",
        "STATE_SNAPSHOT_UNSUPPORTED",
        "TEMPORARY_STATE_SET_FAILED",
        "TEMPORARY_STATE_VERIFY_FAILED",
        "FETCH_FAILED",
        "STATE_RESTORE_FAILED",
        "STATE_RESTORE_VERIFY_FAILED",
        "UNIT_PROVENANCE_UNAVAILABLE",
        "ANALYSIS_STATUS_UNKNOWN",
        "CAPTURE_INTEGRITY_FAILED",
    }
    assert {item.value for item in EtabsSafetyErrorCode} == required
