from __future__ import annotations

import subprocess
import sys

import pytest

from tbdy_engine.etabs.safety import EtabsSafetyError, EtabsSafetyErrorCode, RuntimeCaptureStatus
from tbdy_engine.providers.etabs_concrete_design_combo_selection_probe import (
    EXPECTED_SELECTED_COMBO_FIELD_KEYS,
    SOURCE_NOT_PROVEN,
    TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
    acquire_actual_concrete_design_combo_selection,
    build_actual_concrete_design_combo_selection_population,
    probe_concrete_frame_design_combo_selection_table,
)
from tbdy_engine.providers.etabs_display_table_fetcher import DisplayTableFetchResult
from tbdy_engine.providers.etabs_display_table_parser import ParsedDisplayTable


class FakeDatabaseTables:
    def __init__(self, *, field_keys=None, rows=None, number_records=None):
        self.calls = []
        self.field_keys = list(field_keys or EXPECTED_SELECTED_COMBO_FIELD_KEYS)
        self.rows = list(rows or (("Strength", "CMB2"), ("Strength", "CMB1")))
        self.number_records = len(self.rows) if number_records is None else number_records

    def GetTableForDisplayArray(self, *args):
        self.calls.append(("GetTableForDisplayArray", args))
        flat = [value for row in self.rows for value in row]
        return {
            "return_code": 0,
            "field_keys": list(self.field_keys),
            "table_data": flat,
            "number_records": self.number_records,
        }


def _fetched(
    *,
    status=RuntimeCaptureStatus.FULL,
    fields=EXPECTED_SELECTED_COMBO_FIELD_KEYS,
    rows=(
        {"ComboType": "Strength", "ComboName": "CMB2"},
        {"ComboType": "Strength", "ComboName": "CMB1"},
    ),
    reported=None,
    return_code=0,
    table=TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
):
    rows = tuple(rows)
    reported = len(rows) if reported is None else reported
    parsed = ParsedDisplayTable(
        actual_table_name=table,
        fetch_status="FETCHED",
        field_keys=tuple(fields),
        rows=rows,
        row_count_reported=reported,
        return_code=return_code,
    )
    return DisplayTableFetchResult(
        table_name=table,
        parsed=parsed,
        selected_signature={"signature_name": "sig_fixture"},
        selected_signature_reason="fixture",
        capture_status=status,
    )


def _build(fetched):
    return build_actual_concrete_design_combo_selection_population(
        fetched,
        model_fingerprint="model:fixture",
        evidence_epoch_id="epoch:fixture",
        session_provenance_ref="session:fixture",
    )


def test_candidate_table_probe_is_read_only_and_never_promotes_semantics():
    db = FakeDatabaseTables(
        field_keys=("ComboName", "ComboType", "DesignType"),
        rows=(("CMB1", "Strength", "User"), ("CMB2", "Strength", "Automatic")),
    )
    probe = probe_concrete_frame_design_combo_selection_table(db)
    assert probe.table_key == TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA
    assert probe.combo_names == ("CMB1", "CMB2")
    assert probe.combo_name_field_present
    assert probe.source_semantics_status == SOURCE_NOT_PROVEN
    assert {name for name, _args in db.calls} == {"GetTableForDisplayArray"}
    assert not any(name.startswith("Set") for name, _args in db.calls)


def test_actual_population_uses_exact_live_table_schema_and_full_capture():
    db = FakeDatabaseTables(
        rows=(("Strength", "CMB3"), ("Strength", "CMB1"), ("Strength", "CMB2")),
    )
    population = acquire_actual_concrete_design_combo_selection(
        db,
        model_fingerprint="model:fixture",
        evidence_epoch_id="epoch:fixture",
        session_provenance_ref="session:fixture",
    )
    assert population.table_key == TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA
    assert population.field_keys == ("ComboType", "ComboName")
    assert population.capture_status is RuntimeCaptureStatus.FULL
    assert population.capture_complete
    assert population.row_count_reported == 3
    assert population.names == ("CMB1", "CMB2", "CMB3")
    assert tuple(row.combo_type for row in population.rows) == ("Strength", "Strength", "Strength")
    assert population.model_fingerprint == "model:fixture"
    assert population.evidence_epoch_id == "epoch:fixture"
    assert population.session_provenance_ref == "session:fixture"
    assert all(row.row_id.startswith("selected-design-combo-row:sha256:") for row in population.rows)
    assert all(row.source_row_ref in population.source_refs for row in population.rows)
    assert {name for name, _args in db.calls} == {"GetTableForDisplayArray"}
    assert not any(name.startswith("Set") for name, _args in db.calls)


@pytest.mark.parametrize(
    "status",
    [
        RuntimeCaptureStatus.PARTIAL,
        RuntimeCaptureStatus.SAMPLED,
        RuntimeCaptureStatus.TRUNCATED,
        RuntimeCaptureStatus.UNKNOWN,
    ],
)
def test_nonfull_capture_fails_closed(status):
    with pytest.raises(EtabsSafetyError) as exc_info:
        _build(_fetched(status=status))
    assert exc_info.value.code is EtabsSafetyErrorCode.CAPTURE_INTEGRITY_FAILED
    assert exc_info.value.details["capture_status"] == status.value


@pytest.mark.parametrize(
    "fields",
    [
        ("ComboName", "ComboType"),
        ("ComboType", "ComboName", "DesignType"),
        ("ComboName",),
    ],
)
def test_exact_reviewed_schema_is_required(fields):
    with pytest.raises(EtabsSafetyError) as exc_info:
        _build(_fetched(fields=fields))
    assert exc_info.value.code is EtabsSafetyErrorCode.CAPTURE_INTEGRITY_FAILED


def test_reported_and_captured_row_counts_must_match():
    with pytest.raises(EtabsSafetyError) as exc_info:
        _build(_fetched(reported=3))
    assert exc_info.value.code is EtabsSafetyErrorCode.CAPTURE_INTEGRITY_FAILED


@pytest.mark.parametrize(
    "rows",
    [
        (
            {"ComboType": "Strength", "ComboName": "CMB1"},
            {"ComboType": "Service", "ComboName": "CMB1"},
        ),
        ({"ComboType": "", "ComboName": "CMB1"},),
        ({"ComboType": "Strength", "ComboName": ""},),
        ({"ComboType": " Strength", "ComboName": "CMB1"},),
        ({"ComboType": "Strength", "ComboName": "CMB1 "},),
        ({"ComboType": "Strength", "ComboName": "CMB1", "Extra": "x"},),
    ],
)
def test_duplicate_or_invalid_rows_fail_closed(rows):
    with pytest.raises(EtabsSafetyError) as exc_info:
        _build(_fetched(rows=rows))
    assert exc_info.value.code is EtabsSafetyErrorCode.CAPTURE_INTEGRITY_FAILED


def test_factual_population_and_row_identity_are_deterministic():
    rows_a = (
        {"ComboType": "Service", "ComboName": "CMB2"},
        {"ComboType": "Strength", "ComboName": "CMB1"},
    )
    rows_b = tuple(reversed(rows_a))
    a = _build(_fetched(rows=rows_a))
    b = _build(_fetched(rows=rows_b))
    assert a == b
    assert tuple(row.row_id for row in a.rows) == tuple(row.row_id for row in b.rows)
    assert a.names == ("CMB1", "CMB2")


def test_wrong_table_or_nonzero_return_fails_closed():
    with pytest.raises(EtabsSafetyError):
        _build(_fetched(table="Other Table"))
    with pytest.raises(EtabsSafetyError):
        _build(_fetched(return_code=1))


def test_fresh_interpreter_import_has_no_regulatory_or_column_feature_dependency():
    code = (
        "import sys; "
        "import tbdy_engine.providers.etabs_concrete_design_combo_selection_probe; "
        "assert 'tbdy_engine.regulatory' not in sys.modules; "
        "assert 'tbdy_engine.features.column_concrete_design_evidence' not in sys.modules"
    )
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
