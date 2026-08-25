import inspect

import tools.probe_vs6_etabs_stiffness_basis_sources as probe


def test_stiffness_source_probe_is_read_only_and_factual_only():
    source = inspect.getsource(probe)
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "SetModifiers(",
        "SetModifier(",
        "SWAY_PREVENTED",
        "ENGINE_SELECTED_REBAR",
    ):
        assert forbidden not in source

    assert '"uncracked_stiffness_basis_promoted": False' in source
    assert '"analysis_order_promoted": False' in source
    assert '"reanalysis_required_emitted": False' in source
    assert '"stability_index_calculated": False' in source
    assert '"sway_classification_promoted": False' in source


def test_candidate_selection_uses_metadata_tokens_not_guessed_table_inventory():
    rows = (
        {"index": 1, "table_key": "Frame Assignments - Property Modifiers", "table_name": "Frame Assignments - Property Modifiers", "import_type": 2},
        {"index": 2, "table_key": "Frame Section Property Definitions - Concrete Rectangular", "table_name": "Frame Section Property Definitions - Concrete Rectangular", "import_type": 2},
        {"index": 3, "table_key": "Story Forces", "table_name": "Story Forces", "import_type": 0},
        {"index": 4, "table_key": "Load Case Definitions - Summary", "table_name": "Load Case Definitions - Summary", "import_type": 2},
    )
    selected = probe._candidate_tables(rows)
    assert [item["table_key"] for item in selected] == [
        "Frame Assignments - Property Modifiers",
        "Frame Section Property Definitions - Concrete Rectangular",
        "Load Case Definitions - Summary",
    ]


def test_large_table_projection_keeps_modifier_and_selected_column_rows():
    rows = tuple(
        {"UniqueName": str(i), "Section": "B60x70", "I2Mod": "0.35", "I3Mod": "0.35"}
        for i in range(200)
    ) + ({"UniqueName": "236", "Section": "Column_80x80", "I2Mod": "0.70", "I3Mod": "0.70"},)
    projected = probe._interesting_rows(rows, limit=20)
    assert projected
    assert all("I2Mod" in row for row in projected)
    assert len(projected) == 20
