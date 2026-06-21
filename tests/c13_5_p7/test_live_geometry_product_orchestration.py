from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest

from tbdy_engine.features.live_etabs_geometry_probe import LiveGeometryProbeResult
from tbdy_engine.product import live_geometry_product as live_product
from tbdy_engine.product.live_geometry_product import run_live_geometry_product

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PRODUCT_FILES = (
    "artifacts/check_results.json",
    "artifacts/adapter_diagnostics.json",
    "artifacts/run_summary.json",
    "artifacts/run_manifest.json",
    "reports/geometry_report.md",
    "product_smoke_summary.json",
    "product_smoke_manifest.json",
)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _probe_runner(*, status: str, snapshot_count: int, diagnostic_count: int = 0, capture: dict | None = None):
    def run(**kwargs):
        if capture is not None:
            capture.update(kwargs)
        out = Path(kwargs["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        snapshots = [
            {
                "component_type": "beam",
                "component_id": f"B{index + 1}",
                "identity": {},
                "features": {},
            }
            for index in range(snapshot_count)
        ]
        feature_path = out / "feature_snapshot.json"
        summary_path = out / "live_geometry_probe_summary.json"
        diagnostics_path = out / "live_geometry_probe_diagnostics.json"
        manifest_path = out / "live_geometry_probe_manifest.json"
        feature_path.write_text(json.dumps({"snapshots": snapshots}, sort_keys=True) + "\n", encoding="utf-8")
        summary_path.write_text(
            json.dumps(
                {
                    "status": status,
                    "snapshot_count": snapshot_count,
                    "diagnostic_count": diagnostic_count,
                    "resolved_geometry_row_count": snapshot_count,
                    "feature_status_counts": {"RESOLVED": snapshot_count * 2},
                    "length_unit_source": "m",
                    "target_report_length_unit": "mm",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        diagnostics_path.write_text(
            json.dumps([{"code": "FAKE"}] * diagnostic_count, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest_path.write_text(
            json.dumps({"scope": "FAKE_PROBE", "status": status}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return LiveGeometryProbeResult(
            status=status,
            output_dir=out,
            feature_snapshot_path=feature_path,
            summary_path=summary_path,
            diagnostics_path=diagnostics_path,
            manifest_path=manifest_path,
            snapshot_count=snapshot_count,
            diagnostic_count=diagnostic_count,
        )

    return run


def _successful_product_runner(capture: dict | None = None, *, check_results_text: str = "[]\n"):
    def run(*, feature_snapshot_path: Path, output_dir: Path):
        if capture is not None:
            capture["feature_snapshot_path"] = Path(feature_snapshot_path)
            capture["output_dir"] = Path(output_dir)
        root = Path(output_dir)
        for relative in REQUIRED_PRODUCT_FILES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative == "artifacts/check_results.json":
                path.write_text(check_results_text, encoding="utf-8")
            elif relative == "product_smoke_summary.json":
                path.write_text(
                    json.dumps(
                        {
                            "status": "OK",
                            "p4": {
                                "check_result_count": 2,
                                "adapter_diagnostic_count": 1,
                            },
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            else:
                path.write_text("{}\n" if path.suffix == ".json" else "# fake report\n", encoding="utf-8")
        return SimpleNamespace(
            status="OK",
            output_dir=root,
            artifact_dir=root / "artifacts",
            report_path=root / "reports" / "geometry_report.md",
            product_smoke_summary_path=root / "product_smoke_summary.json",
            product_smoke_manifest_path=root / "product_smoke_manifest.json",
            p4_check_result_count=2,
            p4_adapter_diagnostic_count=1,
        )

    return run


def test_cli_refuses_without_live_opt_in_and_writes_nothing(tmp_path: Path):
    out = tmp_path / "refused"
    completed = subprocess.run(
        [sys.executable, "tools/run_live_geometry_product.py", "--out", str(out)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "--live-etabs" in completed.stderr
    assert not out.exists()


def test_provider_creation_failure_writes_structured_failure_and_skips_product(tmp_path: Path):
    product_called = False

    def provider_factory():
        raise RuntimeError("provider creation failed")

    def product_runner(**_kwargs):
        nonlocal product_called
        product_called = True
        raise AssertionError("product runner must not be called")

    result = run_live_geometry_product(
        output_dir=tmp_path,
        provider_factory=provider_factory,
        probe_runner=_probe_runner(status="OK", snapshot_count=1),
        product_runner=product_runner,
    )
    summary = _read_json(tmp_path / "live_geometry_product_summary.json")

    assert result.status == "FAIL"
    assert product_called is False
    assert summary["status"] == "FAIL"
    assert summary["failure_stage"] == "PROVIDER_CREATION"
    assert summary["error_type"] == "RuntimeError"
    assert summary["product_status"] is None


def test_probe_fail_skips_product_stage(tmp_path: Path):
    product_called = False

    def product_runner(**_kwargs):
        nonlocal product_called
        product_called = True
        raise AssertionError("product runner must not be called")

    result = run_live_geometry_product(
        output_dir=tmp_path,
        provider_factory=lambda: object(),
        probe_runner=_probe_runner(status="FAIL", snapshot_count=1, diagnostic_count=1),
        product_runner=product_runner,
    )

    assert result.status == "FAIL"
    assert product_called is False
    assert _read_json(result.summary_path)["live_probe_status"] == "FAIL"


def test_zero_snapshot_probe_fails_and_skips_product(tmp_path: Path):
    product_called = False

    def product_runner(**_kwargs):
        nonlocal product_called
        product_called = True
        raise AssertionError("product runner must not be called")

    result = run_live_geometry_product(
        output_dir=tmp_path,
        provider_factory=lambda: object(),
        probe_runner=_probe_runner(status="OK", snapshot_count=0),
        product_runner=product_runner,
    )

    assert result.status == "FAIL"
    assert product_called is False
    assert _read_json(result.summary_path)["snapshot_count"] == 0


def test_missing_product_artifact_forces_fail(tmp_path: Path):
    def incomplete_product_runner(*, feature_snapshot_path: Path, output_dir: Path):
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / "product_smoke_summary.json").write_text("{}\n", encoding="utf-8")
        return SimpleNamespace(
            status="OK",
            product_smoke_summary_path=root / "product_smoke_summary.json",
            p4_check_result_count=1,
            p4_adapter_diagnostic_count=0,
        )

    result = run_live_geometry_product(
        output_dir=tmp_path,
        provider_factory=lambda: object(),
        probe_runner=_probe_runner(status="OK", snapshot_count=1),
        product_runner=incomplete_product_runner,
    )
    summary = _read_json(result.summary_path)

    assert result.status == "FAIL"
    assert summary["failure_stage"] == "PRODUCT_ARTIFACT_VALIDATION"
    assert summary["missing_product_files"]


def test_partial_probe_with_snapshots_runs_product_and_stays_partial(tmp_path: Path):
    capture = {}
    result = run_live_geometry_product(
        output_dir=tmp_path,
        provider_factory=lambda: object(),
        probe_runner=_probe_runner(status="PARTIAL", snapshot_count=2, diagnostic_count=3),
        product_runner=_successful_product_runner(capture),
    )
    summary = _read_json(result.summary_path)

    assert result.status == "PARTIAL"
    assert capture["feature_snapshot_path"] == tmp_path / "live_probe" / "feature_snapshot.json"
    assert summary["status"] == "PARTIAL"
    assert summary["live_probe_status"] == "PARTIAL"
    assert summary["product_status"] == "OK"
    assert summary["probe_diagnostic_count"] == 3
    assert summary["feature_snapshot_consumed_by_product"] is True


def test_ok_probe_with_snapshots_and_product_is_ok(tmp_path: Path):
    result = run_live_geometry_product(
        output_dir=tmp_path,
        provider_factory=lambda: object(),
        probe_runner=_probe_runner(status="OK", snapshot_count=2),
        product_runner=_successful_product_runner(),
    )
    summary = _read_json(result.summary_path)

    assert result.status == "OK"
    assert summary["status"] == "OK"
    assert summary["product_check_result_count"] == 2
    assert summary["product_adapter_diagnostic_count"] == 1
    assert summary["resolved_geometry_row_count"] == 2
    assert summary["length_unit_source"] == "m"
    assert summary["target_report_length_unit"] == "mm"


def test_exact_generated_snapshot_path_is_passed_to_product_runner(tmp_path: Path):
    capture = {}
    result = run_live_geometry_product(
        output_dir=tmp_path,
        provider_factory=lambda: object(),
        probe_runner=_probe_runner(status="OK", snapshot_count=1),
        product_runner=_successful_product_runner(capture),
    )

    expected = tmp_path / "live_probe" / "feature_snapshot.json"
    assert capture["feature_snapshot_path"] == expected
    assert result.feature_snapshot_path == expected
    assert _read_json(result.summary_path)["feature_snapshot_path"] == "live_probe/feature_snapshot.json"


def test_orchestrator_does_not_rewrite_existing_product_artifacts(tmp_path: Path):
    marker = "PRODUCT-RUNNER-OWNED\n"
    result = run_live_geometry_product(
        output_dir=tmp_path,
        provider_factory=lambda: object(),
        probe_runner=_probe_runner(status="OK", snapshot_count=1),
        product_runner=_successful_product_runner(check_results_text=marker),
    )

    assert result.status == "OK"
    assert (tmp_path / "product" / "artifacts" / "check_results.json").read_text(encoding="utf-8") == marker


def test_summary_and_manifest_are_deterministic_and_relative(tmp_path: Path):
    outputs = []
    for name in ("first", "second"):
        root = tmp_path / name
        result = run_live_geometry_product(
            output_dir=root,
            provider_factory=lambda: object(),
            probe_runner=_probe_runner(status="OK", snapshot_count=1),
            product_runner=_successful_product_runner(),
        )
        outputs.append((_read_json(result.summary_path), _read_json(result.manifest_path)))

    assert outputs[0] == outputs[1]
    summary, manifest = outputs[0]
    assert summary["live_probe_output_dir"] == "live_probe"
    assert summary["product_output_dir"] == "product"
    assert summary["feature_snapshot_path"] == "live_probe/feature_snapshot.json"
    assert manifest["source_probe_manifest"] == "live_probe/live_geometry_probe_manifest.json"
    assert manifest["source_product_manifest"] == "product/product_smoke_manifest.json"
    assert manifest["feature_snapshot_consumed_without_rewrite"] is True


def test_selectors_and_max_rows_are_propagated_unchanged(tmp_path: Path):
    capture = {}
    run_live_geometry_product(
        output_dir=tmp_path,
        target_story="+14.5",
        target_label="B1",
        target_component="297",
        max_rows=7,
        provider_factory=lambda: object(),
        probe_runner=_probe_runner(status="OK", snapshot_count=1, capture=capture),
        product_runner=_successful_product_runner(),
    )
    manifest = _read_json(tmp_path / "live_geometry_product_manifest.json")

    assert capture["target_story"] == "+14.5"
    assert capture["target_label"] == "B1"
    assert capture["target_component"] == "297"
    assert capture["max_rows"] == 7
    assert manifest["selectors"] == {
        "target_component": "297",
        "target_label": "B1",
        "target_story": "+14.5",
        "max_rows": 7,
    }


def test_offline_injected_dependencies_never_call_live_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    live_called = False

    def forbidden_live_provider():
        nonlocal live_called
        live_called = True
        raise AssertionError("live ETABS provider must not be called in offline tests")

    monkeypatch.setattr(live_product, "create_live_etabs_geometry_provider", forbidden_live_provider)
    result = run_live_geometry_product(
        output_dir=tmp_path,
        provider_factory=lambda: object(),
        probe_runner=_probe_runner(status="OK", snapshot_count=1),
        product_runner=_successful_product_runner(),
    )

    assert result.status == "OK"
    assert live_called is False
