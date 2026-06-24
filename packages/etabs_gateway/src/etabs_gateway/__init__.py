"""Public contract surface for the typed ETABS gateway."""

from .contracts import (
    AttachMode,
    ConnectionDiagnostics,
    ConnectionRequest,
    DiagnosticEvent,
    DiagnosticSeverity,
    ETABSApplicationInfo,
    ETABSModelContext,
    ETABSUnitContext,
    GatewayHealth,
    GatewayState,
    HealthStatus,
)
from .errors import (
    ETABSAttachError,
    ETABSCallError,
    ETABSGatewayError,
    ETABSModelUnavailableError,
    ETABSNotRunningError,
    ETABSThreadViolationError,
    ETABSTimeoutError,
    ETABSVersionReadError,
    ETABSWorkerClosedError,
)

__all__ = [
    "AttachMode",
    "ConnectionDiagnostics",
    "ConnectionRequest",
    "DiagnosticEvent",
    "DiagnosticSeverity",
    "ETABSApplicationInfo",
    "ETABSModelContext",
    "ETABSUnitContext",
    "GatewayHealth",
    "GatewayState",
    "HealthStatus",
    "ETABSAttachError",
    "ETABSCallError",
    "ETABSGatewayError",
    "ETABSModelUnavailableError",
    "ETABSNotRunningError",
    "ETABSThreadViolationError",
    "ETABSTimeoutError",
    "ETABSVersionReadError",
    "ETABSWorkerClosedError",
]
