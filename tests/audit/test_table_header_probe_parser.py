from tools.probe_etabs_table_headers import (
    parse_etabs_display_table_result,
    selected_whitelist,
)


def test_flat_table_data_parsed_into_rows_using_number_fields():
    parsed = parse_etabs_display_table_result(
        {
            "return_code": 0,
            "field_keys": ["Frame", "Story", "Section"],
            "number_fields": 3,
            "number_records": 2,
            "table_data": ["B1", "S1", "B40x70", "B2", "S1", "B30x60"],
        },
        actual_table_name="Frame Assignments - Summary",
        max_rows=3,
    )
    assert parsed.fetch_status == "FETCHED"
    assert parsed.field_keys == ("Frame", "Story", "Section")
    assert parsed.rows[0]["Frame"] == "B1"
    assert parsed.row_count_reported == 2


def test_list_field_keys_parsed():
    parsed = parse_etabs_display_table_result(
        {"return_code": 0, "field_keys": ["Mode", "SumUX"], "table_data": ["1", "0.75"]},
        actual_table_name="Modal Participating Mass Ratios",
    )
    assert parsed.field_keys == ("Mode", "SumUX")
    assert parsed.rows[0]["SumUX"] == "0.75"


def test_string_field_keys_parsed():
    parsed = parse_etabs_display_table_result(
        {"return_code": 0, "field_keys": "Output Case,FX,FY", "table_data": ["EQX", "100", "5"]},
        actual_table_name="Base Reactions",
    )
    assert parsed.field_keys == ("Output Case", "FX", "FY")
    assert parsed.rows[0]["Output Case"] == "EQX"


def test_empty_data_returns_empty():
    parsed = parse_etabs_display_table_result(
        {"return_code": 0, "field_keys": ["Frame", "Story"], "table_data": []},
        actual_table_name="Frame Assignments - Summary",
    )
    assert parsed.fetch_status == "EMPTY"
    assert any(d["code"] == "TABLE_EMPTY" for d in parsed.diagnostics)


def test_failed_return_code_returns_failed():
    parsed = parse_etabs_display_table_result(
        {"return_code": 1, "field_keys": ["Frame"], "table_data": ["B1"]},
        actual_table_name="Frame Assignments - Summary",
    )
    assert parsed.fetch_status == "FAILED"
    assert any(d["code"] == "TABLE_FETCH_FAILED" for d in parsed.diagnostics)


def test_malformed_shape_produces_diagnostic_not_crash():
    parsed = parse_etabs_display_table_result(object(), actual_table_name="Bad Shape")
    assert parsed.fetch_status == "FAILED"
    assert any(d["code"] == "MALFORMED_SHAPE" for d in parsed.diagnostics)


def test_tuple_shape_with_list_headers_and_flat_data():
    parsed = parse_etabs_display_table_result(
        (["Frame", "Story"], ["B1", "S1", "B2", "S2"], 0),
        actual_table_name="Frame Assignments - Summary",
    )
    assert parsed.fetch_status == "FETCHED"
    assert parsed.rows[1]["Frame"] == "B2"


def test_2d_table_data_parsed():
    parsed = parse_etabs_display_table_result(
        {"return_code": 0, "field_keys": ["Frame", "Story"], "table_data": [["B1", "S1"], ["B2", "S2"]]},
        actual_table_name="Frame Assignments - Summary",
    )
    assert parsed.rows[0]["Story"] == "S1"


def test_no_checkresult_ok_fail_or_ratios_in_parser_payload():
    parsed = parse_etabs_display_table_result(
        {"return_code": 0, "field_keys": ["Frame", "Story"], "table_data": ["B1", "OK"]},
        actual_table_name="Frame Assignments - Summary",
    )
    text = repr(parsed)
    assert "CheckResult" not in text
    assert "'OK'" not in text
    assert "'FAIL'" not in text
    assert "ratio" not in text.lower()


def test_selected_whitelist_accepts_groups_and_exact_names():
    tables = selected_whitelist("story,Frame Assignments - Summary")
    assert "Story Definitions" in tables
    assert "Frame Assignments - Summary" in tables
