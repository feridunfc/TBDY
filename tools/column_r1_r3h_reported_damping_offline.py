"""Exact accepted R3D bytes -> reported-total-damping CQC of separate R/V.

Offline factual representative scope only. No ETABS, B5 epoch, global Delta,
concurrent state, Eq.7.13 statistic or readiness promotion is issued.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT, REPO_ROOT / "packages" / "etabs_gateway" / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tools.column_r1_r3e_modal_normalization_offline import (
    ACCEPTED_RECEIPT_SHA256, TABLE, bind_receipt_amplitudes,
)
from tools.column_r1_r3g_modal_operands_offline import MODES, reconcile_receipt_modal_operands
from tbdy_engine.etabs.oapi.database_tables import decode_table_field_metadata
from tbdy_engine.providers.etabs_story_stability_result_provider import qualify_native_reported_total_modal_damping
from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    CSI_REPORTED_TOTAL_MODAL_DAMPING_V1, CSI_REPORTED_TOTAL_DAMPING_SOURCE,
    PeriodicCqcMode, PeriodicCqcOperator, CqcModalQuantity,
)


def validate_native_frequency_correspondence(row):
    """Match native rounded period/frequency/omega/eigenvalue intervals.

    Half one last displayed decimal is a source display-rounding allowance,
    not a model tolerance or an invented internal frequency. The operator
    retains and uses the actual native cyclic Frequency value unchanged.
    """
    intervals = {}
    for key in ("Period", "Frequency", "CircFreq", "Eigenvalue"):
        text = row[key]
        if not isinstance(text, str):
            raise ValueError("exact native frequency text required")
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("invalid native frequency text") from exc
        if not number.is_finite() or number <= 0:
            raise ValueError("finite positive native period/frequency required")
        half = Decimal(5).scaleb(number.as_tuple().exponent - 1)
        lo, hi = float(number - half), float(number + half)
        if lo <= 0 or not math.isfinite(hi):
            raise ValueError("positive finite native frequency rounding interval required")
        intervals[key] = (lo, hi)
    p, f, w, e = (intervals[k] for k in ("Period", "Frequency", "CircFreq", "Eigenvalue"))
    low = max(f[0], 1 / p[1], w[0] / (2 * math.pi), math.sqrt(e[0]) / (2 * math.pi))
    high = min(f[1], 1 / p[0], w[1] / (2 * math.pi), math.sqrt(e[1]) / (2 * math.pi))
    if low > high:
        raise ValueError("native period/frequency/circular-frequency/eigenvalue correspondence mismatch")
    return float(row["Frequency"])


def reconcile_reported_total_damping(receipt):
    """Extend the existing factual projection, preserving R3G's historical API."""
    result = reconcile_receipt_modal_operands(receipt)
    amplitudes = bind_receipt_amplitudes(receipt)
    facts = receipt["facts"]
    metadata_fact = facts[TABLE + ":metadata"]
    metadata = decode_table_field_metadata(metadata_fact["payload"]["raw_response"], table_name=TABLE)
    totals, matrices, checks = {}, {}, {}
    for case, amps in amplitudes.items():
        fact = facts[TABLE + "@" + case]
        parsed = fact["payload"]["parsed"]
        if (parsed["actual_table_name"] != TABLE or parsed["fetch_status"] != "FETCHED"
                or parsed["return_code"] != 0):
            raise ValueError("successful exact reported damping table required")
        damping = qualify_native_reported_total_modal_damping(parsed["rows"], amplitudes=amps,
            expected_modes=MODES, metadata=metadata, raw_response_ref=fact["capture_payload_ref"])
        rows = result["modal_operands"][case]
        cqc_modes = []
        for row, a, d in zip(rows, amps, damping):
            frequency = validate_native_frequency_correspondence(row["native_period_frequency_row"])
            row["total_damping_ratio"] = d.total_ratio
            row["reported_total_damping"] = asdict(d)
            row["source_refs"] = list(dict.fromkeys([*row["source_refs"], d.metadata_ref,
                d.raw_payload_ref, metadata_fact["capture_payload_ref"], CSI_REPORTED_TOTAL_DAMPING_SOURCE]))
            cqc_modes.append(PeriodicCqcMode(row["mode"], frequency, d, a.binding, tuple(row["source_refs"])))
        signature = result["case_signatures"][case]
        settings = {s["method"]: s for s in signature["native_getters"]}
        f2 = dict(settings["GetModalComb_1"]["outputs"])["F2"]
        operator = PeriodicCqcOperator(tuple(cqc_modes), MODES,
            signature["native_case_row"]["ModalCombo"], f2)
        matrix = operator.correlation_matrix
        if (len(matrix) != 100 or any(len(r) != 100 for r in matrix)
                or any(matrix[i][i] != 1 or any(not 0 <= matrix[i][j] <= 1
                    or matrix[i][j] != matrix[j][i] for j in range(100)) for i in range(100))):
            raise ValueError("invalid source-exact complete CQC correlation matrix")
        matrices[case] = matrix
        for quantity, field, unit in (("COLUMN_ONLY_LENGTH_WEIGHTED_R", "R_kN_per_m", "kN/m"),
                                      ("GLOBAL_STORY_BOTTOM_SHEAR", "V_kN", "kN")):
            q = tuple(CqcModalQuantity(r["mode"], r[field], a.binding, quantity, unit, tuple(r["source_refs"]))
                      for r, a in zip(rows, amps))
            result[case + ("_R_CQC" if field == "R_kN_per_m" else "_V_CQC")] = operator.combine(q)
        totals[case] = [asdict(d) for d in damping]
        checks[case] = {"unique_modes": len(damping), "reported_total_values": sorted({d.total_ratio for d in damping}),
            "case_damping_observation": signature["case_damping_observation"],
            "comparison": "NATIVE_TOTAL_OBSERVED_INDEPENDENTLY; NO_COMPONENT_ZERO_INFERENCE",
            "additional_case_material_link_contribution_added": False}
        signature["total_modal_damping"] = "PROVEN_NATIVE_REPORTED_EFFECTIVE_TOTAL"
    result.update({
        "status": "R3H_REPORTED_TOTAL_DAMPING_AND_SEPARATE_R_V_CQC_PROVEN_OFFLINE",
        "total_damping_authority": CSI_REPORTED_TOTAL_MODAL_DAMPING_V1,
        "total_damping_source": CSI_REPORTED_TOTAL_DAMPING_SOURCE,
        "total_damping_checks": checks, "reported_total_damping": totals,
        "CQC": "PROVEN_CONSTANT_REPORTED_TOTAL_F2_ZERO_PERIODIC",
        "CQC_source_authorities": [*result["CQC_source_authorities"], CSI_REPORTED_TOTAL_DAMPING_SOURCE],
        "CQC_matrix_issued": True, "CQC_correlation_matrices": matrices,
        "CQC_result_semantics": "UNSIGNED_STATISTICAL_MAGNITUDES_OF_SEPARATE_QUANTITIES; NOT_CONCURRENT",
        "CQC_precision": "Actual native reported Frequency decimals; no unrounded internal ETABS equality claim",
        "CQC_native_independent_aggregate_comparison": "NOT_AVAILABLE_AT_EXACT_COLUMN_ONLY_LENGTH_WEIGHTED_R_GRAIN",
        "GLOBAL_DELTA": "BLOCKED_POINT_LOCAL_TO_GLOBAL_AXES_NOT_CAPTURED",
        "CURRENT_UNCRACKED_B5": "NOT_PROVIDED",
        "M6_B": "OPEN",
    })
    # Existing source projection already rejects an alleged B5 epoch and keeps
    # these independent gates false. Never promote individual CQC magnitudes.
    if result["current_b5_qualified"] or result["stability_promotion"] or result["R2_RERUN_READY"]:
        raise ValueError("factual separate CQC magnitudes cannot promote a joint stability state")
    return result


def reconcile_exact_receipt(path):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != ACCEPTED_RECEIPT_SHA256:
        raise ValueError("exact accepted R3D receipt SHA256 required")
    return reconcile_reported_total_damping(json.loads(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(REPO_ROOT) or not output.parent.is_dir():
        raise ValueError("new output outside repository required")
    result = reconcile_exact_receipt(args.receipt)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ("status", "RSX_R_CQC", "RSY_R_CQC", "RSX_V_CQC", "RSY_V_CQC",
                                            "CURRENT_UNCRACKED_B5", "R2_RERUN_READY")}))


if __name__ == "__main__":
    raise SystemExit(main())
