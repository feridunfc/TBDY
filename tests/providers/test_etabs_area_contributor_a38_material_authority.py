from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest

import tbdy_engine.providers.etabs_area_contributor_provider as subject
from tbdy_engine.etabs.oapi.area_contributors import AreaDesignOrientation
from tbdy_engine.etabs.oapi.area_modifiers import (
    AreaModifierReadFact,
    AreaModifierSurface,
    AreaModifierVector,
)


class _Snapshot:
    def __init__(
        self,
        *,
        basic_rows=(),
        concrete_rows=(),
        provenance="session:a38",
    ):
        self.basic_material_rows = tuple(basic_rows)
        self.concrete_rows = tuple(concrete_rows)
        self.present_force_unit = 3
        self.present_length_unit = 4
        self.session_provenance_ref = provenance
        self.ownership_proof_ref = "owned:a38"


def _modifier(surface, target):
    return AreaModifierReadFact(
        surface=surface,
        target_name=target,
        modifiers=AreaModifierVector.from_sequence((1.0,) * 10),
        return_code=0,
    )


def _row(
    name,
    *,
    property_name="S15",
    family=subject.AreaPropertyFamily.SLAB,
    material="C35/45",
    shell=2,
    thickness=0.15,
    orientation=AreaDesignOrientation.FLOOR,
    overwrite="None",
):
    state = None
    if property_name != "None":
        state = subject.AreaPropertyFactualState(
            property_name=property_name,
            family=family,
            family_type_code=0,
            shell_type_code=shell,
            material_name=material,
            thickness=thickness,
            property_modifiers=_modifier(
                AreaModifierSurface.AREA_PROPERTY,
                property_name,
            ),
            source_refs=(f"property:{property_name}",),
        )
    diaphragm_assignment = None
    diaphragm_definition = None
    wall_assignment = None
    if orientation is AreaDesignOrientation.FLOOR:
        diaphragm_assignment = SimpleNamespace(
            area_name=name,
            assigned=False,
            diaphragm_name="None",
            success=True,
            evidence_ref=f"diaphragm:{name}",
        )
    if orientation is AreaDesignOrientation.WALL:
        wall_assignment = SimpleNamespace(
            area_name=name,
            success=True,
            assignment_conflict=False,
            pier_assigned=True,
            spandrel_assigned=False,
            pier_name="P1",
            spandrel_name="None",
            evidence_ref=f"wall:{name}",
        )
    original_d = subject.AreaDiaphragmAssignmentFact
    original_w = subject.AreaWallAssignmentFact
    subject.AreaDiaphragmAssignmentFact = SimpleNamespace
    subject.AreaWallAssignmentFact = SimpleNamespace
    try:
        return subject.AreaContributorFact(
            area_name=name,
            orientation=orientation,
            property_name=property_name,
            property_state=state,
            local_axes_angle_degrees=0.0,
            advanced_local_axes=False,
            transformation_matrix=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            raw_material_overwrite_name=overwrite,
            object_modifiers=_modifier(
                AreaModifierSurface.AREA_OBJECT,
                name,
            ),
            diaphragm_assignment=diaphragm_assignment,
            diaphragm_definition=diaphragm_definition,
            wall_assignment=wall_assignment,
            model_fingerprint="model:a38",
            evidence_epoch_id="epoch:a38",
            session_provenance_ref="session:a38",
            source_refs=(f"area:{name}",),
        )
    finally:
        subject.AreaDiaphragmAssignmentFact = original_d
        subject.AreaWallAssignmentFact = original_w


def _scope(row, status):
    return subject.AreaContributorScopeFact(
        area_name=row.area_name,
        property_name=row.property_name,
        property_family=(
            None if row.property_state is None else row.property_state.family
        ),
        material_name=(
            None
            if row.property_state is None
            else row.property_state.material_name
        ),
        status=status,
        reason=f"scope:{row.area_name}:{status.value}",
        model_fingerprint=row.model_fingerprint,
        evidence_epoch_id=row.evidence_epoch_id,
        session_provenance_ref=row.session_provenance_ref,
        source_refs=row.source_refs,
    )


def _population(rows, supported, typed, scopes):
    return subject.AreaContributorPopulation(
        model_fingerprint="model:a38",
        evidence_epoch_id="epoch:a38",
        session_provenance_ref="session:a38",
        expected_area_names=tuple(row.area_name for row in rows),
        rows=tuple(rows),
        source_refs=("population:a38",),
        scope_facts=tuple(scopes),
        supported_rows=tuple(supported),
        typed_out_of_slice_rows=tuple(typed),
    )


def test_exact_supported_plus_typed_partition_equals_expected():
    a = _row("A")
    b = _row(
        "B",
        family=subject.AreaPropertyFamily.DECK,
        material="S355",
        shell=3,
    )
    sa = _scope(a, subject.AreaContributorScopeStatus.SUPPORTED)
    sb = _scope(
        b,
        subject.AreaContributorScopeStatus.DECK_APPLICABILITY_UNRESOLVED,
    )
    pop = _population((a, b), (a,), (sb,), (sa, sb))
    assert tuple(x.area_name for x in pop.supported_rows) == ("A",)
    assert tuple(x.area_name for x in pop.typed_out_of_slice_rows) == ("B",)


def test_duplicate_supported_identity_fails_closed():
    a = _row("A")
    sa = _scope(a, subject.AreaContributorScopeStatus.SUPPORTED)
    with pytest.raises(
        subject.EtabsAreaContributorProviderError,
        match="duplicate supported",
    ):
        _population((a,), (a, a), (), (sa,))


def test_duplicate_typed_identity_fails_closed():
    a = _row(
        "A",
        family=subject.AreaPropertyFamily.DECK,
        material="S355",
        shell=3,
    )
    sa = _scope(
        a,
        subject.AreaContributorScopeStatus.DECK_APPLICABILITY_UNRESOLVED,
    )
    with pytest.raises(
        subject.EtabsAreaContributorProviderError,
        match="duplicate typed",
    ):
        _population((a,), (), (sa, sa), (sa,))


def test_supported_typed_overlap_fails_closed():
    a = _row("A")
    sa = _scope(a, subject.AreaContributorScopeStatus.SUPPORTED)
    typed = replace(
        sa,
        status=subject.AreaContributorScopeStatus.MATERIAL_NOT_PROVEN_CONCRETE,
    )
    with pytest.raises(
        subject.EtabsAreaContributorProviderError,
        match="overlap",
    ):
        _population((a,), (a,), (typed,), (sa,))


def test_missing_partition_identity_fails_closed():
    a = _row("A")
    b = _row("B")
    sa = _scope(a, subject.AreaContributorScopeStatus.SUPPORTED)
    sb = _scope(b, subject.AreaContributorScopeStatus.SUPPORTED)
    with pytest.raises(
        subject.EtabsAreaContributorProviderError,
        match="partition is not exact",
    ):
        _population((a, b), (a,), (), (sa, sb))


def test_orphan_scope_identity_fails_closed():
    a = _row("A")
    sa = _scope(a, subject.AreaContributorScopeStatus.SUPPORTED)
    orphan = replace(sa, area_name="ORPHAN")
    with pytest.raises(
        subject.EtabsAreaContributorProviderError,
        match="scope denominator is not exact",
    ):
        _population((a,), (a,), (), (orphan,))


def test_area_only_mat_can_be_concrete_proven_without_frame_usage(monkeypatch):
    monkeypatch.setattr(subject, "FrameFlexuralBaseCaptureSnapshot", _Snapshot)
    snapshot = _Snapshot(
        basic_rows=({"Material": "Mat", "E1": 30000.0, "G12": 12500.0},),
        concrete_rows=({"Material": "Mat", "Fc": 35.0},),
    )
    facts = subject._capture_area_material_facts(
        rows=(_row("A", material="Mat"),),
        material_snapshot=snapshot,
        model_fingerprint="model:a38",
        evidence_epoch_id="epoch:a38",
        session_provenance_ref="session:a38",
    )
    assert tuple(x.material_name for x in facts) == ("Mat",)
    assert facts[0].resolution is subject.AreaMaterialResolution.CONCRETE_PROVEN
    assert facts[0].concrete_fck_mpa == Decimal("35.0")


def test_area_material_eg_is_read_from_same_epoch_snapshot_without_oapi(monkeypatch):
    monkeypatch.setattr(subject, "FrameFlexuralBaseCaptureSnapshot", _Snapshot)
    facts = subject._capture_area_material_facts(
        rows=(_row("A", material="Mat"),),
        material_snapshot=_Snapshot(
            basic_rows=(
                {
                    "Material": "Mat",
                    "E1": 30000.0,
                    "G12": 12500.0,
                },
            ),
            concrete_rows=({"Material": "Mat", "Fc": 35.0},),
        ),
        model_fingerprint="model:a38",
        evidence_epoch_id="epoch:a38",
        session_provenance_ref="session:a38",
    )
    assert facts[0].factual_ec_mpa == Decimal("30000.0")
    assert facts[0].factual_gc_mpa == Decimal("12500.0")
    assert facts[0].resolution is subject.AreaMaterialResolution.CONCRETE_PROVEN


def test_mat_name_alone_never_proves_concrete(monkeypatch):
    monkeypatch.setattr(subject, "FrameFlexuralBaseCaptureSnapshot", _Snapshot)
    facts = subject._capture_area_material_facts(
        rows=(_row("A", material="Mat"),),
        material_snapshot=_Snapshot(
            basic_rows=({"Material": "Mat", "E1": 30000.0, "G12": 12500.0},),
            concrete_rows=(),
        ),
        model_fingerprint="model:a38",
        evidence_epoch_id="epoch:a38",
        session_provenance_ref="session:a38",
    )
    assert facts[0].resolution is subject.AreaMaterialResolution.CONCRETE_DATA_MISSING
    assert facts[0].concrete_proven is False
    assert facts[0].concrete_fck_mpa is None


def test_s355_never_gets_concrete_basis_without_concrete_data(monkeypatch):
    monkeypatch.setattr(subject, "FrameFlexuralBaseCaptureSnapshot", _Snapshot)
    facts = subject._capture_area_material_facts(
        rows=(
            _row(
                "D",
                family=subject.AreaPropertyFamily.DECK,
                material="S355",
                shell=3,
            ),
        ),
        material_snapshot=_Snapshot(
            basic_rows=({"Material": "S355", "E1": 210000.0, "G12": 80769.23},),
            concrete_rows=(),
        ),
        model_fingerprint="model:a38",
        evidence_epoch_id="epoch:a38",
        session_provenance_ref="session:a38",
    )
    assert facts[0].material_name == "S355"
    assert facts[0].concrete_proven is False
    assert facts[0].concrete_fck_mpa is None


def test_duplicate_basic_mechanical_identity_fails_closed(monkeypatch):
    monkeypatch.setattr(subject, "FrameFlexuralBaseCaptureSnapshot", _Snapshot)
    with pytest.raises(
        subject.EtabsAreaContributorProviderError,
        match="duplicate .*Basic Mechanical",
    ):
        subject._capture_area_material_facts(
            rows=(_row("A", material="Mat"),),
            material_snapshot=_Snapshot(
                basic_rows=(
                    {"Material": "Mat", "E1": 1.0, "G12": 0.4},
                    {"Material": "Mat", "E1": 2.0, "G12": 0.8},
                ),
                concrete_rows=(),
            ),
            model_fingerprint="model:a38",
            evidence_epoch_id="epoch:a38",
            session_provenance_ref="session:a38",
        )


def test_duplicate_concrete_data_identity_fails_closed(monkeypatch):
    monkeypatch.setattr(subject, "FrameFlexuralBaseCaptureSnapshot", _Snapshot)
    with pytest.raises(
        subject.EtabsAreaContributorProviderError,
        match="duplicate .*Concrete Data",
    ):
        subject._capture_area_material_facts(
            rows=(_row("A", material="Mat"),),
            material_snapshot=_Snapshot(
                basic_rows=({"Material": "Mat", "E1": 1.0, "G12": 0.4},),
                concrete_rows=(
                    {"Material": "Mat", "Fc": 30.0},
                    {"Material": "Mat", "Fc": 35.0},
                ),
            ),
            model_fingerprint="model:a38",
            evidence_epoch_id="epoch:a38",
            session_provenance_ref="session:a38",
        )


def test_deck_is_typed_blocked_not_supported():
    deck = _row(
        "D",
        property_name="Deck1",
        family=subject.AreaPropertyFamily.DECK,
        material="S355",
        shell=3,
    )
    scopes = subject._build_area_scope_facts((deck,), ())
    assert scopes[0].status is (
        subject.AreaContributorScopeStatus.DECK_APPLICABILITY_UNRESOLVED
    )
    assert scopes[0].supported is False
    assert "not automatically not-applicable" in scopes[0].reason


def test_no_property_is_explicit_and_does_not_require_material():
    null = _row(
        "N",
        property_name="None",
        material=None,
        orientation=AreaDesignOrientation.NULL,
    )
    scopes = subject._build_area_scope_facts((null,), ())
    assert scopes[0].status is subject.AreaContributorScopeStatus.NO_PROPERTY
    assert scopes[0].supported is True
    assert scopes[0].material_name is None


def test_material_overwrite_mismatch_is_typed_fail_closed():
    row = _row("A", material="Mat", overwrite="Other")
    material = subject.AreaMaterialFactualFact(
        material_name="Mat",
        resolution=subject.AreaMaterialResolution.CONCRETE_DATA_MISSING,
        basic_mechanical_row={"Material": "Mat"},
        concrete_data_row=None,
        factual_ec_mpa=None,
        factual_gc_mpa=None,
        concrete_fck_mpa=None,
        model_fingerprint="model:a38",
        evidence_epoch_id="epoch:a38",
        session_provenance_ref="session:a38",
        source_refs=("material:Mat",),
    )
    scope = subject._build_area_scope_facts((row,), (material,))[0]
    assert scope.status is (
        subject.AreaContributorScopeStatus.MATERIAL_OVERWRITE_UNQUALIFIED
    )


def test_unsupported_shell_formulation_is_typed_not_dropped():
    row = _row("A", material="Mat", shell=1)
    scope = subject._build_area_scope_facts((row,), ())[0]
    assert scope.status is (
        subject.AreaContributorScopeStatus.UNSUPPORTED_SHELL_FORMULATION
    )
    assert scope.area_name == "A"



def test_deck_material_type_fact_is_bound_to_area_material_authority(
    monkeypatch,
):
    monkeypatch.setattr(
        subject,
        "FrameFlexuralBaseCaptureSnapshot",
        _Snapshot,
    )

    material_type = SimpleNamespace(
        material_name="S355",
        material_type_code=1,
        symmetry_type_code=0,
        return_code=0,
        success=True,
        is_steel=True,
        evidence_ref="material-type:S355",
    )

    original = subject.MaterialTypeFact
    subject.MaterialTypeFact = SimpleNamespace

    try:
        facts = subject._capture_area_material_facts(
            rows=(
                _row(
                    "D",
                    family=subject.AreaPropertyFamily.DECK,
                    material="S355",
                    shell=3,
                ),
            ),
            material_snapshot=_Snapshot(
                basic_rows=(
                    {
                        "Material": "S355",
                        "E1": 210000.0,
                        "G12": 80769.23,
                    },
                ),
                concrete_rows=(),
            ),
            model_fingerprint="model:a38",
            evidence_epoch_id="epoch:a38",
            session_provenance_ref="session:a38",
            material_type_facts={
                "S355": material_type,
            },
        )
    finally:
        subject.MaterialTypeFact = original

    assert len(facts) == 1
    assert facts[0].material_name == "S355"
    assert facts[0].material_type is material_type
    assert (
        "material-type:S355"
        in facts[0].source_refs
    )


def test_deck_material_type_capture_is_bounded_to_exact_deck_materials(
    monkeypatch,
):
    calls = []

    fact = SimpleNamespace(
        material_name="S355",
        success=True,
        is_steel=True,
        evidence_ref="material-type:S355",
    )

    original_session = subject.EtabsVerifiedSession
    original_type = subject.MaterialTypeFact

    subject.EtabsVerifiedSession = object
    subject.MaterialTypeFact = SimpleNamespace

    monkeypatch.setattr(
        subject,
        "get_material_type_from_session",
        lambda _session, *, material_name: (
            calls.append(material_name)
            or fact
        ),
    )

    try:
        rows = (
            _row(
                "D",
                family=subject.AreaPropertyFamily.DECK,
                material="S355",
                shell=3,
            ),
            _row(
                "S",
                family=subject.AreaPropertyFamily.SLAB,
                material="Mat",
                shell=2,
            ),
        )

        result = (
            subject._capture_deck_material_type_facts(
                object(),
                rows,
            )
        )
    finally:
        subject.EtabsVerifiedSession = original_session
        subject.MaterialTypeFact = original_type

    assert calls == ["S355"]
    assert tuple(result) == ("S355",)
    assert result["S355"] is fact
