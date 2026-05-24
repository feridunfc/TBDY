from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.contracts.loader import EngineContractLoader


ROOT = Path(__file__).resolve().parents[1]
COMBO_BEARING_CHECKS = {
    "column_axial": ["S_E"],
    "column_pmm": ["S_E"],
    "column_shear": ["K_E"],
    "column_capacity_hierarchy": ["S_E"],
    "beam_flexure": ["S_E"],
    "beam_shear": ["K_E"],
    "beam_capacity_hierarchy": ["S_E"],
}
STRUCTURED_COMBO_FIELDS = {"governing_combo", "combo_family", "evidence"}


def _model_to_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except TypeError:
            pass
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "__dict__"):
        return dict(vars(obj))
    return {}


def _catalog():
    return EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()


def _adapter():
    return CheckAdapter(_catalog())


def _checks_by_id() -> dict[str, dict[str, Any]]:
    return _model_to_dict(_catalog()).get("checks", {})


def _enabled_check_ids() -> set[str]:
    return {
        check_id
        for check_id, check in _checks_by_id().items()
        if _model_to_dict(check).get("runner_enabled", True)
    }


def _by_check_id(rows):
    return {row.check_id: row for row in rows}


def _combo_payload(*, status="OK", ratio=0.8, source="synthetic_combo_fixture", combo="S_E_1", family="S_E"):
    return {
        "status": status,
        "ratio": ratio,
        "value": ratio,
        "limit": 1.0,
        "unit": "ratio",
        "message": f"combo evidence fixture for {family}",
        "action": "",
        "evaluation_level": "DESIGN_LEVEL",
        "source": source,
        "governing_combo": combo,
        "combo_family": family,
        "evidence": {"case": combo, "family": family},
    }


def _plain_payload(*, status="OK", ratio=0.8, source="synthetic_plain_fixture"):
    return {
        "status": status,
        "ratio": ratio,
        "value": ratio,
        "limit": 1.0,
        "unit": "ratio",
        "message": "plain fixture without structured combo evidence",
        "action": "",
        "evaluation_level": "DESIGN_LEVEL",
        "source": source,
    }


def test_runtime_catalog_preserves_uses_combo_for_enabled_combo_bearing_checks():
    checks = _checks_by_id()

    for check_id, expected_combo in COMBO_BEARING_CHECKS.items():
        check = _model_to_dict(checks[check_id])
        assert check["runner_enabled"] is True
        assert check["uses_combo"] == expected_combo


def test_column_axial_combo_payload_preserves_explicit_structured_combo_fields():
    eval_results = {
        "results": {
            "COLUMN_DESIGN": {
                "outputs": [
                    {
                        "label": "C1",
                        "story": "S1",
                        "checks": {
                            "axial": _combo_payload(combo="S_E_1", family="S_E"),
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

    row = _by_check_id(_adapter().adapt_all(eval_results))["column_axial"]

    assert row.check_id == "column_axial"
    assert row.status == "OK"
    assert row.source == "synthetic_combo_fixture"
    assert row.governing_combo == "S_E_1"
    assert row.combo_family == "S_E"
    assert row.evidence == {"case": "S_E_1", "family": "S_E"}


def test_beam_shear_ke_combo_payload_preserves_explicit_structured_combo_fields():
    eval_results = {
        "results": {
            "BEAM_DESIGN": {
                "outputs": [
                    {
                        "label": "B1",
                        "story": "S1",
                        "checks": {
                            "shear": _combo_payload(combo="K_E_2", family="K_E"),
                        },
                    }
                ]
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["BEAM_DESIGN"],
        "cache_stats": {},
    }

    row = _by_check_id(_adapter().adapt_all(eval_results))["beam_shear"]

    assert row.check_id == "beam_shear"
    assert row.status == "OK"
    assert row.source == "synthetic_combo_fixture"
    assert row.governing_combo == "K_E_2"
    assert row.combo_family == "K_E"
    assert row.evidence == {"case": "K_E_2", "family": "K_E"}


def test_scwb_direct_combo_payload_preserves_explicit_structured_combo_fields():
    eval_results = {
        "results": {
            "SCWB_CHECK": {
                "column_capacity_hierarchy": [
                    {
                        **_combo_payload(combo="S_E_SCWB_COLUMN", family="S_E"),
                        "element_label": "J1",
                        "story": "S1",
                    }
                ],
                "beam_capacity_hierarchy": [
                    {
                        **_combo_payload(combo="S_E_SCWB_BEAM", family="S_E"),
                        "element_label": "J1",
                        "story": "S1",
                    }
                ],
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["SCWB_CHECK"],
        "cache_stats": {},
    }

    rows = _by_check_id(_adapter().adapt_all(eval_results))

    assert rows["column_capacity_hierarchy"].governing_combo == "S_E_SCWB_COLUMN"
    assert rows["column_capacity_hierarchy"].combo_family == "S_E"
    assert rows["column_capacity_hierarchy"].evidence == {
        "case": "S_E_SCWB_COLUMN",
        "family": "S_E",
    }
    assert rows["beam_capacity_hierarchy"].governing_combo == "S_E_SCWB_BEAM"
    assert rows["beam_capacity_hierarchy"].combo_family == "S_E"
    assert rows["beam_capacity_hierarchy"].evidence == {
        "case": "S_E_SCWB_BEAM",
        "family": "S_E",
    }


def test_check_result_to_dict_includes_explicit_combo_evidence_fields():
    eval_results = {
        "results": {
            "COLUMN_DESIGN": {
                "outputs": [
                    {
                        "label": "C1",
                        "story": "S1",
                        "checks": {
                            "axial": _combo_payload(combo="S_E_1", family="S_E"),
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

    row_dict = _by_check_id(_adapter().adapt_all(eval_results))["column_axial"].to_dict()

    assert row_dict["check_id"] == "column_axial"
    assert row_dict["governing_combo"] == "S_E_1"
    assert row_dict["combo_family"] == "S_E"
    assert row_dict["evidence"] == {"case": "S_E_1", "family": "S_E"}


def test_missing_structured_combo_evidence_fields_remain_none():
    eval_results = {
        "results": {
            "COLUMN_DESIGN": {
                "outputs": [
                    {
                        "label": "C1",
                        "story": "S1",
                        "checks": {
                            "axial": _plain_payload(),
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

    row = _by_check_id(_adapter().adapt_all(eval_results))["column_axial"]

    assert row.governing_combo is None
    assert row.combo_family is None
    assert row.evidence is None


def test_combo_bearing_checks_remain_active_after_sprint_3d():
    assert COMBO_BEARING_CHECKS.keys() <= _enabled_check_ids()
