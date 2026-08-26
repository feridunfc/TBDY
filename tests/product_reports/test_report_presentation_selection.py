from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from tbdy_engine.product_reports.report_presentation_selection import (
    ComponentFacetRef,
    ReportPresentationSelection,
    ReportPresentationSelectionError,
)


def test_component_facet_ref_total_order_handles_none_and_strings():
    selection = ReportPresentationSelection(
        component_refs=(
            ComponentFacetRef("column", "C1"),
            ComponentFacetRef(None, None),
            ComponentFacetRef("column", None),
            ComponentFacetRef("beam", "B1"),
        )
    )
    assert selection.component_refs == (
        ComponentFacetRef(None, None),
        ComponentFacetRef("beam", "B1"),
        ComponentFacetRef("column", None),
        ComponentFacetRef("column", "C1"),
    )


def test_component_facet_ref_order_is_input_order_independent():
    refs = (
        ComponentFacetRef("column", None),
        ComponentFacetRef("column", "C1"),
        ComponentFacetRef(None, None),
    )
    forward = ReportPresentationSelection(component_refs=refs)
    reverse = ReportPresentationSelection(component_refs=tuple(reversed(refs)))
    assert forward.as_dict() == reverse.as_dict()


def test_component_facet_ref_preserves_project_level_none_exactly():
    ref = ComponentFacetRef("PROJECT", None)
    assert ref.as_dict() == {
        "component_type": "PROJECT",
        "component_id": None,
    }


def test_duplicate_component_refs_fail_closed():
    ref = ComponentFacetRef("beam", "B1")
    with pytest.raises(ReportPresentationSelectionError, match="duplicates"):
        ReportPresentationSelection(component_refs=(ref, ref))


def test_duplicate_exact_text_filters_fail_closed():
    with pytest.raises(ReportPresentationSelectionError, match="duplicates"):
        ReportPresentationSelection(statuses=("FAIL", "FAIL"))


def test_selection_contract_is_immutable():
    selection = ReportPresentationSelection()
    with pytest.raises(FrozenInstanceError):
        selection.include_results = False  # type: ignore[misc]


def test_component_ref_contract_is_immutable():
    ref = ComponentFacetRef("beam", "B1")
    with pytest.raises(FrozenInstanceError):
        ref.component_id = "B2"  # type: ignore[misc]
