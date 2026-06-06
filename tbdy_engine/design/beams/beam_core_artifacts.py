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



def _check_identifier(check: object) -> str:
    """Return stable report check identifier."""
    value = getattr(check, "id", None)
    if value not in (None, ""):
        return str(value)

    component = getattr(check, "component", None)
    story = getattr(check, "story", None)
    check_type = getattr(check, "check_type", None)
    if component not in (None, "") and story not in (None, "") and check_type not in (None, ""):
        return f"{component}:{story}:{check_type}"

    name = getattr(check, "name", None) or getattr(check, "check_id", None) or check_type
    if name not in (None, ""):
        return str(name)

    return "unknown_check"


def _evidence_ref(check: object) -> str:
    """Return compact evidence reference for a check."""
    component = getattr(check, "component", None)
    check_type = getattr(check, "check_type", None)

    evidence = getattr(check, "evidence", None)
    if isinstance(evidence, Mapping):
        story = evidence.get("story") or getattr(check, "story", None)
    else:
        story = getattr(check, "story", None)

    if component not in (None, "") and check_type not in (None, ""):
        if story not in (None, ""):
            return f"{component}:{story}:{check_type}"
        return f"{component}:{check_type}"

    return _check_identifier(check)


def _strip_shared_evidence(value: object) -> dict[str, object]:
    """Return check evidence without repeated full evidence maps."""
    jsonable = _to_jsonable(value)
    if not isinstance(jsonable, dict):
        return {}

    stripped = dict(jsonable)
    stripped.pop("core_check_evidence_by_id", None)
    return stripped


def _per_check_evidence(check: object, evidence_ref: str) -> dict[str, object]:
    """Return evidence only for the current check."""
    evidence = getattr(check, "evidence", None)
    if not isinstance(evidence, Mapping):
        return {}

    full_map = evidence.get("core_check_evidence_by_id")
    if isinstance(full_map, Mapping):
        check_type = getattr(check, "check_type", None)
        candidates = [
            evidence_ref,
            f"{getattr(check, 'component', '')}:{check_type}",
            str(check_type or ""),
        ]
        for key in candidates:
            if key in full_map and isinstance(full_map[key], Mapping):
                return _strip_shared_evidence(full_map[key])

    return _strip_shared_evidence(evidence)


def _compact_check_payload(check: object) -> dict[str, object]:
    """Return report check row with compact evidence and explicit ratio semantics."""
    payload = _to_jsonable(check)
    if not isinstance(payload, dict):
        payload = {"value": payload}

    evidence_ref = _evidence_ref(check)
    payload["id"] = payload.get("id") or _check_identifier(check)
    payload["evidence_ref"] = evidence_ref
    payload["evidence"] = _per_check_evidence(check, evidence_ref)
    payload["ratio_type"] = _ratio_type(check)
    payload["pass_rule"] = _pass_rule(check, str(payload["ratio_type"]))

    return payload


def _ratio_type(check: object) -> str:
    """Return ratio orientation for report users."""
    check_type = str(getattr(check, "check_type", "") or "")
    demand = getattr(check, "demand", None)
    capacity = getattr(check, "capacity", None)

    if "_ge_" in check_type or check_type.endswith("_ge_required") or check_type.endswith("_ge_min"):
        if _is_number(demand) and _is_number(capacity) and float(capacity) != 0.0:
            return "demand_over_capacity"
        return "actual_over_minimum"

    if "_le_" in check_type or check_type.endswith("_le_limit") or check_type.endswith("_le_max"):
        return "demand_over_capacity"

    if check_type.startswith("beam_geometry_min_") or "min_" in check_type:
        return "actual_over_minimum"

    if "rho_ge" in check_type:
        return "actual_over_minimum"

    if "rho_le" in check_type:
        return "actual_over_limit"

    return "demand_over_capacity"


def _pass_rule(check: object, ratio_type: str) -> str:
    """Return explicit pass rule for the report ratio."""
    check_type = str(getattr(check, "check_type", "") or "")

    if ratio_type == "actual_over_minimum":
        return "ratio >= 1.0"

    if ratio_type == "actual_over_limit":
        return "ratio <= 1.0"

    if "_le_" in check_type or ratio_type == "demand_over_capacity":
        return "ratio <= 1.0"

    if "_ge_" in check_type:
        return "ratio >= 1.0"

    return "status-specific"


def _is_number(value: object) -> bool:
    try:
        float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return True


def _evidence_by_id(checks: tuple[object, ...]) -> dict[str, object]:
    """Return centralized evidence map keyed by evidence_ref."""
    out: dict[str, object] = {}
    for check in checks:
        ref = _evidence_ref(check)
        out[ref] = _per_check_evidence(check, ref)
    return out
def _report_payload(checks: tuple[object, ...]) -> dict[str, object]:
    json_checks = [_compact_check_payload(check) for check in checks]
    return {
        "summary": {
            "total": len(checks),
            "ok": sum(1 for check in checks if getattr(check, "status", None) == "OK"),
            "fail": sum(1 for check in checks if getattr(check, "status", None) == "FAIL"),
            "no_data": sum(1 for check in checks if getattr(check, "status", None) == "NO_DATA"),
            "error": sum(1 for check in checks if getattr(check, "status", None) == "ERROR"),
        },
        "checks": json_checks,
        "evidence_by_id": _evidence_by_id(checks),
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
        "id",
        "component",
        "story",
        "section",
        "check_type",
        "status",
        "demand",
        "capacity",
        "ratio",
        "ratio_type",
        "pass_rule",
        "unit",
        "code_ref",
        "evidence_ref",
        "messages",
    ])

    for check in checks:
        ratio_type = _ratio_type(check)
        sheet.append([
            _check_identifier(check),
            getattr(check, "component", None),
            getattr(check, "story", None),
            getattr(check, "section", None),
            getattr(check, "check_type", None),
            getattr(check, "status", None),
            getattr(check, "demand", None),
            getattr(check, "capacity", None),
            getattr(check, "ratio", None),
            ratio_type,
            _pass_rule(check, ratio_type),
            getattr(check, "unit", None),
            getattr(check, "code_ref", None),
            _evidence_ref(check),
            "; ".join(str(message) for message in (getattr(check, "messages", None) or [])),
        ])

    workbook.save(xlsx_path)
    return xlsx_path