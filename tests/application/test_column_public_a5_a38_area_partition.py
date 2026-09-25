from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_public_a5 as a5
from tbdy_engine.etabs.oapi.area_modifiers import AreaModifierVector
from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (
    AreaStiffnessMode,
    ContributorDisposition,
)
from tbdy_engine.providers.etabs_area_contributor_provider import (
    AreaContributorScopeFact,
    AreaContributorScopeStatus,
    AreaMaterialResolution,
    AreaPropertyFamily,
)


def _scope(status, name="A"):
    return AreaContributorScopeFact(
        area_name=name,
        property_name=(
            "Deck1"
            if status
            is AreaContributorScopeStatus.DECK_APPLICABILITY_UNRESOLVED
            else "P1"
        ),
        property_family=None,
        material_name=(
            "S355"
            if status
            is AreaContributorScopeStatus.DECK_APPLICABILITY_UNRESOLVED
            else "Mat"
        ),
        status=status,
        reason=f"reason:{status.value}",
        model_fingerprint="model:a38",
        evidence_epoch_id="epoch:a38",
        session_provenance_ref="session:a38",
        source_refs=(f"area:{name}",),
    )


def test_deck_typed_disposition_is_blocked_not_not_applicable():
    row = a5._typed_out_of_slice_area_disposition(
        _scope(
            AreaContributorScopeStatus.DECK_APPLICABILITY_UNRESOLVED
        )
    )
    assert tuple(x.mode for x in row.mode_dispositions) == tuple(
        AreaStiffnessMode
    )
    assert all(
        x.disposition is ContributorDisposition.BLOCKED_UNSUPPORTED
        for x in row.mode_dispositions
    )
    assert all(
        x.disposition is not ContributorDisposition.PROVEN_NOT_APPLICABLE
        for x in row.mode_dispositions
    )
    assert row.target_property_modifiers is None


def test_supported_scope_cannot_enter_typed_out_of_slice_builder():
    with pytest.raises(a5.PublicA5CompositionError):
        a5._typed_out_of_slice_area_disposition(
            _scope(AreaContributorScopeStatus.SUPPORTED)
        )


def test_area_only_concrete_material_extends_frame_material_registry(monkeypatch):
    area_fact = SimpleNamespace(
        material_name="Mat",
        resolution=AreaMaterialResolution.CONCRETE_PROVEN,
        concrete_fck_mpa=Decimal("35"),
        factual_ec_mpa=Decimal("30000"),
        factual_gc_mpa=Decimal("12500"),
        source_refs=("area-material:Mat",),
    )
    area_population = SimpleNamespace(material_facts=(area_fact,))
    existing = {
        "C35/45": SimpleNamespace(
            material_name="C35/45",
            fck_mpa=Decimal("35"),
            factual_ec_mpa=Decimal("30000"),
            factual_gc_mpa=Decimal("12500"),
        )
    }

    built = []

    def basis(**kwargs):
        built.append(kwargs)
        return SimpleNamespace(
            material_name=kwargs["material_name"],
            fck_mpa=kwargs["fck_mpa"],
            factual_ec_mpa=kwargs["factual_ec_mpa"],
            factual_gc_mpa=kwargs["factual_gc_mpa"],
        )

    monkeypatch.setattr(a5, "build_concrete_uncracked_material_basis", basis)
    result = a5._extend_material_bases_from_area(existing, area_population)
    assert tuple(sorted(result)) == ("C35/45", "Mat")
    assert built[0]["material_name"] == "Mat"


def test_s355_concrete_unproven_never_enters_basis_registry(monkeypatch):
    area_fact = SimpleNamespace(
        material_name="S355",
        resolution=AreaMaterialResolution.CONCRETE_DATA_MISSING,
    )
    area_population = SimpleNamespace(material_facts=(area_fact,))
    called = []
    monkeypatch.setattr(
        a5,
        "build_concrete_uncracked_material_basis",
        lambda **kwargs: called.append(kwargs),
    )
    result = a5._extend_material_bases_from_area({}, area_population)
    assert result == {}
    assert called == []


def test_shared_frame_area_material_keeps_frame_basis_when_table_rounding_agrees(monkeypatch):
    area_fact = SimpleNamespace(
        material_name="C35/45",
        resolution=AreaMaterialResolution.CONCRETE_PROVEN,
        concrete_fck_mpa=Decimal("35"),
        factual_ec_mpa=Decimal("34000"),
        factual_gc_mpa=Decimal("14166.66667"),
        source_refs=("area-material:C35/45",),
    )
    prior = SimpleNamespace(
        material_name="C35/45",
        fck_mpa=Decimal("35.0"),
        factual_ec_mpa=Decimal("34000.0"),
        factual_gc_mpa=Decimal("14166.6666666667"),
    )
    monkeypatch.setattr(
        a5,
        "build_concrete_uncracked_material_basis",
        lambda **kwargs: SimpleNamespace(
            material_name=kwargs["material_name"],
            fck_mpa=kwargs["fck_mpa"],
            factual_ec_mpa=kwargs["factual_ec_mpa"],
            factual_gc_mpa=kwargs["factual_gc_mpa"],
        ),
    )
    result = a5._extend_material_bases_from_area(
        {"C35/45": prior},
        SimpleNamespace(material_facts=(area_fact,)),
    )
    assert result["C35/45"] is prior


def test_contradictory_frame_area_material_basis_fails_closed(monkeypatch):
    area_fact = SimpleNamespace(
        material_name="C35/45",
        resolution=AreaMaterialResolution.CONCRETE_PROVEN,
        concrete_fck_mpa=Decimal("40"),
        factual_ec_mpa=Decimal("30000"),
        factual_gc_mpa=Decimal("12500"),
        source_refs=("area-material:C35/45",),
    )
    prior = SimpleNamespace(
        material_name="C35/45",
        fck_mpa=Decimal("35"),
        factual_ec_mpa=Decimal("30000"),
        factual_gc_mpa=Decimal("12500"),
    )
    monkeypatch.setattr(
        a5,
        "build_concrete_uncracked_material_basis",
        lambda **kwargs: SimpleNamespace(
            material_name=kwargs["material_name"],
            fck_mpa=kwargs["fck_mpa"],
            factual_ec_mpa=kwargs["factual_ec_mpa"],
            factual_gc_mpa=kwargs["factual_gc_mpa"],
        ),
    )
    with pytest.raises(
        a5.PublicA5CompositionError,
        match="contradictory",
    ):
        a5._extend_material_bases_from_area(
            {"C35/45": prior},
            SimpleNamespace(material_facts=(area_fact,)),
        )



def _steel_deck_factual(
    name="557",
    *,
    property_values=(1.0,) * 10,
    object_values=(1.0,) * 10,
):
    return SimpleNamespace(
        area_name=name,
        property_name="Deck1",
        property_state=SimpleNamespace(
            family=AreaPropertyFamily.DECK,
            material_name="S355",
            property_modifiers=SimpleNamespace(
                modifiers=AreaModifierVector.from_sequence(
                    property_values
                ),
            ),
        ),
        object_modifiers=SimpleNamespace(
            modifiers=AreaModifierVector.from_sequence(
                object_values
            ),
        ),
        source_refs=(
            f"area:{name}",
            "deck:Deck1",
        ),
    )


def _steel_deck_material(
    *,
    success=True,
    is_steel=True,
):
    return SimpleNamespace(
        material_name="S355",
        material_type=SimpleNamespace(
            material_name="S355",
            success=success,
            is_steel=is_steel,
            evidence_ref="material-type:S355",
        ),
        source_refs=(
            "material:S355",
            "material-type:S355",
        ),
    )


def test_source_proven_steel_deck_closes_concrete_normalization():
    scope = _scope(
        AreaContributorScopeStatus
        .DECK_APPLICABILITY_UNRESOLVED,
        name="557",
    )

    factual = _steel_deck_factual()
    material = _steel_deck_material()

    original_fact = a5.AreaContributorFact
    original_material = (
        a5.AreaMaterialFactualFact
    )

    a5.AreaContributorFact = SimpleNamespace
    a5.AreaMaterialFactualFact = SimpleNamespace

    try:
        row = (
            a5._typed_out_of_slice_area_disposition(
                scope,
                factual,
                material,
            )
        )
    finally:
        a5.AreaContributorFact = original_fact
        a5.AreaMaterialFactualFact = (
            original_material
        )

    assert row.blocked_reasons == ()
    assert row.target_property_modifiers is None

    assert tuple(
        item.mode
        for item in row.mode_dispositions
    ) == tuple(AreaStiffnessMode)

    assert all(
        item.disposition
        is ContributorDisposition.PROVEN_NOT_APPLICABLE
        for item in row.mode_dispositions
    )

    assert (
        "source-proven steel DECK"
        in row.mode_dispositions[0].reason
    )

    assert (
        "does not classify the DECK as structurally "
        "non-participating"
        in row.mode_dispositions[0].reason
    )

    assert (
        "material-type:S355"
        in row.source_refs
    )


@pytest.mark.parametrize(
    (
        "success",
        "is_steel",
        "property_values",
        "object_values",
    ),
    (
        (
            False,
            False,
            (1.0,) * 10,
            (1.0,) * 10,
        ),
        (
            True,
            False,
            (1.0,) * 10,
            (1.0,) * 10,
        ),
        (
            True,
            True,
            (
                0.5, 1.0, 1.0, 1.0, 1.0,
                1.0, 1.0, 1.0, 1.0, 1.0,
            ),
            (1.0,) * 10,
        ),
        (
            True,
            True,
            (1.0,) * 10,
            (
                1.0, 1.0, 1.0, 1.0, 1.0,
                0.5, 1.0, 1.0, 1.0, 1.0,
            ),
        ),
    ),
)
def test_steel_deck_closure_fails_closed_without_exact_bounded_facts(
    success,
    is_steel,
    property_values,
    object_values,
):
    scope = _scope(
        AreaContributorScopeStatus
        .DECK_APPLICABILITY_UNRESOLVED,
        name="557",
    )

    factual = _steel_deck_factual(
        property_values=property_values,
        object_values=object_values,
    )

    material = _steel_deck_material(
        success=success,
        is_steel=is_steel,
    )

    original_fact = a5.AreaContributorFact
    original_material = (
        a5.AreaMaterialFactualFact
    )

    a5.AreaContributorFact = SimpleNamespace
    a5.AreaMaterialFactualFact = SimpleNamespace

    try:
        row = (
            a5._typed_out_of_slice_area_disposition(
                scope,
                factual,
                material,
            )
        )
    finally:
        a5.AreaContributorFact = original_fact
        a5.AreaMaterialFactualFact = (
            original_material
        )

    assert all(
        item.disposition
        is ContributorDisposition.BLOCKED_UNSUPPORTED
        for item in row.mode_dispositions
    )
