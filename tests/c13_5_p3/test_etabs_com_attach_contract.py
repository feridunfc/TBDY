from __future__ import annotations

import json
from pathlib import Path

import pytest

from tbdy_engine.features.etabs_com_attach import (
    ATTACH_STRATEGIES,
    CANDIDATE_PROG_IDS,
    EtabsAttachAttempt,
    EtabsAttachFailure,
    EtabsAttachResult,
    LEGACY_COMPATIBILITY_ONLY,
    attach_to_running_etabs,
)
from tools import probe_live_etabs_geometry_snapshot as probe_cli

ROOT = Path(__file__).resolve().parents[2]
_FAKE_SAP_MODEL = object()


class FakeEtabsObject:
    SapModel = _FAKE_SAP_MODEL


class SuccessfulActiveObjectClient:
    def GetActiveObject(self, prog_id: str):
        return FakeEtabsObject()

    def CreateObject(self, prog_id: str):
        raise AssertionError("helper strategy must not run after direct attach success")


class FailingClient:
    def GetActiveObject(self, prog_id: str):
        raise FakeComError(-2147467262, "No such interface supported", None, None)

    def CreateObject(self, prog_id: str):
        raise FakeComError(-2147467262, "No such interface supported", None, None)


class FakeComError(Exception):
    pass


def _failed_attach_result() -> EtabsAttachResult:
    return EtabsAttachResult(
        status="FAILED",
        strategy=None,
        etabs_object=None,
        sap_model=None,
        attempts=(
            EtabsAttachAttempt(
                strategy="comtypes_get_active_object_etabs_api_object",
                prog_id="CSI.ETABS.API.ETABSObject",
                status="FAILED",
                message="No such interface supported",
                exception_type="COMError",
                hresult="-2147467262",
            ),
        ),
    )


def test_etabs_com_attach_imports_without_etabs_or_com_modules():
    import tbdy_engine.features.etabs_com_attach as module

    assert module.ATTACH_STRATEGIES == ATTACH_STRATEGIES


def test_attach_module_is_diagnostic_compatibility_facade_without_raw_capability():
    assert LEGACY_COMPATIBILITY_ONLY is True

    with pytest.raises(
        ValueError,
        match="legacy compatibility result must not expose ETABS application/SapModel capability",
    ):
        EtabsAttachResult(
            status="ATTACHED",
            strategy="comtypes_get_active_object_etabs_api_object",
            etabs_object=object(),
            sap_model=object(),
            attempts=(),
        )


def test_attach_strategies_are_bounded_and_ordered():
    assert ATTACH_STRATEGIES == (
        "comtypes_create_helper_get_object_process",
        "comtypes_get_active_object_etabs_api_object",
        "comtypes_create_helper_get_object",
        "win32com_get_active_object_etabs_api_object",
    )
    assert CANDIDATE_PROG_IDS == (
        "CSI.ETABS.API.ETABSObject",
        "CSI.ETABS.API.ETABSObject.1",
        "ETABSv1.Helper",
    )


def test_success_path_returns_attached_diagnostics_without_raw_capability():
    result = attach_to_running_etabs(comtypes_client=SuccessfulActiveObjectClient())

    assert result.status == "ATTACHED"
    assert result.strategy == "comtypes_get_active_object_etabs_api_object"
    assert result.etabs_object is None
    assert result.sap_model is None
    assert len(result.attempts) == 1
    assert result.attempts[0].status == "SUCCESS"
    assert result.as_diagnostic_dict()["raw_capability_exposed"] is False


def test_failure_path_returns_failed_with_all_attempts_recorded():
    result = attach_to_running_etabs(
        comtypes_client=FailingClient(),
        win32com_client=FailingClient(),
    )

    assert result.status == "FAILED"
    assert result.strategy is None
    assert result.etabs_object is None
    assert result.sap_model is None
    assert result.attempts
    observed_strategies = {attempt.strategy for attempt in result.attempts}
    assert "win32com_get_active_object_etabs_api_object" not in observed_strategies
    assert observed_strategies <= {
        "comtypes_create_helper_get_object_process",
        "comtypes_get_active_object_etabs_api_object",
        "comtypes_create_helper_get_object",
    }
    assert {attempt.status for attempt in result.attempts} == {"FAILED"}


def test_comerror_like_exception_records_hresult_and_message():
    result = attach_to_running_etabs(
        comtypes_client=FailingClient(),
        win32com_client=FailingClient(),
    )

    first = result.attempts[0]
    assert first.hresult == "-2147467262"
    assert first.exception_type == "FakeComError"
    assert "No such interface supported" in first.message


def test_cli_without_live_etabs_refuses_explicit_opt_in(tmp_path: Path, capsys):
    exit_code = probe_cli.main(["--out", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "explicit --live-etabs opt-in" in captured.err
    assert not (tmp_path / "feature_snapshot.json").exists()


def test_cli_attach_failure_writes_structured_failure_outputs(tmp_path: Path, monkeypatch, capsys):
    stale_feature_snapshot = tmp_path / "feature_snapshot.json"
    stale_feature_snapshot.write_text("{}", encoding="utf-8")

    def fail_to_create_provider(**_kwargs):
        raise EtabsAttachFailure(_failed_attach_result())

    monkeypatch.setattr(probe_cli, "create_live_etabs_geometry_provider", fail_to_create_provider)

    exit_code = probe_cli.main(["--live-etabs", "--out", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Live geometry probe: FAIL" in captured.out
    assert (tmp_path / "live_geometry_probe_summary.json").is_file()
    assert (tmp_path / "live_geometry_probe_diagnostics.json").is_file()
    assert (tmp_path / "live_geometry_probe_manifest.json").is_file()
    assert not stale_feature_snapshot.exists()

    summary = json.loads((tmp_path / "live_geometry_probe_summary.json").read_text(encoding="utf-8"))
    diagnostics = json.loads((tmp_path / "live_geometry_probe_diagnostics.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "live_geometry_probe_manifest.json").read_text(encoding="utf-8"))

    assert summary["diagnostic_count"] == 1
    assert summary["failure_stage"] == "COM_ATTACH"
    assert summary["feature_snapshot_written"] is False
    assert summary["scope"] == "LIVE_ETABS_GEOMETRY_FEATURE_SNAPSHOT_PROBE"
    assert summary["status"] == "FAIL"
    assert summary["assignment_table_row_count"] == 0
    assert summary["property_table_row_count"] == 0
    assert summary["resolved_geometry_row_count"] == 0
    assert diagnostics[0]["code"] == "ETABS_COM_ATTACH_FAILED"
    assert diagnostics[0]["status"] == "BLOCKED"
    assert diagnostics[0]["attempts"][0]["message"] == "No such interface supported"
    assert diagnostics[0]["attempts"][0]["hresult"] == "-2147467262"
    assert manifest["feature_snapshot_written"] is False
    assert manifest["live_etabs_required_for_ci"] is False
