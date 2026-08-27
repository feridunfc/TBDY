from tbdy_engine.providers.etabs_concrete_design_combo_selection_probe import (
    SOURCE_NOT_PROVEN,
    TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
    probe_concrete_frame_design_combo_selection_table,
)


class FakeDatabaseTables:
    def __init__(self):
        self.calls = []

    def GetTableForDisplayArray(self, *args):
        self.calls.append(("GetTableForDisplayArray", args))
        return {
            "return_code": 0,
            "field_keys": ["ComboName", "ComboType", "DesignType"],
            "table_data": ["CMB1", "Strength", "User", "CMB2", "Strength", "Automatic"],
            "number_records": 2,
        }


def test_candidate_table_probe_is_read_only_and_never_promotes_semantics():
    db = FakeDatabaseTables()
    probe = probe_concrete_frame_design_combo_selection_table(db)
    assert probe.table_key == TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA
    assert probe.combo_names == ("CMB1", "CMB2")
    assert probe.combo_name_field_present
    assert probe.source_semantics_status == SOURCE_NOT_PROVEN
    assert {name for name, _args in db.calls} == {"GetTableForDisplayArray"}
    assert not any(name.startswith("Set") for name, _args in db.calls)
