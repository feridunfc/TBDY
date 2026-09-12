from __future__ import annotations

import pytest

from tbdy_engine.adapters.check_adapter import CheckAdapter


def _check(check_type: str, *, status: str = "OK", ratio: float | None = 0.5, messages=()):
    return {
        "check_type": check_type,
        "status": status,
        "demand": ratio,
        "capacity": 1.0 if ratio is not None else None,
        "ratio": ratio,
        "unit": "ratio",
        "code_ref": "TBDY:TEST",
        "messages": tuple(messages),
    }


def _package(component: str, story: str, *checks, evidence=None, messages=()):
    return {
        "component": component,
        "story": story,
        "section": "SYNTHETIC",
        "evidence": evidence or {"source": "synthetic_fixture"},
        "messages": tuple(messages),
        "checks": list(checks),
    }


def _by_id(rows):
    return {row.id: row for row in rows}


def test_column_traceable_fields_normalize_from_current_package_contract():
    rows = _by_id(
        CheckAdapter().adapt_all(
            {"packages": [_package("C1", "S1", _check("geometry"), _check("axial"), _check("pmm"), _check("shear"), _check("confinement"), _check("rebar_minimum"))]}
        )
    )
    for check_type in ("geometry", "axial", "pmm", "shear", "confinement", "rebar_minimum"):
        row = rows[f"C1:S1:{check_type}"]
        assert row.status == "OK"
        assert row.component == "C1"
        assert row.story == "S1"
        assert row.section == "SYNTHETIC"
        assert row.evidence == {"source": "synthetic_fixture"}


def test_column_rebar_minimum_is_emitted_only_when_package_contains_it():
    rows = CheckAdapter().adapt(_package("C1", "S1", _check("geometry"), _check("rebar_minimum")))
    assert {row.check_type for row in rows} == {"geometry", "rebar_minimum"}
    assert {row.id for row in rows} == {"C1:S1:geometry", "C1:S1:rebar_minimum"}


def test_beam_traceable_fields_normalize_from_current_package_contract():
    rows = CheckAdapter().adapt(_package("B1", "S1", _check("geometry"), _check("flexure"), _check("shear"), _check("ductility")))
    assert [row.check_type for row in rows] == ["geometry", "flexure", "shear", "ductility"]
    assert all(row.component == "B1" and row.story == "S1" for row in rows)


def test_adapter_does_not_synthesize_missing_checks():
    rows = CheckAdapter().adapt(_package("B1", "S1", _check("geometry")))
    assert len(rows) == 1
    assert rows[0].id == "B1:S1:geometry"


def test_adapt_all_mapping_values_are_current_packages():
    rows = CheckAdapter().adapt_all(
        {
            "results": {
                "COLUMN": _package("C1", "S1", _check("axial")),
                "BEAM": _package("B1", "S1", _check("shear")),
            }
        }
    )
    assert {row.id for row in rows} == {"C1:S1:axial", "B1:S1:shear"}


def test_package_and_check_messages_are_preserved_in_order():
    row = CheckAdapter().adapt(
        _package("C1", "S1", _check("axial", messages=("check-message",)), messages=("package-message",))
    )[0]
    assert row.messages == ("package-message", "check-message")


def test_evidence_mapping_is_preserved_without_inference():
    evidence = {"source_refs": ("fact:1",), "case": "S_E_1"}
    row = CheckAdapter().adapt(_package("C1", "S1", _check("axial"), evidence=evidence))[0]
    assert row.evidence == evidence


def test_missing_checks_fails_closed_instead_of_synthesizing_results():
    with pytest.raises(ValueError, match="package.checks is required"):
        CheckAdapter().adapt({"component": "C1", "story": "S1"})


def test_boolean_numeric_values_are_rejected():
    package = _package("C1", "S1", {"check_type": "axial", "status": "OK", "demand": True})
    with pytest.raises(ValueError, match="boolean values"):
        CheckAdapter().adapt(package)
