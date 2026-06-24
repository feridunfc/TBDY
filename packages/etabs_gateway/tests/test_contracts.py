from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from etabs_gateway.contracts import (
    ConnectionRequest,
    DiagnosticEvent,
    DiagnosticSeverity,
    ETABSApplicationInfo,
)


def test_connection_request_is_immutable() -> None:
    request = ConnectionRequest(timeout_seconds=5.0)

    with pytest.raises(FrozenInstanceError):
        request.timeout_seconds = 9.0  # type: ignore[misc]


def test_connection_request_rejects_invalid_pid() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        ConnectionRequest(target_process_id=0)


def test_application_info_requires_utc_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ETABSApplicationInfo(
            version="23.0.0",
            process_id=101,
            attached_at_utc=datetime.now(),
        )

    valid = ETABSApplicationInfo(
        version="23.0.0",
        process_id=101,
        attached_at_utc=datetime.now(timezone.utc),
    )
    assert valid.process_id == 101


def test_diagnostic_details_are_immutable_snapshot() -> None:
    source = {"attempt": 1}
    event = DiagnosticEvent(
        code="ATTACH_ATTEMPT",
        message="Attach attempt started.",
        severity=DiagnosticSeverity.INFO,
        details=source,
    )
    source["attempt"] = 2

    assert event.details["attempt"] == 1
    with pytest.raises(TypeError):
        event.details["attempt"] = 3  # type: ignore[index]
