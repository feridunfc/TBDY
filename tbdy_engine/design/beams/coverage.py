
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd


@dataclass
class BeamCoverageItem:
    key: str
    story: str
    label: str
    section: str = ""
    in_topology: bool = False
    in_design_summary: bool = False
    in_forces: bool = False
    has_rebar_demand: bool = False
    has_shear_rebar_demand: bool = False
    unit_ambiguous_section: bool = False
    empty_or_missing_section: bool = False
    non_design_frame: bool = False
    reasons: List[str] | None = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["reasons"] = self.reasons or []
        return data


@dataclass
class BeamInventoryReport:
    topology_beams: int
    design_summary_beams: int
    force_beams: int
    rebar_demand_beams: int
    shear_rebar_demand_beams: int
    computable_flexure_beams: int
    computable_shear_beams: int

    missing_design_summary: int
    missing_forces: int
    missing_rebar_demand: int
    missing_shear_rebar_demand: int

    unit_ambiguous_sections: int
    empty_or_missing_sections: int
    non_design_frames: int

    # Backward-compatible total of all section-related warnings.
    suspicious_sections: int

    no_data_total: int
    no_data_reasons: Dict[str, int]
    sample_no_data: List[Dict[str, Any]]
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _norm_col(df: Any, names: List[str]) -> Optional[str]:
    if df is None or not hasattr(df, "columns"):
        return None

    targets = {
        str(n).strip().lower().replace(" ", "").replace("_", "")
        for n in names
    }

    for c in df.columns:
        cc = str(c).strip().lower().replace(" ", "").replace("_", "")
        if cc in targets:
            return c

    for c in df.columns:
        cc = str(c).strip().lower().replace(" ", "").replace("_", "")
        if any(t in cc for t in targets):
            return c

    return None


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == "":
            return default
        v = float(str(x).replace(",", "."))
        if v != v:
            return default
        return v
    except Exception:
        return default


def _make_key(story: Any, label: Any) -> str:
    return f"{str(story or '').strip()}|{str(label or '').strip()}"


def _split_key(key: str) -> Tuple[str, str]:
    if "|" in key:
        story, label = key.split("|", 1)
        return story, label
    return "", key


def _get_table(ctx: Any, name: str):
    tables = getattr(ctx, "tables", {}) or {}
    design_metadata = getattr(ctx, "design_metadata", {}) or {}

    obj = tables.get(name)
    if obj is not None:
        return obj

    return design_metadata.get(name)


def _classify_section(label: str, section: str) -> Tuple[bool, bool, bool]:
    """
    Returns:
      unit_ambiguous_section, empty_or_missing_section, non_design_frame

    Rules:
    - Fxxx labels with no design summary / no section are non-design frame candidates.
    - Empty section is tracked separately.
    - B60x100 / B60x130 style sections are not treated as capacity FAIL;
      they are unit-ambiguous because 100/130 can mean cm in section names.
    """
    import re

    label_u = str(label or "").strip().upper()
    section_s = str(section or "").strip()
    section_u = section_s.upper()

    empty_or_missing = not bool(section_s)
    non_design = label_u.startswith("F") and empty_or_missing

    if empty_or_missing:
        return False, True, non_design

    m = re.search(r"(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)", section_u)
    if not m:
        return False, False, non_design

    h = _safe_float(m.group(2), 0.0)

    # Conservative: h=100, 130 etc. is ambiguous in Turkish RC section names.
    unit_ambiguous = 100.0 <= h < 300.0

    return unit_ambiguous, False, non_design


def _topology_beam_inventory(ctx: Any) -> Dict[str, BeamCoverageItem]:
    topology = getattr(ctx, "topology", {}) or {}
    if not isinstance(topology, dict):
        return {}

    out: Dict[str, BeamCoverageItem] = {}

    for b in topology.get("beams", []) or []:
        if not isinstance(b, dict):
            continue

        story = str(b.get("story") or "").strip()
        label = str(b.get("label") or "").strip()
        section = str(b.get("section") or "").strip()

        if not label:
            continue

        key = _make_key(story, label)
        unit_amb, empty_sec, non_design = _classify_section(label, section)

        out[key] = BeamCoverageItem(
            key=key,
            story=story,
            label=label,
            section=section,
            in_topology=True,
            unit_ambiguous_section=unit_amb,
            empty_or_missing_section=empty_sec,
            non_design_frame=non_design,
            reasons=[],
        )

    return out


def _table_beam_keys(df: Any) -> Dict[str, Dict[str, Any]]:
    if df is None or not hasattr(df, "empty") or df.empty:
        return {}

    story_col = _norm_col(df, ["story", "kat", "level"])
    label_col = _norm_col(df, ["label", "beam", "frame", "element", "objlabel"])
    sec_col = _norm_col(df, ["designsect", "section", "section_name"])

    if not label_col:
        return {}

    out: Dict[str, Dict[str, Any]] = {}

    for _, row in df.iterrows():
        story = str(row.get(story_col) or "").strip() if story_col else ""
        label = str(row.get(label_col) or "").strip()
        section = str(row.get(sec_col) or "").strip() if sec_col else ""

        if not label:
            continue

        key = _make_key(story, label)
        out.setdefault(key, {"story": story, "label": label, "section": section, "rows": 0})
        out[key]["rows"] += 1

        if section and not out[key].get("section"):
            out[key]["section"] = section

    return out


def _demand_keys_from_beam_design_summary(df: Any) -> Tuple[Set[str], Set[str]]:
    if df is None or not hasattr(df, "empty") or df.empty:
        return set(), set()

    story_col = _norm_col(df, ["story"])
    label_col = _norm_col(df, ["label", "beam", "frame", "element"])

    if not label_col:
        return set(), set()

    flexure_keys: Set[str] = set()
    shear_keys: Set[str] = set()

    flexure_cols = [
        c for c in [
            _norm_col(df, ["astop"]),
            _norm_col(df, ["asbot"]),
            _norm_col(df, ["tottoprebar"]),
            _norm_col(df, ["totbotrebar"]),
            _norm_col(df, ["asmintop"]),
            _norm_col(df, ["asminbot"]),
        ]
        if c
    ]

    shear_cols = [
        c for c in [
            _norm_col(df, ["vrebar"]),
            _norm_col(df, ["tottrnrebar"]),
        ]
        if c
    ]

    for _, row in df.iterrows():
        story = str(row.get(story_col) or "").strip() if story_col else ""
        label = str(row.get(label_col) or "").strip()

        if not label:
            continue

        key = _make_key(story, label)

        if any(_safe_float(row.get(c), 0.0) > 0 for c in flexure_cols):
            flexure_keys.add(key)

        if any(_safe_float(row.get(c), 0.0) > 0 for c in shear_cols):
            shear_keys.add(key)

    return flexure_keys, shear_keys


def analyze_beam_coverage(ctx: Any) -> BeamInventoryReport:
    topology_items = _topology_beam_inventory(ctx)

    beam_design_summary = _get_table(ctx, "beam_design_summary")
    beam_forces = _get_table(ctx, "beam_forces")

    design_keys_meta = _table_beam_keys(beam_design_summary)
    force_keys_meta = _table_beam_keys(beam_forces)

    design_keys = set(design_keys_meta.keys())
    force_keys = set(force_keys_meta.keys())

    flexure_rebar_keys, shear_rebar_keys = _demand_keys_from_beam_design_summary(beam_design_summary)

    all_keys = set(topology_items.keys()) | design_keys | force_keys

    items: Dict[str, BeamCoverageItem] = {}

    for key in sorted(all_keys):
        story, label = _split_key(key)

        base = topology_items.get(key)
        if base:
            item = base
        else:
            meta = design_keys_meta.get(key) or force_keys_meta.get(key) or {}
            item = BeamCoverageItem(
                key=key,
                story=meta.get("story", story),
                label=meta.get("label", label),
                section=meta.get("section", ""),
                in_topology=False,
                reasons=[],
            )

            unit_amb, empty_sec, non_design = _classify_section(item.label, item.section)
            item.unit_ambiguous_section = unit_amb
            item.empty_or_missing_section = empty_sec
            item.non_design_frame = non_design

        item.in_design_summary = key in design_keys
        item.in_forces = key in force_keys
        item.has_rebar_demand = key in flexure_rebar_keys
        item.has_shear_rebar_demand = key in shear_rebar_keys

        # If design summary gives section but topology section was empty, use design section for classification.
        if not item.section and key in design_keys_meta:
            item.section = str(design_keys_meta[key].get("section") or "")
            unit_amb, empty_sec, non_design = _classify_section(item.label, item.section)
            item.unit_ambiguous_section = unit_amb
            item.empty_or_missing_section = empty_sec
            item.non_design_frame = non_design

        reasons: List[str] = []

        if not item.in_topology:
            reasons.append("not_in_topology")

        if not item.in_design_summary:
            reasons.append("missing_design_summary")

        if not item.in_forces:
            reasons.append("missing_forces")

        if not item.has_rebar_demand:
            reasons.append("missing_flexure_rebar_demand")

        if not item.has_shear_rebar_demand:
            reasons.append("missing_shear_rebar_demand")

        if item.unit_ambiguous_section:
            reasons.append("unit_ambiguous_section")

        if item.empty_or_missing_section:
            reasons.append("empty_or_missing_section")

        if item.non_design_frame:
            reasons.append("non_design_frame")

        item.reasons = reasons
        items[key] = item

    computable_flexure = 0
    computable_shear = 0
    no_data_reasons: Dict[str, int] = {}
    no_data_items: List[BeamCoverageItem] = []

    for item in items.values():
        flex_ok = item.in_design_summary and item.has_rebar_demand
        shear_ok = (
            item.in_design_summary
            and item.in_forces
            and item.has_shear_rebar_demand
            and not item.unit_ambiguous_section
            and not item.empty_or_missing_section
        )

        if flex_ok:
            computable_flexure += 1

        if shear_ok:
            computable_shear += 1

        if item.reasons:
            no_data_items.append(item)
            for r in item.reasons:
                no_data_reasons[r] = no_data_reasons.get(r, 0) + 1

    topology_beams = sum(1 for x in items.values() if x.in_topology)
    unit_ambiguous = sum(1 for x in items.values() if x.unit_ambiguous_section)
    empty_missing = sum(1 for x in items.values() if x.empty_or_missing_section)
    non_design = sum(1 for x in items.values() if x.non_design_frame)

    return BeamInventoryReport(
        topology_beams=topology_beams,
        design_summary_beams=len(design_keys),
        force_beams=len(force_keys),
        rebar_demand_beams=len(flexure_rebar_keys),
        shear_rebar_demand_beams=len(shear_rebar_keys),
        computable_flexure_beams=computable_flexure,
        computable_shear_beams=computable_shear,
        missing_design_summary=sum(1 for x in items.values() if "missing_design_summary" in (x.reasons or [])),
        missing_forces=sum(1 for x in items.values() if "missing_forces" in (x.reasons or [])),
        missing_rebar_demand=sum(1 for x in items.values() if "missing_flexure_rebar_demand" in (x.reasons or [])),
        missing_shear_rebar_demand=sum(1 for x in items.values() if "missing_shear_rebar_demand" in (x.reasons or [])),
        unit_ambiguous_sections=unit_ambiguous,
        empty_or_missing_sections=empty_missing,
        non_design_frames=non_design,
        suspicious_sections=unit_ambiguous + empty_missing,
        no_data_total=len(no_data_items),
        no_data_reasons=no_data_reasons,
        sample_no_data=[x.to_dict() for x in no_data_items[:25]],
        summary=(
            f"topology={topology_beams}, "
            f"design_summary={len(design_keys)}, "
            f"forces={len(force_keys)}, "
            f"flexure_computable={computable_flexure}, "
            f"shear_computable={computable_shear}, "
            f"unit_ambiguous={unit_ambiguous}, "
            f"empty_section={empty_missing}, "
            f"non_design_frame={non_design}, "
            f"no_data={len(no_data_items)}"
        ),
    )
