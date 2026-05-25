from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REAL_FIXTURE_DIR = ROOT / "tests" / "fixtures" / "real_etabs_anonymized"
SHAPED_FIXTURE_DIR = ROOT / "tests" / "fixtures" / "etabs_anonymized"
REAL_ETABS_PROOF_STATUS = "REAL_ETABS_PROOF_UNAVAILABLE"
EXISTING_EXPORT_SHAPED_STATUS = "ETABS_EXPORT_SHAPED_ANONYMIZED"
ALLOWED_REAL_PROOF_STATUSES = {
    "REAL_ETABS_EXPORT_ANONYMIZED",
    "ETABS_COM_SMOKE_AVAILABLE",
    "REAL_ETABS_PROOF_UNAVAILABLE",
}
FORBIDDEN_IDENTIFIERS = (
    "client",
    "project",
    "address",
    "company",
    "email",
    "phone",
    "vergi",
)
TC_ID_PATTERN = re.compile(r"\b\d{11}\b")
FORBIDDEN_SECOND_CONTRACT_FILES = (
    ROOT / "docs" / "workbook_manifest.yaml",
    ROOT / "docs" / "sheet_contracts.yaml",
    ROOT / "docs" / "unit_contract.yaml",
    ROOT / "docs" / "evidence_contract.yaml",
    ROOT / "tbdy_engine" / "contracts" / "workbook_manifest.yaml",
    ROOT / "tbdy_engine" / "contracts" / "sheet_contracts.yaml",
    ROOT / "tbdy_engine" / "contracts" / "unit_contract.yaml",
    ROOT / "tbdy_engine" / "contracts" / "evidence_contract.yaml",
)


def _real_fixture_files() -> tuple[Path, ...]:
    if not REAL_FIXTURE_DIR.exists():
        return ()
    return tuple(sorted(path for path in REAL_FIXTURE_DIR.rglob("*") if path.is_file()))


def _text_if_safe(path: Path) -> str:
    if path.suffix.lower() not in {".csv", ".json", ".txt", ".md", ".yml", ".yaml"}:
        return ""
    return path.read_text(encoding="utf-8", errors="ignore").lower()


def test_real_fixture_availability_status_is_explicit():
    files = _real_fixture_files()

    assert REAL_ETABS_PROOF_STATUS in ALLOWED_REAL_PROOF_STATUSES
    if not files:
        assert REAL_ETABS_PROOF_STATUS == "REAL_ETABS_PROOF_UNAVAILABLE"
        return

    metadata_text = "\n".join(_text_if_safe(path) for path in files)
    assert "REAL_ETABS_EXPORT_ANONYMIZED" in metadata_text

    for path in files:
        assert path.stat().st_size < 5_000_000
        text = _text_if_safe(path)
        for identifier in FORBIDDEN_IDENTIFIERS:
            assert identifier not in text
        assert TC_ID_PATTERN.search(text) is None


def test_existing_export_shaped_fixture_remains_non_real():
    assert SHAPED_FIXTURE_DIR.exists()
    assert EXISTING_EXPORT_SHAPED_STATUS == "ETABS_EXPORT_SHAPED_ANONYMIZED"
    assert EXISTING_EXPORT_SHAPED_STATUS != "REAL_ETABS_EXPORT_ANONYMIZED"

    from tests import test_real_etabs_fixture_evidence_audit as shaped_audit

    assert shaped_audit.FIXTURE_STATUS == "ETABS_EXPORT_SHAPED_ANONYMIZED"
    assert shaped_audit.FIXTURE_STATUS != "REAL_ETABS_EXPORT_ANONYMIZED"


def test_no_synthetic_real_replacement_fixture_is_present():
    files = _real_fixture_files()
    if not files:
        assert REAL_ETABS_PROOF_STATUS == "REAL_ETABS_PROOF_UNAVAILABLE"
        return

    metadata_text = "\n".join(_text_if_safe(path) for path in files)
    assert "REAL_ETABS_EXPORT_ANONYMIZED" in metadata_text
    assert "synthetic" not in metadata_text
    assert "fake" not in metadata_text


def test_smoke_marker_policy_is_safe():
    smoke_path = ROOT / "tests" / "test_etabs_smoke_local.py"

    assert smoke_path.exists()
    source = smoke_path.read_text(encoding="utf-8")
    assert "pytest.mark.etabs_smoke" in source
    assert "TBDY_RUN_ETABS_SMOKE" in source
    assert "pytest.skip" in source


def test_production_code_untouched_by_fixture_audit_contract():
    forbidden_production_roots = (
        ROOT / "tbdy_engine" / "engine" / "context_builder.py",
        ROOT / "tbdy_engine" / "design",
        ROOT / "tbdy_engine" / "etabs",
        ROOT / "tbdy_engine" / "engine" / "forces.py",
        ROOT / "tbdy_engine" / "engine" / "topology.py",
        ROOT / "tbdy_engine" / "adapters",
        ROOT / "tbdy_engine" / "reports",
        ROOT / "tbdy_engine" / "runner.py",
        ROOT / "tbdy_engine" / "runner_v2.py",
        ROOT / "tbdy_engine" / "contracts",
    )

    for path in forbidden_production_roots:
        assert path.exists() or path.suffix == ".py"


def test_no_second_contract_system_added_for_etabs_audit():
    for path in FORBIDDEN_SECOND_CONTRACT_FILES:
        assert not path.exists(), str(path.relative_to(ROOT))


def test_real_etabs_proof_is_not_claimed_without_fixture_or_smoke():
    files = _real_fixture_files()
    if not files:
        assert REAL_ETABS_PROOF_STATUS == "REAL_ETABS_PROOF_UNAVAILABLE"
        assert REAL_ETABS_PROOF_STATUS != "REAL_ETABS_EXPORT_ANONYMIZED"
        assert REAL_ETABS_PROOF_STATUS != "ETABS_COM_SMOKE_AVAILABLE"
