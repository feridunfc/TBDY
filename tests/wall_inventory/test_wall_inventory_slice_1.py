from __future__ import annotations

import pytest

from tbdy_engine.features.wall_inventory import (
    AREA_SOURCE, PIER_SOURCE, WallInventoryRecord, WallInventoryStatus,
    build_wall_inventory,
)

PROPERTY = {"Name": "W25", "Material": "C30", "Thickness": 250}


def area(unique="A100", story="Story 1", label="W1", prop="W25", kind="Wall"):
    return {"UniqueName": unique, "Story": story, "Label": label,
            "SectionProperty": prop, "PropertyType": kind}


def build(rows, *, properties=(PROPERTY,), piers=()):
    return build_wall_inventory(model_fingerprint="MODEL-1", area_assignment_rows=rows,
                                wall_property_rows=properties, pier_assignment_rows=piers)


def bare_record(**overrides):
    values = dict(wall_object_id="wall-area:abc", anonymous_inventory_record_id=None,
                  model_fingerprint="MODEL-1", etabs_area_unique_name="A100",
                  area_label="W1", story="Story 1", assigned_area_property="W25",
                  material_reference="C30", pier_assignment=None,
                  classification_status=WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE,
                  classification_evidence=(), source_row_references=(), diagnostics=())
    values.update(overrides)
    return WallInventoryRecord(**values)


def codes(record):
    return {item.code for item in record.diagnostics}


def area_refs(record):
    return [ref for ref in record.source_row_references if ref.source_family == AREA_SOURCE]


def test_record_identity_accepts_exactly_one_valid_identity():
    assert bare_record().inventory_record_id == "wall-area:abc"
    anonymous = bare_record(wall_object_id=None, anonymous_inventory_record_id="anonymous-area:abc",
                            etabs_area_unique_name=None,
                            classification_status=WallInventoryStatus.UNRESOLVED)
    assert anonymous.inventory_record_id == "anonymous-area:abc"


@pytest.mark.parametrize("wall_id,anonymous_id", [(None, None), ("wall:1", "anonymous:1")])
def test_record_identity_rejects_zero_or_two_ids(wall_id, anonymous_id):
    with pytest.raises(ValueError, match="Exactly one"):
        bare_record(wall_object_id=wall_id, anonymous_inventory_record_id=anonymous_id)


@pytest.mark.parametrize("wall_id", ["", "   "])
def test_identified_record_rejects_blank_internal_id(wall_id):
    with pytest.raises(ValueError, match="nonblank wall_object_id"):
        bare_record(wall_object_id=wall_id)


@pytest.mark.parametrize("anonymous_id", ["", "   "])
def test_anonymous_record_rejects_blank_internal_id(anonymous_id):
    with pytest.raises(ValueError, match="nonblank anonymous ID"):
        bare_record(wall_object_id=None, anonymous_inventory_record_id=anonymous_id,
                    etabs_area_unique_name=None,
                    classification_status=WallInventoryStatus.UNRESOLVED)


@pytest.mark.parametrize("unique", [None, "", "   "])
def test_identified_record_rejects_missing_or_blank_unique_name(unique):
    with pytest.raises(ValueError, match="nonblank authoritative UniqueName"):
        bare_record(etabs_area_unique_name=unique)


def test_anonymous_identity_cannot_carry_unique_name_or_resolved_status():
    with pytest.raises(ValueError, match="cannot carry"):
        bare_record(wall_object_id=None, anonymous_inventory_record_id="anonymous:1")
    with pytest.raises(ValueError, match="must be UNRESOLVED"):
        bare_record(wall_object_id=None, anonymous_inventory_record_id="anonymous:1",
                    etabs_area_unique_name=None)


def test_identical_duplicate_rows_make_one_object_and_preserve_both_rows():
    row = area()
    inventory = build([dict(row), dict(row)])
    assert len(inventory.records) == 1
    refs = area_refs(inventory.records[0])
    assert len(refs) == 2
    assert len({ref.area_row_token for ref in refs}) == 2
    rec = inventory.reconciliation
    assert (rec.discovered_inventory_objects, rec.input_area_source_row_count,
            rec.accounted_area_source_row_count) == (1, 2, 2)
    assert rec.object_reconciled and rec.area_source_rows_reconciled


@pytest.mark.parametrize(
    "changed,diagnostic",
    [(dict(story="Story 2"), "CONFLICTING_STORY"),
     (dict(label="W2"), "CONFLICTING_AREA_LABEL"),
     (dict(prop="W30"), "CONFLICTING_AREA_PROPERTY"),
     (dict(kind="Slab"), "CONFLICTING_AREA_CLASSIFICATION")],
)
def test_grouped_object_identity_conflicts_make_one_unresolved_record(changed, diagnostic):
    first = area()
    second = area(**changed)
    inventory = build([first, second], properties=(PROPERTY, {"Name": "W30", "Material": "C30"}))
    assert len(inventory.records) == 1
    record = inventory.records[0]
    assert record.classification_status == WallInventoryStatus.UNRESOLVED
    assert diagnostic in codes(record)
    assert len(area_refs(record)) == 2
    assert inventory.reconciliation.accounted_area_source_row_count == 2


def test_row_order_does_not_change_serialized_inventory():
    rows = [area("A2", "Story 2", "W2"), area("A1", "Story 1", "W1"),
            area("A1", "Story 1", "W1")]
    assert build(rows).as_dict() == build(list(reversed(rows))).as_dict()


def test_labels_and_reused_properties_do_not_collapse_objects():
    inventory = build([area("A1", "Story 1", "W1"), area("A2", "Story 2", "W1")])
    assert len(inventory.records) == 2
    assert len({record.wall_object_id for record in inventory.records}) == 2


def test_missing_pier_is_nonblocking_with_wall_property_evidence():
    record = build([area()]).records[0]
    assert record.classification_status == WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE
    assert record.pier_assignment is None


def test_conflicting_pier_join_is_unresolved():
    piers = [{"UniqueName": "A100", "Pier": "P1"},
             {"UniqueName": "A100", "Pier": "P2"}]
    record = build([area()], piers=piers).records[0]
    assert record.classification_status == WallInventoryStatus.UNRESOLVED
    assert "CONFLICTING_PIER_JOIN" in codes(record)


def test_different_pier_unique_name_cannot_join_by_story_label():
    pier = {"UniqueName": "A999", "Story": "Story 1", "Label": "W1", "Pier": "P1"}
    record = build([area()], piers=[pier]).records[0]
    assert record.pier_assignment is None
    assert not any(ref.source_family == PIER_SOURCE for ref in record.source_row_references)


def test_invalid_non_string_pier_unique_name_cannot_enable_fallback():
    pier = {"UniqueName": 999, "Story": "Story 1", "Label": "W1", "Pier": "P1"}
    record = build([area()], piers=[pier]).records[0]
    assert record.pier_assignment is None
    assert not any(ref.source_family == PIER_SOURCE for ref in record.source_row_references)


def test_missing_pier_unique_name_can_use_exact_story_label_fallback():
    pier = {"Story": "Story 1", "Label": "W1", "Pier": "P1"}
    assert build([area()], piers=[pier]).records[0].pier_assignment == "P1"


def test_case_distinct_story_or_label_does_not_enable_pier_fallback():
    piers = [{"Story": "STORY 1", "Label": "W1", "Pier": "P1"},
             {"Story": "Story 1", "Label": "w1", "Pier": "P2"}]
    assert build([area()], piers=piers).records[0].pier_assignment is None


def test_wall_evidence_with_missing_or_unmatched_property_is_unresolved():
    cases = [(area(prop=None), "WALL_PROPERTY_ASSIGNMENT_MISSING"),
             (area(prop="UNKNOWN"), "WALL_PROPERTY_JOIN_MISSING")]
    for row, expected in cases:
        record = build([row], properties=(),
                       piers=[{"UniqueName": "A100", "Pier": "P1"}]).records[0]
        assert record.classification_status == WallInventoryStatus.UNRESOLVED
        assert expected in codes(record)


@pytest.mark.parametrize(
    "property_value,expected",
    [("w25", "WALL_PROPERTY_JOIN_MISSING"),
     (25, "WALL_PROPERTY_ASSIGNMENT_MISSING")],
)
def test_property_identifiers_are_exact_strings_only(property_value, expected):
    record = build([area(prop=property_value)]).records[0]
    assert record.classification_status == WallInventoryStatus.UNRESOLVED
    assert expected in codes(record)
    if property_value == 25:
        assert record.assigned_area_property is None


def test_opaque_unique_names_are_not_casefolded_or_parsed():
    rows = [area("A1", label="W1"), area("a1", label="W2"),
            area("01", label="W3"), area("1", label="W4")]
    inventory = build(rows)
    assert len(inventory.records) == 4
    assert {record.etabs_area_unique_name for record in inventory.records} == {"A1", "a1", "01", "1"}


def test_non_string_unique_name_is_anonymous_and_not_merged_with_string_value():
    inventory = build([area(1, label="W1"), area("1", label="W2")])
    assert len(inventory.records) == 2
    assert inventory.reconciliation.anonymous_record_count == 1
    anonymous = next(record for record in inventory.records if record.wall_object_id is None)
    assert anonymous.classification_status == WallInventoryStatus.UNRESOLVED
    assert anonymous.etabs_area_unique_name is None


def test_excluded_and_anonymous_rows_remain_counted_and_nothing_disappears():
    inventory = build([area("S1", prop="SLAB", kind="Slab"),
                       {"UniqueName": None, "Story": "Story 1", "Label": "?",
                        "PropertyType": "Wall"}])
    assert len(inventory.records) == 2
    assert inventory.reconciliation.positively_excluded_objects == 1
    assert inventory.reconciliation.unresolved_objects == 1
    assert inventory.reconciliation.input_area_source_row_count == 2
    assert inventory.reconciliation.accounted_area_source_row_count == 2


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key)
            yield from _all_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _all_keys(nested)


def test_contract_metadata_is_truthful_and_no_engineering_semantic_fields_exist():
    payload = build([area()]).as_dict()
    assert payload["source_contract_status"][AREA_SOURCE] == "VERIFIED_LIVE"
    assert "Contract metadata only" in payload["source_contract_status_note"]
    assert "acquisition_provenance" not in payload
    forbidden = ("applicability", "check_result", "checkresult", "compliance", "pass", "fail")
    for key in _all_keys(payload):
        folded = key.casefold()
        if folded == "classification_status":
            continue
        assert not any(token in folded for token in forbidden), key
    result_tokens = {"PASS", "FAIL", "OK", "NO_DATA", "BLOCKED", "OUT_OF_SCOPE"}
    assert {record["classification_status"] for record in payload["records"]}.isdisjoint(result_tokens)
