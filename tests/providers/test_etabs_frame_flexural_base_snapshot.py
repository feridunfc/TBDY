from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

import pytest

import tbdy_engine.providers.etabs_frame_flexural_base_provider as subject


class _SourceIdentity:
    source_model_ref = "source-model:flexural-snapshot"


class _Context:
    def __init__(self):
        self.verified_session = object()
        self.source_model_identity = _SourceIdentity()
        self.acquisition_context_ref = "acquisition:flexural-snapshot"
        self.session_provenance_ref = "session:flexural-snapshot"


class _Scratch:
    def __init__(self, source_model_identity):
        self.source_model_identity = source_model_identity
        self.ownership_proof_ref = "scratch:owned:flexural-snapshot"
        self.scratch_path = r"C:\tmp\flexural-snapshot.edb"


def _rows_fixture():
    return {
        subject.TABLE_FRAME_ASSIGNMENTS: (
            {"UniqueName": "F1", "SectProp": "R1"},
            {"UniqueName": "F2", "SectProp": "R1"},
            {"UniqueName": "F3", "SectProp": "R2"},
        ),
        subject.TABLE_RECTANGULAR: (
            {"Name": "R1", "Material": "C35", "t2": 0.40, "t3": 0.60},
            {"Name": "R2", "Material": "C35", "t2": 0.50, "t3": 0.70},
        ),
        subject.TABLE_FRAME_SECTION_SUMMARY: (
            {"Name": "R1", "Shape": "Concrete Rectangular", "Material": "C35"},
            {"Name": "R2", "Shape": "Concrete Rectangular", "Material": "C35"},
        ),
        subject.TABLE_BASIC_MATERIAL: (
            {"Material": "C35", "E1": 33_000_000.0},
        ),
        subject.TABLE_CONCRETE: (
            {"Material": "C35", "Fc": 35_000.0},
        ),
    }


def _install_environment(
    monkeypatch,
    *,
    rows=None,
    units=None,
    identities=None,
    calls=None,
):
    context = _Context()
    scratch = _Scratch(context.source_model_identity)
    table_rows = _rows_fixture() if rows is None else rows
    counter = Counter() if calls is None else calls

    monkeypatch.setattr(subject, "TrustedLiveAcquisitionContext", _Context)
    monkeypatch.setattr(subject, "OwnedScratchContext", _Scratch)

    def capture_rows(_context, table):
        counter[table] += 1
        return tuple(table_rows[table])

    monkeypatch.setattr(subject, "_rows", capture_rows)

    stable_units = SimpleNamespace(
        present_force_unit=4,
        present_length_unit=6,
    )
    unit_values = iter(units) if units is not None else None

    def read_units(_session):
        return next(unit_values) if unit_values is not None else stable_units

    monkeypatch.setattr(subject, "read_verified_unit_snapshot", read_units)

    stable_identity = SimpleNamespace(model_full_path=scratch.scratch_path)
    identity_values = iter(identities) if identities is not None else None

    def read_identity(_session):
        return (
            next(identity_values)
            if identity_values is not None
            else stable_identity
        )

    monkeypatch.setattr(
        subject,
        "reread_verified_session_identity",
        read_identity,
    )

    return context, scratch, counter


def test_single_frame_public_capture_preserves_existing_factual_output(monkeypatch):
    context, scratch, _calls = _install_environment(monkeypatch)

    fact = subject.capture_frame_flexural_base_fact(
        context=context,
        owned_scratch=scratch,
        component_unique_name="F1",
    )

    assert fact.component_unique_name == "F1"
    assert fact.assigned_section_name == "R1"
    assert fact.material_name == "C35"
    assert fact.t2_mm == subject.Decimal("400.0")
    assert fact.t3_mm == subject.Decimal("600.0")
    assert fact.concrete_fck_mpa == subject.Decimal("35.0")
    assert fact.etabs_ec_mpa == subject.Decimal("33000.0")
    assert len(fact.source_rows) == 5
    assert len(fact.source_refs) == 5


def test_snapshot_binding_is_semantically_equivalent_to_single_item_capture(
    monkeypatch,
):
    context, scratch, _calls = _install_environment(monkeypatch)

    snapshot = subject.capture_frame_flexural_base_snapshot(
        context=context,
        owned_scratch=scratch,
    )
    batch_fact = subject.bind_frame_flexural_base_fact_from_snapshot(
        snapshot,
        "F1",
    )
    single_fact = subject.capture_frame_flexural_base_fact(
        context=context,
        owned_scratch=scratch,
        component_unique_name="F1",
    )

    assert batch_fact.semantic_payload() == single_fact.semantic_payload()
    assert batch_fact.semantic_state_ref == single_fact.semantic_state_ref
    assert batch_fact.source_rows == single_fact.source_rows
    assert batch_fact.source_refs == single_fact.source_refs
    assert batch_fact.capture_event_ref != single_fact.capture_event_ref
    assert batch_fact.evidence_ref != single_fact.evidence_ref


def test_every_snapshot_bound_fact_keeps_exact_five_source_rows_and_refs(
    monkeypatch,
):
    context, scratch, _calls = _install_environment(monkeypatch)
    snapshot = subject.capture_frame_flexural_base_snapshot(
        context=context,
        owned_scratch=scratch,
    )

    facts = tuple(
        subject.bind_frame_flexural_base_fact_from_snapshot(snapshot, name)
        for name in ("F1", "F2", "F3")
    )

    for fact in facts:
        assert tuple(table for table, _row in fact.source_rows) == (
            subject.TABLE_FRAME_ASSIGNMENTS,
            subject.TABLE_RECTANGULAR,
            subject.TABLE_FRAME_SECTION_SUMMARY,
            subject.TABLE_BASIC_MATERIAL,
            subject.TABLE_CONCRETE,
        )
        assert len(fact.source_refs) == 5
        assert len(set(fact.source_refs)) == 5


def test_snapshot_bound_facts_keep_distinct_capture_events(monkeypatch):
    context, scratch, _calls = _install_environment(monkeypatch)
    snapshot = subject.capture_frame_flexural_base_snapshot(
        context=context,
        owned_scratch=scratch,
    )

    one = subject.bind_frame_flexural_base_fact_from_snapshot(snapshot, "F1")
    two = subject.bind_frame_flexural_base_fact_from_snapshot(snapshot, "F2")

    assert one.capture_event_ref != two.capture_event_ref
    assert one.evidence_ref != two.evidence_ref


def test_population_style_binding_captures_each_full_base_table_exactly_once(
    monkeypatch,
):
    context, scratch, calls = _install_environment(monkeypatch)

    snapshot = subject.capture_frame_flexural_base_snapshot(
        context=context,
        owned_scratch=scratch,
    )
    facts = tuple(
        subject.bind_frame_flexural_base_fact_from_snapshot(snapshot, name)
        for name in ("F1", "F2", "F3")
    )

    assert len(facts) == 3
    assert calls == Counter(
        {
            subject.TABLE_FRAME_ASSIGNMENTS: 1,
            subject.TABLE_RECTANGULAR: 1,
            subject.TABLE_FRAME_SECTION_SUMMARY: 1,
            subject.TABLE_BASIC_MATERIAL: 1,
            subject.TABLE_CONCRETE: 1,
        }
    )
    assert sum(calls.values()) == 5


def test_unit_state_change_during_snapshot_capture_fails_closed(monkeypatch):
    before = SimpleNamespace(present_force_unit=4, present_length_unit=6)
    after = SimpleNamespace(present_force_unit=3, present_length_unit=4)
    context, scratch, _calls = _install_environment(
        monkeypatch,
        units=(before, after),
    )

    with pytest.raises(
        subject.FrameFlexuralBaseFactError,
        match="unit state changed",
    ):
        subject.capture_frame_flexural_base_snapshot(
            context=context,
            owned_scratch=scratch,
        )


def test_active_model_change_during_snapshot_capture_fails_closed(monkeypatch):
    context = _Context()
    scratch = _Scratch(context.source_model_identity)
    before = SimpleNamespace(model_full_path=scratch.scratch_path)
    after = SimpleNamespace(model_full_path=r"C:\tmp\wrong.edb")
    context, scratch, _calls = _install_environment(
        monkeypatch,
        identities=(before, after),
    )

    with pytest.raises(
        subject.FrameFlexuralBaseFactError,
        match="active ETABS model changed",
    ):
        subject.capture_frame_flexural_base_snapshot(
            context=context,
            owned_scratch=scratch,
        )


@pytest.mark.parametrize(
    ("table", "duplicate_row", "match"),
    (
        (
            subject.TABLE_FRAME_ASSIGNMENTS,
            {"UniqueName": "F1", "SectProp": "R1"},
            "duplicate frame UniqueName identity",
        ),
        (
            subject.TABLE_FRAME_SECTION_SUMMARY,
            {"Name": "R1", "Shape": "Concrete Rectangular", "Material": "C35"},
            "duplicate section summary identity",
        ),
        (
            subject.TABLE_RECTANGULAR,
            {"Name": "R1", "Material": "C35", "t2": 0.40, "t3": 0.60},
            "duplicate rectangular section identity",
        ),
        (
            subject.TABLE_BASIC_MATERIAL,
            {"Material": "C35", "E1": 33_000_000.0},
            "duplicate basic material identity",
        ),
        (
            subject.TABLE_CONCRETE,
            {"Material": "C35", "Fc": 35_000.0},
            "duplicate concrete material identity",
        ),
    ),
)
def test_duplicate_exact_identity_in_snapshot_fails_closed(
    monkeypatch,
    table,
    duplicate_row,
    match,
):
    rows = _rows_fixture()
    rows[table] = (*rows[table], duplicate_row)
    context, scratch, _calls = _install_environment(
        monkeypatch,
        rows=rows,
    )

    with pytest.raises(subject.FrameFlexuralBaseFactError, match=match):
        subject.capture_frame_flexural_base_snapshot(
            context=context,
            owned_scratch=scratch,
        )


def test_snapshot_cannot_be_manufactured_by_ordinary_caller():
    with pytest.raises(TypeError, match="provider-issued only"):
        subject.FrameFlexuralBaseCaptureSnapshot(
            source_model_ref="source",
            ownership_proof_ref="scratch",
            acquisition_context_ref="acquisition",
            session_provenance_ref="session",
            scratch_path=r"C:\tmp\x.edb",
            present_force_unit=4,
            present_length_unit=6,
            assignment_rows=(),
            rectangular_rows=(),
            section_summary_rows=(),
            basic_material_rows=(),
            concrete_rows=(),
        )
