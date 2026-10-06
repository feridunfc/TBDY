"""Offline binding checks; synthetic facts do not establish B-BLOK live readiness."""
from dataclasses import fields, replace
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

import test_column_public_mixed_vertical as vertical
from tbdy_engine.design.columns.story_relative_translation import ReviewedStoryTranslationTolerance


MISSING = "A17:REVIEWED_STORY_TRANSLATION_TOLERANCE_NOT_BOUND"


@pytest.fixture
def inputs(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[2] / "tools/column_r1_bblok_e1_reviewed_inputs.py"
    spec = spec_from_file_location("_e1_inputs_test", path)
    wrapper = module_from_spec(spec)
    spec.loader.exec_module(wrapper)
    assert wrapper.ACCEPTED_INPUTS_SHA256 == (
        "9D7BAE7108C655751C018071E9B17D1D401A21904DAAD140BDBE81566AC9FBBC"
    )
    fixture = ModuleType("_e1_reviewed_fixture")
    fixture.request = vertical.population._two_column_request()
    fixture.dependencies = {
        "column_design_basis": replace(vertical._basis(), story_translation_tolerance=None),
        "expected_combo_policy": object(),
        "reviewed_vs5_column_axial_context": object(),
    }
    monkeypatch.setitem(sys.modules, fixture.__name__, fixture)
    source = tmp_path / "reviewed_inputs.py"
    source.write_text(
        "from _e1_reviewed_fixture import request, dependencies\n"
        "def load_inputs(): return request, dependencies\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(wrapper, "ACCEPTED_INPUTS", source)
    monkeypatch.setattr(wrapper, "ACCEPTED_INPUTS_SHA256", sha256(source.read_bytes()).hexdigest().upper())
    return wrapper, fixture


def test_binding_preserves_request_and_every_other_reviewed_field(inputs):
    wrapper, fixture = inputs
    request, dependencies = wrapper.load_inputs()
    assert request is fixture.request
    assert set(dependencies) == set(fixture.dependencies)
    before = fixture.dependencies["column_design_basis"]
    after = dependencies["column_design_basis"]
    assert before.story_translation_tolerance is None
    assert after.story_translation_tolerance is wrapper.REVIEWED_TOLERANCE
    assert after.story_translation_tolerance.absolute_tolerance_mm == 0.01
    assert after.story_translation_tolerance.source_ref == "B-BLOK-COLUMN-A17-TOL-v1"
    for field in fields(before):
        if field.name != "story_translation_tolerance":
            assert getattr(after, field.name) == getattr(before, field.name)
    for key in dependencies.keys() - {"column_design_basis"}:
        assert dependencies[key] is fixture.dependencies[key]


def test_wrong_project_input_hash_fails_before_execution(inputs):
    wrapper, _ = inputs
    wrapper.ACCEPTED_INPUTS.write_text("raise AssertionError('must not execute')\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        wrapper.load_inputs()


@pytest.mark.parametrize("failure", ["dependency", "basis", "conflict"])
def test_wrong_scope_or_conflicting_authority_fails_closed(inputs, failure):
    wrapper, fixture = inputs
    if failure == "dependency":
        fixture.dependencies["verified_session"] = object()
        error, message = ValueError, "dependency scope mismatch"
    elif failure == "basis":
        fixture.dependencies["column_design_basis"] = object()
        error, message = TypeError, "ReviewedColumnDesignBasis"
    else:
        fixture.dependencies["column_design_basis"] = replace(
            fixture.dependencies["column_design_basis"],
            story_translation_tolerance=ReviewedStoryTranslationTolerance(0.02, "other-review"),
        )
        error, message = ValueError, "conflicts with v1"
    with pytest.raises(error, match=message):
        wrapper.load_inputs()


@pytest.mark.parametrize("approved", [False, True])
def test_public_root_reaches_real_a17_with_explicit_authority_only(monkeypatch, inputs, approved):
    wrapper, fixture = inputs
    harness = vertical._install(monkeypatch)
    fixture.dependencies["expected_combo_policy"] = vertical._policy(harness.combos)
    fixture.dependencies["reviewed_vs5_column_axial_context"] = vertical._axial_context()
    request, dependencies = wrapper.load_inputs() if approved else (fixture.request, fixture.dependencies)
    seen, translations = [], []
    owner = vertical.a5.build_public_a5_canonical_second_order_payload
    equality_owner = vertical.stability.resolve_uniform_story_relative_translation

    class A17Observed(BaseException):
        """End this binding test before unrelated downstream design/selection."""

    def capture(**kwargs):
        payload = owner(**kwargs)
        seen.append((kwargs["component_id"], kwargs["reviewed_story_translation_tolerance"], payload))
        if approved:
            raise A17Observed
        return payload

    def capture_equality(*args, **kwargs):
        result = equality_owner(*args, **kwargs)
        translations.append((kwargs["tolerance"], result.source_refs))
        return result

    monkeypatch.setattr(vertical.a5, "build_public_a5_canonical_second_order_payload", capture)
    monkeypatch.setattr(vertical.stability, "resolve_uniform_story_relative_translation", capture_equality)

    def execute():
        return vertical.project.execute_project(
            request, verified_session=harness.setup.module._FakeSession(), **dependencies,
        )

    if approved:
        with pytest.raises(A17Observed):
            execute()
        assert len(seen) == 1
    else:
        result = execute()
        assert len(result.columns) == len(seen) == 2
    expected = wrapper.REVIEWED_TOLERANCE if approved else None
    assert all(tolerance is expected for _, tolerance, _ in seen)
    c1 = next(payload for cid, _, payload in seen if cid == vertical.C1)
    blockers = tuple(c1["canonical_second_order"]["blockers"])
    if approved:
        assert MISSING not in blockers
        assert translations
        assert all(t is expected and expected.source_ref in refs for t, refs in translations)
    else:
        assert blockers == (MISSING,)
        assert not translations
        c2 = next(payload for cid, _, payload in seen if cid == vertical.C2)
        assert any(b.startswith("A18:") for b in c2["canonical_second_order"]["blockers"])
