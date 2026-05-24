from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


def _reason_code(raw: Dict[str, Any]) -> str:
    note = str(raw.get("note") or raw.get("message") or "").lower()
    status = str(raw.get("status") or "").upper()
    ratio = _safe_float(raw.get("ratio"), 0.0)
    sum_mrc = _safe_float(raw.get("sum_mrc_knm"), 0.0)
    sum_mrb = _safe_float(raw.get("sum_mrb_knm"), 0.0)

    if "no valid column" in note or "column moment capacity" in note and sum_mrc <= 0:
        return "missing_column_capacity"
    if "no valid beam" in note or "beam moment capacity" in note and sum_mrb <= 0:
        return "missing_beam_capacity"
    if "non_design" in note or "non-design" in note:
        return "non_design_frame"
    if sum_mrc <= 0 and status == "NO_DATA":
        return "zero_Mrc"
    if sum_mrb <= 0 and status == "NO_DATA":
        return "zero_Mrb"
    if "approx" in note or str(raw.get("evaluation_level") or "").upper() == "APPROXIMATE":
        return "approximate_capacity"
    if "screening" in note or "fallback" in note:
        return "screening_fallback"
    if status == "OK" and ratio >= 1.0:
        return "scwb_ok"
    if status == "FAIL" or (ratio > 0 and ratio < 1.0):
        return "scwb_ratio_below_limit"
    return "scwb_evaluated"


def _project_scwb_result(raw: Dict[str, Any], *, projection: str) -> Dict[str, Any]:
    joint_id = str(raw.get("joint_id") or raw.get("joint") or "").strip()
    story = str(raw.get("story") or "").strip()
    direction = str(raw.get("direction") or "GLOBAL").strip() or "GLOBAL"
    columns = _as_list(raw.get("columns"))
    beams = _as_list(raw.get("beams"))
    ratio = _safe_float(raw.get("ratio"), 0.0)
    sum_mrc = _safe_float(raw.get("sum_mrc_knm"), 0.0)
    sum_mrb = _safe_float(raw.get("sum_mrb_knm"), 0.0)
    required = _safe_float(raw.get("required_mrc_knm"), 0.0)
    status = str(raw.get("status") or "NO_DATA").upper()
    evaluation_level = str(raw.get("evaluation_level") or "NO_DATA").upper()
    note = str(raw.get("note") or "").strip()
    reason = _reason_code(raw)

    if projection == "column":
        element_label = joint_id or (columns[0] if columns else "")
        label_part = f"joint={joint_id}; columns={','.join(columns) or '-'}; beams={','.join(beams) or '-'}"
        action = "Verify connected beams, final column rebar and PMM-based column capacity." if status in {"NO_DATA", "WARNING"} else ""
    else:
        element_label = joint_id or (beams[0] if beams else "")
        label_part = f"joint={joint_id}; beams={','.join(beams) or '-'}; columns={','.join(columns) or '-'}"
        action = "Verify beam end capacities and remove non-design frames from SCWB projection." if status in {"NO_DATA", "WARNING"} else ""

    message = (
        f"SCWB {projection} projection: {label_part}; dir={direction}; "
        f"ΣMrc={sum_mrc:.3f} kNm; ΣMrb={sum_mrb:.3f} kNm; "
        f"required=1.2ΣMrb={required:.3f} kNm; ratio={ratio:.3f}; "
        f"reason_code={reason}; source=scwb_resolver"
    )
    if note:
        message += f"; note={note}"

    return {
        "element_label": element_label,
        "story": story,
        "status": status,
        "ratio": ratio,
        "value": sum_mrc,
        "limit": required,
        "unit": "kNm",
        "message": message,
        "action": action,
        "evaluation_level": evaluation_level,
        "source": "scwb_resolver",
        "reason_code": reason,
        "joint_id": joint_id,
        "direction": direction,
        "columns": columns,
        "beams": beams,
        "sum_mrc_knm": sum_mrc,
        "sum_mrb_knm": sum_mrb,
        "required_mrc_knm": required,
    }


def _build_projection(raw_results: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    column_details: List[Dict[str, Any]] = []
    beam_details: List[Dict[str, Any]] = []
    for raw in raw_results:
        if not isinstance(raw, dict):
            continue
        column_details.append(_project_scwb_result(raw, projection="column"))
        beam_details.append(_project_scwb_result(raw, projection="beam"))
    return column_details, beam_details


class ScwbProjectionModule:
    """
    V2 projection wrapper for existing ScwbResolver.

    It does not change engineering calculations. It only projects joint/direction
    SCWB package results into the regular CheckAdapter fields used by:
      - column_capacity_hierarchy
      - beam_capacity_hierarchy
    """

    def __init__(self, ctx: Any):
        self.ctx = ctx

    def run(self) -> Dict[str, Any]:
        try:
            from tbdy_engine.design.joints.scwb import ScwbResolver

            package = ScwbResolver(self.ctx).evaluate()
        except Exception as exc:
            message = f"SCWB projection failed: {type(exc).__name__}: {exc}"
            fallback = {
                "element_label": "SCWB",
                "story": "",
                "status": "ERROR",
                "ratio": 0.0,
                "value": 0.0,
                "limit": 0.0,
                "unit": "kNm",
                "message": message,
                "evaluation_level": "ERROR",
                "source": "scwb_projection_error",
                "action": "Inspect ScwbResolver and topology inputs.",
            }
            return {
                "status": "ERROR",
                "summary": {"package_status": "ERROR", "total_joints": 0},
                "column_capacity_hierarchy": [fallback],
                "beam_capacity_hierarchy": [fallback],
                "raw_results": [],
                "error": message,
            }

        raw_results = package.get("results", []) or [] if isinstance(package, dict) else []
        column_details, beam_details = _build_projection(raw_results)
        summary = package.get("summary", {}) if isinstance(package, dict) else {}
        package_status = summary.get("package_status") or ("WARNING" if raw_results else "NO_DATA")

        if not raw_results:
            no_data = {
                "element_label": "SCWB",
                "story": "",
                "status": "NO_DATA",
                "ratio": 0.0,
                "value": 0.0,
                "limit": 0.0,
                "unit": "kNm",
                "message": "SCWB resolver produced no joint/direction results; reason_code=no_scwb_results; source=scwb_resolver",
                "evaluation_level": "NO_DATA",
                "source": "scwb_resolver",
                "action": "Inspect topology.joints, connected beams/columns and capacity extraction.",
            }
            column_details = [dict(no_data)]
            beam_details = [dict(no_data)]

        return {
            "status": package_status,
            "summary": summary,
            "column_capacity_hierarchy": column_details,
            "beam_capacity_hierarchy": beam_details,
            "raw_results": raw_results,
            "beam_capacity_count": package.get("beam_capacity_count", 0) if isinstance(package, dict) else 0,
            "column_capacity_count": package.get("column_capacity_count", 0) if isinstance(package, dict) else 0,
        }
