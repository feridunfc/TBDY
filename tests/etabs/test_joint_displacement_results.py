import pytest

import tbdy_engine.etabs.oapi.joint_displacement_results as joint_displ
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


def _raw(*, point="P1", name="COMB_GQE_X", count=1, ret=0, u1=(0.001,), u2=(0.002,)):
    rows = max(len(u1), len(u2))
    return (
        count,
        [point] * rows,
        [f"E{i + 1}" for i in range(rows)],
        [name] * rows,
        [""] * rows,
        [0.0] * rows,
        list(u1),
        list(u2),
        [0.0] * rows,
        [0.0] * rows,
        [0.0] * rows,
        [0.0] * rows,
        ret,
    )


def test_joint_displ_exact_documented_abi_decodes_translation():
    fact = joint_displ.decode_joint_displ_response(
        _raw(u1=(0.0012,), u2=(-0.0008,)),
        point_object="P1",
        output_name="COMB_GQE_X",
        output_kind="combo",
    )
    assert fact.return_code == 0
    assert fact.item_type_elm == 0
    assert len(fact.rows) == 1
    assert fact.rows[0].point_object == "P1"
    assert fact.rows[0].load_case == "COMB_GQE_X"
    assert fact.rows[0].u1 == pytest.approx(0.0012)
    assert fact.rows[0].u2 == pytest.approx(-0.0008)


def test_joint_displ_rejects_malformed_tuple():
    with pytest.raises(EtabsOAPIError, match="unexpected ABI shape"):
        joint_displ.decode_joint_displ_response(
            _raw()[:-1], point_object="P1", output_name="COMB_GQE_X", output_kind="combo"
        )


def test_joint_displ_rejects_nonzero_return_code():
    with pytest.raises(EtabsOAPIError, match="nonzero code"):
        joint_displ.decode_joint_displ_response(
            _raw(ret=5), point_object="P1", output_name="COMB_GQE_X", output_kind="combo"
        )


def test_joint_displ_rejects_row_count_larger_than_arrays():
    with pytest.raises(EtabsOAPIError, match="must contain at least 2 values"):
        joint_displ.decode_joint_displ_response(
            _raw(count=2), point_object="P1", output_name="COMB_GQE_X", output_kind="combo"
        )


def test_joint_displ_rejects_wrong_point_identity():
    with pytest.raises(EtabsOAPIError, match="point binding mismatch"):
        joint_displ.decode_joint_displ_response(
            _raw(point="OTHER"), point_object="P1", output_name="COMB_GQE_X", output_kind="combo"
        )


def test_joint_displ_rejects_wrong_output_identity():
    with pytest.raises(EtabsOAPIError, match="output binding mismatch"):
        joint_displ.decode_joint_displ_response(
            _raw(name="OTHER"), point_object="P1", output_name="COMB_GQE_X", output_kind="combo"
        )


def test_joint_displ_rejects_empty_rows():
    raw = (0, [], [], [], [], [], [], [], [], [], [], [], 0)
    with pytest.raises(EtabsOAPIError, match="returned no rows"):
        joint_displ.decode_joint_displ_response(
            raw, point_object="P1", output_name="COMB_GQE_X", output_kind="combo"
        )


@pytest.mark.parametrize("kind", ("case", "combo"))
def test_joint_displ_session_selects_exact_output_and_restores_without_runanalysis(monkeypatch, kind):
    class FakeSession:
        pass

    class FakeResults:
        def __init__(self):
            self.calls = []

        def JointDispl(self, point, item_type):
            self.calls.append((point, item_type))
            return _raw(point=point, name="OUT")

    class FakeAnalyze:
        def RunAnalysis(self):
            raise AssertionError("JointDispl factual read must not run analysis")

    class FakeSap:
        def __init__(self):
            self.Results = FakeResults()
            self.Analyze = FakeAnalyze()

    transaction_state = {"selected": None, "restored": False}

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
            return False

    sap = FakeSap()

    def execute(_session, function, *, operation, timeout_seconds):
        assert operation == f"joint_displ:{kind}:OUT:P1"
        assert timeout_seconds == 9.0
        return function(None, sap)

    monkeypatch.setattr(joint_displ, "EtabsVerifiedSession", FakeSession)
    monkeypatch.setattr(joint_displ, "ResultsSetupReadTransaction", FakeTransaction)
    monkeypatch.setattr(joint_displ, "_execute_verified_read", execute)

    fact = joint_displ.read_joint_displ_from_session(
        FakeSession(),
        point_object="P1",
        output_name="OUT",
        output_kind=kind,
        timeout_seconds=9.0,
    )
    assert transaction_state["selected"] == (kind, "OUT")
    assert transaction_state["restored"] is True
    assert sap.Results.calls == [("P1", 0)]
    assert fact.rows[0].point_object == "P1"
