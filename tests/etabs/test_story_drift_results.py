import pytest

import tbdy_engine.etabs.oapi.story_drift_results as story_drift
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


def _raw(*, name="COMB_GQE_X", directions=("X",), drifts=(0.001,), ret=0, count=None):
    n = len(directions) if count is None else count
    rows = len(directions)
    return (
        n,
        ["Story1"] * rows,
        [name] * rows,
        [""] * rows,
        [0.0] * rows,
        list(directions),
        list(drifts),
        [f"P{i + 1}" for i in range(rows)],
        [1.0 + i for i in range(rows)],
        [2.0 + i for i in range(rows)],
        [3.0 + i for i in range(rows)],
        ret,
    )


def test_story_drifts_exact_documented_abi_decodes_xy_rows():
    fact = story_drift.decode_story_drifts_response(
        _raw(directions=("X", "Y"), drifts=(0.0012, -0.0008)),
        output_name="COMB_GQE_X",
        output_kind="combo",
    )
    assert fact.output_name == "COMB_GQE_X"
    assert fact.output_kind == "combo"
    assert fact.return_code == 0
    assert tuple(row.direction for row in fact.rows) == ("X", "Y")
    assert tuple(row.drift for row in fact.rows) == pytest.approx((0.0012, -0.0008))
    assert fact.evidence_ref.endswith("combo:COMB_GQE_X:rows=2")


def test_story_drifts_rejects_malformed_tuple():
    with pytest.raises(EtabsOAPIError, match="unexpected ABI shape"):
        story_drift.decode_story_drifts_response(
            _raw()[:-1], output_name="COMB_GQE_X", output_kind="combo"
        )


def test_story_drifts_rejects_nonzero_return_code():
    with pytest.raises(EtabsOAPIError, match="nonzero code"):
        story_drift.decode_story_drifts_response(
            _raw(ret=7), output_name="COMB_GQE_X", output_kind="combo"
        )


def test_story_drifts_rejects_row_count_larger_than_arrays():
    with pytest.raises(EtabsOAPIError, match="must contain at least 2 values"):
        story_drift.decode_story_drifts_response(
            _raw(count=2), output_name="COMB_GQE_X", output_kind="combo"
        )


def test_story_drifts_rejects_wrong_output_identity():
    with pytest.raises(EtabsOAPIError, match="binding mismatch"):
        story_drift.decode_story_drifts_response(
            _raw(name="OTHER"), output_name="COMB_GQE_X", output_kind="combo"
        )


def test_story_drifts_rejects_empty_rows():
    empty = (0, [], [], [], [], [], [], [], [], [], [], 0)
    with pytest.raises(EtabsOAPIError, match="returned no rows"):
        story_drift.decode_story_drifts_response(
            empty, output_name="COMB_GQE_X", output_kind="combo"
        )


def test_story_drifts_rejects_non_xy_direction():
    with pytest.raises(EtabsOAPIError, match="must be X or Y"):
        story_drift.decode_story_drifts_response(
            _raw(directions=("RZ",)), output_name="COMB_GQE_X", output_kind="combo"
        )


@pytest.mark.parametrize("kind", ("case", "combo"))
def test_story_drifts_session_selects_exact_output_and_restores(monkeypatch, kind):
    class FakeSession:
        pass

    class FakeResults:
        def __init__(self):
            self.calls = 0

        def StoryDrifts(self):
            self.calls += 1
            return _raw(name="OUT")

    class FakeSap:
        def __init__(self):
            self.Results = FakeResults()

    transaction_state = {"selected": None, "restored": False, "exited": False}

    class FakeTransaction:
        def __init__(self, _sap):
            pass

        def __enter__(self):
            return self

        def select_case(self, name):
            transaction_state["selected"] = ("case", name)

        def select_combo(self, name):
            transaction_state["selected"] = ("combo", name)

        def __exit__(self, exc_type, exc, tb):
            transaction_state["restored"] = True
            transaction_state["exited"] = True
            return False

    sap = FakeSap()

    def execute(_session, function, *, operation, timeout_seconds):
        assert operation == f"story_drifts:{kind}:OUT"
        assert timeout_seconds == 12.0
        return function(None, sap)

    monkeypatch.setattr(story_drift, "EtabsVerifiedSession", FakeSession)
    monkeypatch.setattr(story_drift, "ResultsSetupReadTransaction", FakeTransaction)
    monkeypatch.setattr(story_drift, "_execute_verified_read", execute)

    fact = story_drift.read_story_drifts_from_session(
        FakeSession(), output_name="OUT", output_kind=kind, timeout_seconds=12.0
    )

    assert transaction_state["selected"] == (kind, "OUT")
    assert transaction_state["restored"] is True
    assert transaction_state["exited"] is True
    assert sap.Results.calls == 1
    assert fact.output_name == "OUT"
    assert fact.output_kind == kind
