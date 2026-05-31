from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.design.beams.beam_core import BeamCoreResult, evaluate_beam_core
from tbdy_engine.design.beams.core_package_adapter import (
    beam_core_result_to_evaluation_packages,
)
from tbdy_engine.design.beams.evaluation_package import BeamEvaluationPackage


@dataclass(frozen=True)
class BeamCoreArtifactResult:
    beam_core: BeamCoreResult
    packages: tuple[BeamEvaluationPackage, ...]
    checks: tuple[object, ...]
    json_path: Path
    xlsx_path: Path | None
    status: str


def generate_beam_core_artifacts(
    data: Mapping[str, object],
    output_dir: Path,
) -> BeamCoreArtifactResult:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    beam_core = evaluate_beam_core(data)
    packages = beam_core_result_to_evaluation_packages(beam_core)
    checks = _adapt_packages(packages)

    json_path = output_dir / "engine_report.json"
    xlsx_path = output_dir / "engine_report.xlsx"

    _write_json_report(checks, json_path)
    actual_xlsx_path = _write_xlsx_report(checks, xlsx_path)

    return BeamCoreArtifactResult(
        beam_core=beam_core,
        packages=packages,
        checks=checks,
        json_path=json_path,
        xlsx_path=actual_xlsx_path,
        status=beam_core.status,
    )


def _adapt_packages(packages: tuple[BeamEvaluationPackage, ...]) -> tuple[object, ...]:
    adapter = CheckAdapter()
    converted: list[object] = []

    for package in packages:
        output = adapter.adapt(package)
        converted.extend(_normalize_adapter_output(output))

    return tuple(converted)


def _normalize_adapter_output(output: object) -> tuple[object, ...]:
    if output is None:
        return ()

    if isinstance(output, tuple):
        return output  # type: ignore[return-value]

    if isinstance(output, list):
        return tuple(output)  # type: ignore[return-value]

    for attr in ("check_results", "checks", "results"):
        value = getattr(output, attr, None)
        if value is not None:
            return _normalize_adapter_output(value)

    if isinstance(output, Iterable) and not isinstance(output, (str, bytes, dict)):
        return tuple(output)  # type: ignore[return-value]

    return (output,)  # type: ignore[return-value]


def _write_json_report(checks: tuple[object, ...], json_path: Path) -> None:
    json_path.write_text(
        json.dumps(_report_payload(checks), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _report_payload(checks: tuple[object, ...]) -> dict[str, object]:
    json_checks = [_to_jsonable(check) for check in checks]
    return {
        "summary": {
            "total": len(checks),
            "ok": sum(1 for check in checks if getattr(check, "status", None) == "OK"),
            "fail": sum(1 for check in checks if getattr(check, "status", None) == "FAIL"),
            "no_data": sum(1 for check in checks if getattr(check, "status", None) == "NO_DATA"),
            "error": sum(1 for check in checks if getattr(check, "status", None) == "ERROR"),
        },
        "checks": json_checks,
    }


def _to_jsonable(value: object) -> object:
    if dataclasses.is_dataclass(value):
        return {
            field.name: _to_jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }

    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]

    return value


def _write_xlsx_report(checks: tuple[object, ...], xlsx_path: Path) -> Path | None:
    try:
        import openpyxl
    except ImportError:
        return None

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Checks"
    sheet.append([
        "component",
        "check_type",
        "status",
        "demand",
        "capacity",
        "ratio",
        "unit",
        "code_ref",
    ])

    for check in checks:
        sheet.append([
            getattr(check, "component", None),
            getattr(check, "check_type", None),
            getattr(check, "status", None),
            getattr(check, "demand", None),
            getattr(check, "capacity", None),
            getattr(check, "ratio", None),
            getattr(check, "unit", None),
            getattr(check, "code_ref", None),
        ])

    workbook.save(xlsx_path)
    return xlsx_path