from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from etabs_gateway.acceptance import (
    AcceptanceStatus,
    canonical_offline_acceptance_report_json,
    run_offline_acceptance,
    scan_source_boundaries,
    validate_phase_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = (
    REPO_ROOT
    / "packages"
    / "etabs_gateway"
    / "tests"
    / "fixtures"
    / "gateway_context_v1.json"
)


def check(report, check_id: str):
    return next(
        item for item in report.checks if item.check_id == check_id
    )


def test_repository_offline_acceptance_passes() -> None:
    report = run_offline_acceptance(
        repo_root=REPO_ROOT,
        fixture_path=FIXTURE_PATH,
    )

    assert report.status is AcceptanceStatus.PASS
    assert report.passed is True
    assert report.fixture_sha256 is not None
    assert report.manifest_phase == "PHASE_1_11_COVERAGE_BUILDER_ORCHESTRATION"
    assert [item.check_id for item in report.checks] == [
        "fixture_integrity",
        "fixture_canonical_json",
        "source_boundaries",
        "phase_manifest",
        "vendor_checksum",
    ]
    assert check(report, "vendor_checksum").details[
        "verified_files"
    ] == 51


def test_report_json_is_byte_deterministic() -> None:
    first = run_offline_acceptance(
        repo_root=REPO_ROOT,
        fixture_path=FIXTURE_PATH,
    )
    second = run_offline_acceptance(
        repo_root=REPO_ROOT,
        fixture_path=FIXTURE_PATH,
    )

    assert (
        canonical_offline_acceptance_report_json(first)
        == canonical_offline_acceptance_report_json(second)
    )


def test_missing_fixture_returns_failed_report(tmp_path) -> None:
    report = run_offline_acceptance(
        repo_root=REPO_ROOT,
        fixture_path=tmp_path / "missing.json",
    )

    assert report.status is AcceptanceStatus.FAIL
    assert check(report, "fixture_integrity").status is (
        AcceptanceStatus.FAIL
    )
    assert check(report, "fixture_canonical_json").status is (
        AcceptanceStatus.FAIL
    )


def test_tampered_fixture_returns_integrity_failure(tmp_path) -> None:
    envelope = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    envelope["context"]["application"]["version"] = "tampered"
    path = tmp_path / "tampered.json"
    path.write_text(
        json.dumps(envelope, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    report = run_offline_acceptance(
        repo_root=REPO_ROOT,
        fixture_path=path,
    )

    assert check(report, "fixture_integrity").status is (
        AcceptanceStatus.FAIL
    )


def test_pretty_but_valid_fixture_fails_canonical_gate(
    tmp_path,
) -> None:
    envelope = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    path = tmp_path / "pretty.json"
    path.write_text(
        json.dumps(envelope, indent=2) + "\n",
        encoding="utf-8",
    )

    report = run_offline_acceptance(
        repo_root=REPO_ROOT,
        fixture_path=path,
    )

    assert check(report, "fixture_integrity").status is (
        AcceptanceStatus.PASS
    )
    assert check(report, "fixture_canonical_json").status is (
        AcceptanceStatus.FAIL
    )


def test_current_source_boundaries_pass() -> None:
    source_root = (
        REPO_ROOT
        / "packages"
        / "etabs_gateway"
        / "src"
        / "etabs_gateway"
    )

    assert scan_source_boundaries(source_root) == ()


def test_source_boundary_rejects_vendor_import(tmp_path) -> None:
    (tmp_path / "bad.py").write_text(
        "import etabs_mcp\n",
        encoding="utf-8",
    )

    findings = scan_source_boundaries(tmp_path)

    assert findings[0].code == "FORBIDDEN_IMPORT"



def test_source_boundary_rejects_reverse_tbdy_engine_import(
    tmp_path,
) -> None:
    (tmp_path / "bad.py").write_text(
        "from tbdy_engine.features import FeatureSnapshot\n",
        encoding="utf-8",
    )

    findings = scan_source_boundaries(tmp_path)

    assert findings[0].code == "FORBIDDEN_IMPORT"
    assert findings[0].message.startswith("tbdy_engine")

def test_source_boundary_rejects_forbidden_call(tmp_path) -> None:
    (tmp_path / "bad.py").write_text(
        "def run(model):\n"
        "    model.RunAnalysis()\n",
        encoding="utf-8",
    )

    findings = scan_source_boundaries(tmp_path)

    assert findings[0].code == "FORBIDDEN_CALL"
    assert findings[0].message == "RunAnalysis"


def test_active_object_is_scoped_to_connection(tmp_path) -> None:
    (tmp_path / "other.py").write_text(
        "def attach(runtime):\n"
        "    return runtime.GetActiveObject('x')\n",
        encoding="utf-8",
    )

    findings = scan_source_boundaries(tmp_path)

    assert findings[0].code == "ACTIVE_OBJECT_SCOPE"


def test_metadata_method_literal_is_scoped_to_context_reader(
    tmp_path,
) -> None:
    (tmp_path / "other.py").write_text(
        "METHOD = 'GetVersion'\n",
        encoding="utf-8",
    )

    findings = scan_source_boundaries(tmp_path)

    assert findings[0].code == "METADATA_READ_SCOPE"


def test_manifest_validation_rejects_wrong_phase(tmp_path) -> None:
    manifest = json.loads(
        (
            REPO_ROOT / "provenance" / "SOURCE_MANIFEST.json"
        ).read_text(encoding="utf-8")
    )
    manifest["phase"] = "WRONG"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    phase, failures = validate_phase_manifest(path)

    assert phase == "WRONG"
    assert any(item.startswith("phase:expected=") for item in failures)


def test_report_contract_is_immutable() -> None:
    report = run_offline_acceptance(
        repo_root=REPO_ROOT,
        fixture_path=FIXTURE_PATH,
    )

    with pytest.raises(FrozenInstanceError):
        report.fixture_sha256 = "changed"  # type: ignore[misc]

    with pytest.raises(TypeError):
        report.checks[0].details["changed"] = True  # type: ignore[index]


def test_cli_returns_zero_and_writes_canonical_json(tmp_path) -> None:
    output_path = tmp_path / "acceptance.json"
    tool = REPO_ROOT / "tools" / "verify_etabs_gateway_offline.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(tool),
            "--repo-root",
            str(REPO_ROOT),
            "--fixture",
            str(FIXTURE_PATH),
            "--json-out",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "ETABS gateway offline acceptance: PASS" in completed.stdout

    text = output_path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert text.count("\n") == 1
    assert json.loads(text)["status"] == "PASS"
