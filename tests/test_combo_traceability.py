from __future__ import annotations

from tbdy_engine.adapters.check_adapter import CheckAdapter


def _package(*, evidence):
    return {
        "component": "C1",
        "story": "S1",
        "section": "C40x60",
        "evidence": evidence,
        "checks": [
            {
                "check_type": "axial",
                "status": "OK",
                "demand": 720.0,
                "capacity": 1000.0,
                "ratio": 0.72,
                "unit": "kN",
                "code_ref": "TBDY 2018 7.3.2",
            }
        ],
    }


def test_explicit_combo_identity_is_preserved_inside_current_evidence_contract():
    evidence = {
        "governing_combo": "S_E_1",
        "combo_family": "S_E",
        "source_refs": ("combo:S_E_1",),
    }
    row = CheckAdapter().adapt(_package(evidence=evidence))[0]
    assert row.id == "C1:S1:axial"
    assert row.status == "OK"
    assert row.evidence["governing_combo"] == "S_E_1"
    assert row.evidence["combo_family"] == "S_E"
    assert row.evidence["source_refs"] == ("combo:S_E_1",)


def test_ke_combo_identity_is_preserved_without_family_rewriting():
    evidence = {"governing_combo": "K_E_2", "combo_family": "K_E"}
    row = CheckAdapter().adapt(
        {
            "component": "B1",
            "story": "S1",
            "evidence": evidence,
            "checks": [{"check_type": "shear", "status": "OK", "ratio": 0.69}],
        }
    )[0]
    assert row.id == "B1:S1:shear"
    assert row.evidence == evidence


def test_multiple_checks_share_exact_package_combo_evidence_without_copy_mutation():
    evidence = {"governing_combo": "S_E_SCWB", "combo_family": "S_E", "joint": "J1"}
    rows = CheckAdapter().adapt(
        {
            "component": "J1",
            "story": "S1",
            "evidence": evidence,
            "checks": [
                {"check_type": "column_capacity_hierarchy", "status": "WARNING", "ratio": 0.95},
                {"check_type": "beam_capacity_hierarchy", "status": "WARNING", "ratio": 0.95},
            ],
        }
    )
    assert len(rows) == 2
    assert all(row.evidence == evidence for row in rows)


def test_to_dict_contains_evidence_and_does_not_invent_legacy_combo_fields():
    evidence = {"governing_combo": "S_E_1", "combo_family": "S_E"}
    payload = CheckAdapter().adapt(_package(evidence=evidence))[0].to_dict()
    assert payload["evidence"] == evidence
    assert "governing_combo" not in payload
    assert "combo_family" not in payload


def test_missing_combo_evidence_remains_missing_instead_of_being_inferred():
    row = CheckAdapter().adapt(_package(evidence={"source_refs": ("fact:1",)}))[0]
    assert "governing_combo" not in row.evidence
    assert "combo_family" not in row.evidence


def test_unrelated_evidence_is_preserved_while_combo_fields_are_absent():
    evidence = {"force": "N_kn", "value": 720.0}
    row = CheckAdapter().adapt(_package(evidence=evidence))[0]
    assert row.evidence == evidence
    assert set(row.evidence) == {"force", "value"}
