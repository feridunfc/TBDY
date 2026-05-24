from tbdy_engine.design.joints.scwb_projection import _build_projection


def test_scwb_projection_maps_joint_result_to_column_and_beam_details():
    raw = [{
        "joint_id": "J1",
        "story": "+0.00",
        "direction": "X",
        "columns": ["C1", "C2"],
        "beams": ["B1"],
        "sum_mrc_knm": 300.0,
        "sum_mrb_knm": 200.0,
        "required_mrc_knm": 240.0,
        "ratio": 1.25,
        "status": "WARNING",
        "evaluation_level": "APPROXIMATE",
        "note": "SCWB ratio computed with non-final or approximate capacities",
    }]

    col, beam = _build_projection(raw)

    assert len(col) == 1
    assert len(beam) == 1
    assert col[0]["source"] == "scwb_resolver"
    assert beam[0]["source"] == "scwb_resolver"
    assert col[0]["evaluation_level"] == "APPROXIMATE"
    assert beam[0]["ratio"] == 1.25
    assert "reason_code=approximate_capacity" in col[0]["message"]
