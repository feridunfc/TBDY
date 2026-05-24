from __future__ import annotations

import json
from pathlib import Path

from tbdy_engine.contracts.loader import EngineContractLoader


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "tests" / "golden" / "runtime_catalog.contract_first.json"
LEGACY_SOURCE_FILES = {
    "check_contract.yaml",
    "detailed_checklist.yaml",
    "combo_contract.yaml",
    "combo_usage_matrix.yaml",
}


def _project_catalog(catalog):
    return {
        "version": catalog.version,
        "counts": {
            "checks": len(catalog.checks),
            "evaluations": len(catalog.evaluations),
            "datasets": len(catalog.datasets),
            "combo_families": len(catalog.combo_families),
            "reports": len(catalog.reports),
        },
        "check_ids": sorted(catalog.checks),
        "enabled_check_ids": sorted(
            check_id for check_id, check in catalog.checks.items() if check.runner_enabled
        ),
        "evaluations": {
            key: {
                "enabled": value.enabled,
                "experimental": value.experimental,
                "depends_on_results": value.depends_on_results,
            }
            for key, value in sorted(catalog.evaluations.items())
        },
        "datasets": sorted(catalog.datasets),
        "combo_families": sorted(catalog.combo_families),
        "reports": sorted(catalog.reports),
        "source_files_by_check": {
            check_id: check.source_files
            for check_id, check in sorted(catalog.checks.items())
        },
    }


def test_contract_first_runtime_catalog_matches_golden():
    catalog = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    assert _project_catalog(catalog) == golden


def test_contract_first_runtime_catalog_has_no_legacy_source_files_or_values():
    catalog = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()

    for check in catalog.checks.values():
        assert not (set(check.source_files or []) & LEGACY_SOURCE_FILES)
        assert check.legacy_contract_id == ""
        assert check.legacy_canonical_check_name == ""
        assert check.legacy_matrix_key == ""
