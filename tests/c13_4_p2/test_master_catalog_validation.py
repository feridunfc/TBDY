from __future__ import annotations

from pathlib import Path

import pytest

from tbdy_engine.catalogs.loader import GEOMETRY_CHECK_IDS, load_modular_catalog, summarize_master_catalog, validate_master_catalog
from tbdy_engine.tools.validate_contract_constitution import (
    ContractValidationError,
    main,
    validate_modular_catalogs,
)

ROOT = Path(__file__).resolve().parents[2]
MODULAR_ROOT = ROOT / "tbdy_engine" / "catalogs" / "modular"
CATALOG_ROOT = ROOT / "tbdy_engine" / "catalogs"


def test_merged_master_catalog_contains_required_geometry_checks_and_features():
    master = load_modular_catalog(MODULAR_ROOT)
    validate_master_catalog(master)
    assert GEOMETRY_CHECK_IDS.issubset(set(master["checks"]))
    for check_id in GEOMETRY_CHECK_IDS:
        for feature_id in master["checks"][check_id]["required_features"]:
            assert feature_id in master["features"]


def test_summary_reports_counts_without_silent_failures():
    master = load_modular_catalog(MODULAR_ROOT)
    summary = summarize_master_catalog(master)
    assert summary["checks"] == 4
    assert summary["features"] == 4
    assert summary["duplicate_ids"] == 0
    assert summary["missing_feature_references"] == 0


def test_constitution_validator_integrates_modular_catalogs():
    summary = validate_modular_catalogs(CATALOG_ROOT)

    assert summary["enabled"] is True
    assert summary["checks"] == 4
    assert summary["features"] == 4
    assert summary["duplicate_ids"] == 0
    assert summary["missing_feature_references"] == 0


def test_constitution_cli_prints_modular_catalog_summary(capsys):
    assert main([]) == 0

    out = capsys.readouterr().out
    assert "Contract Constitution v1.0 C5.6 validation: OK" in out
    assert "Modular Catalog validation: OK" in out
    assert "Modular checks:" in out
    assert "Modular features:" in out


def test_modular_validation_failure_is_reported_as_contract_validation_error(tmp_path):
    modular_root = tmp_path / "modular"
    modular_root.mkdir()
    (modular_root / "bad.yaml").write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(ContractValidationError) as exc:
        validate_modular_catalogs(tmp_path)

    message = str(exc.value)
    assert "Modular catalog validation failed" in message
    assert "bad.yaml" in message
    assert "YAML object" in message
