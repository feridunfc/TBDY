"""C13.5-P3 ETABS COM attach compatibility boundary.

The module is import-safe on machines without ETABS, comtypes, or pywin32.
COM client modules are imported only inside explicit live attach strategy
functions.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
import importlib

ATTACH_STATUS_ATTACHED = "ATTACHED"
ATTACH_STATUS_FAILED = "FAILED"
ATTEMPT_STATUS_SUCCESS = "SUCCESS"
ATTEMPT_STATUS_FAILED = "FAILED"
ATTEMPT_STATUS_SKIPPED = "SKIPPED"

ATTACH_STRATEGIES: tuple[str, ...] = (
    "comtypes_get_active_object_etabs_api_object",
    "comtypes_create_helper_get_object",
    "win32com_get_active_object_etabs_api_object",
)
CANDIDATE_PROG_IDS: tuple[str, ...] = (
    "CSI.ETABS.API.ETABSObject",
    "CSI.ETABS.API.ETABSObject.1",
    "ETABSv1.Helper",
)
_DIRECT_ETABS_PROG_IDS: tuple[str, ...] = (
    "CSI.ETABS.API.ETABSObject",
    "CSI.ETABS.API.ETABSObject.1",
)
_HELPER_PROG_ID = "ETABSv1.Helper"
_ALLOWED_ATTACH_STATUSES = frozenset({ATTACH_STATUS_ATTACHED, ATTACH_STATUS_FAILED})
_ALLOWED_ATTEMPT_STATUSES = frozenset({ATTEMPT_STATUS_SUCCESS, ATTEMPT_STATUS_FAILED, ATTEMPT_STATUS_SKIPPED})


@dataclass(frozen=True, slots=True)
class EtabsAttachAttempt:
    strategy: str
    status: str
    message: str
    exception_type: str | None = None
    hresult: str | None = None
    prog_id: str | None = None

    def __post_init__(self) -> None:
        if self.strategy not in ATTACH_STRATEGIES:
            raise ValueError("Unsupported ETABS attach strategy")
        if self.status not in _ALLOWED_ATTEMPT_STATUSES:
            raise ValueError("Unsupported ETABS attach attempt status")
        if not self.message:
            raise ValueError("EtabsAttachAttempt.message is required")

    def as_dict(self) -> dict[str, object]:
        return {
            "exception_type": self.exception_type,
            "hresult": self.hresult,
            "message": self.message,
            "prog_id": self.prog_id,
            "status": self.status,
            "strategy": self.strategy,
        }


@dataclass(frozen=True, slots=True)
class EtabsAttachResult:
    status: str
    strategy: str | None
    etabs_object: Any | None
    sap_model: Any | None
    attempts: tuple[EtabsAttachAttempt, ...]

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_ATTACH_STATUSES:
            raise ValueError("Unsupported ETABS attach result status")
        if self.status == ATTACH_STATUS_ATTACHED:
            if self.strategy not in ATTACH_STRATEGIES:
                raise ValueError("Attached ETABS result requires a successful strategy")
            if self.etabs_object is None:
                raise ValueError("Attached ETABS result requires etabs_object")
            if self.sap_model is None:
                raise ValueError("Attached ETABS result requires sap_model")
        if self.status == ATTACH_STATUS_FAILED and self.strategy is not None:
            raise ValueError("Failed ETABS attach result must not name a successful strategy")
        object.__setattr__(self, "attempts", tuple(self.attempts))

    def as_diagnostic_dict(self) -> dict[str, object]:
        return {
            "attempts": [attempt.as_dict() for attempt in self.attempts],
            "status": self.status,
            "strategy": self.strategy,
        }


class EtabsAttachFailure(RuntimeError):
    """Raised when no bounded ETABS COM attach strategy succeeds."""

    def __init__(self, attach_result: EtabsAttachResult) -> None:
        super().__init__("No ETABS COM attach strategy succeeded.")
        self.attach_result = attach_result


def attach_to_running_etabs(
    *,
    comtypes_client: Any | None = None,
    win32com_client: Any | None = None,
) -> EtabsAttachResult:
    """Try bounded ETABS COM attach strategies and record every attempt.

    Optional client arguments are test seams for fake COM clients. Production code
    leaves them as None, which imports optional COM packages only inside this
    explicit live boundary.
    """
    attempts: list[EtabsAttachAttempt] = []

    result = _try_direct_active_object(
        strategy="comtypes_get_active_object_etabs_api_object",
        client=comtypes_client,
        import_module_name="comtypes.client",
        prog_ids=_DIRECT_ETABS_PROG_IDS,
    )
    attempts.extend(result.attempts)
    if result.status == ATTACH_STATUS_ATTACHED:
        return result

    result = _try_helper_get_object(
        client=comtypes_client,
        import_module_name="comtypes.client",
        helper_prog_id=_HELPER_PROG_ID,
        etabs_prog_ids=_DIRECT_ETABS_PROG_IDS,
    )
    attempts.extend(result.attempts)
    if result.status == ATTACH_STATUS_ATTACHED:
        return result

    result = _try_direct_active_object(
        strategy="win32com_get_active_object_etabs_api_object",
        client=win32com_client,
        import_module_name="win32com.client",
        prog_ids=_DIRECT_ETABS_PROG_IDS,
    )
    attempts.extend(result.attempts)
    if result.status == ATTACH_STATUS_ATTACHED:
        return result

    return EtabsAttachResult(
        status=ATTACH_STATUS_FAILED,
        strategy=None,
        etabs_object=None,
        sap_model=None,
        attempts=tuple(attempts),
    )


def _try_direct_active_object(
    *,
    strategy: str,
    client: Any | None,
    import_module_name: str,
    prog_ids: Sequence[str],
) -> EtabsAttachResult:
    attempts: list[EtabsAttachAttempt] = []
    try:
        resolved_client = client if client is not None else importlib.import_module(import_module_name)
    except Exception as exc:
        return _failed_strategy_result(
            EtabsAttachAttempt(
                strategy=strategy,
                prog_id=None,
                status=ATTEMPT_STATUS_FAILED,
                message=_exception_message(exc),
                exception_type=type(exc).__name__,
                hresult=_exception_hresult(exc),
            )
        )

    for prog_id in prog_ids:
        try:
            etabs_object = resolved_client.GetActiveObject(prog_id)
            sap_model = _sap_model_from(etabs_object)
            if sap_model is None:
                attempts.append(
                    EtabsAttachAttempt(
                        strategy=strategy,
                        prog_id=prog_id,
                        status=ATTEMPT_STATUS_FAILED,
                        message="ETABS object was returned but SapModel was not accessible.",
                    )
                )
                continue
            attempts.append(
                EtabsAttachAttempt(
                    strategy=strategy,
                    prog_id=prog_id,
                    status=ATTEMPT_STATUS_SUCCESS,
                    message="ETABS object and SapModel attached.",
                )
            )
            return EtabsAttachResult(
                status=ATTACH_STATUS_ATTACHED,
                strategy=strategy,
                etabs_object=etabs_object,
                sap_model=sap_model,
                attempts=tuple(attempts),
            )
        except Exception as exc:
            attempts.append(_attempt_from_exception(strategy=strategy, prog_id=prog_id, exc=exc))

    return _failed_strategy_result(*attempts)


def _try_helper_get_object(
    *,
    client: Any | None,
    import_module_name: str,
    helper_prog_id: str,
    etabs_prog_ids: Sequence[str],
) -> EtabsAttachResult:
    strategy = "comtypes_create_helper_get_object"
    attempts: list[EtabsAttachAttempt] = []
    try:
        resolved_client = client if client is not None else importlib.import_module(import_module_name)
    except Exception as exc:
        return _failed_strategy_result(
            EtabsAttachAttempt(
                strategy=strategy,
                prog_id=helper_prog_id,
                status=ATTEMPT_STATUS_FAILED,
                message=_exception_message(exc),
                exception_type=type(exc).__name__,
                hresult=_exception_hresult(exc),
            )
        )

    try:
        helper = resolved_client.CreateObject(helper_prog_id)
    except Exception as exc:
        return _failed_strategy_result(_attempt_from_exception(strategy=strategy, prog_id=helper_prog_id, exc=exc))

    get_object = getattr(helper, "GetObject", None)
    if get_object is None:
        return _failed_strategy_result(
            EtabsAttachAttempt(
                strategy=strategy,
                prog_id=helper_prog_id,
                status=ATTEMPT_STATUS_FAILED,
                message="ETABS helper object was returned but GetObject was not accessible.",
            )
        )

    for prog_id in etabs_prog_ids:
        try:
            etabs_object = get_object(prog_id)
            sap_model = _sap_model_from(etabs_object)
            if sap_model is None:
                attempts.append(
                    EtabsAttachAttempt(
                        strategy=strategy,
                        prog_id=prog_id,
                        status=ATTEMPT_STATUS_FAILED,
                        message="ETABS helper returned an object but SapModel was not accessible.",
                    )
                )
                continue
            attempts.append(
                EtabsAttachAttempt(
                    strategy=strategy,
                    prog_id=prog_id,
                    status=ATTEMPT_STATUS_SUCCESS,
                    message="ETABS helper returned object and SapModel.",
                )
            )
            return EtabsAttachResult(
                status=ATTACH_STATUS_ATTACHED,
                strategy=strategy,
                etabs_object=etabs_object,
                sap_model=sap_model,
                attempts=tuple(attempts),
            )
        except Exception as exc:
            attempts.append(_attempt_from_exception(strategy=strategy, prog_id=prog_id, exc=exc))

    return _failed_strategy_result(*attempts)


def _failed_strategy_result(*attempts: EtabsAttachAttempt) -> EtabsAttachResult:
    return EtabsAttachResult(
        status=ATTACH_STATUS_FAILED,
        strategy=None,
        etabs_object=None,
        sap_model=None,
        attempts=tuple(attempts),
    )


def _attempt_from_exception(*, strategy: str, prog_id: str | None, exc: Exception) -> EtabsAttachAttempt:
    return EtabsAttachAttempt(
        strategy=strategy,
        prog_id=prog_id,
        status=ATTEMPT_STATUS_FAILED,
        message=_exception_message(exc),
        exception_type=type(exc).__name__,
        hresult=_exception_hresult(exc),
    )


def _sap_model_from(etabs_object: Any) -> Any | None:
    try:
        sap_model = getattr(etabs_object, "SapModel")
    except Exception:
        return None
    return sap_model


def _exception_hresult(exc: Exception) -> str | None:
    hresult = getattr(exc, "hresult", None)
    if hresult is None:
        args = getattr(exc, "args", ())
        if args and isinstance(args[0], int):
            hresult = args[0]
    return None if hresult is None else str(hresult)


def _exception_message(exc: Exception) -> str:
    args = getattr(exc, "args", ())
    if isinstance(args, tuple):
        for candidate in args[1:]:
            if isinstance(candidate, str) and candidate:
                return candidate
    message = str(exc)
    return message if message else repr(exc)


__all__ = [
    "ATTACH_STRATEGIES",
    "CANDIDATE_PROG_IDS",
    "EtabsAttachAttempt",
    "EtabsAttachFailure",
    "EtabsAttachResult",
    "attach_to_running_etabs",
]
