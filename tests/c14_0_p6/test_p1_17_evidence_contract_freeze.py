from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tbdy_engine.features.evidence_contracts import (
    EvidenceContractError,
    assert_p1_17_evidence_contract,
    stable_json_sha256,
    stable_json_text,
)
from tools import smoke_live_feature_resolver as smoke
from tools import verify_p1_17_evidence_contract_freeze as verifier

P1_14_FIXTURE = Path("tests/fixtures/p1_14_story_base_complete_population.json")
P1_15_FIXTURE = Path("tests/fixtures/p1_15_material_design_basis_complete_population.json")


def _run_smoke(tmp_path: Path, fixture: Path, *, preferred_output_case: str = "Crack_SeisX_UpSoil") -> dict:
    out = tmp_path / fixture.stem
    rc = smoke.main(
        [
            "--input",
            str(fixture),
            "--out",
            str(out),
            "--target-component",
            "297",
            "--target-label",
            "B1",
            "--target-story",
            "+14.5",
            "--target-section",
            "B40x70",
            "--preferred-output-case",
            preferred_output_case,
        ]
    )
    assert rc == 0
    return json.loads((out / "feature_snapshot.json").read_text(encoding="utf-8"))


def _component(snapshot: dict, component_type: str) -> dict:
    return next(item for item in snapshot["snapshots"] if item["component_type"] == component_type)


def test_p1_15_fixture_material_evidence_satisfies_frozen_contract(tmp_path):
    snapshot = _run_smoke(tmp_path, P1_15_FIXTURE, preferred_output_case="Crack_SeisY_UpSoil")
    report = assert_p1_17_evidence_contract(snapshot, require=("material",))

    material = _component(snapshot, "material")
    assert report.ok
    assert "material" in report.validated_components
    assert material["features"]["component_section_name"]["value"] == "B40x70"
    assert material["features"]["component_section_type"]["value"] == "Beam"
    assert material["features"]["section_concrete_material_name"]["value"] == "C30/37"
    assert material["features"]["section_rebar_material_name"]["value"] == "B420C"
    assert material["features"]["concrete_fck_mpa"]["value"] == 30.0
    assert material["features"]["rebar_fyk_mpa"]["value"] == 500.0
    assert material["features"]["concrete_material_source_reference"]["value"] == (
        "LIVE_ETABS_DISPLAY_TABLE:Material Properties - Concrete Data:row=0:material=C30/37"
    )
    assert material["features"]["rebar_material_source_reference"]["value"] == (
        "LIVE_ETABS_DISPLAY_TABLE:Material Properties - Rebar Data:row=0:material=B420C"
    )


def test_p1_14_fixture_story_base_evidence_satisfies_frozen_contract(tmp_path):
    snapshot = _run_smoke(tmp_path, P1_14_FIXTURE, preferred_output_case="Crack_SeisX_UpSoil")
    report = assert_p1_17_evidence_contract(snapshot, require=("story_base",))

    story = _component(snapshot, "story")
    global_snapshot = _component(snapshot, "global")
    assert report.ok
    assert {"story", "global"}.issubset(set(report.validated_components))
    assert story["features"]["story_drift_value"]["value"] == pytest.approx(1.125)
    assert story["features"]["story_torsion_a1_coefficient"]["value"] == pytest.approx(1.069)
    assert global_snapshot["features"]["base_reaction_fx"]["value"] == pytest.approx(20396.1433)
    assert global_snapshot["features"]["base_reaction_fy"]["value"] == pytest.approx(5360.3225)


def test_source_reference_format_is_deterministic_and_stable(tmp_path):
    first = _run_smoke(tmp_path, P1_15_FIXTURE, preferred_output_case="Crack_SeisY_UpSoil")
    second = _run_smoke(tmp_path, P1_15_FIXTURE, preferred_output_case="Crack_SeisY_UpSoil")

    first_report = assert_p1_17_evidence_contract(first, require=("material",))
    second_report = assert_p1_17_evidence_contract(second, require=("material",))

    assert first_report.source_references == second_report.source_references
    assert stable_json_sha256(first) == stable_json_sha256(second)
    assert any(
        item == "LIVE_ETABS_DISPLAY_TABLE:Material Properties - Concrete Data:row=0:material=C30/37:column=Fc"
        for item in first_report.source_references
    )


def test_contract_rejects_missing_critical_material_source_reference(tmp_path):
    snapshot = _run_smoke(tmp_path, P1_15_FIXTURE, preferred_output_case="Crack_SeisY_UpSoil")
    material = _component(snapshot, "material")
    del material["features"]["concrete_material_source_reference"]

    with pytest.raises(EvidenceContractError, match="concrete_material_source_reference"):
        assert_p1_17_evidence_contract(snapshot, require=("material",))


def test_contract_rejects_check_result_or_verdict_keys_if_added(tmp_path):
    snapshot = _run_smoke(tmp_path, P1_14_FIXTURE, preferred_output_case="Crack_SeisX_UpSoil")
    drift = _component(snapshot, "story")["features"]["story_drift_value"]
    drift["check_results"] = [{"status": "PASS"}]
    drift["engineering_verdict"] = "PASS"

    with pytest.raises(EvidenceContractError, match="check_results"):
        assert_p1_17_evidence_contract(snapshot, require=("story_base",))


def test_fixture_replay_contract_verifier_works_without_live_etabs(tmp_path):
    out = tmp_path / "p1_17_verify"
    rc = verifier.main(["--out", str(out), "--p1-14-input", str(P1_14_FIXTURE), "--p1-15-input", str(P1_15_FIXTURE)])

    assert rc == 0
    summary = json.loads((out / "p1_17_evidence_contract_freeze_summary.json").read_text(encoding="utf-8"))
    assert summary["ok"] is True
    assert summary["live_etabs_required"] is False
    assert summary["analysis_run"] is False
    assert summary["design_run"] is False
    assert summary["etabs_model_mutated"] is False


def test_contract_data_is_json_safe_and_deterministic(tmp_path):
    snapshot = _run_smoke(tmp_path, P1_15_FIXTURE, preferred_output_case="Crack_SeisY_UpSoil")
    cloned = deepcopy(snapshot)

    first_text = stable_json_text(snapshot)
    second_text = stable_json_text(cloned)
    assert first_text == second_text
    assert stable_json_sha256(snapshot) == stable_json_sha256(cloned)
    assert json.loads(first_text) == snapshot


def test_gateway_vendor_files_are_outside_p1_17_contract_scope():
    touched_scope = {
        "tbdy_engine/features/evidence_contracts.py",
        "tests/c14_0_p6/test_p1_17_evidence_contract_freeze.py",
        "tools/verify_p1_17_evidence_contract_freeze.py",
    }

    assert all(not path.startswith("packages/etabs_gateway/") for path in touched_scope)
    assert all(not path.startswith("vendor/") for path in touched_scope)
