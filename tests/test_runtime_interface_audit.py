from __future__ import annotations

import importlib
import importlib.util
import json
import pkgutil
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Iterable, Sequence

from openpyxl import load_workbook

from tbdy_engine.adapters.check_adapter import CheckAdapter, CheckResult
from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.reports.excel_reporter import ExcelReporter
from tbdy_engine.reports.json_reporter import JSONReporter


ROOT = Path(__file__).resolve().parents[1]
APPROVED_EVAL_RESULT_KEYS = ("results", "errors", "skipped", "execution_order", "cache_stats")
JSON_TOP_LEVEL_KEYS = [
    "report_metadata",
    "summary",
    "checks",
    "evaluation_errors",
    "evaluation_skipped",
    "execution_order",
    "cache_stats",
    "coverage",
    "distributions",
]
EXCEL_SHEETS_WITHOUT_PLANNED_REPORT = ["Summary", "Details", "Eval_Skipped", "Eval_Errors"]
FORBIDDEN_SECOND_CONTRACT_FILES = [
    ROOT / "docs" / "workbook_manifest.yaml",
    ROOT / "docs" / "sheet_contracts.yaml",
    ROOT / "docs" / "unit_contract.yaml",
    ROOT / "docs" / "evidence_contract.yaml",
    ROOT / "tbdy_engine" / "contracts" / "workbook_manifest.yaml",
    ROOT / "tbdy_engine" / "contracts" / "sheet_contracts.yaml",
    ROOT / "tbdy_engine" / "contracts" / "unit_contract.yaml",
    ROOT / "tbdy_engine" / "contracts" / "evidence_contract.yaml",
]
FORBIDDEN_AUDIT_IMPORT_PREFIXES = (
    "tbdy_engine.design",
    "tbdy_engine.etabs",
    "tbdy_engine.engine.context_builder",
)


class RuntimeAuditStatus(str, Enum):
    PRESENT_IMPORTABLE = "PRESENT_IMPORTABLE"
    PRESENT_NOT_IMPORTABLE = "PRESENT_NOT_IMPORTABLE"
    ABSENT = "ABSENT"


@dataclass(frozen=True)
class RuntimeObjectCandidate:
    module_name: str
    class_names: tuple[str, ...]


@dataclass(frozen=True)
class RuntimePackageInventory:
    exists: bool
    modules: tuple[str, ...]


def _catalog():
    return EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()


def _model_to_dict(obj: object) -> dict[str, object]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()  # type: ignore[no-any-return, attr-defined]
    if hasattr(obj, "dict"):
        return obj.dict()  # type: ignore[no-any-return, attr-defined]
    if hasattr(obj, "__dict__"):
        return dict(vars(obj))
    return {}


def _module_spec_exists(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _import_module(module_name: str) -> ModuleType:
    return importlib.import_module(module_name)


def _runtime_object_status(candidates: Sequence[RuntimeObjectCandidate]) -> RuntimeAuditStatus:
    module_found = False
    import_failed = False

    for candidate in candidates:
        if not _module_spec_exists(candidate.module_name):
            continue
        module_found = True
        try:
            module = _import_module(candidate.module_name)
        except Exception:
            import_failed = True
            continue
        if any(hasattr(module, class_name) for class_name in candidate.class_names):
            return RuntimeAuditStatus.PRESENT_IMPORTABLE

    if module_found or import_failed:
        return RuntimeAuditStatus.PRESENT_NOT_IMPORTABLE
    return RuntimeAuditStatus.ABSENT


def _runner_v2_status() -> RuntimeAuditStatus:
    runner_path = ROOT / "tbdy_engine" / "runner_v2.py"
    if not runner_path.exists():
        return RuntimeAuditStatus.ABSENT
    text = runner_path.read_text(encoding="utf-8")
    assert text.strip(), "runner_v2.py is present but empty"
    return RuntimeAuditStatus.PRESENT_IMPORTABLE


def _runtime_package_inventory() -> RuntimePackageInventory:
    runtime_dir = ROOT / "tbdy_engine" / "runtime"
    if not runtime_dir.exists():
        return RuntimePackageInventory(exists=False, modules=())
    modules = tuple(sorted(module.name for module in pkgutil.iter_modules([str(runtime_dir)])))
    return RuntimePackageInventory(exists=True, modules=modules)


def _runtime_interface_status() -> dict[str, RuntimeAuditStatus]:
    return {
        "DatasetValidator": _runtime_object_status(
            (
                RuntimeObjectCandidate("tbdy_engine.runtime.dataset_validator", ("DatasetValidator",)),
                RuntimeObjectCandidate("tbdy_engine.runtime.validator", ("DatasetValidator",)),
            )
        ),
        "EvaluationDAG": _runtime_object_status(
            (RuntimeObjectCandidate("tbdy_engine.runtime.dag", ("EvaluationDAG",)),)
        ),
        "Scheduler": _runtime_object_status(
            (
                RuntimeObjectCandidate("tbdy_engine.runtime.scheduler", ("Scheduler", "RuntimeScheduler")),
            )
        ),
        "EvaluationResult": _runtime_object_status(
            (
                RuntimeObjectCandidate("tbdy_engine.runtime.evaluation_result", ("EvaluationResult",)),
                RuntimeObjectCandidate("tbdy_engine.runtime.results", ("EvaluationResult",)),
            )
        ),
        "runner_v2": _runner_v2_status(),
    }


RUNTIME_INTERFACE_STATUS = _runtime_interface_status()


def _minimal_eval_results() -> dict[str, object]:
    return {
        "results": {
            "COLUMN_DESIGN": {
                "outputs": [
                    {
                        "label": "C1",
                        "story": "S1",
                        "checks": {
                            "geometry": {
                                "status": "OK",
                                "ratio": 0.42,
                                "value": 42.0,
                                "limit": 100.0,
                                "unit": "ratio",
                                "message": "audit fixture with explicit source",
                                "source": "runtime-interface-audit",
                                "evaluation_level": "DESIGN_LEVEL",
                                "evidence": {"audit_fixture": "de_facto_eval_result_shape"},
                            }
                        },
                    }
                ]
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["COLUMN_DESIGN"],
        "cache_stats": {},
    }


def _adapted_rows(eval_results: dict[str, object] | None = None) -> list[CheckResult]:
    return CheckAdapter(_catalog()).adapt_all(eval_results or _minimal_eval_results())


def _find_row(rows: Iterable[CheckResult], check_id: str) -> CheckResult:
    for row in rows:
        if row.check_id == check_id:
            return row
    raise AssertionError(f"Expected CheckResult row not emitted: {check_id}")


def test_contract_loader_exposes_single_runtime_catalog_source():
    catalog = _catalog()

    for attribute in ("checks", "reports", "datasets", "combo_families", "evaluations"):
        value = getattr(catalog, attribute)
        assert value, f"Runtime catalog does not expose populated {attribute}"

    enabled_checks = [check_id for check_id, check in catalog.checks.items() if check.runner_enabled]
    assert enabled_checks, "Runtime catalog should expose at least one enabled check"

    full_engine_report = catalog.reports.get("full_engine_report")
    assert full_engine_report is not None
    assert "evidence" in full_engine_report.include_fields

    for forbidden_path in FORBIDDEN_SECOND_CONTRACT_FILES:
        assert not forbidden_path.exists(), str(forbidden_path.relative_to(ROOT))


def test_runtime_flow_object_availability_is_explicit():
    allowed_statuses = {status.value for status in RuntimeAuditStatus}

    assert set(RUNTIME_INTERFACE_STATUS) == {
        "DatasetValidator",
        "EvaluationDAG",
        "Scheduler",
        "EvaluationResult",
        "runner_v2",
    }
    assert {status.value for status in RUNTIME_INTERFACE_STATUS.values()} <= allowed_statuses


def test_check_adapter_input_boundary_documents_de_facto_eval_result_shape():
    eval_results = _minimal_eval_results()
    assert tuple(eval_results) == APPROVED_EVAL_RESULT_KEYS

    rows = _adapted_rows(eval_results)
    geometry = _find_row(rows, "column_geometry")

    assert geometry.check_name == "geometry"
    assert geometry.evaluation == "COLUMN_DESIGN"
    assert geometry.element_label == "C1"
    assert geometry.story == "S1"
    assert geometry.status == "OK"
    assert geometry.evidence == {"audit_fixture": "de_facto_eval_result_shape"}


def test_reporters_accept_check_rows_plus_eval_results_shape_without_runtime_objects(tmp_path: Path):
    eval_results = _minimal_eval_results()
    geometry = _find_row(_adapted_rows(eval_results), "column_geometry")
    checks = [geometry]

    json_path = tmp_path / "engine_report.json"
    excel_path = tmp_path / "engine_report.xlsx"
    JSONReporter(write_history=False).generate(checks, eval_results, output_path=str(json_path))
    ExcelReporter(write_history=False).generate(checks, eval_results, output_path=str(excel_path))

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert list(payload) == JSON_TOP_LEVEL_KEYS
    assert payload["checks"][0]["evidence"] == {"audit_fixture": "de_facto_eval_result_shape"}
    assert payload["execution_order"] == ["COLUMN_DESIGN"]
    assert payload["cache_stats"] == {}

    workbook = load_workbook(excel_path)
    assert workbook.sheetnames == EXCEL_SHEETS_WITHOUT_PLANNED_REPORT
    details_header = [cell.value for cell in workbook["Details"][1]]
    assert "evidence" in details_header


def test_runner_v2_status_is_explicit():
    status = RUNTIME_INTERFACE_STATUS["runner_v2"]
    assert status in {RuntimeAuditStatus.ABSENT, RuntimeAuditStatus.PRESENT_IMPORTABLE}

    runner_path = ROOT / "tbdy_engine" / "runner_v2.py"
    if status is RuntimeAuditStatus.ABSENT:
        assert not runner_path.exists()
    else:
        assert runner_path.exists()
        assert runner_path.read_text(encoding="utf-8").strip()


def test_audit_does_not_require_forbidden_module_imports():
    forbidden_before = {
        name for name in sys.modules if name.startswith(FORBIDDEN_AUDIT_IMPORT_PREFIXES)
    }

    catalog = _catalog()
    rows = _adapted_rows(_minimal_eval_results())

    forbidden_after = {
        name for name in sys.modules if name.startswith(FORBIDDEN_AUDIT_IMPORT_PREFIXES)
    }
    assert catalog.checks
    assert rows
    assert forbidden_before == forbidden_after == set()


def test_architecture_gap_report_is_encoded_as_test_constants():
    allowed_statuses = set(RuntimeAuditStatus)

    assert set(RUNTIME_INTERFACE_STATUS) == {
        "DatasetValidator",
        "EvaluationDAG",
        "Scheduler",
        "EvaluationResult",
        "runner_v2",
    }
    for object_name, status in RUNTIME_INTERFACE_STATUS.items():
        assert object_name
        assert status in allowed_statuses


def test_runtime_package_inventory_is_non_throwing_and_deterministic():
    inventory = _runtime_package_inventory()

    if not inventory.exists:
        assert inventory.modules == ()
        return

    assert inventory.modules == tuple(sorted(inventory.modules))
    assert len(inventory.modules) == len(set(inventory.modules))
