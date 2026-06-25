"""Deterministic repository-level offline acceptance gate.

This module verifies fixture replay, source boundaries, phase provenance, and
the vendored ETABS-MCP checksum manifest without attaching to ETABS.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .replay import (
    canonical_gateway_context_fixture_json,
    load_gateway_context_fixture,
)


class AcceptanceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class AcceptanceCheckResult:
    check_id: str
    status: AcceptanceStatus
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.check_id.strip():
            raise ValueError("check_id must not be empty.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")
        object.__setattr__(
            self,
            "details",
            MappingProxyType(dict(self.details)),
        )


@dataclass(frozen=True, slots=True)
class OfflineAcceptanceReport:
    checks: tuple[AcceptanceCheckResult, ...]
    fixture_sha256: str | None
    manifest_phase: str | None
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.schema_version != "1.0":
            raise ValueError("Unsupported report schema version.")
        check_ids = [check.check_id for check in self.checks]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("Acceptance check IDs must be unique.")

    @property
    def status(self) -> AcceptanceStatus:
        return (
            AcceptanceStatus.PASS
            if self.checks
            and all(
                check.status is AcceptanceStatus.PASS
                for check in self.checks
            )
            else AcceptanceStatus.FAIL
        )

    @property
    def passed(self) -> bool:
        return self.status is AcceptanceStatus.PASS


@dataclass(frozen=True, slots=True)
class SourceBoundaryFinding:
    path: str
    line: int
    code: str
    message: str


def run_offline_acceptance(
    *,
    repo_root: str | Path,
    fixture_path: str | Path,
) -> OfflineAcceptanceReport:
    root = Path(repo_root).resolve()
    fixture = Path(fixture_path)
    if not fixture.is_absolute():
        fixture = root / fixture

    checks: list[AcceptanceCheckResult] = []
    fixture_sha256: str | None = None
    manifest_phase: str | None = None

    fixture_result, fixture_sha256 = _check_fixture_integrity(fixture)
    checks.append(fixture_result)
    checks.append(_check_fixture_canonical(fixture))

    source_root = root / "packages" / "etabs_gateway" / "src" / "etabs_gateway"
    checks.append(_check_source_boundaries(source_root))

    manifest_result, manifest_phase = _check_manifest(
        root / "provenance" / "SOURCE_MANIFEST.json"
    )
    checks.append(manifest_result)

    checks.append(_check_vendor_verifier(root))

    return OfflineAcceptanceReport(
        checks=tuple(checks),
        fixture_sha256=fixture_sha256,
        manifest_phase=manifest_phase,
    )


def canonical_offline_acceptance_report_json(
    report: OfflineAcceptanceReport,
) -> str:
    payload = {
        "schema_version": report.schema_version,
        "status": report.status.value,
        "fixture_sha256": report.fixture_sha256,
        "manifest_phase": report.manifest_phase,
        "checks": [
            {
                "check_id": check.check_id,
                "status": check.status.value,
                "message": check.message,
                "details": dict(check.details),
            }
            for check in report.checks
        ],
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def scan_source_boundaries(
    source_root: str | Path,
) -> tuple[SourceBoundaryFinding, ...]:
    root = Path(source_root)
    findings: list[SourceBoundaryFinding] = []

    forbidden_import_roots = {
        "etabs_mcp",
        "vendor",
        "pythoncom",
        "win32com",
        "comtypes",
        "tbdy_engine",
    }
    forbidden_calls = {
        "execute_code",
        "SetSection",
        "RunAnalysis",
        "SetPresentUnits",
        "SetModelIsLocked",
        "InitializeNewModel",
        "OpenFile",
        "Save",
        "ApplicationStart",
        "ApplicationExit",
        "GetObject",
        "CreateObject",
        "GetTableForDisplayArray",
        "GetAllTables",
        "GetAvailableTables",
    }
    metadata_names = {
        "GetVersion",
        "GetModelFilename",
        "GetModelIsLocked",
        "GetPresentUnits",
    }

    if not root.is_dir():
        return (
            SourceBoundaryFinding(
                path=str(root),
                line=0,
                code="SOURCE_ROOT_MISSING",
                message="Gateway source root does not exist.",
            ),
        )

    for path in sorted(root.glob("*.py")):
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(path))
        except (OSError, SyntaxError) as exc:
            findings.append(
                SourceBoundaryFinding(
                    path=str(path),
                    line=getattr(exc, "lineno", 0) or 0,
                    code="SOURCE_PARSE_FAILED",
                    message=str(exc),
                )
            )
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = alias.name.split(".", 1)[0]
                    if root_name in forbidden_import_roots:
                        findings.append(
                            SourceBoundaryFinding(
                                path=str(path),
                                line=node.lineno,
                                code="FORBIDDEN_IMPORT",
                                message=alias.name,
                            )
                        )

            elif isinstance(node, ast.ImportFrom) and node.module:
                root_name = node.module.split(".", 1)[0]
                if root_name in forbidden_import_roots:
                    findings.append(
                        SourceBoundaryFinding(
                            path=str(path),
                            line=node.lineno,
                            code="FORBIDDEN_IMPORT",
                            message=node.module,
                        )
                    )

            elif isinstance(node, ast.Call):
                final_name = _dotted_name(node.func).rsplit(".", 1)[-1]
                if final_name in forbidden_calls:
                    findings.append(
                        SourceBoundaryFinding(
                            path=str(path),
                            line=node.lineno,
                            code="FORBIDDEN_CALL",
                            message=final_name,
                        )
                    )
                if (
                    final_name == "GetActiveObject"
                    and path.name != "connection.py"
                ):
                    findings.append(
                        SourceBoundaryFinding(
                            path=str(path),
                            line=node.lineno,
                            code="ACTIVE_OBJECT_SCOPE",
                            message=final_name,
                        )
                    )

            elif isinstance(node, ast.Attribute):
                if node.attr == "SapModel" and path.name != "connection.py":
                    findings.append(
                        SourceBoundaryFinding(
                            path=str(path),
                            line=node.lineno,
                            code="MODEL_API_SCOPE",
                            message=node.attr,
                        )
                    )

            elif isinstance(node, ast.Constant) and isinstance(
                node.value,
                str,
            ):
                if (
                    node.value in metadata_names
                    and path.name not in {
                        "context_reader.py",
                        "acceptance.py",
                    }
                ):
                    findings.append(
                        SourceBoundaryFinding(
                            path=str(path),
                            line=getattr(node, "lineno", 0),
                            code="METADATA_READ_SCOPE",
                            message=node.value,
                        )
                    )

    return tuple(findings)


def validate_phase_manifest(
    manifest_path: str | Path,
) -> tuple[str | None, tuple[str, ...]]:
    path = Path(manifest_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, (f"manifest_read_failed:{type(exc).__name__}",)

    phase = payload.get("phase")
    failures: list[str] = []

    expected_values = {
        "phase": "PHASE_1_11_COVERAGE_BUILDER_ORCHESTRATION",
        "integration_status": "COVERAGE_BUILDER_ORCHESTRATION_IMPLEMENTED",
        "runtime_wiring_status": "OFFLINE_AUTHORITATIVE_ORCHESTRATION_VERIFIED",
    }
    for key, expected in expected_values.items():
        if payload.get(key) != expected:
            failures.append(
                f"{key}:expected={expected}:observed={payload.get(key)}"
            )

    boundaries = payload.get("boundaries")
    if not isinstance(boundaries, dict):
        failures.append("boundaries:missing_or_invalid")
    else:
        expected_boundaries = {
            "integration_performed": True,
            "production_import_from_vendor_allowed": False,
            "generic_execute_code_allowed": False,
        }
        for key, expected in sorted(expected_boundaries.items()):
            if boundaries.get(key) is not expected:
                failures.append(
                    f"boundaries.{key}:expected={str(expected).lower()}:"
                    f"observed={boundaries.get(key)}"
                )

    return phase if isinstance(phase, str) else None, tuple(failures)


def _check_fixture_integrity(
    fixture_path: Path,
) -> tuple[AcceptanceCheckResult, str | None]:
    try:
        fixture = load_gateway_context_fixture(fixture_path)
    except BaseException as exc:
        return (
            AcceptanceCheckResult(
                check_id="fixture_integrity",
                status=AcceptanceStatus.FAIL,
                message="Fixture validation failed.",
                details={
                    "path": str(fixture_path),
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
            ),
            None,
        )

    return (
        AcceptanceCheckResult(
            check_id="fixture_integrity",
            status=AcceptanceStatus.PASS,
            message="Fixture schema and SHA-256 integrity are valid.",
            details={
                "path": str(fixture_path),
                "sha256": fixture.sha256,
            },
        ),
        fixture.sha256,
    )


def _check_fixture_canonical(
    fixture_path: Path,
) -> AcceptanceCheckResult:
    try:
        text = fixture_path.read_text(encoding="utf-8")
        fixture = load_gateway_context_fixture(fixture_path)
        expected = (
            canonical_gateway_context_fixture_json(fixture) + "\n"
        )
    except BaseException as exc:
        return AcceptanceCheckResult(
            check_id="fixture_canonical_json",
            status=AcceptanceStatus.FAIL,
            message="Canonical fixture verification could not run.",
            details={
                "path": str(fixture_path),
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        )

    if text != expected:
        return AcceptanceCheckResult(
            check_id="fixture_canonical_json",
            status=AcceptanceStatus.FAIL,
            message="Fixture is valid but not canonical UTF-8 JSON.",
            details={"path": str(fixture_path)},
        )

    return AcceptanceCheckResult(
        check_id="fixture_canonical_json",
        status=AcceptanceStatus.PASS,
        message="Fixture uses canonical deterministic JSON.",
        details={"path": str(fixture_path)},
    )


def _check_source_boundaries(
    source_root: Path,
) -> AcceptanceCheckResult:
    findings = scan_source_boundaries(source_root)
    if findings:
        return AcceptanceCheckResult(
            check_id="source_boundaries",
            status=AcceptanceStatus.FAIL,
            message="Gateway source boundary violations were found.",
            details={
                "finding_count": len(findings),
                "findings": [
                    {
                        "path": finding.path,
                        "line": finding.line,
                        "code": finding.code,
                        "message": finding.message,
                    }
                    for finding in findings
                ],
            },
        )

    return AcceptanceCheckResult(
        check_id="source_boundaries",
        status=AcceptanceStatus.PASS,
        message="Gateway source boundaries are intact.",
        details={"source_root": str(source_root)},
    )


def _check_manifest(
    manifest_path: Path,
) -> tuple[AcceptanceCheckResult, str | None]:
    phase, failures = validate_phase_manifest(manifest_path)
    if failures:
        return (
            AcceptanceCheckResult(
                check_id="phase_manifest",
                status=AcceptanceStatus.FAIL,
                message="Source manifest does not satisfy P1.7 boundaries.",
                details={
                    "path": str(manifest_path),
                    "failures": list(failures),
                },
            ),
            phase,
        )

    return (
        AcceptanceCheckResult(
            check_id="phase_manifest",
            status=AcceptanceStatus.PASS,
            message="Source manifest declares the offline acceptance phase.",
            details={
                "path": str(manifest_path),
                "phase": phase,
            },
        ),
        phase,
    )


def _check_vendor_verifier(
    repo_root: Path,
) -> AcceptanceCheckResult:
    verifier = repo_root / "tools" / "verify_etabs_mcp_vendor.py"
    if not verifier.is_file():
        return AcceptanceCheckResult(
            check_id="vendor_checksum",
            status=AcceptanceStatus.FAIL,
            message="Vendor verifier is missing.",
            details={"path": str(verifier)},
        )

    completed = subprocess.run(
        [sys.executable, str(verifier)],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    match = re.search(r"Verified files:\s*(\d+)", output)
    verified_files = int(match.group(1)) if match else None

    if completed.returncode != 0:
        return AcceptanceCheckResult(
            check_id="vendor_checksum",
            status=AcceptanceStatus.FAIL,
            message="ETABS-MCP vendor verification failed.",
            details={
                "return_code": completed.returncode,
                "verified_files": verified_files,
            },
        )

    return AcceptanceCheckResult(
        check_id="vendor_checksum",
        status=AcceptanceStatus.PASS,
        message="ETABS-MCP vendor verification passed.",
        details={
            "return_code": completed.returncode,
            "verified_files": verified_files,
        },
    )


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


__all__ = [
    "AcceptanceCheckResult",
    "AcceptanceStatus",
    "OfflineAcceptanceReport",
    "SourceBoundaryFinding",
    "canonical_offline_acceptance_report_json",
    "run_offline_acceptance",
    "scan_source_boundaries",
    "validate_phase_manifest",
]
