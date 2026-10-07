"""Offline acquisition-seam evidence; synthetic values are not B-BLOK facts."""
import ast
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import inspect
import json
from types import SimpleNamespace

import pytest

import tbdy_engine.providers.etabs_frame_flexural_base_provider as owner
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from test_etabs_frame_flexural_base_snapshot import _install_environment, _rows_fixture


def capture(context, scratch):
    return owner.capture_frame_flexural_base_snapshot(context=context, owned_scratch=scratch)


def test_display_only_acquisition_reproduces_exact_current_failure(monkeypatch):
    context, _scratch, _ = _install_environment(monkeypatch)
    display = owner._rows(context, owner.TABLE_RECTANGULAR)
    assert display.field_unit_provenance == () and display.field_metadata_raw == ()
    snapshot = SimpleNamespace(table_unit_provenance={}, table_metadata_refs={})
    with pytest.raises(owner.FrameFlexuralBaseFactError,
                       match="^UNIT_UNQUALIFIED:MISSING_OR_DUPLICATE_FIELD_METADATA$"):
        owner._table_quantity(snapshot, display.table_name, display.parsed.rows[0], ("t2",), "L")


def test_real_acquisition_seam_binds_independent_fields_and_keeps_raw_values(monkeypatch):
    rows = _rows_fixture()
    rows[owner.TABLE_RECTANGULAR][0].update(t2=0.8, t3=800)
    rows[owner.TABLE_BASIC_MATERIAL][0]["E1"] = 33_000_000_000
    rows[owner.TABLE_CONCRETE][0]["Fc"] = 35
    original = deepcopy(rows)
    calls = Counter()
    context, scratch, display_calls = _install_environment(
        monkeypatch, rows=rows, metadata_calls=calls,
        metadata_units={"t2": "m", "t3": "mm", "E1": "N/m2", "Fc": "MPa"})
    snapshot = capture(context, scratch)
    fact = owner.bind_frame_flexural_base_fact_from_snapshot(snapshot, "F1")
    assert fact.t2_mm == fact.t3_mm == 800
    assert fact.etabs_ec_mpa == 33000 and fact.concrete_fck_mpa == 35
    assert calls == Counter({table: 1 for table in owner._DIMENSIONAL_FIELDS})
    assert sum(display_calls.values()) == 5
    assert rows == original
    assert tuple(dict(row) for row in snapshot.rectangular_rows) == original[owner.TABLE_RECTANGULAR]
    assert len(snapshot.table_metadata_refs) == 3
    for table, bindings in snapshot.table_unit_provenance.items():
        if table not in owner._DIMENSIONAL_FIELDS:
            assert bindings == ()
            continue
        assert len(snapshot.table_metadata_raw[table]) == 8
        for binding in bindings:
            assert binding.source_model_ref == context.source_model_identity.source_model_ref
            assert binding.session_ref == context.session_provenance_ref
            assert binding.capture_ref == context.acquisition_context_ref
            proof = json.loads(binding.unit_state_before)["same_capture_bridge"]
            assert proof["metadata_origin"]["source_model_ref"] == context.verified_session.identity.model_full_path
            assert proof["metadata_origin"]["session_ref"] == "etabs-session:pid:73"
            assert proof["metadata_origin"]["capture_ref"].startswith("field-metadata-capture:")
            assert proof["ownership_proof_ref"] == scratch.ownership_proof_ref
            assert proof["active_model_before"] == proof["active_model_after"] == scratch.scratch_path


def test_alias_selection_and_reordered_metadata_bind_exact_raw_FieldKeys(monkeypatch):
    rows = _rows_fixture()
    for row in rows[owner.TABLE_RECTANGULAR]:
        row["Width"] = row.pop("t2")
        row["Depth"] = row.pop("t3") * 1000
    def reverse(_table, raw):
        return raw[:2] + tuple(tuple(reversed(array)) for array in raw[2:7]) + raw[7:]
    context, scratch, _ = _install_environment(
        monkeypatch, rows=rows, metadata_units={"Width": "m", "Depth": "mm"},
        raw_metadata_transform=reverse)
    snapshot = capture(context, scratch)
    fact = owner.bind_frame_flexural_base_fact_from_snapshot(snapshot, "F1")
    assert fact.t2_mm == 400 and fact.t3_mm == 600
    bindings = {item.output_key: item.source_unit for item in snapshot.table_unit_provenance[owner.TABLE_RECTANGULAR]}
    assert bindings == {"Width": "m", "Depth": "mm"}


@pytest.mark.parametrize("key", ["t2", "t3", "E1", "G12", "Fc"])
@pytest.mark.parametrize("bad_unit", ["", "unknown-unit", "m4"])
def test_each_required_field_rejects_its_own_invalid_unit(monkeypatch, key, bad_unit):
    context, scratch, _ = _install_environment(monkeypatch, metadata_units={key: bad_unit})
    with pytest.raises(owner.FrameFlexuralBaseFactError, match="UNIT_UNQUALIFIED"):
        capture(context, scratch)


@pytest.mark.parametrize("key,wrong_dimension_unit", [("t2", "MPa"), ("t3", "MPa"),
                                                     ("E1", "m"), ("G12", "m"), ("Fc", "m")])
def test_supported_unit_with_wrong_physical_dimension_is_rejected(monkeypatch, key, wrong_dimension_unit):
    context, scratch, _ = _install_environment(monkeypatch, metadata_units={key: wrong_dimension_unit})
    with pytest.raises(owner.FrameFlexuralBaseFactError, match="UNIT_UNQUALIFIED"):
        capture(context, scratch)


def test_fresh_metadata_origin_changes_derived_evidence_identity(monkeypatch):
    context, scratch, _ = _install_environment(monkeypatch)
    first, second = capture(context, scratch), capture(context, scratch)
    a = first.table_unit_provenance[owner.TABLE_RECTANGULAR][0]
    b = second.table_unit_provenance[owner.TABLE_RECTANGULAR][0]
    assert a.source_unit == b.source_unit and a.raw_response_ref == b.raw_response_ref
    assert a.evidence_ref != b.evidence_ref
    assert first.rectangular_rows == second.rectangular_rows


@pytest.mark.parametrize("fault", ["missing", "duplicate", "wrong-key", "return-code", "array-length"])
def test_bad_first_metadata_stops_before_next_table_and_never_retries(monkeypatch, fault):
    calls = Counter()
    def corrupt(table, raw):
        assert table == owner.TABLE_RECTANGULAR
        raw = list(raw)
        arrays = [list(array) for array in raw[2:7]]
        index = arrays[0].index("t2")
        if fault == "missing":
            for array in arrays:
                array.pop(index)
            raw[1] -= 1
        elif fault == "duplicate":
            arrays[0][index] = "t3"
        elif fault == "wrong-key":
            arrays[0][index] = "T2"
        elif fault == "return-code":
            raw[7] = 5
        elif fault == "array-length":
            arrays[3].pop()
        raw[2:7] = arrays
        return tuple(raw)
    context, scratch, _ = _install_environment(
        monkeypatch, metadata_calls=calls, raw_metadata_transform=corrupt)
    with pytest.raises(owner.FrameFlexuralBaseFactError, match="UNIT_UNQUALIFIED"):
        capture(context, scratch)
    assert calls == Counter({owner.TABLE_RECTANGULAR: 1})


@pytest.mark.parametrize("attribute,bad_value", [
    ("source_model_ref", r"C:\tmp\foreign.edb"),
    ("session_ref", "etabs-session:pid:999"),
    ("capture_ref", "field-metadata-capture:foreign-event"),
])
def test_foreign_metadata_is_not_retagged_to_pass(monkeypatch, attribute, bad_value):
    context, scratch, _ = _install_environment(monkeypatch)
    real = owner.fetch_table_field_metadata_from_session
    def foreign(*args, **kwargs):
        return replace(real(*args, **kwargs), **{attribute: bad_value})
    monkeypatch.setattr(owner, "fetch_table_field_metadata_from_session", foreign)
    with pytest.raises(owner.FrameFlexuralBaseFactError, match="UNIT_UNQUALIFIED:FIELD_METADATA_.*_MISMATCH"):
        capture(context, scratch)


def test_session_pid_change_fails_closed(monkeypatch):
    identities = (SimpleNamespace(model_full_path=r"C:\tmp\flexural-snapshot.edb", process_id=73),
                  SimpleNamespace(model_full_path=r"C:\tmp\flexural-snapshot.edb", process_id=74))
    context, scratch, _ = _install_environment(monkeypatch, identities=identities)
    with pytest.raises(owner.FrameFlexuralBaseFactError, match="UNIT_UNQUALIFIED:FIELD_METADATA_SESSION_MISMATCH"):
        capture(context, scratch)


def test_active_model_state_change_at_same_path_fails_closed(monkeypatch):
    identities = (SimpleNamespace(model_full_path=r"C:\tmp\flexural-snapshot.edb", process_id=73, model_locked=False),
                  SimpleNamespace(model_full_path=r"C:\tmp\flexural-snapshot.edb", process_id=73, model_locked=True))
    context, scratch, _ = _install_environment(monkeypatch, identities=identities)
    with pytest.raises(owner.FrameFlexuralBaseFactError, match="UNIT_UNQUALIFIED:active ETABS model state changed"):
        capture(context, scratch)


def test_metadata_getter_error_is_not_retried(monkeypatch):
    calls = Counter()
    def unavailable(table, _raw):
        assert table == owner.TABLE_RECTANGULAR
        raise RuntimeError("synthetic metadata getter unavailable")
    context, scratch, _ = _install_environment(
        monkeypatch, metadata_calls=calls, raw_metadata_transform=unavailable)
    with pytest.raises(owner.FrameFlexuralBaseFactError, match="UNIT_UNQUALIFIED:FIELD_METADATA_GETTER_FAILED"):
        capture(context, scratch)
    assert calls == Counter({owner.TABLE_RECTANGULAR: 1})


def test_bridge_preserves_both_raw_unit_observations(monkeypatch):
    from tbdy_engine.etabs.safety import EtabsUnitSnapshot
    before = EtabsUnitSnapshot(present_force_unit=4, present_length_unit=6,
                               raw_unit_reads=(("GetPresentUnits", "pre-raw"),))
    after = replace(before, raw_unit_reads=(("GetPresentUnits", "post-raw"),))
    context, scratch, _ = _install_environment(monkeypatch, units=(before, after))
    binding = capture(context, scratch).table_unit_provenance[owner.TABLE_RECTANGULAR][0]
    assert json.loads(binding.unit_state_before)["raw_unit_reads"] == {"GetPresentUnits": "pre-raw"}
    assert json.loads(binding.unit_state_after)["raw_unit_reads"] == {"GetPresentUnits": "post-raw"}
    binding.require(source_call="SapModel.DatabaseTables.GetAllFieldsInTable",
                    subject_key=owner.TABLE_RECTANGULAR, output_key="t2", dimension="L")


def test_provider_has_no_native_mutation_execution_or_attachment_calls():
    forbidden = {"RunAnalysis", "StartDesign", "SetPresentUnits", "Save", "OpenFile",
                 "ApplicationStart", "GetActiveObject", "GetObject", "GetObjectProcess"}
    tree = ast.parse(inspect.getsource(owner))
    calls = [node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert not forbidden.intersection(calls)
    assert not any(name.startswith("Set") for name in calls)
