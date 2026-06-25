"""Lazy Windows COM apartment lifecycle adapter.

This module intentionally contains no module-level ``pythoncom`` import.
The platform dependency is loaded only when ``initialize`` is invoked.
"""

from __future__ import annotations

import importlib
import threading
from collections.abc import Callable
from typing import Any, Protocol, cast

from .errors import (
    ETABSCOMFinalizationError,
    ETABSCOMInitializationError,
    ETABSThreadViolationError,
)


class _PythonCOMModule(Protocol):
    COINIT_APARTMENTTHREADED: int

    def CoInitializeEx(self, flags: int) -> Any: ...

    def CoUninitialize(self) -> Any: ...


ModuleLoader = Callable[[], object]


def _load_pythoncom() -> object:
    return importlib.import_module("pythoncom")


class WindowsCOMApartment:
    """Own one COM apartment lifecycle on exactly one thread.

    The instance is suitable for injection into ``DedicatedSTAWorker`` through
    ``initializer=apartment.initialize`` and ``finalizer=apartment.finalize``.
    It does not attach to ETABS or acquire any COM application object.
    """

    def __init__(self, *, module_loader: ModuleLoader | None = None) -> None:
        self._module_loader = module_loader or _load_pythoncom
        self._lock = threading.RLock()
        self._module: _PythonCOMModule | None = None
        self._thread_id: int | None = None
        self._initialized = False

    @property
    def initialized(self) -> bool:
        with self._lock:
            return self._initialized

    @property
    def thread_id(self) -> int | None:
        with self._lock:
            return self._thread_id

    def initialize(self) -> None:
        current_thread_id = threading.get_ident()

        with self._lock:
            if self._initialized:
                if self._thread_id != current_thread_id:
                    raise ETABSThreadViolationError(
                        "The COM apartment is already owned by another thread.",
                        operation="com_initialize",
                        details={
                            "expected_thread_id": self._thread_id,
                            "actual_thread_id": current_thread_id,
                        },
                    )
                raise ETABSCOMInitializationError(
                    "The COM apartment is already initialized.",
                    operation="com_initialize",
                    details={"thread_id": current_thread_id},
                )

            module = self._load_and_validate_module()

            try:
                module.CoInitializeEx(module.COINIT_APARTMENTTHREADED)
            except BaseException as exc:
                raise ETABSCOMInitializationError(
                    "Failed to initialize the Windows COM apartment.",
                    operation="com_initialize",
                    details={
                        "stage": "CoInitializeEx",
                        "thread_id": current_thread_id,
                        "exception_type": type(exc).__name__,
                        "exception_message": str(exc),
                    },
                ) from exc

            self._module = module
            self._thread_id = current_thread_id
            self._initialized = True

    def finalize(self) -> None:
        current_thread_id = threading.get_ident()

        with self._lock:
            if not self._initialized:
                return

            if self._thread_id != current_thread_id:
                raise ETABSThreadViolationError(
                    "The COM apartment must be finalized by its owner thread.",
                    operation="com_finalize",
                    details={
                        "expected_thread_id": self._thread_id,
                        "actual_thread_id": current_thread_id,
                    },
                )

            module = self._module
            if module is None:
                self._clear_state()
                raise ETABSCOMFinalizationError(
                    "The initialized COM apartment has no bound module.",
                    operation="com_finalize",
                    details={"thread_id": current_thread_id},
                )

            failure: BaseException | None = None
            try:
                module.CoUninitialize()
            except BaseException as exc:
                failure = exc
            finally:
                # Finalization is one-shot and idempotent even if the platform
                # call reports an error. Do not retain stale thread ownership.
                self._clear_state()

            if failure is not None:
                raise ETABSCOMFinalizationError(
                    "Failed to finalize the Windows COM apartment.",
                    operation="com_finalize",
                    details={
                        "stage": "CoUninitialize",
                        "thread_id": current_thread_id,
                        "exception_type": type(failure).__name__,
                        "exception_message": str(failure),
                    },
                ) from failure

    def __enter__(self) -> WindowsCOMApartment:
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        self.finalize()

    def _load_and_validate_module(self) -> _PythonCOMModule:
        try:
            raw_module = self._module_loader()
        except BaseException as exc:
            raise ETABSCOMInitializationError(
                "The Windows COM runtime dependency could not be loaded.",
                operation="com_initialize",
                details={
                    "stage": "module_load",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
            ) from exc

        missing = [
            name
            for name in (
                "COINIT_APARTMENTTHREADED",
                "CoInitializeEx",
                "CoUninitialize",
            )
            if not hasattr(raw_module, name)
        ]
        if missing:
            raise ETABSCOMInitializationError(
                "The loaded COM runtime does not satisfy the required API.",
                operation="com_initialize",
                details={
                    "stage": "module_validation",
                    "missing_attributes": missing,
                },
            )

        initialize = getattr(raw_module, "CoInitializeEx")
        finalize = getattr(raw_module, "CoUninitialize")
        if not callable(initialize) or not callable(finalize):
            raise ETABSCOMInitializationError(
                "The loaded COM runtime exposes non-callable lifecycle hooks.",
                operation="com_initialize",
                details={"stage": "module_validation"},
            )

        return cast(_PythonCOMModule, raw_module)

    def _clear_state(self) -> None:
        self._module = None
        self._thread_id = None
        self._initialized = False
