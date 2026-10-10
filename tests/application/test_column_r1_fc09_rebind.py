"""FC09 same-value rebind and source guards; all live boundaries are offline mocks."""
from dataclasses import fields, is_dataclass
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import sys

import pytest

from test_column_r1_bblok_e1_binding import inputs as historical_inputs
import tools.column_r1_bblok_e1_reviewed_inputs as accepted_loader


FC09 = "FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F"
OLD_5AA = "5AA83947C46AE886DD43E8BD2270DAEAC6117AE60BAD1F8CB9ED9874CD3E2A44"
INPUT_SHA = "9D7BAE7108C655751C018071E9B17D1D401A21904DAAD140BDBE81566AC9FBBC"
AUTHORITY = "B-BLOK-COLUMN-FC09-REBIND-v1"
ROOT = Path(__file__).resolve().parents[2]


def load_tool(name):
    spec = spec_from_file_location("_fc09_test_"+name, ROOT / "tools" / (name+".py"))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def wrapper():
    return load_tool("column_r1_bblok_fc09_reviewed_inputs")


@pytest.fixture
def synthetic_inputs(wrapper, historical_inputs, monkeypatch):
    loader, fixture = historical_inputs
    monkeypatch.setattr(wrapper, "_load_historical_inputs", loader.load_inputs)
    return wrapper, loader, fixture


def test_wrapper_declares_exact_current_scope_without_relabeling_historical_loader(wrapper):
    assert wrapper.CURRENT_SOURCE_SHA256 == FC09
    assert wrapper.AUTHORITY_REF == AUTHORITY
    assert wrapper.AUTHORITY_CLASSIFICATION == "REVIEWED_PROJECT_AUTHORITY / CURRENT_SOURCE_REBIND"
    assert wrapper.ACCEPTED_INPUTS_SHA256 == accepted_loader.ACCEPTED_INPUTS_SHA256 == INPUT_SHA
    assert wrapper.ACCEPTED_INPUTS == accepted_loader.ACCEPTED_INPUTS
    assert wrapper._load_historical_inputs is accepted_loader.load_inputs
    assert accepted_loader.REVIEWED_TOLERANCE.source_ref == "B-BLOK-COLUMN-A17-TOL-v1"


def test_only_A17_authority_binding_changes(synthetic_inputs):
    wrapper, _, fixture = synthetic_inputs
    request, deps = wrapper.load_inputs()
    assert request is fixture.request
    assert set(deps) == set(wrapper.AUTHORIZED_DEPENDENCIES) == set(fixture.dependencies)
    before, after = fixture.dependencies["column_design_basis"], deps["column_design_basis"]
    tolerance = after.story_translation_tolerance
    assert tolerance is wrapper.REVIEWED_TOLERANCE
    assert tolerance.absolute_tolerance_mm == 0.01 and tolerance.source_ref == AUTHORITY
    for field in fields(before):
        if field.name != "story_translation_tolerance":
            assert getattr(before,field.name) == getattr(after,field.name)
    for key in set(deps)-{"column_design_basis"}:
        assert deps[key] is fixture.dependencies[key]


def test_changed_reviewed_bytes_fail_before_execution(synthetic_inputs):
    wrapper, loader, _ = synthetic_inputs
    loader.ACCEPTED_INPUTS.write_text("raise AssertionError('changed bytes must not execute')\n")
    with pytest.raises(ValueError,match="SHA256 mismatch"):
        wrapper.load_inputs()


@pytest.mark.parametrize("failure", ["extra_dependency","missing_dependency","wrong_basis","conflicting_tolerance"])
def test_existing_hash_scope_type_and_conflict_guards_are_preserved(synthetic_inputs, failure):
    from dataclasses import replace
    from tbdy_engine.design.columns.story_relative_translation import ReviewedStoryTranslationTolerance
    wrapper, _, fixture = synthetic_inputs
    if failure == "extra_dependency":
        fixture.dependencies["reviewed_column_p7_context"] = object()
        error, message = ValueError, "dependency scope mismatch"
    elif failure == "missing_dependency":
        fixture.dependencies.pop("reviewed_vs5_column_axial_context")
        error, message = ValueError, "dependency scope mismatch"
    elif failure == "wrong_basis":
        fixture.dependencies["column_design_basis"] = object()
        error, message = TypeError, "ReviewedColumnDesignBasis"
    else:
        fixture.dependencies["column_design_basis"] = replace(fixture.dependencies["column_design_basis"],
            story_translation_tolerance=ReviewedStoryTranslationTolerance(0.02,"foreign-review"))
        error, message = ValueError, "conflicts with v1"
    with pytest.raises(error,match=message):
        wrapper.load_inputs()


def test_verified_bytes_are_read_and_executed_once(synthetic_inputs, monkeypatch):
    wrapper, loader, fixture = synthetic_inputs
    read = Path.read_bytes
    calls = []
    def once(path):
        if path == loader.ACCEPTED_INPUTS:
            calls.append(path)
            assert len(calls) == 1
        return read(path)
    monkeypatch.setattr(Path,"read_bytes",once)
    request, _ = wrapper.load_inputs()
    assert request is fixture.request and calls == [loader.ACCEPTED_INPUTS]


def test_exact_external_9D7_artifact_preserves_all_engineering_and_policy_values(wrapper, monkeypatch):
    """Optional external-byte proof; supplied explicitly in worker validation.

    The reviewed 50k file is never copied into this repository or manufactured
    as a fixture. Ordinary CI without the separately held artifact skips this
    one proof; synthetic contract/guard tests above remain self-contained.
    """
    path = os.environ.get("COLUMN_R1_ACCEPTED_INPUTS_TEST_PATH")
    if not path:
        pytest.skip("Exact separately held reviewed-input artifact not supplied")
    path = Path(path)
    original_bytes = path.read_bytes()
    assert sha256(original_bytes).hexdigest().upper() == INPUT_SHA
    monkeypatch.setattr(accepted_loader,"ACCEPTED_INPUTS",path)
    before_request, before = accepted_loader.load_inputs()
    request, deps = wrapper.load_inputs()
    assert request == before_request
    assert set(deps) == set(wrapper.AUTHORIZED_DEPENDENCIES)
    old_basis, basis = before["column_design_basis"], deps["column_design_basis"]
    for field in fields(old_basis):
        if field.name != "story_translation_tolerance":
            assert getattr(old_basis,field.name) == getattr(basis,field.name)
    assert basis.story_translation_tolerance.absolute_tolerance_mm == 0.01
    assert basis.story_translation_tolerance.source_ref == AUTHORITY
    assert [(c.material_name,c.fcd_mpa) for c in basis.concrete_strengths] == [("C35/45",23.33)]
    assert [(s.material_name,s.fyd_mpa) for s in basis.longitudinal_steel_strengths] == [("DefaultRebar_500",434.8)]
    assert [(s.material_name,s.fywk_mpa,s.fywd_mpa) for s in basis.transverse_steel_strengths] == [("DefaultRebar_500",500.,434.8)]
    assert basis.aggregate.aggregate_max_mm == 20.
    assert basis.high_ductility_applies is True and basis.limited_ductility_applies is False
    assert basis.route_c_w_applicability.state.value == "PROVEN_NOT_APPLICABLE"
    policy = deps["expected_combo_policy"]
    assert policy == before["expected_combo_policy"]
    assert {c.combo_name for c in policy.combos} == {
        "Crack_SeisX","Crack_SeisX_Soil","Crack_SeisX_Up","Crack_SeisX_UpSoil",
        "Crack_SeisY","Crack_SeisY_Soil","Crack_SeisY_Up","Crack_SeisY_UpSoil",
        "Grav_Service","Grav_TempNeg","Grav_TempPos","Grav_Ult"}
    assert len(policy.combos) == 12 and all(c.reviewed_definition is not None for c in policy.combos)
    vs5 = deps["reviewed_vs5_column_axial_context"]
    assert vs5 == before["reviewed_vs5_column_axial_context"]
    assert vs5.compression_sign == -1 and vs5.linear_superposition_reviewed is True
    assert vs5.ts500_combination_ids == ("Grav_Ult",)
    assert vs5.ts498_reduction_state.value == "NO_REDUCTION"
    assert vs5.ndm_binding.allowed_final_step_types == ("Max","Min")
    # Policies may retain original review refs; no historical result objects
    # or epochs are accepted as dependencies for the fresh R2 execution.
    def no_results(value):
        assert type(value).__name__ not in {"AnalysisResultIdentity","AnalysisStateIdentity",
                                           "DesignResultIdentity","EvidenceEpoch"}
        if is_dataclass(value):
            for field in fields(value): no_results(getattr(value,field.name))
        elif isinstance(value,dict):
            for item in value.values(): no_results(item)
        elif isinstance(value,(tuple,list)):
            for item in value: no_results(item)
    no_results(request)
    no_results(deps)
    assert path.read_bytes() == original_bytes


@pytest.fixture
def harness(monkeypatch,tmp_path):
    module = load_tool("run_column_r1_public_acceptance")
    assert module.SOURCE_SHA256 == FC09
    config = tmp_path / "config.py"
    config.write_text("def load_inputs(): return object(), {}\n")
    output = tmp_path / "outside-repo-output"
    monkeypatch.setattr(module,"_git",lambda *args: {"HEAD":"offline:head","HEAD^{tree}":"offline:tree","--porcelain":""}[args[-1]])
    monkeypatch.setattr(sys,"argv",[str(module.__file__),"--expected-sha","offline:head",
        "--expected-tree","offline:tree","--reviewed-inputs",str(config),
        "--output-dir",str(output),"--pid","2072","--execute-live"])
    import tbdy_engine.application.project_execution as project
    import tbdy_engine.etabs.safety as safety
    calls = []
    def attach(path,*,pid,allow_pid_fallback):
        assert path == str(module.SOURCE) and pid == 2072 and allow_pid_fallback is False
        calls.append("attach")
        return type("OfflineSession",(),{"close":lambda self:calls.append("close")})()
    def execute(*args,**kwargs):
        calls.append("public_root")
        raise RuntimeError("offline public-root sentinel")
    monkeypatch.setattr(safety,"attach_verified_to_running_etabs",attach)
    monkeypatch.setattr(project,"execute_project",execute)
    # Only the actual main() call observes win32; no native ETABS/COM starts.
    return module,output,calls


@pytest.mark.parametrize("pre,post,expected", [
    (OLD_5AA,OLD_5AA,"does not match the accepted source"),
    (FC09,FC09,"offline public-root sentinel"),
    (FC09,OLD_5AA,"protected source SHA256 changed"),
])
def test_current_harness_requires_FC09_before_and_after_even_on_public_failure(harness,monkeypatch,pre,post,expected):
    module, output, calls = harness
    reads = []
    def digest(path):
        if path == module.SOURCE:
            reads.append(path)
            return pre if len(reads)==1 else post
        return "offline:wrapper-integrity"
    monkeypatch.setattr(module,"_sha",digest)
    monkeypatch.setattr(sys,"platform","win32")
    with pytest.raises(RuntimeError,match=expected):
        module.main()
    if pre == OLD_5AA:
        assert len(reads)==1 and not calls and not output.exists()
    else:
        assert len(reads)==2 and calls == ["attach","public_root","close"]
        receipt = json.loads((output / "receipt.json").read_text())
        assert receipt["source_sha256_pre"] == FC09
        assert receipt["source_sha256_post"] == post
        assert receipt["source_unchanged"] is (post==FC09)


def test_authority_document_records_exact_scope_and_historical_epoch_prohibition():
    text = (ROOT / "docs/B-BLOK-COLUMN-FC09-REBIND-v1.md").read_text()
    for value in (FC09,OLD_5AA,INPUT_SHA,AUTHORITY,
        "79A7BCA0DD50F42B6D9852D2ED56DFC03D0A1CDB40A1C534EA7071F6E8C4CE00",
        "A24412D2DECB10E715C2A235FE7FDE0545B4422CEEBB428C7540D9D074D18992",
        "REVIEWED_PROJECT_AUTHORITY / CURRENT_SOURCE_REBIND"):
        assert value in text
    assert "historical result epochs must never be reused" in text
    assert "PRODUCT_ADVANCEMENT_RUN" in text
