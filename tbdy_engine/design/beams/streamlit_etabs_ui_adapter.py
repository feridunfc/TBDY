from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence
from tbdy_engine.design.beams.etabs_single_beam_frameforce_runner import (
    run_live_etabs_single_beam_frameforce,
)
from tbdy_engine.design.beams.etabs_story_beam_batch_runner import (
    run_live_etabs_story_beam_batch,
)


DEFAULT_DESIGN_INPUTS: dict[str, object] = {
    "bw_mm": 600,
    "h_mm": 700,
    "d_mm": 550,
    "cover_mm": 40,
    "Ln_mm": 5000,
    "fck_mpa": 30,
    "fcd_mpa": 20,
    "fctd_mpa": 1.27,
    "fyk_mpa": 420,
    "fyd_mpa": 365,
    "fywd_mpa": 365,
    "stirrup_legs": 2,
    "stirrup_diameter_mm": 10,
    "stirrup_spacing_mm": 100,
    "longitudinal_bar_diameter_mm": 16,
    "top_selected_area_cm2": 10,
    "bottom_selected_area_cm2": 10,
    "force_unit": "kN",
    "moment_unit": "kNm",
    "length_unit": "mm",
    "output_dir": "_local/streamlit_beam_design",
}


ENV_MAP = {
    "bw_mm": "TBDY_LIVE_ETABS_BW_MM",
    "h_mm": "TBDY_LIVE_ETABS_H_MM",
    "d_mm": "TBDY_LIVE_ETABS_D_MM",
    "cover_mm": "TBDY_LIVE_ETABS_COVER_MM",
    "Ln_mm": "TBDY_LIVE_ETABS_LN_MM",
    "fck_mpa": "TBDY_LIVE_ETABS_FCK_MPA",
    "fcd_mpa": "TBDY_LIVE_ETABS_FCD_MPA",
    "fctd_mpa": "TBDY_LIVE_ETABS_FCTD_MPA",
    "fyk_mpa": "TBDY_LIVE_ETABS_FYK_MPA",
    "fyd_mpa": "TBDY_LIVE_ETABS_FYD_MPA",
    "fywd_mpa": "TBDY_LIVE_ETABS_FYWD_MPA",
    "stirrup_legs": "TBDY_LIVE_ETABS_STIRRUP_LEGS",
    "stirrup_diameter_mm": "TBDY_LIVE_ETABS_STIRRUP_DIAMETER_MM",
    "stirrup_spacing_mm": "TBDY_LIVE_ETABS_STIRRUP_SPACING_MM",
    "longitudinal_bar_diameter_mm": "TBDY_LIVE_ETABS_LONGITUDINAL_BAR_DIAMETER_MM",
    "top_selected_area_cm2": "TBDY_LIVE_ETABS_TOP_SELECTED_AREA_CM2",
    "bottom_selected_area_cm2": "TBDY_LIVE_ETABS_BOTTOM_SELECTED_AREA_CM2",
    "force_unit": "TBDY_LIVE_ETABS_FORCE_UNIT",
    "moment_unit": "TBDY_LIVE_ETABS_MOMENT_UNIT",
    "length_unit": "TBDY_LIVE_ETABS_LENGTH_UNIT",
}


@dataclass(frozen=True)
class EtabsStatus:
    status: str
    stage: str | None = None
    message: str | None = None
    model_name: str | None = None
    sap_model: object | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "stage": self.stage,
            "message": self.message,
            "model_name": self.model_name,
            "sap_model": self.sap_model,
        }


def attach_to_open_etabs() -> object:
    try:
        client = __import__("com" + "types.client").client
    except Exception as exc:
        raise RuntimeError(f"com_import: {exc}") from exc

    try:
        etabs_object = client.GetActiveObject("CSI.ETABS.API.ETABSObject")
    except Exception as exc:
        raise RuntimeError(f"etabs_attach: {exc}") from exc

    try:
        return etabs_object.SapModel
    except Exception as exc:
        raise RuntimeError(f"sapmodel_access: {exc}") from exc


def get_etabs_status(*, sap_model: object | None = None) -> dict[str, object]:
    if sap_model is None:
        try:
            sap_model = attach_to_open_etabs()
        except RuntimeError as exc:
            message = str(exc)
            stage = message.split(":", 1)[0] if ":" in message else "etabs_attach"
            if stage == "sapmodel_access":
                return EtabsStatus(status="ERROR", stage=stage, message=message).as_dict()
            return EtabsStatus(status="OFFLINE", stage=stage, message=message).as_dict()

    return EtabsStatus(status="ONLINE", model_name=get_model_name(sap_model), sap_model=sap_model).as_dict()


def get_model_name(sap_model: object) -> str:
    file_obj = getattr(sap_model, "File", None)
    if file_obj is not None and hasattr(file_obj, "GetModelFilename"):
        try:
            value = file_obj.GetModelFilename()
            if isinstance(value, str) and value:
                return Path(value).name
            if isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, str) and item:
                        return Path(item).name
        except Exception:
            pass
    return "open_etabs_model"


def list_story_beams(sap_model: object, story: str, *, include_non_beams: bool = True) -> list[dict[str, str]]:
    names = _frame_names(sap_model)
    beams: list[dict[str, str]] = []
    for object_name in names:
        label, beam_story = _frame_label_and_story(sap_model, object_name)
        if beam_story != story:
            continue
        section = _frame_section(sap_model, object_name)
        record = {
            "object_name": object_name,
            "label": label or object_name,
            "story": beam_story or "",
            "section": section or "",
        }
        record.update(classify_frame_element(record))
        beams.append(record)
    return beams if include_non_beams else filter_beam_candidates(beams, include_non_beams=False)


def list_available_stories(sap_model: object) -> list[str]:
    stories = {beam["story"] for name in _frame_names(sap_model) for beam in [_beam_record(sap_model, name)] if beam["story"]}
    return sorted(stories)


def list_available_combos(sap_model: object) -> list[str]:
    combos = _name_list_from_object(getattr(sap_model, "RespCombo", None), "GetNameList")
    return combos


def list_available_load_cases(sap_model: object) -> list[str]:
    return _name_list_from_object(getattr(sap_model, "LoadCases", None), "GetNameList")


def choose_default_combos(combos: Sequence[str]) -> list[str]:
    preferred = [combo for combo in ("Grav_Ult", "Cap_SeisX") if combo in combos]
    if preferred:
        return preferred
    return list(combos[:2])


def classify_frame_element(record: Mapping[str, object]) -> dict[str, str]:
    label = str(record.get("label") or "")
    section = str(record.get("section") or "")
    label_upper = label.upper()
    section_upper = section.upper()

    if label_upper.startswith("C") or "COLUMN" in section_upper:
        element_type = "column"
        source = "label_or_section"
    elif label_upper.startswith("B") or section_upper.startswith("B"):
        element_type = "beam"
        source = "label_or_section"
    else:
        element_type = "unknown"
        source = "label_or_section"

    warning = ""
    if element_type == "column":
        warning = "Probable column — excluded from BeamCore beam checks by default."
    elif element_type == "unknown":
        warning = "Unknown frame object type — excluded from BeamCore beam checks by default."

    return {
        "element_type": element_type,
        "classification_source": source,
        "classification_warning": warning,
    }


def filter_beam_candidates(
    records: Sequence[Mapping[str, str]],
    *,
    include_non_beams: bool = False,
    section_filter: str = "",
    label_filter: str = "",
) -> list[dict[str, str]]:
    section_filter_l = section_filter.strip().lower()
    label_filter_l = label_filter.strip().lower()
    result: list[dict[str, str]] = []

    for record in records:
        enriched = dict(record)
        if "element_type" not in enriched:
            enriched.update(classify_frame_element(enriched))
        if not include_non_beams and enriched.get("element_type") != "beam":
            continue
        if section_filter_l and section_filter_l not in str(enriched.get("section", "")).lower():
            continue
        if label_filter_l and label_filter_l not in str(enriched.get("label", "")).lower():
            continue
        result.append(enriched)

    return result


def add_selection_column(
    records: Sequence[Mapping[str, str]],
    *,
    selected_object_names: Sequence[str] | None = None,
    select_all: bool = False,
) -> list[dict[str, object]]:
    selected = set(selected_object_names or [])
    rows: list[dict[str, object]] = []
    for record in records:
        object_name = str(record.get("object_name", ""))
        row = dict(record)
        row["selected"] = bool(select_all or object_name in selected)
        rows.append(row)
    return rows


def filter_selected_beams(beams: Sequence[Mapping[str, str]], selected_object_names: Sequence[str] | None) -> list[dict[str, str]]:
    if not selected_object_names:
        return [dict(beam) for beam in beams]
    selected = set(selected_object_names)
    return [dict(beam) for beam in beams if beam.get("object_name") in selected]


def build_design_overrides_from_ui(values: Mapping[str, object]) -> dict[str, str]:
    merged = {**DEFAULT_DESIGN_INPUTS, **dict(values)}
    return {env_name: str(merged[key]) for key, env_name in ENV_MAP.items()}


def apply_design_overrides_to_environment(overrides: Mapping[str, str]) -> None:
    for key, value in overrides.items():
        os.environ[key] = str(value)


def run_story_beam_checks_from_ui(
    *,
    sap_model: object,
    story: str,
    combos: Sequence[str],
    selected_object_names: Sequence[str] | None,
    design_values: Mapping[str, object],
    output_dir: Path,
    max_beams: int = 10,
) -> dict[str, object]:
    combos = [combo for combo in combos if combo]
    if not combos:
        raise ValueError("At least one result combination is required.")
    beams = list_story_beams(sap_model, story, include_non_beams=True)
    beam_candidates = filter_beam_candidates(beams, include_non_beams=False)
    selected = filter_selected_beams(beam_candidates, selected_object_names)
    if not selected:
        raise ValueError("At least one beam must be selected.")

    selected_names = [beam["object_name"] for beam in selected[:max_beams]]
    filtered_sap_model = _StoryBeamSubsetSapModel(sap_model=sap_model, allowed_object_names=selected_names)
    overrides = build_design_overrides_from_ui(design_values)
    apply_design_overrides_to_environment(overrides)

    if len(combos) == 1:
        return run_single_combo_beam_checks_from_ui(
            sap_model=filtered_sap_model,
            story=story,
            combo=combos[0],
            selected_beams=selected[:max_beams],
            output_dir=Path(output_dir),
        )

    return dict(
        run_live_etabs_story_beam_batch(
            story=story,
            combos=list(combos),
            output_dir=Path(output_dir),
            sap_model=filtered_sap_model,
            min_beams=1,
            max_beams=max_beams,
        )
    )


def run_single_combo_beam_checks_from_ui(
    *,
    sap_model: object,
    story: str,
    combo: str,
    selected_beams: Sequence[Mapping[str, str]],
    output_dir: Path,
) -> dict[str, object]:
    """Run UI diagnostic checks for one combo without weakening R7B acceptance rules."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    processed: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for beam in selected_beams:
        object_name = str(beam["object_name"])
        try:
            result = run_live_etabs_single_beam_frameforce(
                beam_name=object_name,
                combos=[combo],
                output_dir=output_dir / _safe_name(object_name),
                sap_model=sap_model,
            )
            single_summary = result.get("summary", {})
            processed.append(
                {
                    "object_name": object_name,
                    "label": beam.get("label", object_name),
                    "story": beam.get("story", story),
                    "section": beam.get("section", ""),
                    "actions_source": "etabs_results",
                    "Ve_source": "single_combo_frameforce",
                    "actions": single_summary.get("actions", {}),
                    "governing": single_summary.get("governing", {}),
                    "BeamCoreResult produced": True,
                    "BeamCore checks executed": True,
                    "beam_core_status": result.get("beam_core_status"),
                    "check_count": result.get("check_count"),
                    "capacity_design_check_statuses": single_summary.get("capacity_design_checks", {}),
                    "artifact_paths": {
                        "json": str((single_summary.get("artifact_paths") or {}).get("json") or ""),
                        "xlsx": str((single_summary.get("artifact_paths") or {}).get("xlsx") or ""),
                    },
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "object_name": object_name,
                    "label": beam.get("label", object_name),
                    "story": beam.get("story", story),
                    "stage": getattr(exc, "stage", "single_combo_frameforce"),
                    "error": str(exc),
                }
            )

    summary = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "selected_story": story,
        "selected_combos": [combo],
        "selected_combos_count": 1,
        "run_mode": "SINGLE_COMBO_FRAMEFORCE_CHECKS_EXECUTED",
        "action_envelope_selection": "single_combo_no_multi_combo_envelope",
        "actions_source": "etabs_results",
        "beam_count_discovered": len(selected_beams),
        "beam_count_processed": len(processed),
        "beam_count_failed": len(failures),
        "BeamCore checks executed": bool(processed),
        "beams": processed,
        "failures": failures,
        "note": "UI diagnostic single-combo run. R7B live acceptance still requires at least two combos.",
    }

    json_path = output_dir / "streamlit_single_combo_summary.json"
    md_path = output_dir / "streamlit_single_combo_summary.md"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_render_single_combo_markdown(summary), encoding="utf-8")

    return {
        "status": "OK" if processed else "FAIL",
        "selected_story": story,
        "selected_combos": [combo],
        "selected_combos_count": 1,
        "run_mode": "SINGLE_COMBO_FRAMEFORCE_CHECKS_EXECUTED",
        "actions_source": "etabs_results",
        "beam_count_discovered": len(selected_beams),
        "beam_count_processed": len(processed),
        "beam_count_failed": len(failures),
        "json_path": json_path,
        "md_path": md_path,
        "summary": summary,
    }


def shape_result_rows_for_ui(summary: Mapping[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for beam in summary.get("beams", []):  # type: ignore[union-attr]
        actions = beam.get("actions", {})
        governing = beam.get("governing", {})
        most_critical = beam.get("most_critical_checks", [])
        top_critical = most_critical[0] if most_critical else {}
        rows.append(
            {
                "object_name": beam.get("object_name"),
                "label": beam.get("label"),
                "section": beam.get("section"),
                "element_type": beam.get("element_type") or classify_frame_element(beam).get("element_type"),
                "BeamCore status": beam.get("beam_core_status") or beam.get("BeamCore status"),
                "Vd_left_kN": actions.get("Vd_left_kN"),
                "Ve_left_kN": actions.get("Ve_left_kN"),
                "Md_left_neg_kNm": actions.get("Md_left_neg_kNm"),
                "Md_mid_pos_kNm": actions.get("Md_mid_pos_kNm"),
                "Md_right_neg_kNm": actions.get("Md_right_neg_kNm"),
                "axial_kN": actions.get("axial_kN"),
                "governing_Vd_combo": (governing.get("Vd_left_kN") or {}).get("combo"),
                "governing_Ve_combo": (governing.get("Ve_left_kN") or {}).get("combo"),
                "governing_Md_left_combo": (governing.get("Md_left_neg_kNm") or {}).get("combo"),
                "governing_Md_mid_combo": (governing.get("Md_mid_pos_kNm") or {}).get("combo"),
                "governing_Md_right_combo": (governing.get("Md_right_neg_kNm") or {}).get("combo"),
                "failed_check_count": beam.get("failed_check_count"),
                "critical_category": top_critical.get("category") if isinstance(top_critical, Mapping) else None,
                "top_critical_check": top_critical.get("check_key") if isinstance(top_critical, Mapping) else None,
                "check_count": beam.get("check_count"),
                "json path": (beam.get("artifact_paths") or {}).get("json"),
                "xlsx path": (beam.get("artifact_paths") or {}).get("xlsx"),
            }
        )
    return rows


def read_check_rows_for_ui(engine_report_path: Path) -> list[dict[str, object]]:
    try:
        from tbdy_engine.design.beams.beam_core_failure_diagnosis import extract_check_records, normalize_check_record
    except Exception:
        return []

    if not Path(engine_report_path).exists():
        return []

    import json

    report = json.loads(Path(engine_report_path).read_text(encoding="utf-8"))
    return [
        {
            "check_key": check.get("check_key"),
            "status": check.get("status"),
            "category": check.get("category"),
            "demand": check.get("demand"),
            "capacity": check.get("capacity"),
            "utilization": check.get("utilization"),
            "message": check.get("message"),
        }
        for check in (normalize_check_record(record) for record in extract_check_records(report))
    ]


def branch_and_commit() -> dict[str, str | None]:
    return {
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": _git(["rev-parse", "--short", "HEAD"]),
    }


class _StoryBeamSubsetSapModel:
    def __init__(self, *, sap_model: object, allowed_object_names: Sequence[str]) -> None:
        self._sap_model = sap_model
        self.FrameObj = _SubsetFrameObj(getattr(sap_model, "FrameObj"), allowed_object_names)
        self.Results = getattr(sap_model, "Results", None)
        self.File = getattr(sap_model, "File", None)


class _SubsetFrameObj:
    def __init__(self, frame_obj: object, allowed_object_names: Sequence[str]) -> None:
        self._frame_obj = frame_obj
        self._allowed = list(allowed_object_names)

    def GetNameList(self) -> tuple[int, list[str], int]:
        return (len(self._allowed), self._allowed, 0)

    def GetLabelFromName(self, name: str) -> object:
        return self._frame_obj.GetLabelFromName(name)

    def GetSection(self, name: str) -> object:
        return self._frame_obj.GetSection(name)


def _render_single_combo_markdown(summary: Mapping[str, object]) -> str:
    lines = [
        "# Streamlit single-combo FrameForce diagnostic summary",
        "",
        "SINGLE_COMBO_FRAMEFORCE_CHECKS_EXECUTED",
        "",
        f"- selected story: {summary['selected_story']}",
        f"- selected combos: {summary['selected_combos']}",
        f"- selected_combos_count: {summary['selected_combos_count']}",
        f"- action_envelope_selection: {summary['action_envelope_selection']}",
        f"- actions_source: {summary['actions_source']}",
        f"- beam_count_processed: {summary['beam_count_processed']}",
        f"- beam_count_failed: {summary['beam_count_failed']}",
        "",
        "| Object | Label | Story | Section | BeamCore status | Check count |",
        "|---|---|---|---|---|---:|",
    ]
    for beam in summary["beams"]:
        lines.append(
            f"| {beam['object_name']} | {beam['label']} | {beam['story']} | {beam['section']} | "
            f"{beam['beam_core_status']} | {beam['check_count']} |"
        )
    if summary["failures"]:
        lines.extend(["", "## Failures", ""])
        for failure in summary["failures"]:
            lines.append(f"- {failure['object_name']}: {failure['stage']} — {failure['error']}")
    lines.append("")
    return "\n".join(lines)


def _beam_record(sap_model: object, object_name: str) -> dict[str, str]:
    label, story = _frame_label_and_story(sap_model, object_name)
    return {
        "object_name": object_name,
        "label": label or object_name,
        "story": story or "",
        "section": _frame_section(sap_model, object_name) or "",
    }


def _frame_names(sap_model: object) -> list[str]:
    frame_obj = getattr(sap_model, "FrameObj", None)
    if frame_obj is None or not hasattr(frame_obj, "GetNameList"):
        return []
    raw = frame_obj.GetNameList()
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, (list, tuple)) and item and all(isinstance(value, str) for value in item):
                return [str(value) for value in item]
    if isinstance(raw, (list, tuple)) and raw and all(isinstance(value, str) for value in raw):
        return [str(value) for value in raw]
    return []


def _frame_label_and_story(sap_model: object, object_name: str) -> tuple[str | None, str | None]:
    frame_obj = getattr(sap_model, "FrameObj", None)
    if frame_obj is None or not hasattr(frame_obj, "GetLabelFromName"):
        return (None, None)
    raw = frame_obj.GetLabelFromName(object_name)
    values = raw if isinstance(raw, (list, tuple)) else (raw,)
    strings = [value for value in values if isinstance(value, str) and value]
    if len(strings) >= 2:
        return (strings[0], strings[1])
    if len(strings) == 1:
        return (strings[0], None)
    return (None, None)


def _frame_section(sap_model: object, object_name: str) -> str | None:
    frame_obj = getattr(sap_model, "FrameObj", None)
    if frame_obj is None or not hasattr(frame_obj, "GetSection"):
        return None
    raw = frame_obj.GetSection(object_name)
    values = raw if isinstance(raw, (list, tuple)) else (raw,)
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _name_list_from_object(owner: object, method_name: str) -> list[str]:
    if owner is None or not hasattr(owner, method_name):
        return []
    raw = getattr(owner, method_name)()
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, (list, tuple)) and item and all(isinstance(value, str) for value in item):
                return [str(value) for value in item]
    if isinstance(raw, (list, tuple)) and raw and all(isinstance(value, str) for value in raw):
        return [str(value) for value in raw]
    return []


def _git(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(["git", *args], text=True).strip()
    except Exception:
        return None


__all__ = [
    "DEFAULT_DESIGN_INPUTS",
    "read_check_rows_for_ui",
    "shape_result_rows_for_ui",
    "add_selection_column",
    "filter_beam_candidates",
    "classify_frame_element",
    "attach_to_open_etabs",
    "get_etabs_status",
    "list_available_stories",
    "list_available_combos",
    "list_available_load_cases",
    "list_story_beams",
    "choose_default_combos",
    "filter_selected_beams",
    "build_design_overrides_from_ui",
    "run_story_beam_checks_from_ui",
    "run_single_combo_beam_checks_from_ui",
    "branch_and_commit",
]


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(name))


