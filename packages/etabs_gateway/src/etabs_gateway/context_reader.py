"""Read-only ETABS application and model context extraction.

This module receives an already-attached private model API reference. It does
not discover processes, attach to ETABS, expose COM objects, read tables, run
analysis, or mutate the model.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeVar

from .contracts import (
    ETABSApplicationInfo,
    ETABSAttachment,
    ETABSGatewayContext,
    utc_now,
)
from .errors import (
    ETABSGatewayError,
    ETABSModelLockReadError,
    ETABSModelPathReadError,
    ETABSUnitsReadError,
    ETABSVersionReadError,
)
from .model_context import build_model_context, normalize_model_path

_ErrorT = TypeVar("_ErrorT", bound=ETABSGatewayError)


def read_gateway_context(
    *,
    model_api: object,
    attachment: ETABSAttachment,
) -> ETABSGatewayContext:
    """Read immutable version/model/unit context from an attached model API."""

    version_raw = _invoke(
        model_api,
        "GetVersion",
        error_type=ETABSVersionReadError,
        operation="etabs_version_read",
    )
    version = _parse_version(version_raw)

    model_path_raw = _invoke(
        model_api,
        "GetModelFilename",
        True,
        error_type=ETABSModelPathReadError,
        operation="etabs_model_path_read",
    )
    model_path = normalize_model_path(
        _extract_value(
            model_path_raw,
            error_type=ETABSModelPathReadError,
            operation="etabs_model_path_read",
            method_name="GetModelFilename",
            return_code_sequence_length=2,
        )
    )

    if model_path is None:
        model_context = build_model_context(
            raw_model_path=None,
            raw_is_locked=None,
            present_units_code=None,
        )
    else:
        lock_raw = _invoke(
            model_api,
            "GetModelIsLocked",
            error_type=ETABSModelLockReadError,
            operation="etabs_model_lock_read",
        )
        is_locked = _parse_lock_state(lock_raw)

        units_raw = _invoke(
            model_api,
            "GetPresentUnits",
            error_type=ETABSUnitsReadError,
            operation="etabs_units_read",
        )
        units_code = _parse_units_code(units_raw)

        model_context = build_model_context(
            raw_model_path=model_path,
            raw_is_locked=is_locked,
            present_units_code=units_code,
        )

    observed_at_utc = utc_now()
    application_info = ETABSApplicationInfo(
        version=version,
        process_id=None,
        attached_at_utc=attachment.attached_at_utc,
    )

    return ETABSGatewayContext(
        attachment=attachment,
        application=application_info,
        model=model_context,
        observed_at_utc=observed_at_utc,
    )


def _invoke(
    target: object,
    method_name: str,
    *args: object,
    error_type: type[_ErrorT],
    operation: str,
) -> object:
    try:
        method = getattr(target, method_name)
    except BaseException as exc:
        raise error_type(
            f"ETABS did not expose {method_name}.",
            operation=operation,
            details={
                "stage": "method_lookup",
                "method": method_name,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc

    if not callable(method):
        raise error_type(
            f"ETABS member {method_name} is not callable.",
            operation=operation,
            details={
                "stage": "method_validation",
                "method": method_name,
            },
        )

    try:
        return method(*args)
    except BaseException as exc:
        raise error_type(
            f"ETABS call {method_name} failed.",
            operation=operation,
            details={
                "stage": "method_call",
                "method": method_name,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc


def _extract_value(
    raw_result: object,
    *,
    error_type: type[_ErrorT],
    operation: str,
    method_name: str,
    return_code_sequence_length: int,
) -> object:
    if not isinstance(raw_result, (list, tuple)):
        return raw_result

    values: Sequence[object] = raw_result
    if not values:
        raise error_type(
            f"ETABS call {method_name} returned an empty response.",
            operation=operation,
            details={
                "stage": "response_validation",
                "method": method_name,
                "response_type": type(raw_result).__name__,
            },
        )

    if len(values) >= return_code_sequence_length:
        possible_return_code = values[-1]
        if (
            isinstance(possible_return_code, int)
            and not isinstance(possible_return_code, bool)
            and possible_return_code != 0
        ):
            raise error_type(
                f"ETABS call {method_name} returned a non-zero code.",
                operation=operation,
                details={
                    "stage": "return_code_validation",
                    "method": method_name,
                    "return_code": possible_return_code,
                },
            )

    return values[0]


def _parse_version(raw_result: object) -> str:
    value = _extract_value(
        raw_result,
        error_type=ETABSVersionReadError,
        operation="etabs_version_read",
        method_name="GetVersion",
        return_code_sequence_length=3,
    )
    version = str(value).strip() if value is not None else ""
    if not version:
        raise ETABSVersionReadError(
            "ETABS returned an empty version.",
            operation="etabs_version_read",
            details={
                "stage": "response_validation",
                "method": "GetVersion",
            },
        )
    return version


def _parse_lock_state(raw_result: object) -> bool:
    value = _extract_value(
        raw_result,
        error_type=ETABSModelLockReadError,
        operation="etabs_model_lock_read",
        method_name="GetModelIsLocked",
        return_code_sequence_length=2,
    )

    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False

    raise ETABSModelLockReadError(
        "ETABS returned an invalid model lock state.",
        operation="etabs_model_lock_read",
        details={
            "stage": "response_validation",
            "method": "GetModelIsLocked",
            "response_type": type(value).__name__,
            "response_repr": repr(value),
        },
    )


def _parse_units_code(raw_result: object) -> int:
    value = _extract_value(
        raw_result,
        error_type=ETABSUnitsReadError,
        operation="etabs_units_read",
        method_name="GetPresentUnits",
        return_code_sequence_length=2,
    )

    if isinstance(value, bool):
        raise ETABSUnitsReadError(
            "ETABS returned a boolean instead of a unit code.",
            operation="etabs_units_read",
            details={
                "stage": "response_validation",
                "method": "GetPresentUnits",
                "response_repr": repr(value),
            },
        )

    try:
        unit_code = int(value)
    except (TypeError, ValueError) as exc:
        raise ETABSUnitsReadError(
            "ETABS returned an invalid unit code.",
            operation="etabs_units_read",
            details={
                "stage": "response_validation",
                "method": "GetPresentUnits",
                "response_type": type(value).__name__,
                "response_repr": repr(value),
            },
        ) from exc

    if unit_code < 0:
        raise ETABSUnitsReadError(
            "ETABS returned a negative unit code.",
            operation="etabs_units_read",
            details={
                "stage": "response_validation",
                "method": "GetPresentUnits",
                "unit_code": unit_code,
            },
        )

    return unit_code


__all__ = ["read_gateway_context"]
