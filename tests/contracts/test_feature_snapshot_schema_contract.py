from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "tbdy_engine" / "catalogs" / "schemas" / "feature_snapshot.schema.json"
VALID_FIXTURE = ROOT / "tests" / "fixtures" / "feature_snapshot_c8_3_minimal_valid.json"
C8_TABLE_FIXTURE = ROOT / "tests" / "fixtures" / "c8_table_headers_fixture.json"


def _schema():
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _valid_fixture():
    return json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))


def _validator():
    return Draft202012Validator(_schema())


def _errors(instance):
    return list(_validator().iter_errors(instance))


def _first_feature(doc):
    snapshot = doc["snapshots"][0]
    feature_name = next(iter(snapshot["features"]))
    return snapshot["features"][feature_name]


def test_feature_snapshot_schema_exists():
    assert SCHEMA.is_file()


def test_current_c8_3_feature_snapshot_validates_against_schema(tmp_path):
    out = tmp_path / "c8"
    result = subprocess.run(
        [sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(C8_TABLE_FIXTURE), "--out", str(out)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    current = json.loads((out / "feature_snapshot.json").read_text(encoding="utf-8"))
    assert not _errors(current)
    assert current["feature_status_counts"] == {"RESOLVED": 28}


def test_feature_snapshot_schema_rejects_check_result_semantics():
    doc = _valid_fixture()
    feature = _first_feature(doc)
    feature["check_id"] = "beam_geometry_min_width"
    errors = _errors(doc)
    assert errors
    assert any("check_id" in err.message for err in errors)


def test_feature_snapshot_schema_rejects_ok_fail_verdict_fields_inside_feature():
    for key, value in [("OK", True), ("FAIL", False), ("verdict", "OK"), ("engineering_verdict", "FAIL")]:
        doc = _valid_fixture()
        _first_feature(doc)[key] = value
        errors = _errors(doc)
        assert errors, key


def test_feature_snapshot_schema_allows_current_resolver_evidence_payloads():
    doc = _valid_fixture()
    assert any(
        feature.get("evidence")
        for snapshot in doc["snapshots"]
        for feature in snapshot["features"].values()
    )
    assert not _errors(doc)


def test_feature_snapshot_schema_rejects_status_from_counts():
    doc = _valid_fixture()
    _first_feature(doc)["status_from_counts"] = "OK"
    errors = _errors(doc)
    assert errors
    assert any("status_from_counts" in err.message for err in errors)


def test_feature_snapshot_schema_rejects_checkresult_status_as_feature_status():
    for status in ["OK", "FAIL", "WARNING", "NO_DATA"]:
        doc = _valid_fixture()
        _first_feature(doc)["status"] = status
        errors = _errors(doc)
        assert errors, status


def test_feature_snapshot_schema_rejects_verdict_fields_inside_evidence():
    doc = _valid_fixture()
    feature = _first_feature(doc)
    feature["evidence"][0]["verdict"] = "OK"
    errors = _errors(doc)
    assert errors
