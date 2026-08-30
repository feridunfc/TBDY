from __future__ import annotations

import ast
import inspect

import pytest

import tbdy_engine.integration.live_etabs_acquisition_context as subject
from tbdy_engine.etabs.safety import (
    EtabsIdentityMismatchError,
    attach_verified_to_running_etabs,
)
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.integration.f0_evidence_adapter import (
    EvidenceBindingSource,
    F0EvidenceBinding,
)
from tbdy_engine.regulatory.beam_min_width import STORY_KEY
from tbdy_engine.regulatory.contracts import (
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.units import UNIT_ENUM_STATE


MODEL_PATH = r"C:\tmp\ACQ_CTX_1.EDB"



_CREATED_VERIFIED_SESSIONS = []


@pytest.fixture(autouse=True)
def _close_test_owned_verified_sessions():
    try:
        yield
    finally:
        while _CREATED_VERIFIED_SESSIONS:
            _CREATED_VERIFIED_SESSIONS.pop().close()


class _FakeAnalyze:
    def GetCaseStatus(self):
        return 0, (), (), 0


class _FakeSap:
    def __init__(self, model_path=MODEL_PATH):
        self.model_path = model_path
        self.Analyze = _FakeAnalyze()
        self.DatabaseTables = object()
        self.Results = None
        self.LoadCases = None
        self.RespCombo = None
        self.DesignConcrete = None
        self.set_present_units_calls = 0

    def GetModelFilename(self, include_path=True):
        return self.model_path if include_path else self.model_path.rsplit("\\", 1)[-1]

    def GetModelFilepath(self):
        return self.model_path.rsplit("\\", 1)[0]

    def GetVersion(self):
        return "23.2.0", 23.2, 0

    def GetProgramInfo(self):
        return "ETABS", "23.2.0", "Ultimate", 0

    def GetModelIsLocked(self):
        return True

    def GetPresentUnits(self):
        return 6

    def GetDatabaseUnits(self):
        return 9

    def GetPresentUnits_2(self):
        return 3, 6, 2, 0

    def GetDatabaseUnits_2(self):
        return 4, 7, 2, 0

    def SetPresentUnits(self, value):
        self.set_present_units_calls += 1
        raise AssertionError("ACQ-CTX-1 must never change present units")


class _FakeEtabsObject:
    def __init__(self, sap_model):
        self.SapModel = sap_model

    def GetOAPIVersionNumber(self):
        return 2.3


class _FakeHelper:
    def __init__(self, etabs_object):
        self.etabs_object = etabs_object

    def GetObject(self, prog_id):
        return self.etabs_object


class _FakeComtypesClient:
    def __init__(self, etabs_object):
        self.etabs_object = etabs_object
        self.helper = _FakeHelper(etabs_object)

    def CreateObject(self, prog_id):
        return self.helper

    def GetActiveObject(self, prog_id):
        return self.etabs_object


class _FailingWin32:
    def GetActiveObject(self, prog_id):
        raise RuntimeError(prog_id)


def _verified_session(*, model_path=MODEL_PATH):
    sap = _FakeSap(model_path)
    etabs = _FakeEtabsObject(sap)
    session = attach_verified_to_running_etabs(
        model_path,
        comtypes_client=_FakeComtypesClient(etabs),
        win32com_client=_FailingWin32(),
    )
    _CREATED_VERIFIED_SESSIONS.append(session)
    return sap, session


def _context():
    sap, session = _verified_session()
    return sap, subject.create_trusted_live_acquisition_context(session)


def test_verified_session_is_required_and_direct_context_construction_is_closed():
    with pytest.raises(TypeError):
        subject.create_trusted_live_acquisition_context(object())

    sap, session = _verified_session()
    with pytest.raises(TypeError):
        subject.TrustedLiveAcquisitionContext(
            verified_session=session,
            source_model_identity=object(),
            evidence_epoch=object(),
            acquisition_generation_ref="caller:generation",
            session_provenance_ref="caller:session",
            acquisition_context_ref="caller:context",
        )
    assert sap.set_present_units_calls == 0


def test_wrong_or_changed_target_model_fails_before_context_creation():
    sap, session = _verified_session()
    sap.model_path = r"C:\tmp\WRONG.EDB"

    with pytest.raises(EtabsIdentityMismatchError):
        subject.create_trusted_live_acquisition_context(session)


def test_factory_accepts_no_caller_identity_epoch_or_provenance_strings():
    signature = inspect.signature(subject.create_trusted_live_acquisition_context)
    assert tuple(signature.parameters) == ("verified_session",)
    assert "model_fingerprint" not in signature.parameters
    assert "evidence_epoch_id" not in signature.parameters
    assert "session_provenance_ref" not in signature.parameters


def test_epoch_and_provenance_originate_inside_context_lifecycle():
    _, context = _context()

    assert context.model_fingerprint.startswith(subject.MODEL_FINGERPRINT_PREFIX)
    assert context.source_model_identity.source_model_ref.startswith(subject.SOURCE_MODEL_REF_PREFIX)
    assert context.acquisition_generation_ref.startswith(subject.ACQUISITION_GENERATION_PREFIX)
    assert context.session_provenance_ref.startswith(subject.SESSION_PROVENANCE_PREFIX)
    assert context.evidence_epoch_id.startswith(subject.ACQUISITION_EPOCH_PREFIX)
    assert context.acquisition_context_ref.startswith(subject.ACQUISITION_CONTEXT_PREFIX)
    assert context.evidence_epoch.model_fingerprint == context.model_fingerprint
    assert context.source_model_identity.source_model_ref in context.evidence_epoch.provenance_refs
    assert context.session_provenance_ref in context.evidence_epoch.provenance_refs
    assert context.acquisition_generation_ref in context.evidence_epoch.provenance_refs


def test_same_context_builds_fnd_factual_external_authority_with_owned_epoch():
    _, context = _context()
    snapshot = FeatureSnapshot(
        component_type="column",
        component_id="Story1:C1:U1",
        identity={"story": "Story1"},
    )
    binding = F0EvidenceBinding(
        source_location=EvidenceBindingSource.SNAPSHOT_IDENTITY,
        source_key="story",
        dependency_key=STORY_KEY,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.COMPONENT_STORY,
        physical_dimension=PhysicalDimension.ENUM_STATE,
        grain=Grain.COMPONENT,
        unit=UNIT_ENUM_STATE,
    )

    authorities = subject.build_component_f0_authorities_from_context(
        context=context,
        snapshot=snapshot,
        bindings=(binding,),
    )

    assert len(authorities) == 1
    authority = authorities[0]
    assert f"epoch:{context.evidence_epoch_id}" in authority.provenance_refs
    assert context.session_provenance_ref in authority.provenance_refs
    assert context.source_model_identity.source_model_ref in authority.provenance_refs


def test_same_context_supplies_p8a_identity_and_session_provenance_without_free_strings(monkeypatch):
    _, context = _context()
    captured = {}
    sentinel = object()

    def fake_acquire(session, *, model_fingerprint, evidence_epoch_id, session_provenance_ref):
        captured.update(
            session=session,
            model_fingerprint=model_fingerprint,
            evidence_epoch_id=evidence_epoch_id,
            session_provenance_ref=session_provenance_ref,
        )
        return sentinel

    monkeypatch.setattr(
        subject,
        "acquire_actual_concrete_design_combo_selection_from_session",
        fake_acquire,
    )

    result = subject.acquire_actual_concrete_design_combo_selection_from_context(
        context=context,
    )

    assert result is sentinel
    assert captured["session"] is context.verified_session
    assert captured["model_fingerprint"] == context.model_fingerprint
    assert captured["evidence_epoch_id"] == context.evidence_epoch_id
    assert captured["session_provenance_ref"] == context.session_provenance_ref


def test_context_a_rejects_context_b_epoch_even_for_same_source_model_reference():
    _, session = _verified_session()
    context_a = subject.create_trusted_live_acquisition_context(session)
    context_b = subject.create_trusted_live_acquisition_context(session)

    assert context_a.model_fingerprint == context_b.model_fingerprint
    assert context_a.evidence_epoch_id != context_b.evidence_epoch_id
    with pytest.raises(subject.LiveAcquisitionContextMismatchError):
        context_a.require_model_epoch(
            model_fingerprint=context_b.model_fingerprint,
            evidence_epoch_id=context_b.evidence_epoch_id,
        )


def test_evidence_epoch_mismatch_is_rejected():
    _, context = _context()
    with pytest.raises(subject.LiveAcquisitionContextMismatchError):
        context.require_model_epoch(
            model_fingerprint=context.model_fingerprint,
            evidence_epoch_id="epoch:other",
        )


def test_source_model_identity_mismatch_is_rejected():
    _, context = _context()
    with pytest.raises(subject.LiveAcquisitionContextMismatchError):
        context.require_model_epoch(
            model_fingerprint="etabs-model-fingerprint:source-reference-only:sha256:" + "0" * 64,
            evidence_epoch_id=context.evidence_epoch_id,
        )


def test_session_provenance_mismatch_is_rejected():
    _, context = _context()
    with pytest.raises(subject.LiveAcquisitionContextMismatchError):
        context.require_session_provenance("etabs-session-provenance:sha256:" + "0" * 64)


def test_source_model_and_model_fingerprint_semantics_explicitly_disclaim_physical_state():
    assert "NOT_PHYSICAL" in subject.SOURCE_MODEL_IDENTITY_SEMANTICS
    assert "NOT_PHYSICAL" in subject.MODEL_FINGERPRINT_SEMANTICS
    assert "IN_MEMORY_STATE" in subject.SOURCE_MODEL_IDENTITY_SEMANTICS
    assert "ANALYSIS_STATE" in subject.MODEL_FINGERPRINT_SEMANTICS


def test_source_reference_identity_is_deterministic_but_acquisition_generation_is_lifecycle_unique():
    _, session = _verified_session()
    first = subject.create_trusted_live_acquisition_context(session)
    second = subject.create_trusted_live_acquisition_context(session)

    assert first.source_model_identity == second.source_model_identity
    assert first.model_fingerprint == second.model_fingerprint
    assert first.acquisition_generation_ref != second.acquisition_generation_ref
    assert first.evidence_epoch_id != second.evidence_epoch_id
    assert first.session_provenance_ref != second.session_provenance_ref
    assert first.acquisition_context_ref != second.acquisition_context_ref

    assert first.evidence_epoch_id == first.evidence_epoch.epoch_id
    assert first.acquisition_context_ref == first.acquisition_context_ref


def test_no_analysis_design_save_unit_change_or_model_mutation_calls_exist_in_context_module():
    source = inspect.getsource(subject)
    tree = ast.parse(source)
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "RunAnalysis" not in called_attributes
    assert "StartDesign" not in called_attributes
    assert "Save" not in called_attributes
    assert "SetPresentUnits" not in called_attributes
    assert not {name for name in called_attributes if name.startswith("Set")}
    assert "AnalysisStateIdentity" not in source


def test_context_module_adds_no_engineering_authority():
    source = inspect.getsource(subject)
    tree = ast.parse(source)
    class_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert not {name for name in class_names if name.endswith("Authority")}
    assert "tbdy_engine.regulatory.authority" not in imports
    assert "tbdy_engine.regulatory.fnd_col_2_authority" not in imports
