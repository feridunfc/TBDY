from tools.apply_provenance_fields_v1 import apply_provenance, apply_provenance_to_row

def test_adds_scwb_provenance_from_message():
    row = {"check_id":"beam_capacity_hierarchy","element_label":"1056","status":"WARNING","ratio":1.248,"message":"SCWB beam projection: joint=1056; beams=F221,B236; columns=C74; dir=X; ΣMrc=1071.458 kNm; ΣMrb=715.607 kNm; required=1.2ΣMrb=858.729 kNm; ratio=1.248; reason_code=approximate_capacity; source=scwb_resolver","evaluation_level":"APPROXIMATE","source":"scwb_resolver"}
    out = apply_provenance_to_row(row)
    assert out["source_table"] == "SCWB Projection / Joint Capacity"
    assert out["combo_family"] == "S_E"
    assert out["combo_provenance_level"] == "required_family_only"
    assert out["raw_unit"] == "kNm"
    assert out["evidence"]["sum_Mrc_kNm"] == 1071.458
    assert out["evidence"]["direction"] == "X"
    assert out["source_is_approximate"] is True

def test_adds_confinement_provenance_fields():
    row = {"check_id":"column_confinement","element_label":"C1","status":"WARNING","message":"Confinement screening warning: Confinement FAIL: Ash=236mm2 < required=567mm2. provided=Phi10@150mm, legs=3/3, source=etabs_design_summary. Proposal: use at least 12 legs Phi8","source":"confinement_proposal","reason_code":"non_final_confinement_proposal","evaluation_level":"SCREENING"}
    out = apply_provenance_to_row(row)
    assert out["source_table"] == "Concrete Frame Design Summary / Confinement Proposal"
    assert out["source_field"] == "Ash_required/Ash_provided/spacing/legs"
    assert out["combo_family"] == "S_E"
    assert out["raw_unit"] == "mm2/mm"
    assert out["evidence"]["Ash_required"] == 567
    assert out["source_is_proposal"] is True

def test_report_summary_counts_provenance_fields():
    report = {"report_metadata":{"schema":"final_engine_report.v1"},"checks":[
        {"check_id":"column_confinement","status":"WARNING","source":"confinement_proposal","reason_code":"non_final_confinement_proposal","evaluation_level":"SCREENING","message":"Confinement FAIL: Ash=236mm2 < required=567mm2. provided=Phi10@150mm, legs=3/3"},
        {"check_id":"beam_capacity_hierarchy","status":"WARNING","source":"scwb_resolver","evaluation_level":"APPROXIMATE","message":"SCWB beam projection: joint=1; beams=B1; columns=C1; dir=Y; ΣMrc=100 kNm; ΣMrb=50 kNm; required=1.2ΣMrb=60 kNm"}]}
    out = apply_provenance(report)
    s = out["provenance_summary"]
    assert s["total_rows"] == 2
    assert s["source_table_count"] == 2
    assert s["governing_combo_count"] == 2
    assert s["raw_unit_count"] == 2
    assert s["combo_provenance_level"]["required_family_only"] == 2
