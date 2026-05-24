
from tools.discover_etabs_combo_columns_v1 import is_combo_column_name, is_actual_combo_like_value

def test_combo_column_name_detection():
    assert is_combo_column_name("Combo")
    assert is_combo_column_name("Load Combo")
    assert is_combo_column_name("DesignCombo")
    assert is_combo_column_name("OutputCase")
    assert not is_combo_column_name("combo_family")
    assert not is_combo_column_name("combo_resolved_family")

def test_combo_value_detection():
    assert is_actual_combo_like_value("G+0.3Q+Ex")
    assert is_actual_combo_like_value("K_E_X")
    assert is_actual_combo_like_value("EQX")
    assert not is_actual_combo_like_value("K_E")
    assert not is_actual_combo_like_value("UNEXPOSED_ETABS_COMBO::S_E")
