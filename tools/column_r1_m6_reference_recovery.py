"""Reproduce the exact October 1 Prota/ETABS example offline.

This is evidence recovery, not a modal solver or FC09 input provider. The
comparison retains independent ETABS Max/Min effects as such and never emits
TS500 authority, AnalysisResultIdentity, a synchronous state, or READY.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile


SOURCE_FILES = {
    "Pasted text(20261001-041302).txt": (
        "libfile_f876b2387fec8191ab5dfcfddcab4151",
        "d0b87f6c98b80b8e1d3516a2f148befe0713c204ed2e8b474cdff95db44a30c1",
    ),
    "tr1-RCColDes.docx": (
        "libfile_d38fc3eecac48191978b7554109c0aa8",
        "d89a69e1647e2078ff9da037fdc9c6e26b320a6f1060b5147e2218d5163751ed",
    ),
    "tr1-ColSln.docx": (
        "libfile_de5de29fad848191a0030a35ae127965",
        "0bb29e790038e81fbe2a0c9ccee421b955f196bbfd780a154a04c370b805f5dd",
    ),
    "tr1-A2.docx": (
        "libfile_d96db2fe70608191927bb245d4fe6b9e",
        "6fae0fd5197cc3e806fd4dcb993393ff2570b96d2a70556078fa30694ff48f2a",
    ),
}
X_EXPORT_LABEL = "Gc+Qc+Ez+Ex-"
Y_EXPORT_LABEL = "Gc+Qc+Ez+Ey-"
REFERENCE_SCOPE = "OCTOBER_1_PROTA_EXPORT_EXAMPLE_ONLY_NOT_FC09"
FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/column_r1_m6_prota_etabs_reference.json"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _number(value):
    if not isinstance(value, str):
        raise ValueError("reference quantities must retain original decimal strings")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("nonfinite reference quantity")
    return result


def _paragraphs(path):
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    return ["".join(n.text or "" for n in p.iter(_W + "t")).strip()
            for p in root.iter(_W + "p")]


def recover(source_directory):
    """Read exact original bytes; project a bounded subset without changing them."""
    directory = Path(source_directory)
    for filename, (_, digest) in SOURCE_FILES.items():
        if hashlib.sha256((directory / filename).read_bytes()).hexdigest() != digest:
            raise ValueError(f"original reference SHA256 mismatch: {filename}")
    raw = (directory / "Pasted text(20261001-041302).txt").read_text(encoding="utf-8-sig")
    rows = [line.split("\t") for line in raw.splitlines()
            if line.startswith(("ST1\t", "ST2\t"))]
    if len(rows) != 5568 or any(len(row) != 16 for row in rows):
        raise ValueError("original ETABS full row count/shape differs")
    names = {(row[0], row[1]) for row in rows}
    expected = {(f"ST{s}", f"S{c}-{s} 50/50") for s in (1, 2) for c in range(1, 17)}
    if names != expected:
        raise ValueError("original ETABS story/column population differs")
    paragraphs = _paragraphs(directory / "tr1-RCColDes.docx")
    columns = []
    for index, paragraph in enumerate(paragraphs):
        match = re.fullmatch(r"S(\d+)\s+\([^)]+\)\s+Storey:\s+([12])\s+\(50/50\)", paragraph)
        if not match:
            continue
        column, story = int(match[1]), int(match[2])
        end = paragraphs.index("Interaction Diagram", index)
        start = paragraphs.index("M2 Bot", index, end) + 2
        cells = paragraphs[start:end]
        if len(cells) != 19 * 7:
            raise ValueError("Prota design table is incomplete")
        design = [cells[n:n + 7] for n in range(0, len(cells), 7)]
        if [row[0] for row in design] != [str(n) for n in range(1, 20)]:
            raise ValueError("Prota design combination population differs")
        selected = [row for row in rows if row[0] == f"ST{story}"
                    and row[1] == f"S{column}-{story} 50/50"
                    and row[3] in ("G+Q", X_EXPORT_LABEL, Y_EXPORT_LABEL)
                    and row[6] in ("0", "3")]
        columns.append({"story": f"ST{story}", "column": f"S{column}",
                        "prota_design_rows": [design[n - 1] for n in (1, 6, 10)],
                        "etabs_export_rows": selected})
    sway = []
    paragraphs = _paragraphs(directory / "tr1-ColSln.docx")
    for direction in (1, 2):
        start = paragraphs.index(f"Dir: {direction} - STOREY SWAY CHECK")
        start = paragraphs.index("Sway Status", start) + 1
        for offset in (0, 10):
            cells = paragraphs[start + offset:start + offset + 10]
            sway.append({"story": f"ST{cells[0]}", "direction": "X" if direction == 1 else "Y",
                         "height_cm": cells[1], "delta_mm": cells[2],
                         "sum_Nd_tonf": cells[3], "Vf_tonf": cells[4],
                         "combo_number": cells[5], "reported_phi": cells[8].split("≤")[0].strip(),
                         "reported_status": cells[9]})
    result = {
        "scope": REFERENCE_SCOPE,
        "source_files": {name: {"library_file_id": ref, "original_sha256": digest}
                         for name, (ref, digest) in SOURCE_FILES.items()},
        "original_etabs_result_row_count": len(rows),
        "projection": "32 columns; Prota rows 1/6/10; ETABS G+Q and paired X/Y Max/Min at stations 0/3",
        "columns": sorted(columns, key=lambda c: (c["story"], int(c["column"][1:]))),
        "sway_rows": sway,
    }
    compare(result)  # Reject incomplete/duplicate projection before returning it.
    return result


def compare(reference):
    """Compare the historical reported pair, without promoting a load basis."""
    if reference["scope"] != REFERENCE_SCOPE:
        raise ValueError("historical example cannot be rebound to a current source")
    sources = {name: {"library_file_id": ref, "original_sha256": digest}
               for name, (ref, digest) in SOURCE_FILES.items()}
    if reference["source_files"] != sources or reference["original_etabs_result_row_count"] != 5568:
        raise ValueError("reference source binding differs")
    expected = {(f"ST{s}", f"S{c}") for s in (1, 2) for c in range(1, 17)}
    identities = [(c["story"], c["column"]) for c in reference["columns"]]
    if len(identities) != len(set(identities)) or set(identities) != expected:
        raise ValueError("complete unique 16-column population per story required")
    force_keys = {(case, step, station) for case, steps in (
        ("G+Q", ("",)), (X_EXPORT_LABEL, ("Max", "Min")), (Y_EXPORT_LABEL, ("Max", "Min")))
                  for step in steps for station in ("0", "3")}
    for column in reference["columns"]:
        design = column["prota_design_rows"]
        if len(design) != 3 or [r[0] for r in design] != ["1", "6", "10"] or any(len(r) != 7 for r in design):
            raise ValueError("exact Prota design rows 1/6/10 required")
        for row in design:
            for value in row[1:]:
                _number(value)
        keys = []
        for row in column["etabs_export_rows"]:
            if len(row) != 16 or (row[0], row[1]) != (
                column["story"], f"{column['column']}-{column['story'][2:]} 50/50"):
                raise ValueError("ETABS row story/column binding differs")
            if row[4] != "Combination":
                raise ValueError("wrong factual ETABS output type")
            for value in row[7:13]:
                _number(value)
            keys.append((row[3], row[5], row[6]))
        if len(keys) != len(set(keys)) or set(keys) != force_keys:
            raise ValueError("ETABS Max/Min/station population incomplete or duplicate")
    sway_keys = [(row["story"], row["direction"]) for row in reference["sway_rows"]]
    if len(sway_keys) != 4 or set(sway_keys) != {(s, d) for s in ("ST1", "ST2") for d in ("X", "Y")}:
        raise ValueError("complete unique story/direction sway report required")
    comparisons = []
    for sway in reference["sway_rows"]:
        columns = [c for c in reference["columns"] if c["story"] == sway["story"]]
        combo = "6" if sway["direction"] == "X" else "10"
        if sway["combo_number"] != combo:
            raise ValueError("reported critical combination number differs")
        label = X_EXPORT_LABEL if sway["direction"] == "X" else Y_EXPORT_LABEL
        prota_sum = sum((_number(next(r for r in c["prota_design_rows"] if r[0] == combo)[4])
                         for c in columns), Decimal(0))
        etabs_sum = sum((-_number(next(r for r in c["etabs_export_rows"]
                         if (r[3], r[5], r[6]) == (label, "Min", "0"))[7])
                        for c in columns), Decimal(0))
        reported = _number(sway["sum_Nd_tonf"])
        comparisons.append({"story": sway["story"], "direction": sway["direction"],
                            "column_count": len(columns), "reported_combo_number": combo,
                            "paired_export_label": label, "reported_sum_Nd_tonf": str(reported),
                            "rounded_Prota_NBot_sum_tonf": str(prota_sum),
                            "ETABS_independent_Min_P_sum_tonf": str(etabs_sum),
                            "Prota_rounding_difference_tonf": str(prota_sum - reported),
                            "ETABS_difference_tonf": str(etabs_sum - reported)})
    return {"scope": REFERENCE_SCOPE, "comparison": comparisons,
            "qualified_modal_aggregate": False, "current_FC09_qualification": False,
            "physical_concurrency_proven": False,
            "meaning": "Reported comparison only. Independent modal-combined member extrema do not reproduce Prota story design totals; this does not prove Prota internal modal algebra."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-directory", type=Path,
                        help="Directory containing all four exact historical files")
    args = parser.parse_args(argv)
    reference = recover(args.source_directory) if args.source_directory else json.loads(FIXTURE.read_text())
    if args.source_directory and reference != json.loads(FIXTURE.read_text()):
        raise ValueError("exact original bytes do not reproduce the checked-in projection")
    print(json.dumps(compare(reference), indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
