from __future__ import annotations

from tbdy_engine.etabs.safety import (
    attach_verified_to_running_etabs,
    exercise_verified_results_setup_selection,
    read_verified_results_setup_selection,
    read_verified_sta_execution_fact,
)

MODEL_PATH = r"C:\tmp\OAPI_LAYER1_SAFETY_TEST.EDB"


class FakeAnalyze:
    def GetCaseStatus(self):
        return 0, (), (), 0


class FakeNameList:
    def __init__(self, names):
        self.names = list(names)

    def GetNameList(self):
        return len(self.names), list(self.names), 0


class FakeResultsSetup:
    def __init__(self):
        self.case_flags = {"CASE_A": False, "CASE_B": True}
        self.combo_flags = {"COMBO_A": True}

    def GetCaseSelectedForOutput(self, name):
        return self.case_flags[name], 0

    def SetCaseSelectedForOutput(self, name, selected):
        self.case_flags[name] = bool(selected)
        return 0

    def GetComboSelectedForOutput(self, name):
        return self.combo_flags[name], 0

    def SetComboSelectedForOutput(self, name, selected):
        self.combo_flags[name] = bool(selected)
        return 0

    def DeselectAllCasesAndCombosForOutput(self):
        for name in self.case_flags:
            self.case_flags[name] = False
        for name in self.combo_flags:
            self.combo_flags[name] = False
        return 0


class FakeResults:
    def __init__(self):
        self.Setup = FakeResultsSetup()


class FakeDatabaseTables:
    def __init__(self):
        self.cases = ["CASE_B"]
        self.combos = ["COMBO_A"]

    def GetLoadCasesSelectedForDisplay(self):
        return len(self.cases), list(self.cases), 0

    def SetLoadCasesSelectedForDisplay(self, names):
        self.cases = list(names)
        return 0

    def GetLoadCombinationsSelectedForDisplay(self):
        return len(self.combos), list(self.combos), 0

    def SetLoadCombinationsSelectedForDisplay(self, names):
        self.combos = list(names)
        return 0


class FakeSap:
    def __init__(self):
        self.Analyze = FakeAnalyze()
        self.LoadCases = FakeNameList(("CASE_A", "CASE_B"))
        self.RespCombo = FakeNameList(("COMBO_A",))
        self.Results = FakeResults()
        self.DatabaseTables = FakeDatabaseTables()

    def GetModelFilename(self, include_path=True):
        return MODEL_PATH if include_path else "OAPI_LAYER1_SAFETY_TEST.EDB"

    def GetModelFilepath(self):
        return r"C:\tmp"

    def GetVersion(self):
        return "23.2.0", 23.2, 0

    def GetProgramInfo(self):
        return "ETABS", "23.2.0", "Ultimate", 0

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


class FakeEtabsObject:
    def __init__(self, sap):
        self.SapModel = sap

    def GetOAPIVersionNumber(self):
        return 2.3


class FakeHelper:
    def __init__(self, etabs_object):
        self.etabs_object = etabs_object

    def GetObject(self, prog_id):
        return self.etabs_object


class FakeComtypesClient:
    def __init__(self, etabs_object):
        self.etabs_object = etabs_object
        self.helper = FakeHelper(etabs_object)

    def CreateObject(self, prog_id):
        return self.helper

    def GetActiveObject(self, prog_id):
        return self.etabs_object


class FailingWin32:
    def GetActiveObject(self, prog_id):
        raise RuntimeError(prog_id)


def _session():
    sap = FakeSap()
    etabs = FakeEtabsObject(sap)
    session = attach_verified_to_running_etabs(
        MODEL_PATH,
        comtypes_client=FakeComtypesClient(etabs),
        win32com_client=FailingWin32(),
    )
    return sap, session


def test_verified_session_has_no_legacy_raw_attach_result_surface():
    _, session = _session()
    try:
        assert not hasattr(session, "attach_result")
        assert not hasattr(session, "sap_model")
        assert not hasattr(session, "etabs_object")
    finally:
        session.close()


def test_verified_sta_execution_fact_matches_gateway_worker_thread():
    _, session = _session()
    try:
        fact = read_verified_sta_execution_fact(session)
        assert fact.worker_thread_id > 0
        assert fact.executing_thread_id > 0
        assert fact.exact_worker_thread_match is True
    finally:
        session.close()


def test_results_setup_temporary_case_selection_restores_exactly():
    sap, session = _session()
    try:
        before = read_verified_results_setup_selection(session)
        fact = exercise_verified_results_setup_selection(session, case_name="CASE_A")
        after = read_verified_results_setup_selection(session)

        assert fact.selection_kind == "case"
        assert fact.selection_name == "CASE_A"
        assert fact.restoration_verified_exact is True
        assert fact.before == before
        assert fact.after == after == before
        assert sap.Results.Setup.case_flags == {"CASE_A": False, "CASE_B": True}
        assert sap.Results.Setup.combo_flags == {"COMBO_A": True}
    finally:
        session.close()


def test_results_setup_temporary_combo_selection_restores_exactly():
    sap, session = _session()
    try:
        before = read_verified_results_setup_selection(session)
        fact = exercise_verified_results_setup_selection(session, combo_name="COMBO_A")
        after = read_verified_results_setup_selection(session)

        assert fact.selection_kind == "combo"
        assert fact.selection_name == "COMBO_A"
        assert fact.restoration_verified_exact is True
        assert after == before
        assert sap.Results.Setup.case_flags == {"CASE_A": False, "CASE_B": True}
        assert sap.Results.Setup.combo_flags == {"COMBO_A": True}
    finally:
        session.close()
