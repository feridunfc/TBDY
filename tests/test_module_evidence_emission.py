from __future__ import annotations

from tbdy_engine.adapters.check_adapter import CheckAdapter


def _package(component: str, checks, *, evidence=None, messages=()):
    return {
        "component": component,
        "story": "S1",
        "section": "SYNTHETIC",
        "evidence": {} if evidence is None else evidence,
        "messages": tuple(messages),
        "checks": list(checks),
    }


def _check(check_type: str, *, status="OK", ratio=0.8, messages=()):
    return {
        "check_type": check_type,
        "status": status,
        "demand": ratio,
        "capacity": 1.0,
        "ratio": ratio,
        "unit": "ratio",
        "code_ref": "TBDY 2018",
        "messages": tuple(messages),
    }


def test_column_module_shaped_package_without_explicit_evidence_stays_empty():
    rows = CheckAdapter().adapt(
        _package("C1", [_check("axial"), _check("pmm"), _check("shear")])
    )
    assert {row.check_type for row in rows} == {"axial", "pmm", "shear"}
    assert all(row.evidence == {} for row in rows)


def test_beam_module_shaped_package_without_explicit_evidence_stays_empty():
    rows = CheckAdapter().adapt(_package("B1", [_check("flexure"), _check("shear")]))
    assert {row.check_type for row in rows} == {"flexure", "shear"}
    assert all(row.evidence == {} for row in rows)


def test_scwb_diagnostic_evidence_is_preserved_exactly():
    evidence = {
        "joint_id": "J1",
        "direction": "X",
        "columns": ("C1", "C2"),
        "beams": ("B1", "B2"),
        "sum_mrc_knm": 950.0,
        "sum_mrb_knm": 830.0,
        "required_mrc_knm": 996.0,
        "reason_code": "scwb_ratio_below_limit",
    }
    rows = CheckAdapter().adapt(
        _package(
            "J1",
            [
                _check("column_capacity_hierarchy", status="WARNING", ratio=0.95),
                _check("beam_capacity_hierarchy", status="WARNING", ratio=0.95),
            ],
            evidence=evidence,
        )
    )
    assert len(rows) == 2
    assert all(row.status == "WARNING" for row in rows)
    assert all(row.evidence == evidence for row in rows)


def test_diagnostic_evidence_is_not_flattened_into_result_fields():
    evidence = {"joint_id": "J2", "direction": "Y", "reason_code": "diagnostic"}
    row = CheckAdapter().adapt(_package("J2", [_check("capacity_hierarchy")], evidence=evidence))[0]
    payload = row.to_dict()
    assert payload["evidence"] == evidence
    assert "joint_id" not in payload
    assert "direction" not in payload


def test_package_and_check_messages_are_serialized_without_losing_evidence():
    evidence = {"case": "K_E_2", "family": "K_E", "force": "V_max_kn", "value": 345.0}
    row = CheckAdapter().adapt(
        _package(
            "B1",
            [_check("shear", messages=("check evidence message",))],
            evidence=evidence,
            messages=("module evidence message",),
        )
    )[0]
    assert row.messages == ("module evidence message", "check evidence message")
    assert row.evidence == evidence
