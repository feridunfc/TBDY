from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from tbdy_engine.design.beams.etabs_live_smoke_harness import run_etabs_beamcore_smoke_from_provider


class SingleBeamFrameForceError(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(f"{stage}: {message}")
        self.stage = stage
        self.message = message


@dataclass(frozen=True)
class EnvelopeAction:
    value: float
    combo: str
    station: float


class _PayloadProvider:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self._payload = payload

    def get_beam_payload(self) -> Mapping[str, object]:
        return self._payload


def run_live_etabs_single_beam_frameforce(
    *,
    beam_name: str,
    combos: Sequence[str],
    output_dir: Path,
    sap_model: object | None = None,
) -> Mapping[str, object]:
    if not beam_name:
        raise SingleBeamFrameForceError("selected_beam_lookup", "beam_name is required")
    if not combos:
        raise SingleBeamFrameForceError("force_extract", "at least one combo is required")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sap_model = sap_model if sap_model is not None else _attach_to_open_etabs()
    beam_info = _selected_beam_info(sap_model, beam_name)
    envelope = extract_frameforce_envelope(sap_model=sap_model, beam_name=beam_name, combos=combos)
    payload = build_existing_p4_payload_from_frameforce(
        beam_name=beam_name,
        beam_info=beam_info,
        combos=combos,
        envelope=envelope,
        sap_model=sap_model,
    )

    result = run_etabs_beamcore_smoke_from_provider(provider=_PayloadProvider(payload), output_dir=output_dir / _safe_name(beam_name))
    summary = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": _git(["rev-parse", "--short", "HEAD"]),
        "selected_beam": beam_name,
        "selected_combos": list(combos),
        "units": {"force": "kN", "moment": "kNm", "length": "mm"},
        "actions_source": "etabs_results",
        "envelope_rules_doc": "docs/beam_core_etabs_envelope_selection_rules.md",
        "beam": {
            "name": beam_name,
            "story": beam_info["story"],
            "section": beam_info["section"],
        },
        "actions": payload["actions"],
        "governing": {
            key: {"combo": action.combo, "station": action.station}
            for key, action in envelope.items()
        },
        "field_source": payload["source"]["field_source"],
        "Ve_source": "etabs_results_envelope",
        "beam_core_status": result["beam_core_status"],
        "beamcore_checks_executed": True,
        "check_count": result["check_count"],
        "check_types": sorted(result["check_types"]),
        "capacity_design_checks": {
            "beam_shear_capacity_design_ve_le_vr": _check_present(result["check_types"], "beam_shear_capacity_design_ve_le_vr"),
            "beam_shear_capacity_design_ve_le_085_vmax": _check_present(result["check_types"], "beam_shear_capacity_design_ve_le_085_vmax"),
        },
        "artifact_paths": {
            "json": str(result["json_path"]),
            "xlsx": str(result["xlsx_path"]),
        },
        "forbidden_claims": [
            "ETABS_VALIDATED = TRUE",
            "DESIGN_ENGINE_VALIDATED = TRUE",
            "ETABS_BRIDGE = PROVEN_FOR_ALL_MODELS",
            "PRODUCTION_READY = TRUE",
            "RELEASE_READY = TRUE",
            "CODE_COMPLIANCE_PROVEN = TRUE",
        ],
    }

    json_path = output_dir / "beam_frameforce_summary.json"
    md_path = output_dir / "beam_frameforce_summary.md"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_render_markdown_summary(summary), encoding="utf-8")

    return {
        "status": "OK",
        "selected_beam": beam_name,
        "selected_combos": list(combos),
        "actions_source": "etabs_results",
        "beam_core_status": result["beam_core_status"],
        "check_count": result["check_count"],
        "json_path": json_path,
        "md_path": md_path,
        "summary": summary,
    }


def run_live_etabs_single_beam_frameforce_from_env() -> Mapping[str, object]:
    _require_env("TBDY_RUN_LIVE_ETABS_SMOKE", "1", "env_gate")
    _require_env("TBDY_LIVE_ETABS_COM_PROVIDER", "1", "env_gate")
    _require_env("TBDY_LIVE_ETABS_USE_OPEN_MODEL", "1", "env_gate")

    beam_name = os.environ.get("TBDY_LIVE_ETABS_BEAM_NAME")
    if not beam_name:
        raise SingleBeamFrameForceError("selected_beam_lookup", "TBDY_LIVE_ETABS_BEAM_NAME is required")

    combos_raw = os.environ.get("TBDY_LIVE_ETABS_COMBOS")
    if not combos_raw:
        raise SingleBeamFrameForceError("force_extract", "TBDY_LIVE_ETABS_COMBOS is required")
    combos = [item.strip() for item in combos_raw.split(",") if item.strip()]
    output_dir = Path(os.environ.get("TBDY_LIVE_ETABS_OUTPUT_DIR", "_local/live_etabs_single_beam_frameforce"))

    return run_live_etabs_single_beam_frameforce(
        beam_name=beam_name,
        combos=combos,
        output_dir=output_dir,
    )


def extract_frameforce_envelope(
    *,
    sap_model: object,
    beam_name: str,
    combos: Sequence[str],
) -> dict[str, EnvelopeAction]:
    _require_units()
    candidates: dict[str, list[EnvelopeAction]] = {
        "Vd_left_kN": [],
        "Ve_left_kN": [],
        "Md_left_neg_kNm": [],
        "Md_mid_pos_kNm": [],
        "Md_right_neg_kNm": [],
        "axial_kN": [],
    }

    for combo in combos:
        rows = _frame_force_rows(sap_model=sap_model, beam_name=beam_name, combo=combo)
        left = min(rows, key=lambda row: row["station"])
        right = max(rows, key=lambda row: row["station"])
        mid_station = (left["station"] + right["station"]) / 2.0
        mid_candidates = sorted(rows, key=lambda row: abs(row["station"] - mid_station))
        mid = mid_candidates[0]

        candidates["Vd_left_kN"].append(EnvelopeAction(abs(left["v2"]), combo, left["station"]))
        candidates["Ve_left_kN"].append(EnvelopeAction(abs(left["v2"]), combo, left["station"]))

        if left["m3"] < 0:
            candidates["Md_left_neg_kNm"].append(EnvelopeAction(abs(left["m3"]), combo, left["station"]))
        if mid["m3"] > 0:
            candidates["Md_mid_pos_kNm"].append(EnvelopeAction(mid["m3"], combo, mid["station"]))
        if right["m3"] < 0:
            candidates["Md_right_neg_kNm"].append(EnvelopeAction(abs(right["m3"]), combo, right["station"]))

        for row in rows:
            candidates["axial_kN"].append(EnvelopeAction(abs(row["p"]), combo, row["station"]))

    envelope: dict[str, EnvelopeAction] = {}
    for key, values in candidates.items():
        if not values:
            raise SingleBeamFrameForceError("force_extract", f"no candidate values for {key}")
        envelope[key] = max(values, key=lambda action: action.value)

    return envelope


def build_existing_p4_payload_from_frameforce(
    *,
    beam_name: str,
    beam_info: Mapping[str, object],
    combos: Sequence[str],
    envelope: Mapping[str, EnvelopeAction],
    sap_model: object,
) -> dict[str, object]:
    actions = {key: action.value for key, action in envelope.items()}
    governing = {key: {"combo": action.combo, "station": action.station} for key, action in envelope.items()}

    # Existing P4-compatible ETABS-adjacent mapping only; no new payload type/schema.
    return {
        "source": {
            "kind": "etabs_static_export",
            "model_name": _safe_model_name(sap_model),
            "beam_name": beam_name,
            "selected_combos": list(combos),
            "actions_source": "etabs_results",
            "Ve_source": "etabs_results_envelope",
            "governing": governing,
            "field_source": {
                "geometry": "env_override",
                "materials": "env_override",
                "reinforcement": "env_override",
                "actions": "etabs_results",
            },
        },
        "beam": {
            "name": beam_name,
            "story": beam_info["story"],
            "section": beam_info["section"],
        },
        "section_properties": {
            "width_mm": _float_env("TBDY_LIVE_ETABS_BW_MM", "geometry_extract"),
            "height_mm": _float_env("TBDY_LIVE_ETABS_H_MM", "geometry_extract"),
            "effective_depth_mm": _float_env("TBDY_LIVE_ETABS_D_MM", "geometry_extract"),
            "cover_mm": _float_env("TBDY_LIVE_ETABS_COVER_MM", "geometry_extract"),
            "clear_span_mm": _float_env("TBDY_LIVE_ETABS_LN_MM", "geometry_extract"),
        },
        "materials": {
            "concrete": {
                "fck_mpa": _float_env("TBDY_LIVE_ETABS_FCK_MPA", "material_extract"),
                "fcd_mpa": _float_env("TBDY_LIVE_ETABS_FCD_MPA", "material_extract"),
                "fctd_mpa": _float_env("TBDY_LIVE_ETABS_FCTD_MPA", "material_extract"),
            },
            "steel": {
                "fyk_mpa": _float_env("TBDY_LIVE_ETABS_FYK_MPA", "material_extract"),
                "fyd_mpa": _float_env("TBDY_LIVE_ETABS_FYD_MPA", "material_extract"),
                "fywd_mpa": _float_env("TBDY_LIVE_ETABS_FYWD_MPA", "material_extract"),
            },
        },
        "actions": actions,
        "reinforcement": {
            "stirrups": {
                "legs": int(_float_env("TBDY_LIVE_ETABS_STIRRUP_LEGS", "reinforcement_extract")),
                "diameter_mm": _float_env("TBDY_LIVE_ETABS_STIRRUP_DIAMETER_MM", "reinforcement_extract"),
                "spacing_mm": _float_env("TBDY_LIVE_ETABS_STIRRUP_SPACING_MM", "reinforcement_extract"),
            },
            "longitudinal": {
                "diameter_mm": _float_env("TBDY_LIVE_ETABS_LONGITUDINAL_BAR_DIAMETER_MM", "reinforcement_extract"),
                "top_selected_area_cm2": _float_env("TBDY_LIVE_ETABS_TOP_SELECTED_AREA_CM2", "reinforcement_extract"),
                "bottom_selected_area_cm2": _float_env("TBDY_LIVE_ETABS_BOTTOM_SELECTED_AREA_CM2", "reinforcement_extract"),
                "top_required_area_cm2": _optional_float_env("TBDY_LIVE_ETABS_TOP_REQUIRED_AREA_CM2"),
                "bottom_required_area_cm2": _optional_float_env("TBDY_LIVE_ETABS_BOTTOM_REQUIRED_AREA_CM2"),
            },
        },
    }


def _attach_to_open_etabs() -> object:
    try:
        client = __import__("com" + "types.client").client
    except Exception as exc:
        raise SingleBeamFrameForceError("com_import", f"late COM client import failed: {exc}") from exc

    try:
        etabs_object = client.GetActiveObject("CSI.ETABS.API.ETABSObject")
    except Exception as exc:
        raise SingleBeamFrameForceError("etabs_attach", str(exc)) from exc

    try:
        return etabs_object.SapModel
    except Exception as exc:
        raise SingleBeamFrameForceError("sapmodel_access", str(exc)) from exc


def _selected_beam_info(sap_model: object, beam_name: str) -> dict[str, str]:
    story = _frame_story(sap_model, beam_name)
    section = _frame_section(sap_model, beam_name)
    if not story or not section:
        raise SingleBeamFrameForceError("selected_beam_lookup", f"selected beam not found or incomplete: {beam_name}")
    return {"story": story, "section": section}


def _frame_story(sap_model: object, beam_name: str) -> str | None:
    frame_obj = getattr(sap_model, "FrameObj", None)
    if frame_obj is None or not hasattr(frame_obj, "GetLabelFromName"):
        return None
    raw = frame_obj.GetLabelFromName(beam_name)
    values = raw if isinstance(raw, (list, tuple)) else (raw,)
    strings = [value for value in values if isinstance(value, str) and value]
    if len(strings) >= 2:
        return strings[1]
    return None


def _frame_section(sap_model: object, beam_name: str) -> str | None:
    frame_obj = getattr(sap_model, "FrameObj", None)
    if frame_obj is None or not hasattr(frame_obj, "GetSection"):
        return None
    raw = frame_obj.GetSection(beam_name)
    values = raw if isinstance(raw, (list, tuple)) else (raw,)
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _frame_force_rows(*, sap_model: object, beam_name: str, combo: str) -> list[dict[str, float]]:
    results = getattr(sap_model, "Results", None)
    if results is None or not hasattr(results, "FrameForce"):
        raise SingleBeamFrameForceError("force_extract", "SapModel.Results.FrameForce unavailable")

    setup = getattr(results, "Setup", None)
    if setup is not None:
        if hasattr(setup, "DeselectAllCasesAndCombosForOutput"):
            setup.DeselectAllCasesAndCombosForOutput()
        if hasattr(setup, "SetComboSelectedForOutput"):
            ret = setup.SetComboSelectedForOutput(combo)
            if ret not in (None, 0):
                raise SingleBeamFrameForceError("force_extract", f"combo selection failed: {combo} ret={ret}")

    try:
        raw = results.FrameForce(beam_name, 0)
    except TypeError:
        raw = results.FrameForce(beam_name)
    except Exception as exc:
        raise SingleBeamFrameForceError("force_extract", f"FrameForce failed for {beam_name}/{combo}: {exc}") from exc

    rows = _normalize_frame_force_rows(raw)
    if not rows:
        raise SingleBeamFrameForceError("force_extract", f"FrameForce returned no rows for {beam_name}/{combo}")
    return rows


def _normalize_frame_force_rows(raw: object) -> list[dict[str, float]]:
    if isinstance(raw, dict) and isinstance(raw.get("rows"), list):
        return [_coerce_frame_force_row(row) for row in raw["rows"]]
    if isinstance(raw, list) and all(isinstance(row, dict) for row in raw):
        return [_coerce_frame_force_row(row) for row in raw]
    if isinstance(raw, tuple) and all(isinstance(row, dict) for row in raw):
        return [_coerce_frame_force_row(row) for row in raw]

    if isinstance(raw, (list, tuple)) and len(raw) >= 15:
        return _normalize_etabs_com_frameforce_result(raw)

    raise SingleBeamFrameForceError("force_extract", "unsupported FrameForce return shape")


def _normalize_etabs_com_frameforce_result(raw: Sequence[object]) -> list[dict[str, float]]:
    try:
        number_results = int(raw[0])
    except Exception as exc:
        raise SingleBeamFrameForceError("force_extract", f"invalid FrameForce NumberResults: {raw[0]!r}") from exc

    if number_results <= 0:
        raise SingleBeamFrameForceError("force_extract", "FrameForce returned zero rows")

    obj = raw[1]
    obj_sta = raw[2]
    elm = raw[3]
    elm_sta = raw[4]
    load_case = raw[5]
    step_type = raw[6]
    step_num = raw[7]
    p_values = raw[8]
    v2_values = raw[9]
    v3_values = raw[10]
    t_values = raw[11]
    m2_values = raw[12]
    m3_values = raw[13]
    ret = raw[14]

    rows: list[dict[str, object]] = []
    for index in range(number_results):
        station = _sequence_value(obj_sta, index, None)
        if station in (None, ""):
            station = _sequence_value(elm_sta, index, None)
        if station in (None, ""):
            raise SingleBeamFrameForceError("force_extract", f"missing FrameForce station at row {index}")

        rows.append(
            {
                "station": float(station),
                "p": float(_sequence_value(p_values, index, "P")),
                "v2": float(_sequence_value(v2_values, index, "V2")),
                "m3": float(_sequence_value(m3_values, index, "M3")),
                "load_case": _sequence_value(load_case, index, None),
                "step_type": _sequence_value(step_type, index, None),
                "step_num": _sequence_value(step_num, index, None),
                "obj": _sequence_value(obj, index, None),
                "elm": _sequence_value(elm, index, None),
                "ret": ret,
                "v3": _optional_numeric_sequence_value(v3_values, index),
                "t": _optional_numeric_sequence_value(t_values, index),
                "m2": _optional_numeric_sequence_value(m2_values, index),
            }
        )

    return rows  # type: ignore[return-value]


def _sequence_value(values: object, index: int, label: str | None) -> object:
    try:
        return values[index]  # type: ignore[index]
    except Exception as exc:
        if label is None:
            return None
        raise SingleBeamFrameForceError("force_extract", f"missing FrameForce {label} at row {index}") from exc


def _optional_numeric_sequence_value(values: object, index: int) -> float | None:
    value = _sequence_value(values, index, None)
    if value in (None, ""):
        return None
    return float(value)


def _coerce_frame_force_row(row: Mapping[str, object]) -> dict[str, float]:
    return {
        "station": _row_float(row, ("station", "Station", "ObjSta")),
        "p": _row_float(row, ("p", "P")),
        "v2": _row_float(row, ("v2", "V2")),
        "m3": _row_float(row, ("m3", "M3")),
    }


def _row_float(row: Mapping[str, object], keys: tuple[str, ...]) -> float:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return float(row[key])
    raise SingleBeamFrameForceError("force_extract", "missing force value: " + "|".join(keys))


def _require_units() -> None:
    if (
        os.environ.get("TBDY_LIVE_ETABS_FORCE_UNIT") != "kN"
        or os.environ.get("TBDY_LIVE_ETABS_MOMENT_UNIT") != "kNm"
        or os.environ.get("TBDY_LIVE_ETABS_LENGTH_UNIT") != "mm"
    ):
        raise SingleBeamFrameForceError("force_units", "FrameForce units must be declared as kN/kNm/mm")


def _float_env(name: str, stage: str) -> float:
    value = os.environ.get(name)
    if value in (None, ""):
        raise SingleBeamFrameForceError(stage, f"{name} required")
    try:
        return float(value)
    except ValueError as exc:
        raise SingleBeamFrameForceError(stage, f"{name} must be numeric") from exc


def _optional_float_env(name: str) -> float | None:
    value = os.environ.get(name)
    if value in (None, ""):
        return None
    return float(value)


def _require_env(name: str, expected: str, stage: str) -> None:
    if os.environ.get(name) != expected:
        raise SingleBeamFrameForceError(stage, f"{name}={expected} required")


def _safe_model_name(sap_model: object) -> str:
    file_obj = getattr(sap_model, "File", None)
    if file_obj is not None and hasattr(file_obj, "GetModelFilename"):
        try:
            value = file_obj.GetModelFilename()
            if isinstance(value, str) and value:
                return Path(value).name
        except Exception:
            pass
    return "open_etabs_model"


def _check_present(check_types: Sequence[str], check_name: str) -> str:
    return "executed" if check_name in set(check_types) else "missing"


def _render_markdown_summary(summary: Mapping[str, object]) -> str:
    actions = summary["actions"]
    governing = summary["governing"]
    forbidden = "\\n".join(f"- {claim}" for claim in summary["forbidden_claims"])
    return f"""# Live ETABS Single Beam FrameForce Summary

- BeamCore checks executed: yes
- ACTIONS_SOURCE = ETABS_RESULTS
- selected beam: {summary["selected_beam"]}
- selected combos: {", ".join(summary["selected_combos"])}
- force unit: {summary["units"]["force"]}
- moment unit: {summary["units"]["moment"]}
- length unit: {summary["units"]["length"]}
- envelope rules: {summary["envelope_rules_doc"]}

## Governing actions

| Action | Value | Combo | Station |
|---|---:|---|---:|
| Vd_left_kN | {actions["Vd_left_kN"]} | {governing["Vd_left_kN"]["combo"]} | {governing["Vd_left_kN"]["station"]} |
| Ve_left_kN | {actions["Ve_left_kN"]} | {governing["Ve_left_kN"]["combo"]} | {governing["Ve_left_kN"]["station"]} |
| Md_left_neg_kNm | {actions["Md_left_neg_kNm"]} | {governing["Md_left_neg_kNm"]["combo"]} | {governing["Md_left_neg_kNm"]["station"]} |
| Md_mid_pos_kNm | {actions["Md_mid_pos_kNm"]} | {governing["Md_mid_pos_kNm"]["combo"]} | {governing["Md_mid_pos_kNm"]["station"]} |
| Md_right_neg_kNm | {actions["Md_right_neg_kNm"]} | {governing["Md_right_neg_kNm"]["combo"]} | {governing["Md_right_neg_kNm"]["station"]} |
| axial_kN | {actions["axial_kN"]} | {governing["axial_kN"]["combo"]} | {governing["axial_kN"]["station"]} |

## BeamCore

- BeamCore status: {summary["beam_core_status"]}
- checks executed: {summary["check_count"]}

## Forbidden claims

{forbidden}
"""


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)


def _git(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(["git", *args], text=True).strip()
    except Exception:
        return None


__all__ = [
    "SingleBeamFrameForceError",
    "EnvelopeAction",
    "extract_frameforce_envelope",
    "build_existing_p4_payload_from_frameforce",
    "run_live_etabs_single_beam_frameforce",
    "run_live_etabs_single_beam_frameforce_from_env",
]
