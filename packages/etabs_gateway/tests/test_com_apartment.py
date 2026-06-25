from __future__ import annotations

import importlib
import threading
from typing import Any

import pytest

from etabs_gateway.com_apartment import WindowsCOMApartment
from etabs_gateway.errors import (
    ETABSCOMFinalizationError,
    ETABSCOMInitializationError,
    ETABSThreadViolationError,
)
from etabs_gateway.worker import DedicatedSTAWorker


class FakePythonCOM:
    COINIT_APARTMENTTHREADED = 2

    def __init__(
        self,
        *,
        initialize_error: BaseException | None = None,
        finalize_error: BaseException | None = None,
    ) -> None:
        self.initialize_error = initialize_error
        self.finalize_error = finalize_error
        self.initialize_calls: list[tuple[int, int]] = []
        self.finalize_calls: list[int] = []

    def CoInitializeEx(self, flags: int) -> None:
        self.initialize_calls.append((flags, threading.get_ident()))
        if self.initialize_error is not None:
            raise self.initialize_error

    def CoUninitialize(self) -> None:
        self.finalize_calls.append(threading.get_ident())
        if self.finalize_error is not None:
            raise self.finalize_error


def test_default_loader_imports_pythoncom_only_during_initialize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakePythonCOM()
    imported: list[str] = []

    def fake_import(name: str) -> Any:
        imported.append(name)
        return fake

    monkeypatch.setattr(importlib, "import_module", fake_import)

    apartment = WindowsCOMApartment()
    assert imported == []

    apartment.initialize()
    assert imported == ["pythoncom"]

    apartment.finalize()


def test_initialize_and_finalize_use_sta_flag_on_owner_thread() -> None:
    fake = FakePythonCOM()
    apartment = WindowsCOMApartment(module_loader=lambda: fake)
    owner_thread = threading.get_ident()

    apartment.initialize()

    assert apartment.initialized is True
    assert apartment.thread_id == owner_thread
    assert fake.initialize_calls == [
        (fake.COINIT_APARTMENTTHREADED, owner_thread)
    ]

    apartment.finalize()

    assert fake.finalize_calls == [owner_thread]
    assert apartment.initialized is False
    assert apartment.thread_id is None


def test_double_initialize_is_rejected_without_second_platform_call() -> None:
    fake = FakePythonCOM()
    apartment = WindowsCOMApartment(module_loader=lambda: fake)

    apartment.initialize()

    with pytest.raises(ETABSCOMInitializationError):
        apartment.initialize()

    assert len(fake.initialize_calls) == 1
    apartment.finalize()


def test_finalize_is_idempotent_before_and_after_initialization() -> None:
    fake = FakePythonCOM()
    apartment = WindowsCOMApartment(module_loader=lambda: fake)

    apartment.finalize()
    apartment.initialize()
    apartment.finalize()
    apartment.finalize()

    assert len(fake.finalize_calls) == 1


def test_finalize_from_non_owner_thread_is_rejected_without_state_loss() -> None:
    fake = FakePythonCOM()
    apartment = WindowsCOMApartment(module_loader=lambda: fake)
    apartment.initialize()

    observed: list[BaseException] = []

    def wrong_thread_finalize() -> None:
        try:
            apartment.finalize()
        except BaseException as exc:
            observed.append(exc)

    thread = threading.Thread(target=wrong_thread_finalize)
    thread.start()
    thread.join(timeout=1.0)

    assert len(observed) == 1
    assert isinstance(observed[0], ETABSThreadViolationError)
    assert apartment.initialized is True
    assert fake.finalize_calls == []

    apartment.finalize()


def test_module_load_failure_is_typed() -> None:
    def fail_load() -> object:
        raise ImportError("pythoncom missing")

    apartment = WindowsCOMApartment(module_loader=fail_load)

    with pytest.raises(ETABSCOMInitializationError) as caught:
        apartment.initialize()

    assert caught.value.details["stage"] == "module_load"
    assert caught.value.details["exception_type"] == "ImportError"
    assert apartment.initialized is False


def test_invalid_module_contract_is_typed() -> None:
    apartment = WindowsCOMApartment(module_loader=lambda: object())

    with pytest.raises(ETABSCOMInitializationError) as caught:
        apartment.initialize()

    assert caught.value.details["stage"] == "module_validation"
    assert set(caught.value.details["missing_attributes"]) == {
        "COINIT_APARTMENTTHREADED",
        "CoInitializeEx",
        "CoUninitialize",
    }


def test_platform_initialization_failure_does_not_publish_ownership() -> None:
    fake = FakePythonCOM(initialize_error=RuntimeError("init failed"))
    apartment = WindowsCOMApartment(module_loader=lambda: fake)

    with pytest.raises(ETABSCOMInitializationError) as caught:
        apartment.initialize()

    assert caught.value.details["stage"] == "CoInitializeEx"
    assert caught.value.details["exception_type"] == "RuntimeError"
    assert apartment.initialized is False
    assert apartment.thread_id is None


def test_platform_finalization_failure_is_typed_and_clears_state() -> None:
    fake = FakePythonCOM(finalize_error=RuntimeError("finalize failed"))
    apartment = WindowsCOMApartment(module_loader=lambda: fake)
    apartment.initialize()

    with pytest.raises(ETABSCOMFinalizationError) as caught:
        apartment.finalize()

    assert caught.value.details["stage"] == "CoUninitialize"
    assert caught.value.details["exception_type"] == "RuntimeError"
    assert apartment.initialized is False
    assert apartment.thread_id is None

    apartment.finalize()


def test_apartment_integrates_with_dedicated_worker_lifecycle() -> None:
    fake = FakePythonCOM()
    apartment = WindowsCOMApartment(module_loader=lambda: fake)
    worker = DedicatedSTAWorker(
        initializer=apartment.initialize,
        finalizer=apartment.finalize,
    )
    caller_thread = threading.get_ident()

    worker_thread = worker.call(
        threading.get_ident,
        operation="worker_thread_identity",
    )

    assert worker_thread != caller_thread
    assert apartment.initialized is True
    assert apartment.thread_id == worker_thread

    worker.close()

    assert fake.initialize_calls == [
        (fake.COINIT_APARTMENTTHREADED, worker_thread)
    ]
    assert fake.finalize_calls == [worker_thread]
    assert apartment.initialized is False
    assert apartment.thread_id is None
