"""Immutable contracts for the read-only ETABS gateway."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import PureWindowsPath
from types import MappingProxyType
from typing import Any, Mapping


class AttachMode(str, Enum):
    RUNNING_INSTANCE = "RUNNING_INSTANCE"


class GatewayState(str, Enum):
    NEW = "NEW"
    STARTING = "STARTING"
    READY = "READY"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class DiagnosticSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_aware_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field_name} must be expressed in UTC.")


@dataclass(frozen=True, slots=True)
class ConnectionRequest:
    attach_mode: AttachMode = AttachMode.RUNNING_INSTANCE
    timeout_seconds: float = 10.0
    target_process_id: int | None = None
    require_exact_process_match: bool = True

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        if self.target_process_id is not None and self.target_process_id <= 0:
            raise ValueError("target_process_id must be a positive integer.")
        if self.target_process_id is None and not self.require_exact_process_match:
            raise ValueError(
                "require_exact_process_match=False is meaningful only when "
                "target_process_id is supplied."
            )


@dataclass(frozen=True, slots=True)
class ETABSAttachment:
    prog_id: str
    attach_mode: AttachMode
    attached_at_utc: datetime
    worker_thread_id: int

    def __post_init__(self) -> None:
        if not self.prog_id.strip():
            raise ValueError("prog_id must not be empty.")
        if self.worker_thread_id <= 0:
            raise ValueError("worker_thread_id must be a positive integer.")
        _require_aware_utc(self.attached_at_utc, "attached_at_utc")


@dataclass(frozen=True, slots=True)
class ETABSUnitContext:
    present_units_code: int
    display_name: str | None = None
    source_contract: str = "SapModel.GetPresentUnits"

    def __post_init__(self) -> None:
        if self.present_units_code < 0:
            raise ValueError("present_units_code must be non-negative.")
        if not self.source_contract.strip():
            raise ValueError("source_contract must not be empty.")


@dataclass(frozen=True, slots=True)
class ETABSApplicationInfo:
    version: str
    process_id: int | None
    attached_at_utc: datetime

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version must not be empty.")
        if self.process_id is not None and self.process_id <= 0:
            raise ValueError("process_id must be a positive integer.")
        _require_aware_utc(self.attached_at_utc, "attached_at_utc")


@dataclass(frozen=True, slots=True)
class ETABSModelContext:
    has_open_model: bool
    model_path: str | None
    is_locked: bool | None
    units: ETABSUnitContext | None

    def __post_init__(self) -> None:
        if not self.has_open_model:
            if self.model_path is not None:
                raise ValueError(
                    "model_path must be None when has_open_model is False."
                )
            if self.is_locked is not None:
                raise ValueError(
                    "is_locked must be None when has_open_model is False."
                )
            if self.units is not None:
                raise ValueError(
                    "units must be None when has_open_model is False."
                )
            return

        if self.model_path is not None and not self.model_path.strip():
            raise ValueError("model_path must be None or a non-empty string.")

    @property
    def model_name(self) -> str | None:
        if self.model_path is None:
            return None
        return PureWindowsPath(self.model_path).name


@dataclass(frozen=True, slots=True)
class DiagnosticEvent:
    code: str
    message: str
    severity: DiagnosticSeverity
    operation: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    observed_at_utc: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("Diagnostic code must not be empty.")
        if not self.message.strip():
            raise ValueError("Diagnostic message must not be empty.")
        _require_aware_utc(self.observed_at_utc, "observed_at_utc")
        object.__setattr__(
            self,
            "details",
            MappingProxyType(dict(self.details)),
        )


@dataclass(frozen=True, slots=True)
class ConnectionDiagnostics:
    state: GatewayState
    started_at_utc: datetime
    completed_at_utc: datetime | None = None
    events: tuple[DiagnosticEvent, ...] = ()

    def __post_init__(self) -> None:
        _require_aware_utc(self.started_at_utc, "started_at_utc")
        if self.completed_at_utc is not None:
            _require_aware_utc(
                self.completed_at_utc,
                "completed_at_utc",
            )
            if self.completed_at_utc < self.started_at_utc:
                raise ValueError(
                    "completed_at_utc cannot precede started_at_utc."
                )


@dataclass(frozen=True, slots=True)
class GatewayHealth:
    status: HealthStatus
    state: GatewayState
    application: ETABSApplicationInfo | None
    model: ETABSModelContext | None
    diagnostics: ConnectionDiagnostics
