SHEET_NAMES = [
    "00_Summary",
    "01_Checks",
    "02_Features",
    "03_No_Data",
    "04_Evidence",
    "05_ETABS_Tables",
    "06_Beam_Design",
    "07_Review",
    "99_Manifest",
]


def test_reserved_excel_sheet_names_are_within_excel_limit():
    assert all(len(name) <= 31 for name in SHEET_NAMES)
