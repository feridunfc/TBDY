from __future__ import annotations

from typing import Any, Dict, List, Tuple

from tbdy_engine.design.core.capacity_design import (
    MemberMomentCapacity,
    ScwbJointResult,
    approximate_column_moment_capacity,
    beam_moment_capacity,
    compute_scwb_joint_result,
    safe_float,
)


def _ensure_topology(ctx: Any) -> None:
    topo = getattr(ctx, "topology", None)
    if isinstance(topo, dict) and topo.get("topology_status") == "OK":
        return

    try:
        from tbdy_engine.checks.registry import registry

        registry.load_from_matrix()
        fn = registry.get_check("beam_geometry")
        if fn:
            fn(ctx)
    except Exception:
        return


def _key(story: Any, label: Any) -> str:
    return f"{str(story or '').strip()}|{str(label or '').strip()}"


def _section_dims_from_name(section: str) -> Tuple[float, float]:
    import re

    s = str(section or "").upper()
    m = re.search(r"(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)", s)
    if not m:
        return 0.0, 0.0

    b = safe_float(m.group(1), 0.0)
    h = safe_float(m.group(2), 0.0)

    if 0.0 < b < 100.0:
        b *= 10.0
    if 0.0 < h < 100.0:
        h *= 10.0

    return b, h


def _material_values(ctx: Any) -> Dict[str, float]:
    fck = 35.0
    fcd = 35.0 / 1.5
    fyk = 500.0
    fyd = 500.0 / 1.15

    try:
        from tbdy_engine.design.beams.beam_module import BeamDesignModule

        bm = BeamDesignModule(ctx)
        mat = bm.resolve_materials()
        fck = safe_float(getattr(mat, "fck", fck), fck)
        fcd = safe_float(getattr(mat, "fcd", fcd), fcd)
        fyk = safe_float(getattr(mat, "fyk", fyk), fyk)
        fyd = safe_float(getattr(mat, "fyd", fyd), fyd)
    except Exception:
        pass

    return {"fck": fck, "fcd": fcd, "fyk": fyk, "fyd": fyd}

# === SPRINT32_SCWB_COLUMN_CAPACITY_HELPERS_BEGIN ===

def _obj_get(obj, *names, default=None):
    if obj is None:
        return default

    if isinstance(obj, dict):
        for n in names:
            if n in obj:
                return obj.get(n)
            # case-insensitive fallback
            for k, v in obj.items():
                if str(k).lower() == str(n).lower():
                    return v
        return default

    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)

    return default


def _first_number(obj, names, default=0.0):
    for n in names:
        v = _obj_get(obj, n, default=None)
        x = safe_float(v, 0.0)
        if x > 0:
            return x
    return default


def _column_dims_from_obj_or_context(ctx, col):
    label = str(_obj_get(col, "label", "element_id", default="") or "").strip()
    story = str(_obj_get(col, "story", default="") or "").strip()
    section = str(_obj_get(col, "section_name", "section", "section_label", default="") or "").strip()

    width = _first_number(
        col,
        [
            "width_mm", "b_mm", "bx_mm", "dim_x_mm", "depth_x_mm",
            "width", "b", "t2_mm",
        ],
        0.0,
    )
    depth = _first_number(
        col,
        [
            "depth_mm", "h_mm", "hy_mm", "dim_y_mm", "depth_y_mm",
            "height", "h", "t3_mm",
        ],
        0.0,
    )

    # If values are in meters accidentally, convert to mm.
    if 0 < width < 10:
        width *= 1000.0
    if 0 < depth < 10:
        depth *= 1000.0

    geometry = getattr(ctx, "geometry", {}) or {}
    section_dims = geometry.get("section_dims", {}) or {}
    column_sections = geometry.get("column_sections", {}) or {}

    if not section:
        section = str(
            column_sections.get(f"{story}|{label}")
            or column_sections.get(label)
            or ""
        ).strip()

    if (width <= 0 or depth <= 0) and section:
        dims = section_dims.get(section, {}) or {}

        if width <= 0:
            width = safe_float(
                dims.get("width_mm")
                or dims.get("b_mm")
                or dims.get("t2_mm")
                or dims.get("width_m"),
                0.0,
            )
            if 0 < width < 10:
                width *= 1000.0

        if depth <= 0:
            depth = safe_float(
                dims.get("depth_mm")
                or dims.get("h_mm")
                or dims.get("t3_mm")
                or dims.get("depth_m"),
                0.0,
            )
            if 0 < depth < 10:
                depth *= 1000.0

    if (width <= 0 or depth <= 0) and section:
        w2, d2 = _section_dims_from_name(section)
        if width <= 0:
            width = w2
        if depth <= 0:
            depth = d2

    # Last fallback: topology column section.
    if (width <= 0 or depth <= 0):
        topo = getattr(ctx, "topology", {}) or {}
        if isinstance(topo, dict):
            for c in topo.get("columns", []) or []:
                if not isinstance(c, dict):
                    continue

                if str(c.get("label") or "").strip() != label:
                    continue

                cstory = str(c.get("story") or "").strip()
                if story and cstory and story != cstory:
                    continue

                sec = str(c.get("section") or "").strip()
                if sec:
                    w2, d2 = _section_dims_from_name(sec)
                    if width <= 0:
                        width = w2
                    if depth <= 0:
                        depth = d2
                    break

    return width, depth, section


def _column_as_total_from_rebar(rb):
    if rb is None:
        return 0.0, "unknown"

    source = str(_obj_get(rb, "source", default="unknown") or "unknown")

    as_total = _first_number(
        rb,
        [
            "As_total_mm2", "as_total_mm2",
            "longitudinal_area_mm2", "As_longitudinal_mm2",
            "Ast_mm2", "ast_mm2", "As_mm2", "as_mm2",
            "total_longitudinal_rebar_mm2",
            "total_rebar_area_mm2",
            "area_longitudinal_mm2",
            "rebar_area_mm2",
            "provided_as_total_mm2",
        ],
        0.0,
    )

    if as_total > 0:
        return as_total, source

    n = _first_number(rb, ["bar_count", "n_bars", "number_of_bars", "bars"], 0.0)
    dia = _first_number(rb, ["bar_diameter_mm", "main_bar_diameter_mm", "dia_mm", "phi"], 0.0)

    if n > 0 and dia > 0:
        import math
        return n * math.pi * dia * dia / 4.0, source

    return 0.0, source


def _minimum_column_as_fallback(width_mm, depth_mm):
    """
    Approximate fallback for SCWB inspector only.

    Uses 1% gross area when real/provided longitudinal As cannot be extracted.
    This must remain APPROXIMATE/WARNING, never DESIGN_LEVEL.
    """
    if width_mm <= 0 or depth_mm <= 0:
        return 0.0
    return 0.01 * width_mm * depth_mm

# === SPRINT32_SCWB_COLUMN_CAPACITY_HELPERS_END ===

# === SPRINT33_SCWB_DIRECTION_HELPERS_BEGIN ===

def _coord_xy(value):
    """
    Returns (x, y) from topology coord formats:
    - tuple/list: (x, y, z)
    - dict: {"x":..., "y":...}
    - None -> None
    """
    if value is None:
        return None

    if isinstance(value, dict):
        x = safe_float(value.get("x") or value.get("globalx"), None)
        y = safe_float(value.get("y") or value.get("globaly"), None)
        if x is None or y is None:
            return None
        return float(x), float(y)

    if isinstance(value, (list, tuple)) and len(value) >= 2:
        x = safe_float(value[0], None)
        y = safe_float(value[1], None)
        if x is None or y is None:
            return None
        return float(x), float(y)

    return None


def _beam_direction_from_coords(beam_data):
    """
    Classify a beam as X or Y from end coordinates.
    Returns None if coordinates are missing.
    """
    if not isinstance(beam_data, dict):
        return None

    ci = _coord_xy(beam_data.get("coord_i"))
    cj = _coord_xy(beam_data.get("coord_j"))

    if ci is None or cj is None:
        return None

    dx = abs(cj[0] - ci[0])
    dy = abs(cj[1] - ci[1])

    if dx <= 1e-9 and dy <= 1e-9:
        return None

    return "X" if dx >= dy else "Y"


def _build_beam_direction_map(topology):
    """
    Builds:
      {
        "story|B1": "X",
        "B1": "X"   # label alias only if unique enough
      }
    """
    if not isinstance(topology, dict):
        return {}

    direction_map = {}
    label_dirs = {}

    for b in topology.get("beams", []) or []:
        if not isinstance(b, dict):
            continue

        label = str(b.get("label") or "").strip()
        story = str(b.get("story") or "").strip()

        if not label:
            continue

        direction = _beam_direction_from_coords(b)
        if not direction:
            continue

        key = _key(story, label)
        direction_map[key] = direction

        label_dirs.setdefault(label, set()).add(direction)

    # Add label alias only if all same direction.
    for label, dirs in label_dirs.items():
        if len(dirs) == 1:
            direction_map[label] = list(dirs)[0]

    return direction_map


def _split_beams_by_direction(story, beams, beam_direction_map):
    groups = {"X": [], "Y": [], "GLOBAL": []}

    for b in beams:
        b_str = str(b)
        direction = (
            beam_direction_map.get(_key(story, b_str))
            or beam_direction_map.get(b_str)
        )

        if direction in ("X", "Y"):
            groups[direction].append(b_str)
        else:
            groups["GLOBAL"].append(b_str)

    # If at least one directional group exists, keep X/Y and ignore GLOBAL-only
    # beams only if they are absent. If some beams are unclassified, keep an
    # additional GLOBAL result for them.
    out = {}

    if groups["X"]:
        out["X"] = groups["X"]
    if groups["Y"]:
        out["Y"] = groups["Y"]
    if groups["GLOBAL"]:
        out["GLOBAL"] = groups["GLOBAL"]

    return out

# === SPRINT33_SCWB_DIRECTION_HELPERS_END ===

class ScwbResolver:
    """
    Joint-based Strong Column - Weak Beam resolver.

    First implementation is fail-safe:
    - Beam provided/user rebar can produce DESIGN_LEVEL beam capacity.
    - Column capacity is approximate until PMM solver is connected.
    - Therefore package usually returns WARNING, not hard FAIL.
    """

    def __init__(self, ctx: Any):
        self.ctx = ctx
        _ensure_topology(ctx)
        self.materials = _material_values(ctx)

    def evaluate(self) -> Dict[str, Any]:
        beam_caps = self._beam_capacities()
        column_caps = self._column_capacities()

        topo = getattr(self.ctx, "topology", {}) or {}
        joints = topo.get("joints", {}) if isinstance(topo, dict) else {}
        beam_direction_map = _build_beam_direction_map(topo)

        results: List[ScwbJointResult] = []

        for joint_id, joint_data in joints.items():
            if not isinstance(joint_data, dict):
                continue

            story = str(joint_data.get("story") or "").strip()
            beams = [str(b) for b in (joint_data.get("connected_beams") or [])]
            columns = [str(c) for c in (joint_data.get("connected_columns") or [])]

            if not beams or not columns:
                continue

            column_capacity_list = []
            for c in columns:
                column_capacity_list.append(
                    column_caps.get(_key(story, c))
                    or column_caps.get(c)
                    or MemberMomentCapacity(element_id=c, story=story, member_type="COLUMN")
                )

            directional_beams = _split_beams_by_direction(story, beams, beam_direction_map)

            for direction, dir_beams in directional_beams.items():
                if not dir_beams:
                    continue

                beam_capacity_list = []
                for b in dir_beams:
                    beam_capacity_list.append(
                        beam_caps.get(_key(story, b))
                        or beam_caps.get(b)
                        or MemberMomentCapacity(element_id=b, story=story, member_type="BEAM")
                    )

                res = compute_scwb_joint_result(
                    joint_id=str(joint_id),
                    story=story,
                    direction=direction,
                    columns=columns,
                    beams=dir_beams,
                    column_capacities=column_capacity_list,
                    beam_capacities=beam_capacity_list,
                )
                results.append(res)

        return {
            "summary": self._summary(results),
            "results": [r.to_dict() for r in results],
            "beam_capacity_count": len(beam_caps),
            "column_capacity_count": len(column_caps),
        }

    def _beam_capacities(self) -> Dict[str, MemberMomentCapacity]:
        out: Dict[str, MemberMomentCapacity] = {}

        try:
            from tbdy_engine.design.beams.beam_module import BeamDesignModule

            module = BeamDesignModule(self.ctx)
            result = module.run()
        except Exception:
            return out

        fcd = self.materials["fcd"]
        fyd = self.materials["fyd"]

        for item in result.get("outputs", []) or []:
            label = str(item.get("label") or "").strip()
            story = str(item.get("story") or "").strip()
            section = str(item.get("section") or "").strip()

            if not label:
                continue

            geometry = item.get("geometry", {}) or {}
            rebar = item.get("rebar", {}) or {}

            width = safe_float(geometry.get("width_mm"), 0.0)
            depth = safe_float(geometry.get("depth_mm"), 0.0)

            if width <= 0 or depth <= 0:
                width, depth = _section_dims_from_name(section)

            as_top = safe_float(rebar.get("As_top_mm2") or rebar.get("as_top_provided_mm2"), 0.0)
            as_bot = safe_float(rebar.get("As_bottom_mm2") or rebar.get("as_bottom_provided_mm2"), 0.0)
            source = str(rebar.get("source") or item.get("source") or "unknown")

            cap = beam_moment_capacity(
                element_id=label,
                story=story,
                width_mm=width,
                depth_mm=depth,
                as_top_mm2=as_top,
                as_bottom_mm2=as_bot,
                fyd_mpa=fyd,
                fcd_mpa=fcd,
                source=source,
            )

            out[_key(story, label)] = cap
            out.setdefault(label, cap)

        return out

    def _column_capacities(self) -> Dict[str, MemberMomentCapacity]:
        out: Dict[str, MemberMomentCapacity] = {}

        try:
            from tbdy_engine.design.columns.module import ColumnDesignModule

            module = ColumnDesignModule(self.ctx)
            module.run()
            columns = getattr(module, "_columns", []) or []
            rebar_map = getattr(module, "_rebar", {}) or {}
        except Exception:
            return out

        fcd = self.materials["fcd"]
        fyd = self.materials["fyd"]

        for col in columns:
            label = str(_obj_get(col, "label", "element_id", default="") or "").strip()
            story = str(_obj_get(col, "story", default="") or "").strip()

            if not label:
                continue

            width, depth, section = _column_dims_from_obj_or_context(self.ctx, col)

            rb = (
                rebar_map.get(_key(story, label))
                or rebar_map.get(label)
                or rebar_map.get(f"{story}|{label}")
            )

            as_total, source = _column_as_total_from_rebar(rb)

            used_minimum_fallback = False
            if as_total <= 0 and width > 0 and depth > 0:
                as_total = _minimum_column_as_fallback(width, depth)
                source = "minimum_rebar_fallback_for_scwb"
                used_minimum_fallback = True

            cap = approximate_column_moment_capacity(
                element_id=label,
                story=story,
                width_mm=width,
                depth_mm=depth,
                as_total_mm2=as_total,
                fyd_mpa=fyd,
                fcd_mpa=fcd,
                source=source,
            )

            if used_minimum_fallback and cap.m_governing_knm and cap.m_governing_knm > 0:
                cap.status = "WARNING"
                cap.evaluation_level = "APPROXIMATE"
                cap.note = (
                    "minimum 1% longitudinal rebar fallback used for SCWB inspector; "
                    "provide final column rebar or PMM solver for DESIGN_LEVEL"
                )

            # Attach diagnostics for debug.
            try:
                setattr(cap, "section", section)
                setattr(cap, "width_mm", width)
                setattr(cap, "depth_mm", depth)
                setattr(cap, "as_total_mm2", as_total)
            except Exception:
                pass

            out[_key(story, label)] = cap
            out.setdefault(label, cap)

        return out

    def _summary(self, results: List[ScwbJointResult]) -> Dict[str, Any]:
        counts = {"OK": 0, "FAIL": 0, "WARNING": 0, "NO_DATA": 0, "NOT_EVALUATED": 0}

        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1

        total = len(results)

        if counts.get("FAIL", 0) > 0:
            package_status = "FAIL"
        elif counts.get("WARNING", 0) > 0:
            package_status = "WARNING"
        elif total > 0 and counts.get("NO_DATA", 0) == total:
            package_status = "NO_DATA"
        elif counts.get("OK", 0) > 0:
            package_status = "OK"
        else:
            package_status = "NO_DATA"

        ratios = [r.ratio for r in results if r.ratio > 0]

        return {
            "total_joints": total,
            "ok": counts.get("OK", 0),
            "fail": counts.get("FAIL", 0),
            "warning": counts.get("WARNING", 0),
            "no_data": counts.get("NO_DATA", 0),
            "package_status": package_status,
            "min_ratio": min(ratios) if ratios else 0.0,
            "max_ratio": max(ratios) if ratios else 0.0,
        }
