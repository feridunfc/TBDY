from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.integration.etabs_design_execution as subject
from tbdy_engine.etabs.oapi.concrete_design import (
    ConcreteColumnSummaryFact,
    ConcreteDesignResultsAvailabilityFact,
)


class _FakeContext:
    def __init__(self) -> None:
        self.source_model_identity = SimpleNamespace(
            source_model_ref="source-model-ref:test",
        )
        self.model_fingerprint = "model-fingerprint:test"
        self.evidence_epoch_id = "epoch:test"
        self.verified_session = object()
        self.acquisition_context_ref = "acquisition-context:test"
        self.session_provenance_ref = "session-provenance:test"
        self.reject_epoch = False

    def require_model_epoch(self, *, model_fingerprint, evidence_epoch_id):
        if self.reject_epoch:
            raise RuntimeError("epoch mismatch")
        assert model_fingerprint == self.model_fingerprint
        assert evidence_epoch_id == self.evidence_epoch_id


class _FakeOwnedScratch:
    def __init__(self, source_identity) -> None:
        self.source_model_identity = source_identity
        self.scratch_path = r"C:\tmp\model.tbdy-b4s-test.edb"
        self.active_model_path = self.scratch_path
        self.ownership_proof_ref = "owned-scratch:test"


class _FakeAnalysisLineage:
    def __init__(
        self,
        source_model_ref: str,
        *,
        ownership_proof_ref: str = "owned-scratch:test",
    ) -> None:
        self.qualification_ref = "analysis-lineage:test"
        self.capture_provenance_refs = (
            "acquisition-context:test",
            "session-provenance:test",
            ownership_proof_ref,
        )
        self.result = SimpleNamespace(
            source_model_ref=source_model_ref,
            identity_ref="analysis-result:test",
        )
        self.qualified = True

    def require_qualified_result(self):
        if not self.qualified:
            raise subject.AnalysisLineageQualificationError("not qualified")
        return self.result


class _FakeTopology:
    def __init__(
        self,
        *,
        model_fingerprint: str,
        evidence_epoch_id: str,
        names=("10", "20"),
    ) -> None:
        self.model_fingerprint = model_fingerprint
        self.evidence_epoch_id = evidence_epoch_id
        self.source_refs = ("topology:test",)
        columns = tuple(
            SimpleNamespace(
                component_id=f"Story1:C{index}:{name}",
                unique_name=name,
            )
            for index, name in enumerate(names, start=1)
        )
        self.topology = SimpleNamespace(columns=columns)


@pytest.fixture
def harness(monkeypatch):
    context = _FakeContext()
    owned = _FakeOwnedScratch(context.source_model_identity)
    analysis = _FakeAnalysisLineage(
        context.source_model_identity.source_model_ref
    )
    topology = _FakeTopology(
        model_fingerprint=context.model_fingerprint,
        evidence_epoch_id=context.evidence_epoch_id,
    )

    monkeypatch.setattr(subject, "TrustedLiveAcquisitionContext", _FakeContext)
    monkeypatch.setattr(subject, "OwnedScratchContext", _FakeOwnedScratch)
    monkeypatch.setattr(
        subject,
        "AnalysisLineageQualification",
        _FakeAnalysisLineage,
    )
    monkeypatch.setattr(
        subject,
        "ColumnTopologyEvidenceEnvelope",
        _FakeTopology,
    )

    state = {
        "active_path": owned.scratch_path,
        "availability": False,
        "availability_error": None,
        "rows": {"10": 0, "20": 0},
        "row_errors": set(),
        "calls": [],
    }

    def identity(_session, *, timeout_seconds=30.0):
        state["calls"].append(("identity", None, timeout_seconds))
        return SimpleNamespace(model_full_path=state["active_path"])

    def availability(_session, *, timeout_seconds=30.0):
        state["calls"].append(("availability", None, timeout_seconds))
        if state["availability_error"] is not None:
            raise state["availability_error"]
        return ConcreteDesignResultsAvailabilityFact(
            results_available=state["availability"],
            raw_response=state["availability"],
        )

    def summary(_session, frame_name, *, timeout_seconds=30.0):
        state["calls"].append(("summary", frame_name, timeout_seconds))
        if frame_name in state["row_errors"]:
            raise RuntimeError(f"summary failed for {frame_name}")
        count = state["rows"][frame_name]
        return ConcreteColumnSummaryFact(
            requested_frame_name=frame_name,
            reported_row_count=count,
            rows=tuple(object() for _ in range(count)),
            raw_response=("test", frame_name, count),
        )

    monkeypatch.setattr(subject, "reread_verified_session_identity", identity)
    monkeypatch.setattr(subject, "read_results_available_from_session", availability)
    monkeypatch.setattr(
        subject,
        "read_summary_results_column_from_session",
        summary,
    )

    return context, owned, analysis, topology, state


def capture(harness):
    context, owned, analysis, topology, _state = harness
    return subject.capture_design_preflight(
        context=context,
        owned_scratch=owned,
        analysis_lineage=analysis,
        topology=topology,
    )


def test_false_availability_and_all_expected_zero_rows_is_absent(harness) -> None:
    snapshot = capture(harness)

    assert snapshot.status is subject.DesignPreflightStatus.ABSENT
    assert snapshot.absent is True
    assert snapshot.blockers == ()
    assert snapshot.availability is not None
    assert snapshot.availability.results_available is False
    assert snapshot.column_census.complete is True
    assert snapshot.column_census.all_rows_absent is True
    assert snapshot.column_census.expected_frame_names == ("10", "20")


def test_true_availability_is_present_even_when_expected_rows_are_zero(
    harness,
) -> None:
    _context, _owned, _analysis, _topology, state = harness
    state["availability"] = True

    snapshot = capture(harness)

    assert snapshot.status is subject.DesignPreflightStatus.PRESENT
    assert snapshot.absent is False
    assert snapshot.blockers == (
        "PREEXISTING_CONCRETE_DESIGN_RESULTS_AVAILABLE",
    )


def test_false_availability_plus_preexisting_expected_row_is_ambiguous(
    harness,
) -> None:
    _context, _owned, _analysis, _topology, state = harness
    state["rows"]["20"] = 1

    snapshot = capture(harness)

    assert snapshot.status is subject.DesignPreflightStatus.AMBIGUOUS
    assert snapshot.blockers == (
        "RESULTS_AVAILABLE_FALSE_WITH_PREEXISTING_COLUMN_ROWS",
    )
    assert snapshot.column_census.any_rows_present is True


def test_incomplete_expected_column_presence_census_is_ambiguous(harness) -> None:
    _context, _owned, _analysis, _topology, state = harness
    state["row_errors"].add("20")

    snapshot = capture(harness)

    assert snapshot.status is subject.DesignPreflightStatus.AMBIGUOUS
    assert snapshot.blockers == (
        "EXPECTED_COLUMN_PRESENCE_CENSUS_INCOMPLETE",
    )
    assert snapshot.column_census.complete is False
    failed = next(
        item
        for item in snapshot.column_census.entries
        if item.frame_name == "20"
    )
    assert failed.reported_row_count is None
    assert failed.diagnostic.startswith(
        "SUMMARY_RESULT_PRESENCE_READ_FAILED:"
    )


def test_availability_read_failure_is_ambiguous_even_with_zero_rows(
    harness,
) -> None:
    _context, _owned, _analysis, _topology, state = harness
    state["availability_error"] = RuntimeError("availability unavailable")

    snapshot = capture(harness)

    assert snapshot.status is subject.DesignPreflightStatus.AMBIGUOUS
    assert snapshot.availability is None
    assert len(snapshot.blockers) == 1
    assert snapshot.blockers[0].startswith("RESULTS_AVAILABLE_READ_FAILED:")


def test_unqualified_b5_parent_blocks_before_any_design_result_read(
    harness,
) -> None:
    _context, _owned, analysis, _topology, state = harness
    analysis.qualified = False

    with pytest.raises(
        subject.DesignPreflightError,
        match="QUALIFIED parent AnalysisResultIdentity",
    ):
        capture(harness)

    assert state["calls"] == []


def test_wrong_active_scratch_blocks_before_any_design_result_read(
    harness,
) -> None:
    _context, _owned, _analysis, _topology, state = harness
    state["active_path"] = r"C:\tmp\other.edb"

    with pytest.raises(
        subject.DesignPreflightError,
        match="exact OwnedScratchContext",
    ):
        capture(harness)

    assert state["calls"] == [("identity", None, 30.0)]


def test_same_source_different_scratch_lineage_blocks_before_design_reads(
    harness,
) -> None:
    _context, owned, _analysis, _topology, state = harness
    owned.ownership_proof_ref = "owned-scratch:B"
    owned.scratch_path = r"C:\tmp\model.tbdy-b4s-B.edb"
    owned.active_model_path = owned.scratch_path
    state["active_path"] = owned.scratch_path

    with pytest.raises(
        subject.DesignPreflightError,
        match="qualified B5 lineage is not bound to this exact OwnedScratchContext",
    ):
        capture(harness)

    # Exact ownership binding is checked before active-model or design factual reads.
    assert state["calls"] == []


def test_exact_scratch_lineage_binding_continues_to_normal_classification(
    harness,
) -> None:
    snapshot = capture(harness)

    assert snapshot.status is subject.DesignPreflightStatus.ABSENT
    assert snapshot.ownership_proof_ref == "owned-scratch:test"
    assert (
        "owned-scratch:test"
        in harness[2].capture_provenance_refs
    )


def test_timeout_reaches_identity_availability_and_summary_read_seams(
    harness,
) -> None:
    context, owned, analysis, topology, state = harness

    snapshot = subject.capture_design_preflight(
        context=context,
        owned_scratch=owned,
        analysis_lineage=analysis,
        topology=topology,
        timeout_seconds=12.75,
    )

    assert snapshot.status is subject.DesignPreflightStatus.ABSENT
    assert state["calls"] == [
        ("identity", None, 12.75),
        ("availability", None, 12.75),
        ("summary", "10", 12.75),
        ("summary", "20", 12.75),
    ]


def test_parent_analysis_source_mismatch_blocks(harness) -> None:
    _context, _owned, analysis, _topology, state = harness
    analysis.result.source_model_ref = "source-model-ref:other"

    with pytest.raises(
        subject.DesignPreflightError,
        match="different source-model root",
    ):
        capture(harness)

    assert state["calls"] == []


def test_topology_epoch_mismatch_blocks(harness) -> None:
    context, _owned, _analysis, _topology, state = harness
    context.reject_epoch = True

    with pytest.raises(
        subject.DesignPreflightError,
        match="does not belong to the active acquisition context",
    ):
        capture(harness)

    assert state["calls"] == []


def test_snapshot_identity_is_deterministic_for_same_semantic_population(
    harness,
) -> None:
    first = capture(harness)
    second = capture(harness)

    assert first.preflight_ref == second.preflight_ref
    assert first.column_census.census_ref == second.column_census.census_ref


def test_expected_column_census_is_order_independent(monkeypatch, harness) -> None:
    context, owned, analysis, _topology, state = harness
    reversed_topology = _FakeTopology(
        model_fingerprint=context.model_fingerprint,
        evidence_epoch_id=context.evidence_epoch_id,
        names=("20", "10"),
    )
    # Preserve component identities so only input order differs.
    reversed_topology.topology = SimpleNamespace(
        columns=tuple(
            reversed(
                _FakeTopology(
                    model_fingerprint=context.model_fingerprint,
                    evidence_epoch_id=context.evidence_epoch_id,
                    names=("10", "20"),
                ).topology.columns
            )
        )
    )

    first = capture(harness)
    second = subject.capture_design_preflight(
        context=context,
        owned_scratch=owned,
        analysis_lineage=analysis,
        topology=reversed_topology,
    )

    assert first.column_census.census_ref == second.column_census.census_ref
    assert first.preflight_ref == second.preflight_ref
    assert state["calls"]


def test_preflight_snapshot_is_not_publicly_constructible() -> None:
    with pytest.raises(TypeError, match="factory-created only"):
        subject.DesignPreflightSnapshot(
            status=subject.DesignPreflightStatus.ABSENT,
            source_model_ref="source:test",
            analysis_result_ref="analysis-result:test",
            analysis_lineage_qualification_ref="analysis-lineage:test",
            ownership_proof_ref="scratch:test",
            model_fingerprint="model:test",
            evidence_epoch_id="epoch:test",
            availability=ConcreteDesignResultsAvailabilityFact(False, False),
            column_census=object(),
            blockers=(),
            provenance_refs=("test",),
        )
