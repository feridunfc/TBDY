from __future__ import annotations

import json
from pathlib import Path

from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.features.resolver.live_smoke import (
    C8LiveFeatureResolverSmoke,
    tables_from_probe_report,
    unit_context_from_payload,
    write_smoke_outputs,
    direct_api_geometry_from_payload,
)
from tbdy_engine.features.value import FeatureValueStatus
from tbdy_engine.providers.etabs_display_table_parser import parse_etabs_display_table_result as engine_parse
from tools.probe_etabs_table_headers import parse_etabs_display_table_result as probe_parse

FIXTURE = Path("tests/fixtures/c8_3_direct_api_geometry_fixture.json")


def _unit_context() -> dict:
    return {
        "source": "fixture_declared_units",
        "force_unit": "kN",
        "length_unit": "mm",
        "temperature_unit": "C",
        "unit_query_status": "RESOLVED",
        "unit_query_succeeded": True,
        "unit_basis_confidence": "high",
    }


def _payload_with_table(table: dict) -> dict:
    return {"unit_context": _unit_context(), "tables": [table]}


def _resolver(payload: dict, *, target_story: str = "+14.5") -> C8LiveFeatureResolverSmoke:
    bundle = load_contracts()
    return C8LiveFeatureResolverSmoke(
        bundle,
        tables_from_probe_report(payload, bundle),
        unit_context=unit_context_from_payload(payload),
        target_story=target_story,
        target_component="297",
        target_label="B1",
        target_section="B40x70",
        direct_api_geometry=direct_api_geometry_from_payload(payload),
    )


def _story_rows() -> list[dict]:
    return [
        {"Story": "+3.5", "OutputCase": "Crack_SeisX", "Direction": "X", "Drift": 1.0},
        {"Story": "+7.0", "OutputCase": "Crack_SeisX", "Direction": "X", "Drift": 2.0},
        {"Story": "+10.5", "OutputCase": "Crack_SeisX", "Direction": "X", "Drift": 3.0},
        {"Story": "+14.5", "OutputCase": "Crack_SeisY_UpSoil", "Direction": "Y", "Drift": 9.5},
    ]


def _base_rows() -> list[dict]:
    return [
        {"OutputCase": "Envelope", "FX": "not_numeric", "FY": "not_numeric"},
        {"OutputCase": "Crack_SeisX", "FX": 100.0, "FY": 200.0},
        {"OutputCase": "Crack_SeisY_UpSoil", "FX": 1020.5, "FY": 2440.1},
    ]


def test_tables_from_probe_report_uses_full_rows_not_sample_rows():
    table = {
        "actual_table_name": "Story Drifts",
        "canonical_table_key": "story_drifts",
        "headers": ["Story", "OutputCase", "Direction", "Drift"],
        "sample_rows_limited": _story_rows()[:1],
        "rows": _story_rows(),
        "row_count_reported": len(_story_rows()),
    }
    bundle = load_contracts()
    tables = tables_from_probe_report(_payload_with_table(table), bundle)
    story = next(t for t in tables if t.table_key == "story_drifts")
    assert len(story.rows) == 4
    assert story.units["source_row_storage_field_used"] == "rows"
    assert story.rows[-1]["Story"] == "+14.5"
    assert story.units["debug_sample_row_count"] == 5 or story.units["debug_sample_row_count"] == 4


def test_tables_from_probe_report_does_not_use_sample_rows_limited_as_resolver_rows():
    table = {
        "actual_table_name": "Story Drifts",
        "canonical_table_key": "story_drifts",
        "headers": ["Story", "OutputCase", "Direction", "Drift"],
        "sample_rows_limited": _story_rows()[:1],
        "row_count_reported": 716,
        "raw_table_diagnostics": {"number_records": 716, "table_data_length": 8592, "expected_flat_length": 8592},
    }
    bundle = load_contracts()
    tables = tables_from_probe_report(_payload_with_table(table), bundle)
    story = next(t for t in tables if t.table_key == "story_drifts")
    assert story.rows == ()
    assert story.units["source_row_storage_field_used"] == "sample_rows_limited"
    assert any(d["code"] == "RESOLVER_ONLY_HAS_SAMPLE_ROWS" for d in story.units["resolver_ingestion_diagnostics"])


def test_resolver_reports_only_sample_rows_diagnostic():
    table = {
        "actual_table_name": "Story Drifts",
        "canonical_table_key": "story_drifts",
        "headers": ["Story", "OutputCase", "Direction", "Drift"],
        "sample_rows": _story_rows()[:1],
        "row_count": 716,
        "raw_table_diagnostics": {"number_records": 716, "table_data_length": 8592, "expected_flat_length": 8592},
    }
    snapshot = _resolver(_payload_with_table(table)).build_story_snapshot()
    feature = snapshot.features["story_drift_value"]
    assert feature.status == FeatureValueStatus.PARTIAL
    assert any(d.code.value == "RESOLVER_ONLY_HAS_SAMPLE_ROWS" for d in feature.diagnostics)


def test_live_smoke_story_selector_finds_target_story_beyond_first_sample():
    table = {
        "actual_table_name": "Story Drifts",
        "canonical_table_key": "story_drifts",
        "headers": ["Story", "OutputCase", "Direction", "Drift"],
        "sample_rows": _story_rows()[:1],
        "parsed_rows": _story_rows(),
        "row_count_reported": len(_story_rows()),
    }
    snapshot = _resolver(_payload_with_table(table)).build_story_snapshot()
    feature = snapshot.features["story_drift_value"]
    assert feature.status == FeatureValueStatus.RESOLVED
    assert feature.evidence[0].source_row["story"] == "+14.5"
    assert feature.evidence[0].source_column == "Drift"


def test_live_smoke_base_selector_finds_valid_fx_fy_beyond_first_sample():
    table = {
        "actual_table_name": "Base Reactions",
        "canonical_table_key": "base_reactions",
        "headers": ["OutputCase", "FX", "FY"],
        "sample_rows": _base_rows()[:1],
        "full_rows": _base_rows(),
        "row_count_reported": len(_base_rows()),
    }
    snapshot = _resolver(_payload_with_table(table)).build_global_snapshot()
    fx = snapshot.features["base_reaction_fx"]
    fy = snapshot.features["base_reaction_fy"]
    assert fx.status == FeatureValueStatus.RESOLVED
    assert fy.status == FeatureValueStatus.RESOLVED
    assert fx.value == 1020.5
    assert fy.value == 2440.1
    assert fx.evidence[0].output_case == "Crack_SeisY_UpSoil"


def test_story_base_resolver_debug_reports_resolver_row_count(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bundle = load_contracts()
    resolver = C8LiveFeatureResolverSmoke(
        bundle,
        tables_from_probe_report(payload, bundle),
        unit_context=unit_context_from_payload(payload),
        target_story="+14.5",
        target_component="297",
        target_label="B1",
        target_section="B40x70",
        direct_api_geometry=direct_api_geometry_from_payload(payload),
    )
    outputs = resolver.build_all()
    report = outputs.story_base_table_debug_report
    assert report["story_drifts"]["resolver_row_count"] > 0
    assert report["story_drifts"]["source_row_storage_field_used"] in {"sample_rows_limited", "rows", "parsed_rows", "full_rows", "table_rows", "raw_response"}
    out = tmp_path / "smoke"
    write_smoke_outputs(out, outputs)
    written = json.loads((out / "story_base_resolver_table_debug_report.json").read_text(encoding="utf-8"))
    assert written["story_drifts"]["resolver_row_count"] == report["story_drifts"]["resolver_row_count"]


def test_probe_and_resolver_parser_parity_for_story_drifts():
    raw = {
        "return_code": 0,
        "field_keys": ["Story", "OutputCase", "CaseType", "StepType", "StepNumber", "Direction", "Drift", "Drift/", "Label", "X", "Y", "Z"],
        "number_records": 2,
        "number_fields": 12,
        "table_data": [
            "+3.5", "Crack_SeisX", "Combination", "Max", "", "X", 1.0, "", "", 0, 0, 3.5,
            "+14.5", "Crack_SeisY_UpSoil", "Combination", "Max", "", "Y", 9.5, "", "", 0, 0, 14.5,
        ],
    }
    a = probe_parse(raw, actual_table_name="Story Drifts", max_rows=100000)
    b = engine_parse(raw, actual_table_name="Story Drifts", max_rows=None)
    assert a.field_keys == b.field_keys
    assert [dict(r) for r in a.rows] == [dict(r) for r in b.rows]
    assert b.debug["expected_flat_length"] == 24


def test_probe_and_resolver_parser_parity_for_base_reactions():
    raw = {
        "return_code": 0,
        "field_keys": ["OutputCase", "CaseType", "StepType", "StepNumber", "FX", "FY", "FZ", "MX", "MY", "MZ", "X", "Y", "Z"],
        "number_records": 2,
        "number_fields": 13,
        "table_data": [
            "Crack_SeisX", "Combination", "Max", "", 100.0, 200.0, 0, 0, 0, 0, 0, 0, 0,
            "Crack_SeisY_UpSoil", "Combination", "Max", "", 1020.5, 2440.1, 0, 0, 0, 0, 0, 0, 0,
        ],
    }
    a = probe_parse(raw, actual_table_name="Base Reactions", max_rows=100000)
    b = engine_parse(raw, actual_table_name="Base Reactions", max_rows=None)
    assert a.field_keys == b.field_keys
    assert [dict(r) for r in a.rows] == [dict(r) for r in b.rows]
    assert b.debug["expected_flat_length"] == 26


def test_selector_called_by_feature_resolution_path(monkeypatch):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    resolver = _resolver(payload)
    calls = {"drift": 0, "torsion": 0, "base": 0}
    original_drift = resolver._select_story_drift_row
    original_torsion = resolver._select_story_torsion_row
    original_base = resolver._select_base_reaction_row

    def drift_wrapper():
        calls["drift"] += 1
        return original_drift()

    def torsion_wrapper():
        calls["torsion"] += 1
        return original_torsion()

    def base_wrapper():
        calls["base"] += 1
        return original_base()

    monkeypatch.setattr(resolver, "_select_story_drift_row", drift_wrapper)
    monkeypatch.setattr(resolver, "_select_story_torsion_row", torsion_wrapper)
    monkeypatch.setattr(resolver, "_select_base_reaction_row", base_wrapper)
    resolver.build_story_snapshot()
    resolver.build_global_snapshot()
    assert calls == {"drift": 1, "torsion": 1, "base": 1}


def test_c8_3_historical_sample_modal_rows_remain_fail_closed():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    outputs = _resolver(payload).build_all()
    counts = {}
    for row in outputs.feature_resolution_report:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    assert counts == {"RESOLVED": 26, "PARTIAL": 2}
    modal_rows = {
        row["feature_name"]: row
        for row in outputs.missing_features_report
        if row["feature_name"] in {"modal_sum_ux", "modal_sum_uy"}
    }
    assert set(modal_rows) == {"modal_sum_ux", "modal_sum_uy"}
    for row in modal_rows.values():
        assert row["status"] == "PARTIAL"
        assert {item["code"] for item in row["diagnostics"]} == {"MODAL_SOURCE_INCOMPLETE"}


def _sequence_response(headers: list[str], rows: list[list[str]] | None, number_records: int, return_code: int = 0):
    flat: list[str] = []
    for row in rows or []:
        flat.extend(row)
    # Tuple-shaped COM wrapper response.  The small integer before the record
    # count reproduces the live ambiguity where smoke previously reported
    # number_fields=1/2 while the header count was 9/12/13.
    return (headers, flat, 1, number_records, return_code)


class _FakeDatabaseTables:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple] = []

    def GetTableForDisplayArray(self, *args):
        self.calls.append(args)
        index = len(self.calls) - 1
        item = self.responses[index]
        if isinstance(item, Exception):
            raise item
        return item


def test_fetcher_continues_after_empty_tabledata_success_code():
    from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table

    headers = ["Story", "OutputCase", "Direction", "Drift"]
    empty_success = _sequence_response(headers, [], 716, return_code=0)
    full_success = _sequence_response(
        headers,
        [["+14.5", "Crack_SeisY_UpSoil", "Y", "9.5"]],
        1,
        return_code=0,
    )
    db = _FakeDatabaseTables([empty_success, full_success])

    fetched = fetch_display_table(db, "Story Drifts", max_rows=None)

    assert len(db.calls) == 2
    assert fetched.selected_signature["signature_index"] == 2
    assert fetched.selected_signature_reason == "first_signature_with_parsed_rows"
    assert fetched.parsed.rows[0]["Story"] == "+14.5"
    assert fetched.signature_attempts[0]["parser_status"] == "TABLEDATA_EMPTY_DESPITE_RECORDS"
    assert fetched.signature_attempts[1]["parser_status"] == "PARSED_ROWS"


def test_fetcher_does_not_accept_empty_tabledata_despite_records_as_success():
    from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table

    headers = ["OutputCase", "FX", "FY"]
    empty_success = _sequence_response(headers, [], 96, return_code=0)
    db = _FakeDatabaseTables([empty_success, RuntimeError("bad sig"), RuntimeError("bad sig"), RuntimeError("bad sig"), RuntimeError("bad sig")])

    fetched = fetch_display_table(db, "Base Reactions", max_rows=None)

    assert fetched.parsed.rows == ()
    assert fetched.selected_signature_reason == "all_signatures_failed_best_empty_tabledata"
    assert fetched.selected_signature["parser_status"] == "TABLEDATA_EMPTY_DESPITE_RECORDS"
    assert fetched.signature_attempts[0]["parser_status"] == "TABLEDATA_EMPTY_DESPITE_RECORDS"


def test_smoke_live_uses_shared_display_table_fetcher_for_story_base_tables():
    import inspect
    import tools.smoke_live_feature_resolver as smoke_tool

    source = inspect.getsource(smoke_tool._live_probe_tables_and_units)
    assert "fetch_display_table" in source
    assert "_try_get_display_table" not in source


def test_number_fields_diagnostics_do_not_report_ambiguous_wrong_values():
    headers = ["Story", "OutputCase", "Direction", "Drift"]
    raw = _sequence_response(headers, [], 716, return_code=0)
    parsed = engine_parse(raw, actual_table_name="Story Drifts", max_rows=None)

    assert parsed.debug["header_count"] == 4
    assert parsed.debug["number_fields_source"] == "ambiguous"
    assert parsed.debug["number_fields_detected"] is None
    assert parsed.debug["number_fields"] is None
    assert parsed.debug["number_records"] == 716


def test_story_base_resolver_debug_reports_signature_attempts():
    from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table
    from tbdy_engine.providers.table_registry import TableRegistry

    bundle = load_contracts()
    registry = TableRegistry.from_dict(bundle.catalog("table_registry.yaml"))
    headers = ["Story", "OutputCase", "Direction", "Drift"]
    empty_success = _sequence_response(headers, [], 716, return_code=0)
    full_success = _sequence_response(
        headers,
        [["+14.5", "Crack_SeisY_UpSoil", "Y", "9.5"]],
        1,
        return_code=0,
    )
    fetched = fetch_display_table(_FakeDatabaseTables([empty_success, full_success]), "Story Drifts", max_rows=None)
    table_payload = fetched.header_payload(registry)
    report = _resolver(_payload_with_table(table_payload)).build_all().story_base_table_debug_report["story_drifts"]

    assert report["resolver_row_count"] == 1
    assert report["selected_row"] is not None
    assert len(report["signature_attempts"]) == 2
    assert report["selected_signature"]["signature_index"] == 2
    assert report["selected_signature_reason"] == "first_signature_with_parsed_rows"
    assert report["parser_status_by_signature"]["sig_7_list_fields_records_data"] == "TABLEDATA_EMPTY_DESPITE_RECORDS"
    assert report["table_data_length_by_signature"]["sig_7_string_fields_records_data"] == 4
    assert report["number_fields_source"] == "ambiguous"
    assert report["number_fields_detected"] is None


def test_shared_fetcher_uses_fresh_mutable_args_per_signature():
    from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table

    headers = ["Story", "OutputCase", "Direction", "Drift"]
    full = ["+14.5", "Crack_SeisY_UpSoil", "Y", "9.5"]

    class MutatingDb:
        def __init__(self):
            self.calls = []

        def GetTableForDisplayArray(self, *args):
            self.calls.append(args)
            # Mutate only the out args of the second signature.  The first call
            # must not leak its mutable lists into the second call.
            if len(self.calls) == 1:
                if isinstance(args[1], list):
                    args[1].append("SHOULD_NOT_LEAK")
                return (headers, [], 1, 716, 0)
            if isinstance(args[4], list):
                args[4].extend(headers)
            if isinstance(args[6], list):
                args[6].extend(full)
            return 0

    db = MutatingDb()
    fetched = fetch_display_table(db, "Story Drifts", max_rows=None)

    assert fetched.parsed.rows[0]["Story"] == "+14.5"
    assert fetched.selected_signature["signature_index"] == 2
    assert "SHOULD_NOT_LEAK" not in fetched.selected_signature.get("headers", [])
    assert id(db.calls[0][1]) != id(db.calls[1][4])


def test_shared_fetcher_scans_string_sequences_like_legacy_probe():
    from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table

    headers = ["OutputCase", "FX", "FY"]
    flat = ["Crack_SeisY_UpSoil", "10.5", "20.5"]

    class Db:
        def GetTableForDisplayArray(self, *args):
            # Header and TableData are both string sequences inside the raw tuple,
            # exactly the legacy parser's sequence-scan case.
            return (headers, flat, 1, 0)

    fetched = fetch_display_table(Db(), "Base Reactions", max_rows=None)

    assert fetched.parsed.rows[0]["OutputCase"] == "Crack_SeisY_UpSoil"
    assert fetched.parsed.rows[0]["FX"] == "10.5"
    assert fetched.signature_attempts[0]["parser_status"] == "PARSED_ROWS"


def test_shared_fetcher_matches_legacy_parser_on_tuple_string_sequences():
    from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table
    from tools.probe_live_story_base_tables_legacy_oracle import parse_etabs_display_table_result as legacy_parse

    headers = ["Story", "OutputCase", "Direction", "Drift"]
    flat = ["+14.5", "Crack_SeisY_UpSoil", "Y", "9.5"]
    raw = (headers, flat, 1, 0)
    legacy = legacy_parse(raw, actual_table_name="Story Drifts", max_rows=100000)

    class Db:
        def GetTableForDisplayArray(self, *args):
            return raw

    fetched = fetch_display_table(Db(), "Story Drifts", max_rows=None)

    assert [dict(r) for r in fetched.parsed.rows] == [dict(r) for r in legacy.rows]
    assert fetched.parsed.field_keys == legacy.field_keys


def test_shared_fetcher_selects_parsed_rows_when_legacy_would_parse_rows():
    from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table
    from tools.probe_live_story_base_tables_legacy_oracle import parse_etabs_display_table_result as legacy_parse

    headers = ["Story", "OutputCase", "Direction", "Drift"]
    flat = ["+14.5", "Crack_SeisY_UpSoil", "Y", "9.5"]
    raw = (headers, flat, 1, 0)
    assert legacy_parse(raw, actual_table_name="Story Drifts", max_rows=100000).rows

    class Db:
        def __init__(self):
            self.calls = 0

        def GetTableForDisplayArray(self, *args):
            self.calls += 1
            return raw

    db = Db()
    fetched = fetch_display_table(db, "Story Drifts", max_rows=None)

    assert db.calls == 1
    assert fetched.selected_signature_reason == "first_signature_with_parsed_rows"
    assert fetched.selected_signature["parser_status"] == "PARSED_ROWS"


def test_legacy_oracle_shape_reproduced_by_shared_fetcher():
    from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table
    from tools.probe_live_story_base_tables_legacy_oracle import parse_etabs_display_table_result as legacy_parse

    headers = ["OutputCase", "FX", "FY"]
    flat = ["Crack_SeisY_UpSoil", "10", "20"]
    raw = (headers, flat, 1, 0)
    legacy = legacy_parse(raw, actual_table_name="Base Reactions", max_rows=100000)

    class Db:
        def GetTableForDisplayArray(self, *args):
            return raw

    fetched = fetch_display_table(Db(), "Base Reactions", max_rows=None)

    assert legacy.rows
    assert fetched.parsed.rows
    assert fetched.parsed.debug["table_data_length"] == legacy.debug["table_data_length"]
    assert fetched.parsed.debug["header_count"] == legacy.debug["header_count"]


def test_display_selection_uses_list_only_combo_call():
    from tbdy_engine.providers.etabs_display_table_fetcher import select_output_for_display

    class Db:
        def __init__(self):
            self.combo_calls = []
            self.case_calls = []

        def SetLoadCombinationsSelectedForDisplay(self, *args):
            self.combo_calls.append(args)
            return (["Crack_SeisY_UpSoil"], 0)

        def SetLoadCasesSelectedForDisplay(self, *args):
            self.case_calls.append(args)
            return (["Crack_SeisY_UpSoil"], 0)

    db = Db()
    diag = select_output_for_display(db, "Crack_SeisY_UpSoil")

    assert db.combo_calls == [(["Crack_SeisY_UpSoil"],)]
    assert all(len(call) == 1 and isinstance(call[0], list) for call in db.combo_calls)
    assert diag["display_selection_success"] is True
    assert diag["display_selection_selected_method"] == "SetLoadCombinationsSelectedForDisplay"


def test_display_selection_uses_list_only_case_call_as_fallback_or_diagnostic():
    from tbdy_engine.providers.etabs_display_table_fetcher import select_output_for_display

    class Db:
        def __init__(self):
            self.case_calls = []

        def SetLoadCombinationsSelectedForDisplay(self, *args):
            raise RuntimeError("combo not found")

        def SetLoadCasesSelectedForDisplay(self, *args):
            self.case_calls.append(args)
            return (["Crack_SeisY_UpSoil"], 0)

    db = Db()
    diag = select_output_for_display(db, "Crack_SeisY_UpSoil")

    assert db.case_calls == [(["Crack_SeisY_UpSoil"],)]
    assert all(len(call) == 1 and isinstance(call[0], list) for call in db.case_calls)
    assert diag["display_selection_success"] is True
    assert diag["display_selection_selected_method"] == "SetLoadCasesSelectedForDisplay"


def test_fetch_story_base_tables_after_display_selection():
    from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table, select_output_for_display

    headers = ["Story", "OutputCase", "Direction", "Drift"]
    empty = _sequence_response(headers, [], 16, return_code=0)
    full = _sequence_response(headers, [["+14.5", "Crack_SeisY_UpSoil", "X", "0.000534"]], 1, return_code=0)

    class Db:
        def __init__(self):
            self.selected = False

        def SetLoadCombinationsSelectedForDisplay(self, values):
            self.selected = values == ["Crack_SeisY_UpSoil"]
            return (values, 0)

        def SetLoadCasesSelectedForDisplay(self, values):
            return (values, 0)

        def GetTableForDisplayArray(self, *args):
            return full if self.selected else empty

    db = Db()
    before = fetch_display_table(db, "Story Drifts", max_rows=None)
    assert before.parsed.rows == ()
    diag = select_output_for_display(db, "Crack_SeisY_UpSoil")
    after = fetch_display_table(db, "Story Drifts", max_rows=None)

    assert diag["fetch_after_display_selection"] is True
    assert after.parsed.rows[0]["Story"] == "+14.5"
    assert after.parsed.rows[0]["OutputCase"] == "Crack_SeisY_UpSoil"


def test_does_not_accept_empty_tabledata_when_display_selection_not_applied():
    from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table, select_output_for_display

    headers = ["OutputCase", "FX", "FY"]
    empty = _sequence_response(headers, [], 2, return_code=0)

    class Db:
        def SetLoadCombinationsSelectedForDisplay(self, values):
            raise RuntimeError("selection failed")

        def SetLoadCasesSelectedForDisplay(self, values):
            raise RuntimeError("selection failed")

        def GetTableForDisplayArray(self, *args):
            return empty

    db = Db()
    diag = select_output_for_display(db, "Crack_SeisY_UpSoil")
    fetched = fetch_display_table(db, "Base Reactions", max_rows=None)

    assert diag["display_selection_success"] is False
    assert fetched.parsed.rows == ()
    assert fetched.selected_signature["parser_status"] == "TABLEDATA_EMPTY_DESPITE_RECORDS"


def test_display_selection_diagnostics_are_recorded():
    table = {
        "actual_table_name": "Story Drifts",
        "canonical_table_key": "story_drifts",
        "headers": ["Story", "OutputCase", "Direction", "Drift"],
        "rows": [{"Story": "+14.5", "OutputCase": "Crack_SeisY_UpSoil", "Direction": "X", "Drift": "0.000534"}],
        "raw_table_diagnostics": {
            "number_records": 1,
            "table_data_length": 4,
            "preferred_output_case": "Crack_SeisY_UpSoil",
            "display_selection_attempted": True,
            "display_selection_attempts": [{"method": "SetLoadCombinationsSelectedForDisplay", "args_shape": ["list"], "call_succeeded": True, "return_code": 0}],
            "display_selection_selected_method": "SetLoadCombinationsSelectedForDisplay",
            "display_selection_success": True,
            "fetch_after_display_selection": True,
        },
    }
    report = _resolver(_payload_with_table(table)).build_all().story_base_table_debug_report["story_drifts"]

    assert report["display_selection_attempted"] is True
    assert report["display_selection_success"] is True
    assert report["fetch_after_display_selection"] is True
    assert report["display_selection_selected_method"] == "SetLoadCombinationsSelectedForDisplay"
    assert list(report["display_selection_attempts"][0]["args_shape"]) == ["list"]


def test_live_smoke_story_base_fetch_uses_preferred_output_case():
    import inspect
    import tools.smoke_live_feature_resolver as smoke_tool

    source = inspect.getsource(smoke_tool._live_probe_tables_and_units)
    assert "select_output_for_display(database_tables, preferred_output_case)" in source
    assert "STORY_BASE_RESULT_TABLES" in source
    assert "preferred_output_case=args.preferred_output_case" in inspect.getsource(smoke_tool.main)


def test_probe_live_story_base_tables_uses_display_selection_before_fetch():
    import inspect
    import tools.probe_live_story_base_tables as probe_tool

    source = inspect.getsource(probe_tool.run_live_probe)
    assert "select_output_for_display(database_tables, preferred_output_case)" in source
    assert source.index("select_output_for_display") < source.index("fetch_display_table")


def test_display_selection_does_not_use_int_overload():
    from tbdy_engine.providers.etabs_display_table_fetcher import select_output_for_display

    class Db:
        def __init__(self):
            self.calls = []

        def SetLoadCombinationsSelectedForDisplay(self, *args):
            self.calls.append(args)
            if len(args) != 1 or not isinstance(args[0], list):
                raise AssertionError("int overload must not be used")
            return (args[0], 0)

    db = Db()
    diag = select_output_for_display(db, "Crack_SeisY_UpSoil")
    assert diag["display_selection_success"] is True
    assert db.calls == [(["Crack_SeisY_UpSoil"],)]


def test_display_selection_combo_success_skips_case_mutation():
    from tbdy_engine.providers.etabs_display_table_fetcher import select_output_for_display

    class Db:
        def __init__(self):
            self.combo_calls = []
            self.case_calls = []

        def SetLoadCombinationsSelectedForDisplay(self, *args):
            self.combo_calls.append(args)
            return (args[0], 0)

        def SetLoadCasesSelectedForDisplay(self, *args):
            self.case_calls.append(args)
            return (args[0], 0)

    db = Db()
    diag = select_output_for_display(db, "Crack_SeisY_UpSoil")
    assert db.combo_calls == [(["Crack_SeisY_UpSoil"],)]
    assert db.case_calls == []
    assert diag["display_selection_selected_method"] == "SetLoadCombinationsSelectedForDisplay"
    assert diag["attempted_case_fallback"] is False
    assert diag["skipped_case_selection_because_combo_succeeded"] is True
    assert [a["method"] for a in diag["display_selection_attempts"]] == ["SetLoadCombinationsSelectedForDisplay"]


def test_display_selection_case_fallback_when_combo_fails():
    from tbdy_engine.providers.etabs_display_table_fetcher import select_output_for_display

    class Db:
        def __init__(self):
            self.combo_calls = []
            self.case_calls = []

        def SetLoadCombinationsSelectedForDisplay(self, *args):
            self.combo_calls.append(args)
            return (args[0], 1)

        def SetLoadCasesSelectedForDisplay(self, *args):
            self.case_calls.append(args)
            return (args[0], 0)

    db = Db()
    diag = select_output_for_display(db, "Crack_SeisY_UpSoil")
    assert db.combo_calls == [(["Crack_SeisY_UpSoil"],)]
    assert db.case_calls == [(["Crack_SeisY_UpSoil"],)]
    assert diag["display_selection_selected_method"] == "SetLoadCasesSelectedForDisplay"
    assert diag["attempted_case_fallback"] is True
    assert diag["skipped_case_selection_because_combo_succeeded"] is False


def test_display_selection_reports_kind_combo_case_unknown():
    from tbdy_engine.providers.etabs_display_table_fetcher import select_output_for_display

    class ComboDb:
        load_combination_names = ["Crack_SeisY_UpSoil"]

        def SetLoadCombinationsSelectedForDisplay(self, values):
            return (values, 0)

    class CaseDb:
        load_case_names = ["EQX"]

        def SetLoadCombinationsSelectedForDisplay(self, values):
            return (values, 1)

        def SetLoadCasesSelectedForDisplay(self, values):
            return (values, 0)

    class UnknownDb:
        def SetLoadCombinationsSelectedForDisplay(self, values):
            return (values, 0)

    assert select_output_for_display(ComboDb(), "Crack_SeisY_UpSoil")["preferred_output_kind_detected"] == "combo"
    assert select_output_for_display(CaseDb(), "EQX")["preferred_output_kind_detected"] == "case"
    assert select_output_for_display(UnknownDb(), "Crack_SeisY_UpSoil")["preferred_output_kind_detected"] == "unknown"
