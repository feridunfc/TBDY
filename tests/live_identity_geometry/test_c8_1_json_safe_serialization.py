from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType

import pytest

from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.features.resolver.live_smoke import (
    C8LiveFeatureResolverSmoke,
    tables_from_probe_report,
    to_jsonable,
    unit_context_from_payload,
    write_json_payload,
    write_smoke_outputs,
)

FIXTURE = Path("tests/fixtures/c8_1_live_units_fixture.json")


def _outputs():
    bundle = load_contracts()
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    resolver = C8LiveFeatureResolverSmoke(
        bundle,
        tables_from_probe_report(payload, bundle),
        unit_context=unit_context_from_payload(payload),
    )
    return resolver.build_all()


def test_c8_1_json_safe_converts_mappingproxy():
    value = MappingProxyType({"a": MappingProxyType({"b": 2})})
    assert to_jsonable(value) == {"a": {"b": 2}}
    json.dumps(to_jsonable(value))


def test_c8_1_json_safe_converts_dataclass_with_metadata():
    @dataclass
    class Payload:
        name: str = field(metadata={"source": "test"})
        nested: object = field(default_factory=lambda: MappingProxyType({"x": 1}))

    assert to_jsonable(Payload("demo")) == {"name": "demo", "nested": {"x": 1}}
    json.dumps(to_jsonable(Payload("demo")))


def test_c8_1_json_safe_converts_enum_path_set_tuple():
    class Example(Enum):
        VALUE = "value"

    payload = {
        "enum": Example.VALUE,
        "path": Path("a/b"),
        "set": {"x", "y"},
        "tuple": (1, 2),
    }
    jsonable = to_jsonable(payload)
    assert jsonable["enum"] == "value"
    assert jsonable["path"] == "a/b"
    assert sorted(jsonable["set"]) == ["x", "y"]
    assert jsonable["tuple"] == [1, 2]
    json.dumps(jsonable)


def test_c8_1_all_c8_1_reports_are_json_serializable(tmp_path):
    outputs = _outputs()
    write_smoke_outputs(tmp_path, outputs)
    for path in tmp_path.glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    assert not (tmp_path / "serialization_failure_report.json").exists()


def test_c8_1_serialization_failure_report_is_written_without_silent_swallow(tmp_path):
    class Unsupported:
        __slots__ = ()

    target = tmp_path / "bad_report.json"
    with pytest.raises(TypeError):
        write_json_payload(target, {"bad": Unsupported()})
    failure = json.loads((tmp_path / "serialization_failure_report.json").read_text(encoding="utf-8"))
    assert failure["stage"] == "write_outputs"
    assert failure["check_engine_executed"] is False
    assert failure["check_result_emitted"] is False
    assert failure["ok_fail_emitted"] is False


def test_c8_1_live_failure_does_not_emit_checkresult(tmp_path):
    class Unsupported:
        __slots__ = ()

    with pytest.raises(TypeError):
        write_json_payload(tmp_path / "bad_report.json", {"bad": Unsupported()})
    text = (tmp_path / "serialization_failure_report.json").read_text(encoding="utf-8")
    assert "CheckResult" not in text


def test_c8_1_no_ok_fail_verdicts_on_serialization_failure(tmp_path):
    class Unsupported:
        __slots__ = ()

    with pytest.raises(TypeError):
        write_json_payload(tmp_path / "bad_report.json", {"bad": Unsupported()})
    text = (tmp_path / "serialization_failure_report.json").read_text(encoding="utf-8")
    assert '"OK"' not in text
    assert '"FAIL"' not in text


def test_c8_1_tool_fixture_mode_reports_remain_serializable(tmp_path):
    out = tmp_path / "smoke"
    result = subprocess.run(
        [sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    for path in out.glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def test_c8_2_path_serialization_uses_as_posix():
    path = Path("nested") / "report.json"
    assert to_jsonable(path) == path.as_posix()
