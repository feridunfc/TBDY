from __future__ import annotations

import threading
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from etabs_gateway.connection import ReadOnlyETABSConnection
from etabs_gateway.context_reader import read_gateway_context
from etabs_gateway.contracts import (
    AttachMode,
    ETABSAttachment,
)
from etabs_gateway.errors import (
    ETABSAttachError,
    ETABSModelLockReadError,
    ETABSModelPathReadError,
    ETABSUnitsReadError,
    ETABSVersionReadError,
)
from etabs_gateway.worker import DedicatedSTAWorker


class FakeModelAPI:
    def __init__(
        self,
        *,
        version: object = ("23.0.0", 1200, 0),
        model_path: object = (r"C:\models\sample.edb", 0),
        is_locked: object = (True, 0),
        units: object = (6, 0),
        failures: dict[str, BaseException] | None = None,
    ) -> None:
        self.version = version
        self.model_path = model_path
        self.is_locked = is_locked
        self.units = units
        self.failures = failures or {}
        self.calls: list[tuple[str, tuple[object, ...], int]] = []

    def _record(self, name: str, args: tuple[object, ...]) -> None:
        self.calls.append((name, args, threading.get_ident()))
        failure = self.failures.get(name)
        if failure is not None:
            raise failure

    def GetVersion(self) -> object:
        self._record("GetVersion", ())
        return self.version

    def GetModelFilename(self, include_path: bool) -> object:
        self._record("GetModelFilename", (include_path,))
        return self.model_path

    def GetModelIsLocked(self) -> object:
        self._record("GetModelIsLocked", ())
        return self.is_locked

    def GetPresentUnits(self) -> object:
        self._record("GetPresentUnits", ())
        return self.units


class FakeApplication:
    def __init__(self, model_api: object) -> None:
        self.SapModel = model_api


class FakeRuntime:
    def __init__(self, application: object) -> None:
        self.application = application

    def GetActiveObject(self, prog_id: str) -> object:
        return self.application


def attachment() -> ETABSAttachment:
    return ETABSAttachment(
        prog_id="ETABS.TEST",
        attach_mode=AttachMode.RUNNING_INSTANCE,
        attached_at_utc=datetime(2026, 6, 25, tzinfo=timezone.utc),
        worker_thread_id=123,
    )


def test_scalar_and_tuple_responses_build_immutable_context() -> None:
    model = FakeModelAPI(
        version="23.0.1",
        model_path=r"C:\models\tower.edb",
        is_locked=1,
        units=6,
    )

    context = read_gateway_context(
        model_api=model,
        attachment=attachment(),
    )

    assert context.application.version == "23.0.1"
    assert context.application.process_id is None
    assert context.model.has_open_model is True
    assert context.model.model_name == "tower.edb"
    assert context.model.is_locked is True
    assert context.model.units is not None
    assert context.model.units.present_units_code == 6

    with pytest.raises(FrozenInstanceError):
        context.application.version = "changed"  # type: ignore[misc]


def test_sequence_responses_validate_zero_return_codes() -> None:
    context = read_gateway_context(
        model_api=FakeModelAPI(),
        attachment=attachment(),
    )

    assert context.application.version == "23.0.0"
    assert context.model.is_locked is True
    assert context.model.units is not None
    assert context.model.units.present_units_code == 6


def test_empty_model_path_returns_no_model_and_skips_lock_and_units() -> None:
    model = FakeModelAPI(model_path=("", 0))

    context = read_gateway_context(
        model_api=model,
        attachment=attachment(),
    )

    assert context.model.has_open_model is False
    assert context.model.model_path is None
    assert context.model.is_locked is None
    assert context.model.units is None
    assert [name for name, _, _ in model.calls] == [
        "GetVersion",
        "GetModelFilename",
    ]


@pytest.mark.parametrize(
    ("method_name", "error_type", "operation"),
    [
        ("GetVersion", ETABSVersionReadError, "etabs_version_read"),
        (
            "GetModelFilename",
            ETABSModelPathReadError,
            "etabs_model_path_read",
        ),
        (
            "GetModelIsLocked",
            ETABSModelLockReadError,
            "etabs_model_lock_read",
        ),
        ("GetPresentUnits", ETABSUnitsReadError, "etabs_units_read"),
    ],
)
def test_individual_call_failures_are_typed(
    method_name: str,
    error_type: type[BaseException],
    operation: str,
) -> None:
    model = FakeModelAPI(
        failures={method_name: RuntimeError(f"{method_name} failed")}
    )

    with pytest.raises(error_type) as caught:
        read_gateway_context(
            model_api=model,
            attachment=attachment(),
        )

    assert getattr(caught.value, "operation") == operation
    assert getattr(caught.value, "details")["stage"] == "method_call"
    assert (
        getattr(caught.value, "details")["exception_type"]
        == "RuntimeError"
    )


@pytest.mark.parametrize(
    ("field_name", "value", "error_type"),
    [
        ("version", ("", 1200, 0), ETABSVersionReadError),
        ("is_locked", ("not-a-bool", 0), ETABSModelLockReadError),
        ("units", (True, 0), ETABSUnitsReadError),
        ("units", (-1, 0), ETABSUnitsReadError),
    ],
)
def test_invalid_responses_are_typed(
    field_name: str,
    value: object,
    error_type: type[BaseException],
) -> None:
    kwargs = {field_name: value}
    model = FakeModelAPI(**kwargs)

    with pytest.raises(error_type):
        read_gateway_context(
            model_api=model,
            attachment=attachment(),
        )


@pytest.mark.parametrize(
    ("field_name", "value", "error_type", "expected_code"),
    [
        ("version", ("23.0.0", 1200, 7), ETABSVersionReadError, 7),
        (
            "model_path",
            (r"C:\models\sample.edb", 8),
            ETABSModelPathReadError,
            8,
        ),
        ("is_locked", (True, 9), ETABSModelLockReadError, 9),
        ("units", (6, 10), ETABSUnitsReadError, 10),
    ],
)
def test_nonzero_return_codes_are_typed(
    field_name: str,
    value: object,
    error_type: type[BaseException],
    expected_code: int,
) -> None:
    model = FakeModelAPI(**{field_name: value})

    with pytest.raises(error_type) as caught:
        read_gateway_context(
            model_api=model,
            attachment=attachment(),
        )

    assert getattr(caught.value, "details")["stage"] == (
        "return_code_validation"
    )
    assert getattr(caught.value, "details")["return_code"] == expected_code


def test_connection_read_context_runs_all_reads_on_worker_thread() -> None:
    model = FakeModelAPI()
    worker = DedicatedSTAWorker()
    connection = ReadOnlyETABSConnection(
        worker,
        runtime_loader=lambda: FakeRuntime(FakeApplication(model)),
        prog_ids=("ETABS.TEST",),
    )
    caller_thread = threading.get_ident()

    try:
        attachment_result = connection.attach()
        context = connection.read_context()

        call_thread_ids = {thread_id for _, _, thread_id in model.calls}
        assert call_thread_ids == {attachment_result.worker_thread_id}
        assert attachment_result.worker_thread_id != caller_thread
        assert context.attachment == attachment_result
        assert context.observed_at_utc >= attachment_result.attached_at_utc
    finally:
        connection.detach()
        worker.close(timeout_seconds=1.0)


def test_connection_read_context_requires_attachment() -> None:
    worker = DedicatedSTAWorker()
    connection = ReadOnlyETABSConnection(
        worker,
        runtime_loader=lambda: object(),
    )

    try:
        with pytest.raises(ETABSAttachError) as caught:
            connection.read_context()

        assert caught.value.details["stage"] == "connection_state"
    finally:
        worker.close(timeout_seconds=1.0)
