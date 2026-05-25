from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.runtime.dataset_validator import (
    DatasetCheck,
    DatasetStatus,
    DatasetValidationResult,
    DatasetValidator,
)


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_IMPORT_PREFIXES = (
    "tbdy_engine.design",
    "tbdy_engine.etabs",
    "tbdy_engine.engine.context_builder",
    "tbdy_engine.adapters",
    "tbdy_engine.reports",
)
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


@dataclass(frozen=True)
class FakeContext:
    geometry: dict[str, object]
    topology: dict[str, object]


@dataclass(frozen=True)
class FakeCheck:
    id: str
    runner_enabled: bool
    required_datasets: tuple[str, ...]


@dataclass(frozen=True)
class FakeCatalog:
    checks: dict[str, FakeCheck]


def _by_dataset(result: DatasetValidationResult) -> dict[str, DatasetCheck]:
    return {check.dataset: check for check in result.checks}


def test_manual_validator_detects_present_missing_empty_datasets():
    context = FakeContext(geometry={"section_dims": {}}, topology={})
    validator = DatasetValidator(required_datasets=("geometry", "topology", "envelopes"))

    result = validator.validate(context)
    by_dataset = _by_dataset(result)

    assert by_dataset["geometry"].status is DatasetStatus.PRESENT
    assert by_dataset["topology"].status is DatasetStatus.EMPTY
    assert by_dataset["envelopes"].status is DatasetStatus.MISSING
    assert result.ok is False
    assert tuple(check.dataset for check in result.missing) == ("envelopes",)
    assert tuple(check.dataset for check in result.empty) == ("topology",)


def test_mapping_context_support():
    context = {
        "geometry": {"a": 1},
        "topology": {"columns": []},
        "envelopes": {},
    }
    validator = DatasetValidator(required_datasets=("geometry", "topology", "envelopes"))

    result = validator.validate(context)
    by_dataset = _by_dataset(result)

    assert by_dataset["geometry"].status is DatasetStatus.PRESENT
    assert by_dataset["topology"].status is DatasetStatus.PRESENT
    assert by_dataset["envelopes"].status is DatasetStatus.EMPTY


def test_non_container_scalar_values_count_as_present():
    context = {
        "design_basis": False,
        "story_count": 0,
    }
    validator = DatasetValidator(required_datasets=("design_basis", "story_count"))

    result = validator.validate(context)
    by_dataset = _by_dataset(result)

    assert by_dataset["design_basis"].status is DatasetStatus.PRESENT
    assert by_dataset["story_count"].status is DatasetStatus.PRESENT
    assert result.ok is True


def test_from_catalog_collects_enabled_required_datasets():
    catalog = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()
    validator = DatasetValidator.from_catalog(catalog)

    assert validator.required_datasets
    assert validator.required_datasets == tuple(sorted(validator.required_datasets))
    for dataset in ("geometry", "topology", "envelopes", "design_basis"):
        assert dataset in validator.required_datasets


def test_required_by_lists_check_ids_and_respects_enabled_only():
    fake_catalog = FakeCatalog(
        checks={
            "check_a": FakeCheck(
                id="check_a",
                runner_enabled=True,
                required_datasets=("geometry", "topology"),
            ),
            "check_b": FakeCheck(
                id="check_b",
                runner_enabled=True,
                required_datasets=("geometry",),
            ),
            "check_disabled": FakeCheck(
                id="check_disabled",
                runner_enabled=False,
                required_datasets=("envelopes",),
            ),
        }
    )

    enabled_validator = DatasetValidator.from_catalog(fake_catalog, enabled_only=True)
    enabled_result = enabled_validator.validate({})
    enabled_by_dataset = _by_dataset(enabled_result)

    assert enabled_by_dataset["geometry"].required_by == ("check_a", "check_b")
    assert enabled_by_dataset["topology"].required_by == ("check_a",)
    assert "envelopes" not in enabled_by_dataset

    all_validator = DatasetValidator.from_catalog(fake_catalog, enabled_only=False)
    all_result = all_validator.validate({})
    all_by_dataset = _by_dataset(all_result)

    assert all_by_dataset["envelopes"].required_by == ("check_disabled",)


def test_to_dict_has_stable_shape():
    result = DatasetValidationResult(
        checks=(
            DatasetCheck(
                dataset="geometry",
                status=DatasetStatus.PRESENT,
                required_by=("check_a",),
                message="Dataset 'geometry' is present.",
            ),
            DatasetCheck(
                dataset="topology",
                status=DatasetStatus.EMPTY,
                required_by=("check_a",),
                message="Dataset 'topology' is empty.",
            ),
            DatasetCheck(
                dataset="envelopes",
                status=DatasetStatus.MISSING,
                required_by=("check_b",),
                message="Dataset 'envelopes' is missing.",
            ),
        )
    )

    assert result.to_dict() == {
        "ok": False,
        "checks": [
            {
                "dataset": "geometry",
                "status": "PRESENT",
                "required_by": ["check_a"],
                "message": "Dataset 'geometry' is present.",
            },
            {
                "dataset": "topology",
                "status": "EMPTY",
                "required_by": ["check_a"],
                "message": "Dataset 'topology' is empty.",
            },
            {
                "dataset": "envelopes",
                "status": "MISSING",
                "required_by": ["check_b"],
                "message": "Dataset 'envelopes' is missing.",
            },
        ],
        "missing": ["envelopes"],
        "empty": ["topology"],
    }


def test_dataset_validator_has_no_forbidden_imports():
    source_path = ROOT / "tbdy_engine" / "runtime" / "dataset_validator.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    forbidden_imports = sorted(
        module_name
        for module_name in imported_modules
        if any(
            module_name == prefix or module_name.startswith(prefix + ".")
            for prefix in FORBIDDEN_IMPORT_PREFIXES
        )
    )

    assert forbidden_imports == []


def test_runtime_interface_audit_sees_dataset_validator_importable():
    from tests import test_runtime_interface_audit as audit

    assert audit.RUNTIME_INTERFACE_STATUS["DatasetValidator"] == "PRESENT_IMPORTABLE"


def test_no_second_contract_system_files_exist():
    for path in FORBIDDEN_SECOND_CONTRACT_FILES:
        assert not path.exists(), str(path.relative_to(ROOT))
