import inspect

import tools.probe_vs6_etabs_direction_sources as probe


def test_direction_source_probe_is_read_only_and_factual_only():
    source = inspect.getsource(probe)
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "SetLoadType(",
        "SetLoads(",
        "SWAY_PREVENTED",
        "ENGINE_SELECTED_REBAR",
    ):
        assert forbidden not in source

    assert '"case_names_used_for_direction_inference": False' in source
    assert '"seismic_direction_promoted": False' in source
    assert '"wind_direction_promoted": False' in source
    assert '"stability_index_calculated": False' in source
    assert '"sway_classification_promoted": False' in source


def test_available_table_decoder_accepts_generated_com_shapes():
    class DatabaseTables:
        def GetAvailableTables(self):
            return (
                3,
                (
                    "Load Pattern Definitions - Auto Seismic - User Coefficient",
                    "Story Definitions",
                    "Load Pattern Definitions - Auto Wind - ASCE 7-22",
                ),
                ("Auto Seismic", "Stories", "Auto Wind"),
                (3, 0, 3),
                0,
            )

    rows = probe._available_tables(DatabaseTables())
    assert len(rows) == 3
    assert rows[0]["table_key"] == "Load Pattern Definitions - Auto Seismic - User Coefficient"
    assert rows[2]["import_type"] == 3


def test_candidate_filter_uses_table_metadata_not_case_names():
    rows = (
        {"index": 0, "table_key": "A", "table_name": "Story Definitions", "import_type": 0},
        {"index": 1, "table_key": "B", "table_name": "Auto Seismic Parameters", "import_type": 0},
        {"index": 2, "table_key": "Load Pattern Definitions", "table_name": "Load Pattern Definitions", "import_type": 0},
        {"index": 3, "table_key": "D", "table_name": "Wind Parameters", "import_type": 0},
    )
    selected = probe._direction_candidate_tables(rows)
    assert [item["table_key"] for item in selected] == ["B", "Load Pattern Definitions", "D"]
