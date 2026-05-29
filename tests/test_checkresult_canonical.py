from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import get_type_hints

import pytest

from tbdy_engine.adapters.check_adapter import CheckResult


REQUIRED_FIELDS = {
    "id",
    "component",
    "check_type",
    "status",
    "demand",
    "capacity",
    "ratio",
    "evidence",
    "messages",
}

OPTIONAL_FIELDS = {
    "story",
    "section",
    "unit",
    "code_ref",
}

FORBIDDEN_FIELDS = {
    "runtime_bridge",
    "execution_order",
    "cache_stats",
    "coverage",
    "distributions",
    "report_contract",
    "evaluation_errors",
    "evaluation_skipped",
    "scheduler_metadata",
    "dag_metadata",
    "contract_metadata",
    "history_metadata",
    "legacy_contract_id",
    "report_section",
    "evaluation_level",
    "source",
    "severity",
    "category",
    "action",
    "tbdy_ref",
    "element_label",
    "value",
    "limit",
}


def _sample() -> CheckResult:
    return CheckResult(
        id="beam_geometry:B1:S1",
        component="B1",
        check_type="beam_geometry",
        status="OK",
        demand=300.0,
        capacity=250.0,
        ratio=1.2,
        evidence={"source_table": "beam_design_summary", "source_row": 1},
        messages=("geometry ok",),
        story="S1",
        section="B25x50",
        unit="mm",
        code_ref="TBDY 2018 §7.4.1",
    )


def test_checkresult_is_frozen_dataclass() -> None:
    assert is_dataclass(CheckResult)
    assert CheckResult.__dataclass_params__.frozen is True
    result = _sample()
    with pytest.raises(FrozenInstanceError):
        result.status = "FAIL"


def test_checkresult_has_exact_canonical_fields() -> None:
    names = {field.name for field in fields(CheckResult)}
    assert names == REQUIRED_FIELDS | OPTIONAL_FIELDS
    assert FORBIDDEN_FIELDS.isdisjoint(names)


def test_checkresult_type_boundary_accepts_mapping_and_tuple_messages() -> None:
    result = _sample()
    hints = get_type_hints(CheckResult)

    assert "Mapping" in str(hints["evidence"])
    assert isinstance(result.evidence, dict)
    assert isinstance(result.messages, tuple)
    assert result.messages == ("geometry ok",)


def test_checkresult_to_dict_returns_only_canonical_fields() -> None:
    payload = _sample().to_dict()
    assert set(payload) == REQUIRED_FIELDS | OPTIONAL_FIELDS
    assert FORBIDDEN_FIELDS.isdisjoint(payload)
    assert payload["id"] == "beam_geometry:B1:S1"
    assert payload["component"] == "B1"
    assert payload["check_type"] == "beam_geometry"
    assert payload["demand"] == 300.0
    assert payload["capacity"] == 250.0
    assert payload["messages"] == ("geometry ok",)
    assert payload["evidence"] == {"source_table": "beam_design_summary", "source_row": 1}
