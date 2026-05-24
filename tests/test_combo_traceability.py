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


def test_runtime_catalog_preserves_uses_combo_for_enabled_combo_bearing_checks():
    checks = _checks_by_id()

    for check_id, expected_combo in COMBO_BEARING_CHECKS.items():
        check = _model_to_dict(checks[check_id])
        assert check["runner_enabled"] is True
        assert check["uses_combo"] == expected_combo


def test_column_axial_combo_payload_normalizes_but_structured_combo_fields_are_not_preserved():
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
    for field in STRUCTURED_COMBO_FIELDS:
        assert not hasattr(row, field)


def test_beam_shear_ke_combo_payload_normalizes_but_structured_combo_fields_are_not_preserved():
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
    for field in STRUCTURED_COMBO_FIELDS:
        assert not hasattr(row, field)


def test_scwb_direct_combo_payload_normalizes_but_structured_combo_fields_are_not_preserved():
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

    for check_id in ["column_capacity_hierarchy", "beam_capacity_hierarchy"]:
        row = rows[check_id]
        assert row.check_id == check_id
        assert row.status == "OK"
        assert row.source == "synthetic_combo_fixture"
        for field in STRUCTURED_COMBO_FIELDS:
            assert not hasattr(row, field)


def test_check_result_to_dict_does_not_include_combo_evidence_fields_yet():
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
    assert not (STRUCTURED_COMBO_FIELDS & set(row_dict))


def test_combo_bearing_checks_remain_active_after_sprint_3d():
    assert COMBO_BEARING_CHECKS.keys() <= _enabled_check_ids()
