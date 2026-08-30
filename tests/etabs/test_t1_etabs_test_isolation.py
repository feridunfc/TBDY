from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

import etabs_gateway.connection as connection_module
from etabs_gateway.connection import (
    STRATEGY_COMTYPES_GET_ACTIVE_OBJECT,
    STRATEGY_WIN32_GET_ACTIVE_OBJECT,
    ReadOnlyETABSConnection,
)
from etabs_gateway.contracts import ConnectionRequest
from etabs_gateway.errors import ETABSNotRunningError
from etabs_gateway.worker import DedicatedSTAWorker

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_SRC = ROOT / "packages" / "etabs_gateway" / "src"


class _Model:
    def GetVersion(self):
        return ("23.0.0", 1200, 0)

    def GetModelFilename(self, include_path: bool):
        assert include_path is True
        return (r"C:\models\t1-isolation.edb", 0)

    def GetModelIsLocked(self):
        return (True, 0)

    def GetPresentUnits(self):
        return (6, 0)


class _Application:
    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.SapModel = _Model()


class _ActiveRuntime:
    def __init__(self, outcomes: dict[str, object | BaseException]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def GetActiveObject(self, prog_id: str):
        self.calls.append(prog_id)
        outcome = self.outcomes[prog_id]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _ComtypesClient(_ActiveRuntime):
    def __init__(self, outcomes: dict[str, object | BaseException]) -> None:
        super().__init__(outcomes)
        self.create_calls: list[str] = []

    def CreateObject(self, prog_id: str):
        self.create_calls.append(prog_id)
        raise RuntimeError("helper unavailable in T1 fake")


@pytest.fixture
def worker() -> DedicatedSTAWorker:
    active = DedicatedSTAWorker(thread_name="t1-fake-sta")
    try:
        yield active
    finally:
        active.close(timeout_seconds=1.0)


def _poison_real_loader(monkeypatch: pytest.MonkeyPatch, *, would_succeed: bool):
    hits: list[str] = []
    real_runtime = _ActiveRuntime({"ETABS.TEST": _Application("REAL")})

    def load_real_runtime():
        hits.append("win32com.client")
        if would_succeed:
            return real_runtime
        raise AssertionError("real win32com loader must be unreachable in fake mode")

    monkeypatch.setattr(connection_module, "_load_win32com_client", load_real_runtime)
    return hits, real_runtime


def test_t1_fake_success_real_com_poison_is_structurally_unreachable(
    monkeypatch: pytest.MonkeyPatch,
    worker: DedicatedSTAWorker,
) -> None:
    real_loader_hits, real_runtime = _poison_real_loader(monkeypatch, would_succeed=False)
    fake = _ComtypesClient({"ETABS.TEST": _Application("FAKE")})
    connection = ReadOnlyETABSConnection(
        worker,
        comtypes_loader=lambda: fake,
        prog_ids=("ETABS.TEST",),
    )

    attachment = connection.attach()
    try:
        assert connection.attach_diagnostics["strategy"] == STRATEGY_COMTYPES_GET_ACTIVE_OBJECT
        assert fake.calls == ["ETABS.TEST"]
        assert real_loader_hits == []
        assert real_runtime.calls == []
        assert attachment.worker_thread_id != threading.get_ident()
    finally:
        connection.detach()


def test_t1_real_com_would_succeed_but_fake_selection_wins_without_real_call(
    monkeypatch: pytest.MonkeyPatch,
    worker: DedicatedSTAWorker,
) -> None:
    real_loader_hits, real_runtime = _poison_real_loader(monkeypatch, would_succeed=True)
    fake = _ComtypesClient({"ETABS.TEST": _Application("FAKE")})
    connection = ReadOnlyETABSConnection(
        worker,
        comtypes_loader=lambda: fake,
        prog_ids=("ETABS.TEST",),
    )

    connection.attach()
    try:
        assert connection.attach_diagnostics["strategy"] == STRATEGY_COMTYPES_GET_ACTIVE_OBJECT
        assert fake.calls == ["ETABS.TEST"]
        assert real_loader_hits == []
        assert real_runtime.calls == []
    finally:
        connection.detach()


def test_t1_fake_failure_propagates_without_real_com_fallback(
    monkeypatch: pytest.MonkeyPatch,
    worker: DedicatedSTAWorker,
) -> None:
    real_loader_hits, real_runtime = _poison_real_loader(monkeypatch, would_succeed=True)
    fake = _ComtypesClient({"ETABS.TEST": RuntimeError("fake attach failed")})
    connection = ReadOnlyETABSConnection(
        worker,
        comtypes_loader=lambda: fake,
        prog_ids=("ETABS.TEST",),
    )

    with pytest.raises(ETABSNotRunningError):
        connection.attach()

    assert fake.calls == ["ETABS.TEST"]
    assert real_loader_hits == []
    assert real_runtime.calls == []
    assert connection.attached is False


def test_t1_fake_retry_stays_inside_fake_dependency_universe(
    monkeypatch: pytest.MonkeyPatch,
    worker: DedicatedSTAWorker,
) -> None:
    real_loader_hits, real_runtime = _poison_real_loader(monkeypatch, would_succeed=True)
    fake = _ComtypesClient(
        {
            "ETABS.MISSING": RuntimeError("fake missing"),
            "ETABS.FAKE": _Application("FAKE"),
        }
    )
    connection = ReadOnlyETABSConnection(
        worker,
        comtypes_loader=lambda: fake,
        prog_ids=("ETABS.MISSING", "ETABS.FAKE"),
    )

    attachment = connection.attach(ConnectionRequest())
    try:
        assert attachment.prog_id == "ETABS.FAKE"
        assert fake.calls == ["ETABS.MISSING", "ETABS.FAKE"]
        assert real_loader_hits == []
        assert real_runtime.calls == []
    finally:
        connection.detach()


def test_t1_production_default_route_remains_win32_first(
    monkeypatch: pytest.MonkeyPatch,
    worker: DedicatedSTAWorker,
) -> None:
    runtime = _ActiveRuntime({"ETABS.TEST": _Application("PRODUCTION-SPY")})
    win32_loads: list[str] = []
    comtypes_loads: list[str] = []

    def load_win32():
        win32_loads.append("win32com.client")
        return runtime

    def load_comtypes():
        comtypes_loads.append("comtypes.client")
        raise AssertionError("production win32 success must remain first")

    monkeypatch.setattr(connection_module, "_load_win32com_client", load_win32)
    monkeypatch.setattr(connection_module, "_load_comtypes_client", load_comtypes)
    connection = ReadOnlyETABSConnection(worker, prog_ids=("ETABS.TEST",))

    connection.attach()
    try:
        assert connection.attach_diagnostics["strategy"] == STRATEGY_WIN32_GET_ACTIVE_OBJECT
        assert win32_loads == ["win32com.client"]
        assert runtime.calls == ["ETABS.TEST"]
        assert comtypes_loads == []
    finally:
        connection.detach()


def test_t1_fake_path_imports_without_real_com_modules_in_fresh_process() -> None:
    code = textwrap.dedent(
        r'''
        import importlib.abc
        import sys

        class BlockRealCOM(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "pythoncom" or fullname == "win32com" or fullname.startswith("win32com.") or fullname == "comtypes" or fullname.startswith("comtypes."):
                    raise AssertionError(f"real COM import attempted: {fullname}")
                return None

        sys.meta_path.insert(0, BlockRealCOM())

        from etabs_gateway import ETABSGatewaySession

        class PythonCOM:
            COINIT_APARTMENTTHREADED = 2
            def CoInitializeEx(self, flags): assert flags == 2
            def CoUninitialize(self): pass
        class Model:
            def GetVersion(self): return ("23.0.0", 1200, 0)
            def GetModelFilename(self, include_path): return (r"C:\\models\\t1.edb", 0)
            def GetModelIsLocked(self): return (True, 0)
            def GetPresentUnits(self): return (6, 0)
        class App:
            SapModel = Model()
        class Fake:
            def GetActiveObject(self, prog_id): return App()
            def CreateObject(self, prog_id): raise RuntimeError("unused")

        session = ETABSGatewaySession(
            com_module_loader=lambda: PythonCOM(),
            comtypes_loader=lambda: Fake(),
        )
        try:
            session.start()
            assert session.attach_diagnostics["strategy"] == "comtypes_get_active_object_etabs_api_object"
        finally:
            session.close()
        print("FAKE_ONLY_OK")
        '''
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(GATEWAY_SRC)))
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "FAKE_ONLY_OK"
