from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.providers.etabs_column_force_result_population_provider as subject
from tbdy_engine.etabs.safety import RuntimeCaptureStatus


class _FakeSession:
    pass


def _rows(case_name: str = "EX", unique_names: tuple[str, ...] = ("1", "2")):
    rows = []
    for index, uid in enumerate(unique_names, start=1):
        rows.append(
            {
                "Story": "Story1",
                "Column": f"C{index}",
                "UniqueName": uid,
                "OutputCase": case_name,
                "CaseType": "LinStatic",
                "StepType": "",
                "StepNumber": None,
                "Station": 0.0,
                "Element": uid,
                "ElemStation": 0.0,
                "P": float(index),
                "V2": 0.0,
                "V3": 0.0,
                "T": 0.0,
                "M2": float(index) * 2.0,
                "M3": float(index) * 3.0,
            }
        )
    return tuple(rows)


def _fetch(rows, *, status=RuntimeCaptureStatus.FULL, ret=0, reported=None, restore=True):
    diagnostics = (
        ({"phase": "restore_verify", "success": True},)
        if restore
        else ({"phase": "restore_verify", "success": False},)
    )
    return SimpleNamespace(
        capture_status=status,
        parsed=SimpleNamespace(
            return_code=ret,
            rows=tuple(rows),
            row_count_reported=len(rows) if reported is None else reported,
        ),
        state_diagnostics=diagnostics,
    )


def _expectation():
    return subject.ColumnForcePopulationExpectation(
        expected_unique_names=("1", "2"),
        source_row_count=2,
    )


def test_expectation_rejects_duplicate_factual_column_identity():
    with pytest.raises(subject.ColumnForceResultPopulationError, match="duplicate"):
        subject.ColumnForcePopulationExpectation(
            expected_unique_names=("1", "1"),
            source_row_count=2,
        )


def test_population_rejects_missing_expected_column():
    expectation = _expectation()
    with pytest.raises(subject.ColumnForceResultPopulationError, match="missing=.*2"):
        subject.ColumnForceResultPopulationFact(
            case_name="EX",
            expectation_ref=expectation.evidence_ref,
            expected_unique_names=expectation.expected_unique_names,
            observed_unique_names=("1",),
            rows=_rows(unique_names=("1",)),
        )


def test_population_rejects_extra_column():
    expectation = _expectation()
    with pytest.raises(subject.ColumnForceResultPopulationError, match="extra=.*3"):
        subject.ColumnForceResultPopulationFact(
            case_name="EX",
            expectation_ref=expectation.evidence_ref,
            expected_unique_names=expectation.expected_unique_names,
            observed_unique_names=("1", "2", "3"),
            rows=_rows(unique_names=("1", "2", "3")),
        )


def test_population_rejects_duplicate_exact_row_identity():
    expectation = _expectation()
    first, second = _rows()
    with pytest.raises(subject.ColumnForceResultPopulationError, match="duplicate exact"):
        subject.ColumnForceResultPopulationFact(
            case_name="EX",
            expectation_ref=expectation.evidence_ref,
            expected_unique_names=expectation.expected_unique_names,
            observed_unique_names=expectation.expected_unique_names,
            rows=(first, first, second),
        )


def test_population_rejects_missing_required_force_payload():
    expectation = _expectation()
    rows = [dict(row) for row in _rows()]
    rows[0].pop("M3")
    with pytest.raises(subject.ColumnForceResultPopulationError, match="missing required field"):
        subject.ColumnForceResultPopulationFact(
            case_name="EX",
            expectation_ref=expectation.evidence_ref,
            expected_unique_names=expectation.expected_unique_names,
            observed_unique_names=expectation.expected_unique_names,
            rows=tuple(rows),
        )


def test_expectation_capture_requires_full_nontruncated_population(monkeypatch):
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)
    monkeypatch.setattr(
        subject,
        "fetch_display_table_from_session",
        lambda *args, **kwargs: _fetch(
            ({"UniqueName": "1"},),
            status=RuntimeCaptureStatus.PARTIAL,
        ),
    )
    with pytest.raises(subject.ColumnForceResultPopulationError, match="FULL"):
        subject.capture_column_force_population_expectation_from_session(_FakeSession())


def test_result_capture_requires_output_selection_restore(monkeypatch):
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)
    monkeypatch.setattr(
        subject,
        "fetch_display_table_for_output_from_session",
        lambda *args, **kwargs: _fetch(_rows(), restore=False),
    )
    with pytest.raises(subject.ColumnForceResultPopulationError, match="restoration"):
        subject.capture_column_force_result_population_from_session(
            _FakeSession(),
            case_name="EX",
            expectation=_expectation(),
        )


def test_result_capture_rejects_wrong_output_case_only(monkeypatch):
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)
    monkeypatch.setattr(
        subject,
        "fetch_display_table_for_output_from_session",
        lambda *args, **kwargs: _fetch(_rows(case_name="EY")),
    )
    with pytest.raises(subject.ColumnForceResultPopulationError, match="no exact OutputCase"):
        subject.capture_column_force_result_population_from_session(
            _FakeSession(),
            case_name="EX",
            expectation=_expectation(),
        )


def test_result_capture_qualifies_exact_full_population(monkeypatch):
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)
    monkeypatch.setattr(
        subject,
        "fetch_display_table_for_output_from_session",
        lambda *args, **kwargs: _fetch(_rows()),
    )
    fact = subject.capture_column_force_result_population_from_session(
        _FakeSession(),
        case_name="EX",
        expectation=_expectation(),
    )
    assert fact.case_name == "EX"
    assert fact.expected_unique_names == ("1", "2")
    assert fact.observed_unique_names == ("1", "2")
    assert fact.row_count == 2
    assert fact.evidence_ref.startswith(subject.COLUMN_FORCE_POPULATION_REF_PREFIX)


def test_linstat_population_accepts_absent_step_fields():
    expectation = _expectation()
    rows = [dict(row) for row in _rows()]
    for row in rows:
        row.pop("StepType")
        row.pop("StepNumber")

    fact = subject.ColumnForceResultPopulationFact(
        case_name="EX",
        expectation_ref=expectation.evidence_ref,
        expected_unique_names=expectation.expected_unique_names,
        observed_unique_names=expectation.expected_unique_names,
        rows=tuple(rows),
    )

    assert fact.row_count == 2
    assert all(row["StepType"] is None for row in fact.rows)
    assert all(row["StepNumber"] is None for row in fact.rows)


def test_non_linstat_population_does_not_invent_absent_step_fields():
    expectation = _expectation()
    rows = [dict(row) for row in _rows()]
    for row in rows:
        row["CaseType"] = "ResponseSpectrum"
        row.pop("StepType")
        row.pop("StepNumber")

    with pytest.raises(
        subject.ColumnForceResultPopulationError,
        match="missing required field",
    ):
        subject.ColumnForceResultPopulationFact(
            case_name="EX",
            expectation_ref=expectation.evidence_ref,
            expected_unique_names=expectation.expected_unique_names,
            observed_unique_names=expectation.expected_unique_names,
            rows=tuple(rows),
        )
