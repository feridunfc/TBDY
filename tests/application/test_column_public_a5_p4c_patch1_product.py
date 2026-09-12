from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_public_a5 as a5
import tbdy_engine.application.project_execution as project_execution
import tbdy_engine.integration.etabs_analysis_state_mutation as b4b
from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (
    AreaEq713TargetDisposition,
    AreaStiffnessMode,
    ContributorDisposition,
    Eq713PopulationDisposition,
    FrameModeAuditDisposition,
    FrameStiffnessMode,
    ModeDisposition,
)
from tbdy_engine.etabs.oapi.area_contributors import AreaDesignOrientation
from tbdy_engine.etabs.oapi.area_modifiers import (
    AreaModifierReadFact,
    AreaModifierSetFact,
    AreaModifierSurface,
    AreaModifierVector,
)
from tbdy_engine.etabs.oapi.eq713_response_results import AreaStrainShellResponseRow
from tbdy_engine.providers.etabs_area_contributor_provider import AreaPropertyFamily


def _load_test_module(name: str, path: Path):
    spec = spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_APP_TEST_DIR = Path(__file__).resolve().parent
base = _load_test_module(
    "_column_public_a5_product_path_base_for_p4c",
    _APP_TEST_DIR / "test_column_public_a5_product_path.py",
)
frame_join = _load_test_module(
    "_column_public_a5_frame_join_for_p4c",
    _APP_TEST_DIR / "test_column_public_a5_frame_production_join.py",
)


def _mode(mode, disposition, reason="p4c-patch-1"):
    return ModeDisposition(mode, disposition, reason, ("p4c-patch-1:mode",))


def _blocked_frame(name: str) -> FrameModeAuditDisposition:
    reason = "participation in Eq7.13 Delta_i is unresolved"
    return FrameModeAuditDisposition(
        name,
        (_mode(FrameStiffnessMode.FLEXURE_2, ContributorDisposition.BLOCKED_UNSUPPORTED, reason),),
        (reason,),
        (f"frame:{name}",),
    )


def _blocked_area(name: str) -> AreaEq713TargetDisposition:
    reason = "plate participation in Eq7.13 Delta_i is unresolved"
    return AreaEq713TargetDisposition(
        name,
        (_mode(AreaStiffnessMode.M11, ContributorDisposition.BLOCKED_UNSUPPORTED, reason),),
        (0.5,) * 8 + (1.0, 1.0),
        (reason,),
        (f"area:{name}",),
    )


def _execution(identity: str):
    return SimpleNamespace(
        analysis_result_identity=SimpleNamespace(identity_ref=identity),
        execution_proof_ref=f"proof:{identity}",
    )


def test_mixed_target_change_without_new_positive_participation_fails_closed(monkeypatch):
    context = SimpleNamespace(
        verified_session=object(),
        model_fingerprint="model:p4c-patch-1",
        evidence_epoch_id="epoch:p4c-patch-1",
    )
    execution = _execution("result:G0")
    provisional = Eq713PopulationDisposition(
        frame_rows=(_blocked_frame("B1"),),
        area_rows=(_blocked_area("A1"),),
    )
    unresolved = Eq713PopulationDisposition(
        frame_rows=(_blocked_frame("B1"),),
        area_rows=(_blocked_area("A1"),),
    )

    monkeypatch.setattr(a5, "_initial_beam_classifications", lambda *_args: {})
    monkeypatch.setattr(
        a5,
        "_run_a3_generation",
        lambda **_kwargs: (("T0",), SimpleNamespace(), execution),
    )
    monkeypatch.setattr(
        a5,
        "capture_eq713_response_population_from_session",
        lambda _session, **kwargs: SimpleNamespace(
            model_fingerprint=context.model_fingerprint,
            evidence_epoch_id=context.evidence_epoch_id,
            analysis_result_ref=execution.analysis_result_identity.identity_ref,
            execution_proof_ref=execution.execution_proof_ref,
            case_names=tuple(kwargs["case_names"]),
            frame_names=tuple(kwargs["frame_names"]),
            area_names=tuple(kwargs["area_names"]),
        ),
    )
    monkeypatch.setattr(a5, "_classify_beam_generation", lambda **_kwargs: {})
    monkeypatch.setattr(
        a5,
        "_area_shell_thick_generations_from_response",
        lambda **_kwargs: {"A1": object()},
    )
    monkeypatch.setattr(a5, "_build_a3", lambda **_kwargs: (unresolved, ()))
    monkeypatch.setattr(a5, "_b4b_targets", lambda *_args: ("T1",))

    with pytest.raises(
        a5.PublicA5CompositionError,
        match="without learning a new positive Frame/Area response participation mode",
    ):
        a5._legacy_area_response_closure(
            context=context,
            owned_scratch=object(),
            frame_pre=SimpleNamespace(rows=()),
            area_pre=SimpleNamespace(rows=()),
            topology_pre=object(),
            provisional_a3=provisional,
            frame_names=("B1",),
            area_names=("A1",),
            unresolved_count=2,
            requested_cases=("EX", "EY"),
            qualified_static_cases=("EX", "EY"),
            qualified_static_refs=("qualified:xy",),
        )


def _area_modifier(surface: AreaModifierSurface, target: str, values) -> AreaModifierReadFact:
    return AreaModifierReadFact(
        surface=surface,
        target_name=target,
        modifiers=AreaModifierVector.from_sequence(values),
        return_code=0,
    )


def _area_fact(
    *,
    name: str,
    property_name: str,
    orientation: AreaDesignOrientation,
    family: AreaPropertyFamily | None,
    shell_type: int | None,
    thickness: float | None,
    property_values=(0.5,) * 8 + (1.0, 1.0),
):
    null = orientation is AreaDesignOrientation.NULL
    state = None
    if not null:
        state = SimpleNamespace(
            family=family,
            family_type_code=0,
            shell_type_code=shell_type,
            material_name="C35",
            thickness=thickness,
            property_modifiers=_area_modifier(
                AreaModifierSurface.AREA_PROPERTY,
                property_name,
                property_values,
            ),
        )
    wall = orientation is AreaDesignOrientation.WALL
    floor = orientation is AreaDesignOrientation.FLOOR
    return SimpleNamespace(
        area_name=name,
        orientation=orientation,
        property_name=property_name,
        property_state=state,
        local_axes_angle_degrees=0.0,
        advanced_local_axes=False,
        transformation_matrix=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        raw_material_overwrite_name="None",
        diaphragm_assignment=SimpleNamespace(diaphragm_name="D1") if floor else None,
        diaphragm_definition=SimpleNamespace(semi_rigid=True) if floor else None,
        wall_assignment=(
            SimpleNamespace(pier_name="P1", spandrel_name="None") if wall else None
        ),
        object_modifiers=_area_modifier(
            AreaModifierSurface.AREA_OBJECT,
            name,
            (1.0,) * 10,
        ),
        semi_rigid_diaphragm_assigned=True if floor else False,
        wall_assignment_role="PIER" if wall else None,
        default_local_axes_assignment_proven=True if wall else None,
        source_refs=(f"area-fact:{name}",),
    )


def _strain_row(area_name: str, case_name: str, generation: int):
    return AreaStrainShellResponseRow(
        object_name=area_name,
        element_name=f"{area_name}:E1",
        point_element_name=f"{area_name}:P1",
        load_case=case_name,
        step_type="",
        step_number=float(generation),
        e11_top=3.0,
        e22_top=5.0,
        g12_top=7.0,
        emax_top=0.0,
        emin_top=0.0,
        eangle_top=0.0,
        evm_top=0.0,
        e11_bottom=1.0,
        e22_bottom=1.0,
        g12_bottom=1.0,
        emax_bottom=0.0,
        emin_bottom=0.0,
        eangle_bottom=0.0,
        evm_bottom=0.0,
        g13_avg=11.0,
        g23_avg=13.0,
        gmax_avg=0.0,
        gangle_avg=0.0,
    )


def test_execute_project_public_mixed_whole_system_reaches_fnd2_with_only_final_b5_identity(monkeypatch):
    proof = frame_join._configure(monkeypatch, zero_v2=False)

    floor_shell = _area_fact(
        name="F-SHELL",
        property_name="SLAB-THICK",
        orientation=AreaDesignOrientation.FLOOR,
        family=AreaPropertyFamily.SLAB,
        shell_type=2,
        thickness=0.20,
    )
    wall_shell = _area_fact(
        name="W-SHELL",
        property_name="WALL-THICK",
        orientation=AreaDesignOrientation.WALL,
        family=AreaPropertyFamily.WALL,
        shell_type=2,
        thickness=0.30,
    )
    membrane = _area_fact(
        name="F-MEM",
        property_name="SLAB-MEM",
        orientation=AreaDesignOrientation.FLOOR,
        family=AreaPropertyFamily.SLAB,
        shell_type=3,
        thickness=0.15,
    )
    null = _area_fact(
        name="NULL-1",
        property_name="None",
        orientation=AreaDesignOrientation.NULL,
        family=None,
        shell_type=None,
        thickness=None,
    )
    area_population = SimpleNamespace(
        expected_area_names=("F-MEM", "F-SHELL", "NULL-1", "W-SHELL"),
        rows=(membrane, floor_shell, null, wall_shell),
        source_refs=("area-population:p4c-patch-1",),
    )
    monkeypatch.setattr(
        a5,
        "capture_area_contributor_population_from_session",
        lambda *_args, **_kwargs: area_population,
    )

    area_values = {
        (AreaModifierSurface.AREA_PROPERTY.value, row.property_name): row.property_state.property_modifiers.modifiers
        for row in (membrane, floor_shell, wall_shell)
    }

    def get_area(_session, *, surface, target_name, timeout_seconds=30.0):
        return AreaModifierReadFact(
            surface=surface,
            target_name=target_name,
            modifiers=area_values[(surface.value, target_name)],
            return_code=0,
        )

    def set_area(_session, *, surface, target_name, modifiers, timeout_seconds=30.0):
        area_values[(surface.value, target_name)] = modifiers
        return AreaModifierSetFact(
            surface=surface,
            target_name=target_name,
            requested_modifiers=modifiers,
            return_code=0,
        )

    monkeypatch.setattr(b4b, "get_area_modifiers_from_session", get_area)
    monkeypatch.setattr(b4b, "set_area_modifiers_from_session", set_area)
    monkeypatch.setattr(
        a5,
        "probe_eq713_response_population_capability",
        lambda *_args, **_kwargs: ("FrameForce", "AreaStrainShell"),
    )

    response_calls = []

    def capture_response(
        _session,
        *,
        model_fingerprint,
        evidence_epoch_id,
        analysis_result_ref,
        execution_proof_ref,
        case_names,
        frame_names,
        area_names,
        case_scope_refs,
    ):
        generation = len(response_calls)
        response_calls.append(
            (
                tuple(case_names),
                tuple(frame_names),
                tuple(area_names),
                tuple(case_scope_refs),
                analysis_result_ref,
            )
        )
        assert tuple(frame_names) == ("B1",)
        assert tuple(area_names) == ("F-SHELL", "W-SHELL")
        frame_results = tuple(
            SimpleNamespace(
                frame_name="B1",
                case_name=case_name,
                rows=(
                    SimpleNamespace(p=10.0, v2=20.0, v3=30.0, t=5.0, m2=40.0, m3=50.0),
                ),
                evidence_ref=f"frame:B1:{case_name}:g{generation}",
            )
            for case_name in case_names
        )
        area_strain_results = tuple(
            SimpleNamespace(
                area_name=area_name,
                case_name=case_name,
                rows=(_strain_row(area_name, case_name, generation),),
                evidence_ref=f"strain:{area_name}:{case_name}:g{generation}",
            )
            for area_name in area_names
            for case_name in case_names
        )
        return SimpleNamespace(
            model_fingerprint=model_fingerprint,
            evidence_epoch_id=evidence_epoch_id,
            analysis_result_ref=analysis_result_ref,
            execution_proof_ref=execution_proof_ref,
            case_names=tuple(case_names),
            frame_names=tuple(frame_names),
            area_names=tuple(area_names),
            frame_results=frame_results,
            area_results=(),
            area_strain_results=area_strain_results,
            source_refs=("response:p4c-patch-1", *case_scope_refs),
            evidence_ref=f"response:p4c-patch-1:g{generation}",
        )

    monkeypatch.setattr(a5, "capture_eq713_response_population_from_session", capture_response)

    observed_a3 = []
    real_build = a5._build_a3

    def build_probe(**kwargs):
        result = real_build(**kwargs)
        observed_a3.append(result[0])
        return result

    monkeypatch.setattr(a5, "_build_a3", build_probe)

    result = project_execution.execute_project(
        proof.harness.request,
        verified_session=base._FakeSession(),
    )

    assert result.column.fnd_col_2_execution is not None
    assert proof.harness.runtime["run_calls"] == 2
    assert len(response_calls) == 2
    assert [row[4] for row in response_calls] == proof.generation_refs
    assert proof.fnd2_result_refs == [proof.generation_refs[-1]]
    assert proof.generation_refs[0] != proof.generation_refs[-1]
    assert all(row[0] == ("quake-alpha", "quake-beta") for row in response_calls)
    assert all(row[1] == ("B1",) for row in response_calls)
    assert all(row[2] == ("F-SHELL", "W-SHELL") for row in response_calls)

    positive = [whole for whole in observed_a3 if whole.positive]
    assert positive
    final = positive[-1]
    assert tuple(row.component_uid for row in final.frame_rows) == ("1", "B1")
    assert tuple(row.area_name for row in final.area_rows) == (
        "F-MEM",
        "F-SHELL",
        "NULL-1",
        "W-SHELL",
    )
    assert area_values[(AreaModifierSurface.AREA_PROPERTY.value, "SLAB-THICK")].as_tuple()[:8] == (1.0,) * 8
    assert area_values[(AreaModifierSurface.AREA_PROPERTY.value, "WALL-THICK")].as_tuple()[:8] == (
        0.5,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
    )
