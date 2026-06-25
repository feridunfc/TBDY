"""Typed failures exposed by the ETABS gateway boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar


class ETABSGatewayError(RuntimeError):
    """Base class for deterministic gateway failures."""

    code: ClassVar[str] = "ETABS_GATEWAY_ERROR"

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        clean_message = message.strip()
        if not clean_message:
            raise ValueError("Gateway error message must not be empty.")

        super().__init__(clean_message)
        self.operation = operation
        self.details = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "operation": self.operation,
            "details": dict(self.details),
        }


class ETABSNotRunningError(ETABSGatewayError):
    code = "ETABS_NOT_RUNNING"


class ETABSAttachError(ETABSGatewayError):
    code = "ETABS_ATTACH_FAILED"


class ETABSVersionReadError(ETABSGatewayError):
    code = "ETABS_VERSION_READ_FAILED"


class ETABSModelPathReadError(ETABSGatewayError):
    code = "ETABS_MODEL_PATH_READ_FAILED"


class ETABSModelLockReadError(ETABSGatewayError):
    code = "ETABS_MODEL_LOCK_READ_FAILED"


class ETABSUnitsReadError(ETABSGatewayError):
    code = "ETABS_UNITS_READ_FAILED"


class ETABSModelUnavailableError(ETABSGatewayError):
    code = "ETABS_MODEL_UNAVAILABLE"


class ETABSCallError(ETABSGatewayError):
    code = "ETABS_CALL_FAILED"


class ETABSTimeoutError(ETABSGatewayError):
    code = "ETABS_TIMEOUT"


class ETABSCOMInitializationError(ETABSGatewayError):
    code = "ETABS_COM_INITIALIZATION_FAILED"


class ETABSCOMFinalizationError(ETABSGatewayError):
    code = "ETABS_COM_FINALIZATION_FAILED"


class ETABSWorkerStartError(ETABSGatewayError):
    code = "ETABS_WORKER_START_FAILED"


class ETABSWorkerClosedError(ETABSGatewayError):
    code = "ETABS_WORKER_CLOSED"


class ETABSThreadViolationError(ETABSGatewayError):
    code = "ETABS_THREAD_VIOLATION"
