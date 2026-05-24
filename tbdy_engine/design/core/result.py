from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from .status import CheckStatus, Severity
from .evidence import Evidence, DataRequest

@dataclass(slots=True)
class CheckResult:
    check_id: str
    title: str
    status: CheckStatus
    scope: str
    severity: Severity = Severity.INFO
    code_ref: str | None = None
    message: str = ""
    member_id: str | None = None
    demand: float | None = None
    capacity: float | None = None
    ratio: float | None = None
    evidence: list[Evidence] = field(default_factory=list)
    data_requests: list[DataRequest] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class ModuleResult:
    module: str
    status: CheckStatus
    checks: list[CheckResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    governing: dict[str, Any] = field(default_factory=dict)
    report_tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    data_requests: list[DataRequest] = field(default_factory=list)

    def add(self, check: CheckResult) -> None:
        self.checks.append(check)
        self.data_requests.extend(check.data_requests)
        if check.status == CheckStatus.FAIL:
            self.status = CheckStatus.FAIL
        elif check.status == CheckStatus.BLOCKED and self.status != CheckStatus.FAIL:
            self.status = CheckStatus.BLOCKED
        elif check.status == CheckStatus.WARNING and self.status == CheckStatus.PASS:
            self.status = CheckStatus.WARNING
