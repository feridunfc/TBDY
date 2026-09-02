"""Private bounded mutation transport for future typed ETABS OAPI setters.

B4T adds transport mechanics only.  The public gateway remains read-only:
this module is intentionally absent from ``etabs_gateway.__all__`` and its
entry point requires a private capability key.  Repository architecture guards
restrict production reachability to the gateway itself and the trusted
``tbdy_engine.etabs.safety`` / ``tbdy_engine.etabs.oapi`` factual boundary.

The callback receives only the private SapModel reference, only while executing
on the already-owned STA worker.  The application object is never supplied.
Returned values must be recursively transport-safe factual data so raw COM
capabilities cannot cross the boundary.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import TypeVar

from .contracts import GatewayState
from .errors import ETABSAttachError, ETABSCallError, ETABSSessionStateError
from .session import ETABSGatewaySession

T = TypeVar("T")
BoundedMutation = Callable[[object], T]

# Private capability key.  It is deliberately not re-exported from the package
# root.  Future typed OAPI mutation primitives may consume this private seam;
# application/product/engineering layers are guarded from reaching it.
_B4T_MUTATION_TRANSPORT_KEY = object()


def _raise_unsafe_result(
    *,
    operation: str,
    stage: str,
    path: str,
    value: object,
) -> None:
    raise ETABSCallError(
        "Bounded ETABS mutation returned a non-factual or raw capability value.",
        operation=operation,
        details={
            "stage": stage,
            "path": path,
            "result_type": type(value).__name__,
        },
    )


def _require_transport_safe_result(
    value: object,
    *,
    application: object,
    model_api: object,
    operation: str,
    path: str = "$",
    seen: set[int] | None = None,
) -> None:
    """Reject raw/live capability objects from the mutation result graph.

    The accepted result universe is intentionally narrow: scalar facts, enums,
    tuples/frozensets, plain dictionaries, and frozen dataclass facts whose
    fields recursively satisfy the same rule.  Arbitrary objects are rejected,
    which prevents child COM proxies from escaping even when they are not the
    exact application/SapModel owner references.
    """

    if value is application or value is model_api:
        _raise_unsafe_result(
            operation=operation,
            stage="raw_owner_reference_escape",
            path=path,
            value=value,
        )

    if value is None or type(value) in {bool, int, float, str, bytes}:
        return

    if isinstance(value, Enum):
        _require_transport_safe_result(
            value.value,
            application=application,
            model_api=model_api,
            operation=operation,
            path=f"{path}.value",
            seen=seen,
        )
        return

    active_seen = set() if seen is None else seen

    if isinstance(value, tuple):
        marker = id(value)
        if marker in active_seen:
            _raise_unsafe_result(
                operation=operation,
                stage="cyclic_result_graph",
                path=path,
                value=value,
            )
        active_seen.add(marker)
        try:
            for index, item in enumerate(value):
                _require_transport_safe_result(
                    item,
                    application=application,
                    model_api=model_api,
                    operation=operation,
                    path=f"{path}[{index}]",
                    seen=active_seen,
                )
        finally:
            active_seen.remove(marker)
        return

    if isinstance(value, frozenset):
        marker = id(value)
        if marker in active_seen:
            _raise_unsafe_result(
                operation=operation,
                stage="cyclic_result_graph",
                path=path,
                value=value,
            )
        active_seen.add(marker)
        try:
            for index, item in enumerate(value):
                _require_transport_safe_result(
                    item,
                    application=application,
                    model_api=model_api,
                    operation=operation,
                    path=f"{path}{{{index}}}",
                    seen=active_seen,
                )
        finally:
            active_seen.remove(marker)
        return

    if type(value) is dict:
        marker = id(value)
        if marker in active_seen:
            _raise_unsafe_result(
                operation=operation,
                stage="cyclic_result_graph",
                path=path,
                value=value,
            )
        active_seen.add(marker)
        try:
            for key, item in value.items():
                _require_transport_safe_result(
                    key,
                    application=application,
                    model_api=model_api,
                    operation=operation,
                    path=f"{path}.<key>",
                    seen=active_seen,
                )
                _require_transport_safe_result(
                    item,
                    application=application,
                    model_api=model_api,
                    operation=operation,
                    path=f"{path}[{key!r}]",
                    seen=active_seen,
                )
        finally:
            active_seen.remove(marker)
        return

    if is_dataclass(value) and not isinstance(value, type):
        params = getattr(type(value), "__dataclass_params__", None)
        if params is None or not params.frozen:
            _raise_unsafe_result(
                operation=operation,
                stage="mutable_dataclass_result",
                path=path,
                value=value,
            )
        marker = id(value)
        if marker in active_seen:
            _raise_unsafe_result(
                operation=operation,
                stage="cyclic_result_graph",
                path=path,
                value=value,
            )
        active_seen.add(marker)
        try:
            for item in fields(value):
                _require_transport_safe_result(
                    getattr(value, item.name),
                    application=application,
                    model_api=model_api,
                    operation=operation,
                    path=f"{path}.{item.name}",
                    seen=active_seen,
                )
        finally:
            active_seen.remove(marker)
        return

    _raise_unsafe_result(
        operation=operation,
        stage="unsafe_result_type",
        path=path,
        value=value,
    )


def _execute_mutation_on_worker(
    session: ETABSGatewaySession,
    function: BoundedMutation[T],
    *,
    operation: str,
) -> T:
    connection = session._connection  # noqa: SLF001 - same-package transport boundary
    connection._worker.assert_worker_thread()  # noqa: SLF001

    with connection._state_lock:  # noqa: SLF001
        application = connection._application  # noqa: SLF001
        model_api = connection._model_api  # noqa: SLF001
        attachment = connection._attachment  # noqa: SLF001

    if attachment is None or application is None or model_api is None:
        raise ETABSAttachError(
            "Bounded ETABS mutation requires an attached gateway session.",
            operation=operation,
            details={"stage": "connection_state"},
        )

    result = function(model_api)
    _require_transport_safe_result(
        result,
        application=application,
        model_api=model_api,
        operation=operation,
    )
    return result


def _execute_bounded_model_mutation(
    session: ETABSGatewaySession,
    function: BoundedMutation[T],
    *,
    operation: str,
    timeout_seconds: float = 30.0,
    _transport_key: object = None,
) -> T:
    """Execute one private trusted model mutation on the existing STA owner.

    This is a transport primitive, not a lifecycle/domain authority.  It does
    not decide what should be mutated, whether state is established, or whether
    any requested-vs-observed comparison matches.
    """

    if _transport_key is not _B4T_MUTATION_TRANSPORT_KEY:
        raise TypeError("bounded mutation transport is private to trusted ETABS boundaries")
    if not isinstance(session, ETABSGatewaySession):
        raise TypeError("session must be ETABSGatewaySession")
    if not callable(function):
        raise TypeError("function must be callable")
    clean_operation = str(operation).strip()
    if not clean_operation:
        raise ValueError("operation must not be empty")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    if session.state is not GatewayState.READY:
        raise ETABSSessionStateError(
            "Bounded ETABS mutations require a ready gateway session.",
            operation=clean_operation,
            details={"state": session.state.value},
        )

    connection = session._connection  # noqa: SLF001 - same-package transport boundary
    return connection._worker.call(  # noqa: SLF001
        lambda: _execute_mutation_on_worker(
            session,
            function,
            operation=clean_operation,
        ),
        operation=clean_operation,
        timeout_seconds=timeout,
    )


__all__: list[str] = []
