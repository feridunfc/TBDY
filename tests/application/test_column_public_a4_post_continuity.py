"""A4 compares qualified property semantics across fresh acquisitions."""
from dataclasses import replace
import logging
from types import SimpleNamespace as NS
import uuid

import pytest

import tbdy_engine.application.column_public_a5 as a5
import tbdy_engine.application.project_execution as project
from tests.application._a4_property_facts import section_fact, material_fact, fresh_capture
from tests.application import test_column_public_population_project_root as population


def _row(name="1", capture="property-capture:pre"):
    return NS(frame_name=name, base_fact=NS(semantic_state_ref=f"base:{name}"),
              section_mechanics=section_fact(capture=capture),
              isotropic_material=material_fact(capture=capture),
              releases=NS(evidence_ref=f"release:{name}"))


def _column(name="1", height=3.):
    return NS(component_id=f"Story:C:{name}", unique_name=name,
              as_dict=lambda: {"unique_name": name, "height": height})


def _area(thickness=.2):
    return NS(area_name="A1", orientation="WALL", property_name="W1",
              property_state=NS(family="WALL", family_type_code=1, shell_type_code=1,
                                material_name="C35", thickness=thickness),
              local_axes_angle_degrees=0., advanced_local_axes=False,
              transformation_matrix=(), raw_material_overwrite_name=None,
              diaphragm_assignment=None, diaphragm_definition=None, wall_assignment=None)


@pytest.fixture
def continuity_case(monkeypatch):
    pre = NS(expected_frame_names=("1",), rows=(_row(),),
             line_spring_property_universe=NS(evidence_ref="springs:stable"))
    post_row = _row(capture="property-capture:post")
    post = NS(**{**vars(pre), "rows": (post_row,)})
    topology = NS(columns=(_column(),))
    area = NS(expected_area_names=("A1",), rows=(_area(),))
    after = NS(topology=topology, frame=post, area=area)
    base_checks = []
    monkeypatch.setattr(a5, "capture_frame_flexural_base_continuity_evidence",
                        lambda **kwargs: base_checks.append(kwargs))
    monkeypatch.setattr(a5, "capture_etabs_strict_column_topology_from_session",
                        lambda *_args, **_kwargs: NS(topology=after.topology))
    monkeypatch.setattr(a5, "capture_frame_eq713_factual_population",
                        lambda *_args, **_kwargs: after.frame)
    monkeypatch.setattr(a5, "capture_area_contributor_population_from_session",
                        lambda *_args, **_kwargs: after.area)

    def prove():
        return a5._prove_post_continuity(
            context=NS(verified_session=object(), model_fingerprint="model",
                       evidence_epoch_id="epoch", session_provenance_ref="session"),
            owned_scratch=object(), topology_pre=topology,
            target_column=topology.columns[0], frame_pre=pre, area_pre=area,
            established_state=object(), execution_result=object(), verify_full_population=True,
        )
    return NS(pre=pre, post=post, topology=topology, after=after,
              prove=prove, base_checks=base_checks)


def test_fresh_capture_digests_differ_but_qualified_semantics_pass(continuity_case):
    case = continuity_case
    for field in ("section_mechanics", "isotropic_material"):
        pre, post = getattr(case.pre.rows[0], field), getattr(case.post.rows[0], field)
        assert pre.capture_ref != post.capture_ref
        assert pre.evidence_ref != post.evidence_ref
        assert all(p.evidence_ref != q.evidence_ref for p, q in zip(pre.unit_provenance, post.unit_provenance))
    assert case.prove()[2] is case.post


def _changed_fact(fact, field, value):
    changes = {field: value}
    positions = ({"area": 0, "shear_area_2": 1, "shear_area_3": 2,
                  "torsional_constant": 3, "inertia_22": 4, "inertia_33": 5,
                  "return_code": 12} if hasattr(fact, "section_name") else
                 {"modulus_of_elasticity": 0, "poisson_ratio": 1,
                  "thermal_coefficient": 2, "shear_modulus": 3, "return_code": 4})
    if field in positions:
        raw = list(fact.raw_response)
        raw[positions[field]] = value
        changes["raw_response"] = tuple(raw)
    changed = replace(fact, **changes)
    # Keep each changed acquisition internally bound: reject actual semantics,
    # rather than relying solely on a broken capture/raw/subject binding.
    return replace(changed, unit_provenance=tuple(replace(
        p, raw_response_ref=changed.raw_response_ref,
        subject_key=getattr(changed, "section_name", getattr(changed, "material_name", None)),
        source_model_ref=changed.source_model_ref, session_ref=changed.session_ref,
        return_code=changed.return_code,
    ) for p in changed.unit_provenance))


@pytest.mark.parametrize("property_name,field,value", [
    ("section_mechanics", "section_name", "other-section"),
    *( ("section_mechanics", field, 1.23) for field in
       ("area", "shear_area_2", "shear_area_3", "torsional_constant", "inertia_22", "inertia_33") ),
    ("section_mechanics", "raw_response", (.4, .3, .3, .006, .0083, .0213, 99., 2., 3., 4., 5., 6., 0)),
    ("isotropic_material", "material_name", "other-material"),
    *( ("isotropic_material", field, 1.23) for field in
       ("modulus_of_elasticity", "poisson_ratio", "thermal_coefficient", "shear_modulus", "temperature") ),
    ("isotropic_material", "raw_response", (33000, .2, 1.e-5, 13200., 0)),
    *( (prop, field, value) for prop in ("section_mechanics", "isotropic_material")
       for field, value in (("source_model_ref", "foreign-source"), ("session_ref", "foreign-session"),
                            ("return_code", 2)) ),
])
def test_changed_factual_property_fails(continuity_case, property_name, field, value):
    row = continuity_case.post.rows[0]
    setattr(row, property_name, _changed_fact(getattr(row, property_name), field, value))
    with pytest.raises(a5.PublicA5CompositionError, match=property_name) as caught:
        continuity_case.prove()
    assert caught.value.blocker == a5.BLOCKER_A4_POST_CONTINUITY


@pytest.mark.parametrize("property_name,key", [
    ("section_mechanics", "I22"), ("section_mechanics", "I33"),
    ("isotropic_material", "E"), ("isotropic_material", "G"),
])
@pytest.mark.parametrize("field,value", [
    ("source_unit", "mm4"), ("output_key", "other-output"), ("dimension", "L"),
    ("authority_ref", "other-authority"), ("authority_version", "other-version"),
    ("authority_kind", "UNVERIFIED"), ("qualification", "UNIT_UNQUALIFIED"),
    ("reason", "other-reviewed-reason"), ("source_model_ref", "foreign-source"),
    ("session_ref", "foreign-session"), ("raw_response_ref", "foreign-raw"),
    ("capture_ref", "foreign-capture"), ("return_code", 1),
    ("source_call", "foreign-call"), ("subject_key", "foreign-subject"),
    ("unit_state_after", "drifted-state"),
])
def test_unit_semantic_or_binding_change_fails(continuity_case, property_name, key, field, value):
    row = continuity_case.post.rows[0]
    fact = getattr(row, property_name)
    bindings = tuple(replace(p, **{field: value}) if p.output_key == key else p for p in fact.unit_provenance)
    setattr(row, property_name, replace(fact, unit_provenance=bindings))
    with pytest.raises(a5.PublicA5CompositionError, match=property_name):
        continuity_case.prove()


@pytest.mark.parametrize("property_name,key", [
    ("section_mechanics", "I22"), ("section_mechanics", "I33"),
    ("isotropic_material", "E"), ("isotropic_material", "G"),
])
@pytest.mark.parametrize("defect", ["missing", "duplicate", "both-unqualified"])
def test_each_output_remains_independently_qualified(continuity_case, property_name, key, defect):
    rows = (continuity_case.pre.rows[0], continuity_case.post.rows[0]) if defect == "both-unqualified" else (continuity_case.post.rows[0],)
    for row in rows:
        fact = getattr(row, property_name)
        if defect == "duplicate":
            bindings = (*fact.unit_provenance, next(p for p in fact.unit_provenance if p.output_key == key))
        else:
            bindings = tuple(p for p in fact.unit_provenance if p.output_key != key)
        setattr(row, property_name, replace(fact, unit_provenance=bindings))
    with pytest.raises(a5.PublicA5CompositionError, match="MISSING_OR_DUPLICATE") as caught:
        continuity_case.prove()
    assert caught.value.__cause__ is not None


@pytest.mark.parametrize("change", ["topology", "column-population", "frame-population", "base", "release", "area", "area-population", "springs", "spring-availability"])
def test_existing_continuity_guards_remain(continuity_case, change):
    case = continuity_case
    if change == "topology":
        case.after.topology = NS(columns=(_column(height=4.),))
    elif change == "column-population":
        case.after.topology = NS(columns=(_column(), _column("2")))
    elif change == "frame-population":
        case.post.expected_frame_names = ("1", "2")
    elif change == "base":
        case.post.rows[0].base_fact = NS(semantic_state_ref="changed-base")
    elif change == "release":
        case.post.rows[0].releases = NS(evidence_ref="changed-release")
    elif change == "area":
        case.after.area = NS(expected_area_names=("A1",), rows=(_area(.3),))
    elif change == "area-population":
        case.after.area = NS(expected_area_names=(), rows=())
    else:
        case.post.line_spring_property_universe = None if change == "spring-availability" else NS(evidence_ref="changed-springs")
    with pytest.raises(a5.PublicA5CompositionError) as caught:
        case.prove()
    assert caught.value.blocker == a5.BLOCKER_A4_POST_CONTINUITY


def test_260_fresh_property_acquisitions_pass_full_population_a4(continuity_case):
    case = continuity_case
    names = tuple(str(i) for i in range(260))
    case.topology.columns = tuple(_column(name) for name in names)
    case.pre.expected_frame_names = case.post.expected_frame_names = names
    case.pre.rows = tuple(_row(name, f"property-capture:{uuid.uuid4()}") for name in names)
    case.post.rows = tuple(_row(name, f"property-capture:{uuid.uuid4()}") for name in names)
    assert case.prove()[2] is case.post
    assert len(case.base_checks) == 260


def test_public_population_fresh_acquisitions_reach_real_fnd2_and_shared_b6(monkeypatch):
    setup = population._install_two_column_harness(monkeypatch)
    b6_counts, _ = population._install_real_b6_owner(monkeypatch, setup)
    acquisitions = []

    def capture(*_args, **_kwargs):
        rows = tuple(NS(**{**vars(row),
            "section_mechanics": fresh_capture(row.section_mechanics, f"property-capture:{uuid.uuid4()}"),
            "isotropic_material": fresh_capture(row.isotropic_material, f"property-capture:{uuid.uuid4()}"),
        }) for row in setup.frame_population.rows)
        acquisitions.append(rows)
        return NS(**{**vars(setup.frame_population), "rows": rows})

    monkeypatch.setattr(a5, "capture_frame_eq713_factual_population", capture)
    result = project.execute_project(population._two_column_request(), verified_session=setup.module._FakeSession())
    assert len(acquisitions) >= 2
    assert acquisitions[0][0].section_mechanics.evidence_ref != acquisitions[-1][0].section_mechanics.evidence_ref
    assert acquisitions[0][0].isotropic_material.evidence_ref != acquisitions[-1][0].isotropic_material.evidence_ref
    assert len(result.columns) == 2
    assert all(item.fnd_col_2_execution is not None for item in result.columns)
    assert all(a5.BLOCKER_A4_POST_CONTINUITY not in item.blockers for item in result.columns)
    assert b6_counts["controlled_design"] == b6_counts["start_design"] == 1


@pytest.mark.parametrize("qualified_error", [False, True])
def test_outer_a4_failure_retains_exception_diagnostic_and_blocks(monkeypatch, caplog, qualified_error):
    setup = population._install_two_column_harness(monkeypatch)
    def fail(**_kwargs):
        if qualified_error:
            raise a5.PublicA5CompositionError(a5.BLOCKER_A4_POST_CONTINUITY, "Frame 2 I33 authority mismatch")
        raise RuntimeError("post property acquisition ABI mismatch")
    monkeypatch.setattr(a5, "_prove_post_continuity", fail)
    with caplog.at_level(logging.ERROR, logger=a5.__name__):
        result = project.execute_project(population._two_column_request(), verified_session=setup.module._FakeSession())
    assert all(item.status == "FACTUAL_ACQUISITION_BLOCKED" for item in result.columns)
    assert all(a5.BLOCKER_A4_POST_CONTINUITY in item.blockers for item in result.columns)
    message = "Frame 2 I33 authority mismatch" if qualified_error else "post property acquisition ABI mismatch"
    assert message in caplog.text
    assert any(record.exc_info is not None for record in caplog.records)
