
"""
Topology Engine - Kolon-Kiriş-Joint bağlantı analizi.

Desteklenen ETABS tablo formatları:

1) Connectivity format
- Beam Object Connectivity
- Column Object Connectivity
- Point Object Connectivity
- Frame Assignments - Summary

2) Objects / Elements format
- Objects and Elements - Frames
- Objects and Elements - Joints
- Frame Assignments - Summary
"""

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class ConnectionSide(Enum):
    LEFT = "left"
    RIGHT = "right"
    FRONT = "front"
    BACK = "back"
    CENTER = "center"
    CORNER = "corner"
    UNKNOWN = "unknown"


class JointType(Enum):
    INTERIOR = "interior"
    EDGE = "edge"
    CORNER = "corner"
    EXTERIOR = "exterior"
    ISOLATED = "isolated"


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass
class JointInfo:
    name: str
    story: str
    x: float
    y: float
    z: float
    connected_columns: List[str] = field(default_factory=list)
    connected_beams: List[str] = field(default_factory=list)
    joint_type: JointType = JointType.ISOLATED
    confinement_status: str = "UNKNOWN"

    @property
    def n_beams(self) -> int:
        return len(set(self.connected_beams))

    @property
    def n_columns(self) -> int:
        return len(set(self.connected_columns))


@dataclass
class FrameInfo:
    story: str
    label: str
    unique_name: str
    design_type: str
    section: str
    length_m: float
    jt_i: str
    jt_j: str
    coord_i: Optional[Tuple[float, float, float]] = None
    coord_j: Optional[Tuple[float, float, float]] = None
    angle_from_vertical: Optional[float] = None
    classified_as: str = "UNKNOWN"

    @property
    def is_column(self) -> bool:
        return self.classified_as == "COLUMN"

    @property
    def is_beam(self) -> bool:
        return self.classified_as == "BEAM"

    @property
    def bottom_joint(self) -> Optional[str]:
        if not self.coord_i or not self.coord_j:
            return None
        return self.jt_i if self.coord_i[2] <= self.coord_j[2] else self.jt_j

    @property
    def top_joint(self) -> Optional[str]:
        if not self.coord_i or not self.coord_j:
            return None
        return self.jt_j if self.coord_i[2] <= self.coord_j[2] else self.jt_i


@dataclass
class BeamConnectionInfo:
    beam_label: str
    column_label: str
    joint_name: str
    joint_coord: Tuple[float, float, float]
    connection_side: ConnectionSide
    eccentricity_mm: Tuple[float, float]
    beam_direction: str
    beam_angle_deg: float
    is_primary_direction: bool = True


@dataclass
class ColumnConnectionMap:
    column_label: str
    story: str
    joint_top: str
    joint_bot: str
    coord_top: Tuple[float, float, float]
    coord_bot: Tuple[float, float, float]
    section: Optional[str] = None
    width_mm: Optional[float] = None
    depth_mm: Optional[float] = None
    beams_at_top: List[BeamConnectionInfo] = field(default_factory=list)
    beams_at_bot: List[BeamConnectionInfo] = field(default_factory=list)

    @property
    def all_beams(self) -> List[str]:
        beams = set()
        for conn in self.beams_at_top + self.beams_at_bot:
            beams.add(conn.beam_label)
        return list(beams)

    @property
    def primary_beams(self) -> List[str]:
        beams = set()
        for conn in self.beams_at_top + self.beams_at_bot:
            if conn.is_primary_direction:
                beams.add(conn.beam_label)
        return list(beams)


@dataclass
class TopologyResult:
    frames: List[FrameInfo]
    columns: List[FrameInfo]
    beams: List[FrameInfo]
    joints: Dict[str, JointInfo]
    column_beam_map: Dict[str, ColumnConnectionMap]
    warnings: List[str] = field(default_factory=list)
    debug_info: Dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> Dict[str, Any]:
        return {
            "total_frames": len(self.frames),
            "columns": len(self.columns),
            "beams": len(self.beams),
            "joints": len(self.joints),
            "joints_with_beams": sum(1 for j in self.joints.values() if j.n_beams > 0),
            "joints_confined": sum(1 for j in self.joints.values() if j.confinement_status == "CONFINED"),
            "joints_partial": sum(1 for j in self.joints.values() if j.confinement_status == "PARTIAL"),
            "joints_unconfined": sum(1 for j in self.joints.values() if j.confinement_status == "UNCONFINED"),
            "warnings": len(self.warnings),
            "debug": self.debug_info,
        }


# ============================================================================
# HELPERS
# ============================================================================

def _as_float(val: Any, default: float = 0.0) -> float:
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _as_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _first_existing(row: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    # 1) direct match
    for key in keys:
        val = row.get(key)
        if val is not None and val != "":
            return val

    # 2) case-insensitive / normalized match
    norm_row = {
        str(k).strip().lower().replace(" ", "").replace("_", ""): v
        for k, v in row.items()
    }

    for key in keys:
        nk = str(key).strip().lower().replace(" ", "").replace("_", "")
        val = norm_row.get(nk)
        if val is not None and val != "":
            return val

    return default


def _angle_from_vertical(ci: Tuple[float, float, float], cj: Tuple[float, float, float]) -> float:
    dx = cj[0] - ci[0]
    dy = cj[1] - ci[1]
    dz = cj[2] - ci[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-9:
        return 90.0
    return math.degrees(math.acos(min(1.0, abs(dz) / length)))


def parse_section_dims(section_name: str) -> Tuple[float, float]:
    if not section_name:
        return 400.0, 400.0

    patterns = [
        r"[CcBb]?(\d+)[xX/](\d+)",
        r"(\d+)\s*[xX]\s*(\d+)",
        r"(\d+)/(\d+)",
    ]

    for pat in patterns:
        match = re.search(pat, section_name)
        if match:
            w = float(match.group(1))
            d = float(match.group(2))
            if w < 100:
                w *= 10
            if d < 100:
                d *= 10
            return w, d

    return 400.0, 400.0


def _frame_label_from_row(row: Dict[str, Any]) -> str:
    return _as_str(_first_existing(row, [
        "BeamBay", "ColumnBay",
        "ObjLabel", "Object Label", "Label", "ObjectLabel", "Obj Label",
        "Frame", "ObjName"
    ]))


def _frame_unique_name_from_row(row: Dict[str, Any]) -> str:
    return _as_str(_first_existing(row, [
        "UniqueName", "ElmName", "Element Name", "Unique Name", "ObjName"
    ]))


def _frame_joint_i_from_row(row: Dict[str, Any]) -> str:
    return _as_str(_first_existing(row, [
        "UniquePtI",
        "ElmJtI", "Elm JtI",
        "JointI", "JtI",
        "End I", "End.I", "I-End", "I_End"
    ]))


def _frame_joint_j_from_row(row: Dict[str, Any]) -> str:
    return _as_str(_first_existing(row, [
        "UniquePtJ",
        "ElmJtJ", "Elm JtJ",
        "JointJ", "JtJ",
        "End J", "End.J", "J-End", "J_End"
    ]))


def _joint_name_from_row(row: Dict[str, Any]) -> str:
    return _as_str(_first_existing(row, [
        "UniqueName",
        "ElmName", "Element Name",
        "ObjLabel", "Object Label",
        "ObjName", "Object Name",
        "Name", "Joint", "Joint Name",
        "PointBay",
    ]))


# ============================================================================
# TOPOLOGY BUILDER
# ============================================================================
def build_topology(
    frame_rows: List[Dict[str, Any]],
    joint_rows: List[Dict[str, Any]],
    assign_rows: List[Dict[str, Any]],
    vertical_angle_threshold: float = 20.0
) -> TopologyResult:
    """
    Frame, Joint ve Assign tablolarından topoloji oluştur.

    Desteklenen ETABS formatları:
    - Beam Object Connectivity
    - Column Object Connectivity
    - Point Object Connectivity
    - Frame Assignments - Summary

    Notlar:
    - Frame rows object-level dedupe edilir (Story + Label)
    - Top joint her zaman dikkate alınır
    - Bottom joint sadece aynı katta ise dikkate alınır
    """

    warnings: List[str] = []
    debug: Dict[str, Any] = {
        "frame_rows_in": len(frame_rows),
        "joint_rows_in": len(joint_rows),
        "assign_rows_in": len(assign_rows),
        "frame_rows_discarded_no_story_or_label": 0,
        "frame_rows_discarded_no_joint_match": 0,
        "unknown_frames": 0,
        "sample_frame_keys": list(frame_rows[0].keys()) if frame_rows else [],
        "sample_joint_keys": list(joint_rows[0].keys()) if joint_rows else [],
        "sample_assign_keys": list(assign_rows[0].keys()) if assign_rows else [],
        "joint_lookup_size": 0,
        "assign_map_size": 0,
        "deduped_object_rows": 0,
    }

    # ---------------------------------------------------------------------
    # 1. JOINTS
    # ---------------------------------------------------------------------
    joint_coords: Dict[str, Tuple[float, float, float]] = {}
    joint_story: Dict[str, str] = {}
    joint_lookup: Dict[str, str] = {}

    for row in joint_rows:
        unique_name = _as_str(_first_existing(row, ["UniqueName"]))
        elm_name = _as_str(_first_existing(row, ["ElmName", "Element Name"]))
        obj_label = _as_str(_first_existing(row, ["ObjLabel", "Object Label", "Label"]))
        obj_name = _as_str(_first_existing(row, ["ObjName", "Object Name", "Name"]))
        point_bay = _as_str(_first_existing(row, ["PointBay"]))

        name = unique_name or elm_name or obj_label or obj_name or point_bay
        if not name:
            continue

        x = _as_float(_first_existing(row, ["X", "GlobalX", "Global X", "CoordX"]))
        y = _as_float(_first_existing(row, ["Y", "GlobalY", "Global Y", "CoordY"]))
        z = _as_float(_first_existing(row, ["Z", "GlobalZ", "Global Z", "CoordZ"]))
        story = _as_str(_first_existing(row, ["Story", "Level", "StoryName"]))

        joint_coords[name] = (x, y, z)
        joint_story[name] = story

        for alias in [unique_name, elm_name, obj_label, obj_name, point_bay]:
            if alias:
                joint_lookup[alias] = name

    debug["joints_extracted"] = len(joint_coords)
    debug["joint_lookup_size"] = len(joint_lookup)

    if not joint_coords:
        warnings.append(
            "FATAL: No joints extracted. Check joint_rows column names. "
            f"Available keys: {debug['sample_joint_keys']}"
        )
        return TopologyResult([], [], [], {}, {}, warnings, debug)

    def resolve_joint_key(raw_key: str) -> Optional[str]:
        raw_key = _as_str(raw_key)
        if not raw_key:
            return None

        if raw_key in joint_coords:
            return raw_key

        if raw_key in joint_lookup:
            return joint_lookup[raw_key]

        raw_norm = raw_key.upper()
        for alias, canonical in joint_lookup.items():
            if _as_str(alias).upper() == raw_norm:
                return canonical

        for canonical in joint_coords.keys():
            if _as_str(canonical).upper() == raw_norm:
                return canonical

        return None

    # ---------------------------------------------------------------------
    # 2. ASSIGNS
    # ---------------------------------------------------------------------
    assign_map: Dict[str, Dict[str, Any]] = {}

    for row in assign_rows:
        label = _as_str(_first_existing(row, [
            "Label", "BeamBay", "ColumnBay",
            "ObjLabel", "Object Label", "ObjectLabel", "Obj Label",
            "Frame", "UniqueName", "Unique Name", "ElmName"
        ])).upper()

        unique_name = _as_str(_first_existing(row, [
            "UniqueName", "Unique Name", "ElmName", "Element Name"
        ])).upper()

        if label:
            assign_map[label] = row
        if unique_name:
            assign_map[unique_name] = row

    debug["assign_map_size"] = len(assign_map)

    # ---------------------------------------------------------------------
    # 3. FRAME ROWS DEDUPE
    # ---------------------------------------------------------------------
    def _frame_label_from_row(row: Dict[str, Any]) -> str:
        return _as_str(_first_existing(row, [
            "BeamBay", "ColumnBay",
            "ObjLabel", "Object Label", "Label", "ObjectLabel", "Obj Label",
            "Frame", "ObjName"
        ]))

    def _frame_unique_name_from_row(row: Dict[str, Any]) -> str:
        return _as_str(_first_existing(row, [
            "UniqueName", "ElmName", "Element Name", "Unique Name", "ObjName"
        ]))

    def _frame_joint_i_from_row(row: Dict[str, Any]) -> str:
        return _as_str(_first_existing(row, [
            "UniquePtI",
            "ElmJtI", "Elm JtI",
            "JointI", "JtI",
            "End I", "End.I", "I-End", "I_End"
        ]))

    def _frame_joint_j_from_row(row: Dict[str, Any]) -> str:
        return _as_str(_first_existing(row, [
            "UniquePtJ",
            "ElmJtJ", "Elm JtJ",
            "JointJ", "JtJ",
            "End J", "End.J", "J-End", "J_End"
        ]))

    first_obj_row: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for row in frame_rows:
        story = _as_str(_first_existing(row, ["Story", "Level", "StoryName"]))
        label = _frame_label_from_row(row)

        if not story or not label:
            debug["frame_rows_discarded_no_story_or_label"] += 1
            continue

        key = (story.upper(), label.upper())
        if key not in first_obj_row:
            first_obj_row[key] = row

    debug["deduped_object_rows"] = len(first_obj_row)

    # ---------------------------------------------------------------------
    # 4. FRAMES
    # ---------------------------------------------------------------------
    frames: List[FrameInfo] = []

    for (_, _), row in first_obj_row.items():
        story = _as_str(_first_existing(row, ["Story", "Level", "StoryName"]))
        label = _frame_label_from_row(row)

        if not story or not label:
            continue

        label_upper = label.upper()
        unique_name = _frame_unique_name_from_row(row) or label
        unique_upper = unique_name.upper()

        assign = assign_map.get(label_upper) or assign_map.get(unique_upper) or {}

        design_type = _as_str(_first_existing(assign, [
            "Design Type", "DesignType", "Frame Type", "Type", "Element Type"
        ]))

        section = _as_str(_first_existing(assign, [
            "DesignSect", "AnalysisSect",
            "Design Section", "Analysis Section",
            "Section", "section",
            "Frame Section", "FrameSection",
            "SectProp", "sectprop",
        ]))

        length_m = _as_float(_first_existing(assign, ["Length", "Frame Length", "L"]))
        if length_m <= 0:
            length_m = _as_float(_first_existing(row, ["Length", "Frame Length", "L"]))

        jt_i_raw = _frame_joint_i_from_row(row)
        jt_j_raw = _frame_joint_j_from_row(row)

        jt_i = resolve_joint_key(jt_i_raw) or jt_i_raw
        jt_j = resolve_joint_key(jt_j_raw) or jt_j_raw

        ci = joint_coords.get(jt_i)
        cj = joint_coords.get(jt_j)

        if not ci or not cj:
            debug["frame_rows_discarded_no_joint_match"] += 1
            warnings.append(
                f"{story}/{label}: Cannot locate joints "
                f"I={jt_i_raw}->{jt_i} (found={jt_i in joint_coords}), "
                f"J={jt_j_raw}->{jt_j} (found={jt_j in joint_coords})"
            )

        design_lower = design_type.lower().strip()

        if design_lower in ["beam", "kiriş", "kiris", "b"]:
            classified = "BEAM"
        elif design_lower in ["column", "kolon", "col", "c"]:
            classified = "COLUMN"
        elif ci and cj:
            angle = _angle_from_vertical(ci, cj)
            if angle <= vertical_angle_threshold:
                classified = "COLUMN"
            elif angle >= 90 - vertical_angle_threshold:
                classified = "BEAM"
            else:
                classified = "INCLINED"
                warnings.append(f"{story}/{label}: Inclined frame, angle={angle:.1f}°")
        else:
            classified = "UNKNOWN"
            debug["unknown_frames"] += 1
            warnings.append(
                f"{story}/{label}: Cannot classify - no design type and missing coordinates"
            )

        frames.append(FrameInfo(
            story=story,
            label=label,
            unique_name=unique_name,
            design_type=design_type,
            section=section,
            length_m=length_m,
            jt_i=jt_i,
            jt_j=jt_j,
            coord_i=ci,
            coord_j=cj,
            angle_from_vertical=_angle_from_vertical(ci, cj) if ci and cj else None,
            classified_as=classified,
        ))

    debug["frames_extracted"] = len(frames)

    columns = [f for f in frames if f.is_column]
    beams = [f for f in frames if f.is_beam]
    inclined = [f for f in frames if f.classified_as == "INCLINED"]
    unknown = [f for f in frames if f.classified_as == "UNKNOWN"]

    debug["columns_found"] = len(columns)
    debug["beams_found"] = len(beams)
    debug["inclined_found"] = len(inclined)
    debug["unknown_found"] = len(unknown)

    if not columns:
        warnings.append(
            f"No columns found - check frame classification or assign table. "
            f"Total frames={len(frames)}, unknown={len(unknown)}, inclined={len(inclined)}"
        )
    if not beams:
        warnings.append(
            f"No beams found - check frame classification or assign table. "
            f"Total frames={len(frames)}, unknown={len(unknown)}, inclined={len(inclined)}"
        )

    # ---------------------------------------------------------------------
    # 5. JOINT OBJECTS
    # ---------------------------------------------------------------------
    joints: Dict[str, JointInfo] = {}
    for name, coords in joint_coords.items():
        joints[name] = JointInfo(
            name=name,
            story=joint_story.get(name, ""),
            x=coords[0],
            y=coords[1],
            z=coords[2],
        )

    for col in columns:
        if col.jt_i in joints:
            joints[col.jt_i].connected_columns.append(col.label)
        if col.jt_j in joints:
            joints[col.jt_j].connected_columns.append(col.label)

    for bm in beams:
        if bm.jt_i in joints:
            joints[bm.jt_i].connected_beams.append(bm.label)
        if bm.jt_j in joints:
            joints[bm.jt_j].connected_beams.append(bm.label)

    debug["joints_with_columns"] = sum(1 for j in joints.values() if j.n_columns > 0)
    debug["joints_with_beams"] = sum(1 for j in joints.values() if j.n_beams > 0)

    # ---------------------------------------------------------------------
    # 6. CONFINEMENT TAGGING
    # ---------------------------------------------------------------------
    beam_index = {f"{b.story}|{b.label}": b for b in beams}

    for _, joint in joints.items():
        joint_beams = []
        for bm_label in set(joint.connected_beams):
            # önce aynı kattaki beam'i ara
            same_story = beam_index.get(f"{joint.story}|{bm_label}")
            if same_story:
                joint_beams.append(same_story)
                continue

            # fallback: ilk bulunan
            fallback = next((b for b in beams if b.label == bm_label), None)
            if fallback:
                joint_beams.append(fallback)

        n_beams = len(joint_beams)
        x_beams = []
        y_beams = []

        for bm in joint_beams:
            if not bm.coord_i or not bm.coord_j:
                continue

            dx = abs(bm.coord_j[0] - bm.coord_i[0])
            dy = abs(bm.coord_j[1] - bm.coord_i[1])
            angle = math.degrees(math.atan2(dy, dx)) % 180

            if angle < 20 or angle > 160:
                x_beams.append(bm)
            elif 70 < angle < 110:
                y_beams.append(bm)

        has_opposite_x = len(x_beams) >= 2
        has_opposite_y = len(y_beams) >= 2

        if has_opposite_x and has_opposite_y:
            joint.joint_type = JointType.INTERIOR
            joint.confinement_status = "CONFINED"
        elif has_opposite_x or has_opposite_y:
            joint.joint_type = JointType.EDGE
            joint.confinement_status = "PARTIAL"
        elif n_beams >= 2:
            joint.joint_type = JointType.CORNER
            joint.confinement_status = "UNCONFINED"
        elif n_beams == 1:
            joint.joint_type = JointType.EXTERIOR
            joint.confinement_status = "UNCONFINED"
        else:
            joint.joint_type = JointType.ISOLATED
            joint.confinement_status = "UNKNOWN"

    # ---------------------------------------------------------------------
    # 7. COLUMN-BEAM MAP
    # ---------------------------------------------------------------------
    column_beam_map: Dict[str, ColumnConnectionMap] = {}
    section_dims_cache: Dict[str, Tuple[float, float]] = {}

    for col in columns:
        if not col.coord_i or not col.coord_j:
            warnings.append(f"{col.story}/{col.label}: Missing coordinates")
            continue

        if col.coord_i[2] <= col.coord_j[2]:
            bot_jt, top_jt = col.jt_i, col.jt_j
            coord_bot, coord_top = col.coord_i, col.coord_j
        else:
            bot_jt, top_jt = col.jt_j, col.jt_i
            coord_bot, coord_top = col.coord_j, col.coord_i

        if col.section not in section_dims_cache:
            section_dims_cache[col.section] = parse_section_dims(col.section)
        width_mm, depth_mm = section_dims_cache[col.section]

        center_x = (coord_top[0] + coord_bot[0]) / 2
        center_y = (coord_top[1] + coord_bot[1]) / 2

        cmap = ColumnConnectionMap(
            column_label=col.label,
            story=col.story,
            joint_top=top_jt,
            joint_bot=bot_jt,
            coord_top=coord_top,
            coord_bot=coord_bot,
            section=col.section,
            width_mm=width_mm,
            depth_mm=depth_mm,
        )

        def _append_beams_for_joint(target_joint_name: str, is_top: bool):
            if target_joint_name not in joints:
                return

            joint = joints[target_joint_name]

            for bm_label in set(joint.connected_beams):
                bm = beam_index.get(f"{joint.story}|{bm_label}")
                if not bm:
                    bm = next((b for b in beams if b.label == bm_label and b.story == joint.story), None)
                if not bm:
                    continue
                if not bm.coord_i or not bm.coord_j:
                    continue

                if bm.jt_i == target_joint_name:
                    other = bm.coord_j
                elif bm.jt_j == target_joint_name:
                    other = bm.coord_i
                else:
                    continue

                dx = other[0] - joint.x
                dy = other[1] - joint.y
                beam_angle = math.degrees(math.atan2(dy, dx)) % 360

                if 45 <= beam_angle < 135:
                    beam_dir = "Y"
                elif 135 <= beam_angle < 225:
                    beam_dir = "X"
                elif 225 <= beam_angle < 315:
                    beam_dir = "Y"
                else:
                    beam_dir = "X"

                ex_mm = (joint.x - center_x) * 1000
                ey_mm = (joint.y - center_y) * 1000

                tol = 100.0
                if abs(ex_mm) < tol and abs(ey_mm) < tol:
                    side = ConnectionSide.CENTER
                elif abs(ex_mm) > tol and abs(ey_mm) > tol:
                    side = ConnectionSide.CORNER
                elif abs(ex_mm) >= abs(ey_mm):
                    side = ConnectionSide.RIGHT if ex_mm > 0 else ConnectionSide.LEFT
                else:
                    side = ConnectionSide.FRONT if ey_mm > 0 else ConnectionSide.BACK

                conn = BeamConnectionInfo(
                    beam_label=bm.label,
                    column_label=col.label,
                    joint_name=target_joint_name,
                    joint_coord=(joint.x, joint.y, joint.z),
                    connection_side=side,
                    eccentricity_mm=(round(ex_mm, 1), round(ey_mm, 1)),
                    beam_direction=beam_dir,
                    beam_angle_deg=round(beam_angle, 1),
                    is_primary_direction=beam_dir in ["X", "Y"],
                )

                if is_top:
                    cmap.beams_at_top.append(conn)
                else:
                    cmap.beams_at_bot.append(conn)

        # TOP JOINT HER ZAMAN
        _append_beams_for_joint(top_jt, is_top=True)

        # BOTTOM JOINT SADECE AYNI KATSA
        if bot_jt in joints and joints[bot_jt].story == col.story:
            _append_beams_for_joint(bot_jt, is_top=False)

        if cmap.beams_at_top or cmap.beams_at_bot:
            column_beam_map[f"{col.story}|{col.label}"] = cmap

    debug["column_beam_map_size"] = len(column_beam_map)

    return TopologyResult(
        frames=frames,
        columns=columns,
        beams=beams,
        joints=joints,
        column_beam_map=column_beam_map,
        warnings=warnings,
        debug_info=debug,
    )

# ============================================================================
# CONFINEMENT ANALYSIS
# ============================================================================

def analyze_confinement(topology: TopologyResult) -> Dict[str, Any]:
    joint_analysis = {}
    summary = {"total": 0, "confined": 0, "partial": 0, "unconfined": 0, "unknown": 0}
    unconfined_joints = []

    for name, joint in topology.joints.items():
        summary["total"] += 1

        if joint.confinement_status == "CONFINED":
            summary["confined"] += 1
        elif joint.confinement_status == "PARTIAL":
            summary["partial"] += 1
        elif joint.confinement_status == "UNCONFINED":
            summary["unconfined"] += 1
            unconfined_joints.append({
                "name": name,
                "story": joint.story,
                "n_beams": joint.n_beams,
                "n_columns": joint.n_columns,
            })
        else:
            summary["unknown"] += 1

        joint_analysis[name] = {
            "story": joint.story,
            "joint_type": joint.joint_type.value,
            "confinement": joint.confinement_status,
            "n_beams": joint.n_beams,
            "n_columns": joint.n_columns,
            "beams": list(set(joint.connected_beams)),
            "columns": list(set(joint.connected_columns)),
            "coordinates": {"x": round(joint.x, 3), "y": round(joint.y, 3), "z": round(joint.z, 3)},
        }

    return {
        "joints": joint_analysis,
        "summary": summary,
        "unconfined_joints": unconfined_joints,
    }


# ============================================================================
# DETAILED SCWB CALCULATION
# ============================================================================

def calculate_scwb_detailed(
    topology: TopologyResult,
    col_forces: List[Dict[str, Any]],
    beam_forces: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    SCWB detailed approximation.
    """
    col_end_moments: Dict[str, Dict[str, float]] = {}

    for row in col_forces:
        col = _as_str(_first_existing(row, [
            "Column", "Frame", "Label", "UniqueName", "Element Name", "ElmName", "ObjLabel"
        ]))
        if not col:
            continue

        station = _as_float(row.get("Station", 0))
        M2 = _as_float(row.get("M2", 0))
        M3 = _as_float(row.get("M3", 0))
        M = math.sqrt(M2 * M2 + M3 * M3)

        if col not in col_end_moments:
            col_end_moments[col] = {"top": 0, "bottom": 0}

        if station < 0.01:
            col_end_moments[col]["bottom"] = max(col_end_moments[col]["bottom"], abs(M))
        else:
            col_end_moments[col]["top"] = max(col_end_moments[col]["top"], abs(M))

    beam_moments: Dict[str, float] = {}
    for row in beam_forces:
        beam = _as_str(_first_existing(row, [
            "Beam", "Frame", "Label", "UniqueName", "Element Name", "ElmName", "ObjLabel"
        ]))
        if not beam:
            continue
        M2 = _as_float(row.get("M2", 0))
        M3 = _as_float(row.get("M3", 0))
        M = math.sqrt(M2 * M2 + M3 * M3)
        beam_moments[beam] = max(beam_moments.get(beam, 0), abs(M))

    results = []

    for col_label, cmap in topology.column_beam_map.items():
        col_M = col_end_moments.get(col_label, {"top": 0, "bottom": 0})

        top_beams = [c.beam_label for c in cmap.beams_at_top if c.is_primary_direction]
        M_beam_top = sum(beam_moments.get(b, 0) for b in top_beams)
        M_col_top = col_M["top"] if col_M["top"] > 0 else max(col_M["top"], col_M["bottom"])
        ratio_top = M_col_top / (1.2 * M_beam_top) if M_beam_top > 0 else None
        status_top = "OK" if ratio_top and ratio_top >= 1.0 else ("FAIL" if ratio_top else "NO_BEAM")

        bot_beams = [c.beam_label for c in cmap.beams_at_bot if c.is_primary_direction]
        M_beam_bot = sum(beam_moments.get(b, 0) for b in bot_beams)
        M_col_bot = col_M["bottom"] if col_M["bottom"] > 0 else max(col_M["top"], col_M["bottom"])
        ratio_bot = M_col_bot / (1.2 * M_beam_bot) if M_beam_bot > 0 else None
        status_bot = "OK" if ratio_bot and ratio_bot >= 1.0 else ("FAIL" if ratio_bot else "NO_BEAM")

        if status_top == "FAIL" or status_bot == "FAIL":
            overall = "FAIL"
        elif status_top == "NO_BEAM" and status_bot == "NO_BEAM":
            overall = "NO_BEAM"
        else:
            overall = "OK"

        results.append({
            "column": col_label,
            "story": cmap.story,
            "section": cmap.section,
            "joint_top": cmap.joint_top,
            "M_col_top": round(M_col_top, 2),
            "M_beam_top": round(M_beam_top, 2),
            "ratio_top": round(ratio_top, 4) if ratio_top else None,
            "status_top": status_top,
            "beams_top": top_beams,
            "joint_bot": cmap.joint_bot,
            "M_col_bot": round(M_col_bot, 2),
            "M_beam_bot": round(M_beam_bot, 2),
            "ratio_bot": round(ratio_bot, 4) if ratio_bot else None,
            "status_bot": status_bot,
            "beams_bot": bot_beams,
            "status": overall,
            "level": "SCWB detailed approximation",
            "tbdy_ref": "TBDY 2018 §7.3.5",
            "note": "Joint-based moment check only; envelope & full joint capacity not considered.",
        })

    priority = {"FAIL": 0, "NO_BEAM": 1, "OK": 2}
    results.sort(key=lambda x: priority.get(x["status"], 3))
    return results


# ============================================================================
# JOINT SHEAR SCREENING
# ============================================================================

def calculate_joint_shear_screening(
    topology: TopologyResult,
    col_forces: List[Dict[str, Any]],
    beam_forces: List[Dict[str, Any]],
    fck: float = 35.0,
) -> List[Dict[str, Any]]:
    col_shears: Dict[str, float] = {}
    for row in col_forces:
        col = _as_str(_first_existing(row, [
            "Column", "Frame", "Label", "UniqueName", "Element Name", "ElmName", "ObjLabel"
        ]))
        if not col:
            continue
        V2 = abs(_as_float(row.get("V2", 0)))
        V3 = abs(_as_float(row.get("V3", 0)))
        col_shears[col] = max(col_shears.get(col, 0), V2, V3)

    beam_moments: Dict[str, float] = {}
    for row in beam_forces:
        beam = _as_str(_first_existing(row, [
            "Beam", "Frame", "Label", "UniqueName", "Element Name", "ElmName", "ObjLabel"
        ]))
        if not beam:
            continue
        M2 = abs(_as_float(row.get("M2", 0)))
        M3 = abs(_as_float(row.get("M3", 0)))
        beam_moments[beam] = max(beam_moments.get(beam, 0), M2, M3)

    results = []
    beam_index = {b.label: b for b in topology.beams}

    for joint_name, joint in topology.joints.items():
        if joint.n_beams == 0:
            continue

        column_label = joint.connected_columns[0] if joint.connected_columns else None
        if not column_label:
            continue

        col = next((c for c in topology.columns if c.label == column_label), None)
        if not col:
            continue

        V_col = col_shears.get(column_label, 0)

        V_beam_total = 0.0
        for bm_label in set(joint.connected_beams):
            M_beam = beam_moments.get(bm_label, 0)
            bm = beam_index.get(bm_label)
            L_beam = bm.length_m if bm and bm.length_m > 0 else 4.0
            V_beam_total += M_beam / L_beam if L_beam > 0 else 0

        V_joint = max(V_beam_total - V_col, 0)

        width_mm, depth_mm = parse_section_dims(col.section)
        V_max = 1.7 * 1.0 * math.sqrt(fck) * width_mm * depth_mm / 1000

        ratio = V_joint / V_max if V_max > 0 else 0
        status = "OK" if ratio <= 1.0 else "FAIL"

        results.append({
            "joint": joint_name,
            "story": joint.story,
            "column": column_label,
            "section": col.section,
            "V_joint_kN": round(V_joint, 2),
            "V_col_kN": round(V_col, 2),
            "V_beam_kN": round(V_beam_total, 2),
            "b_j_mm": round(width_mm, 0),
            "h_j_mm": round(depth_mm, 0),
            "V_max_kN": round(V_max, 2),
            "ratio": round(ratio, 4),
            "status": status,
            "confinement": joint.confinement_status,
            "n_beams": joint.n_beams,
            "beams": list(set(joint.connected_beams)),
            "source": "Screening",
            "level": "Joint shear screening (no reinforcement)",
            "tbdy_ref": "TBDY 2018 §7.4.5",
            "warning": "Screening only - reinforcement and confinement factor not included",
        })

    priority = {"FAIL": 0, "OK": 1}
    results.sort(key=lambda x: priority.get(x["status"], 2))
    return results


# ============================================================================
# PRODUCTION GRADE - SCWB / JOINT SHEAR / TOPOLOGY HELPERS
# ============================================================================

def _coord_distance(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _frame_length_from_coords(frame: FrameInfo) -> float:
    if frame.coord_i and frame.coord_j:
        return _coord_distance(frame.coord_i, frame.coord_j)
    return frame.length_m or 0.0


def _joint_matches_coord(
    coord_a: Tuple[float, float, float],
    coord_b: Tuple[float, float, float],
    member_length: float = 0.0,
) -> bool:
    """
    Coordinate match with a model-scale tolerance.

    ETABS table coordinates are usually clean, but rounding differs by table.
    Use max(5 mm, 0.1% of member length), capped at 50 mm.
    """
    tol = max(0.005, min(0.05, abs(member_length) * 0.001))
    return _coord_distance(coord_a, coord_b) <= tol


def _beam_end_at_joint(bm: FrameInfo, joint_coord: Tuple[float, float, float]) -> Optional[str]:
    """
    Return 'i' or 'j' if the joint coordinate coincides with a beam end.
    """
    if not bm.coord_i or not bm.coord_j:
        return None
    length = _frame_length_from_coords(bm)
    if _joint_matches_coord(joint_coord, bm.coord_i, length):
        return "i"
    if _joint_matches_coord(joint_coord, bm.coord_j, length):
        return "j"
    return None


def _beam_direction_signed(
    bm: FrameInfo,
    joint_coord: Tuple[float, float, float],
) -> Optional[str]:
    """
    Beam direction relative to the joint, with sign.

    Returns '+X', '-X', '+Y', '-Y', or None.

    Rule:
    - If joint is at i-end, vector points from i -> j.
    - If joint is at j-end, vector points from j -> i.
    - Dominant horizontal component defines axis.
    - Very short horizontal projection is ignored.
    """
    if not bm.coord_i or not bm.coord_j:
        return None

    end = _beam_end_at_joint(bm, joint_coord)
    if end == "i":
        dx = bm.coord_j[0] - joint_coord[0]
        dy = bm.coord_j[1] - joint_coord[1]
    elif end == "j":
        dx = bm.coord_i[0] - joint_coord[0]
        dy = bm.coord_i[1] - joint_coord[1]
    else:
        return None

    horizontal = math.sqrt(dx * dx + dy * dy)
    if horizontal < 0.01:
        return None

    if abs(dx) >= abs(dy):
        return "+X" if dx > 0 else "-X"
    return "+Y" if dy > 0 else "-Y"


def build_joint_model(topology: TopologyResult) -> Dict[str, Dict[str, Any]]:
    """
    Build a compute-ready joint model for SCWB and joint shear.

    Output contract:
    {
        joint_name: {
            "joint": joint_name,
            "story": story,
            "coord": (x, y, z),
            "beams": {"+X": [...], "-X": [...], "+Y": [...], "-Y": [...]},
            "beam_items": {
                "+X": [{"beam": "B1", "end": "i", "signed": "+X"}],
                ...
            },
            "columns_up": [...],
            "columns_down": [...],
            "connected_columns": [...],
        }
    }

    Only frame joints with at least one column and one beam are included.
    """
    beam_dict = {b.label: b for b in topology.beams}
    column_dict = {c.label: c for c in topology.columns}

    joint_model: Dict[str, Dict[str, Any]] = {}

    for name, jt in topology.joints.items():
        if jt.n_columns < 1 or jt.n_beams < 1:
            continue

        joint_coord = (jt.x, jt.y, jt.z)
        node = {
            "joint": name,
            "story": jt.story,
            "coord": joint_coord,
            "beams": {"+X": [], "-X": [], "+Y": [], "-Y": []},
            "beam_items": {"+X": [], "-X": [], "+Y": [], "-Y": []},
            "columns_up": [],
            "columns_down": [],
            "connected_columns": list(set(jt.connected_columns)),
        }

        for bm_label in set(jt.connected_beams):
            bm = beam_dict.get(bm_label)
            if not bm:
                continue
            signed = _beam_direction_signed(bm, joint_coord)
            end = _beam_end_at_joint(bm, joint_coord)
            if not signed or not end:
                continue
            node["beams"][signed].append(bm_label)
            node["beam_items"][signed].append({"beam": bm_label, "end": end, "signed": signed})

        for col_label in set(jt.connected_columns):
            col = column_dict.get(col_label)
            if not col or not col.coord_i or not col.coord_j:
                continue

            z_joint = jt.z
            z_i = col.coord_i[2]
            z_j = col.coord_j[2]
            z_bot = min(z_i, z_j)
            z_top = max(z_i, z_j)
            tol_z = max(0.01, min(0.05, abs(z_top - z_bot) * 0.001))

            if z_top > z_joint + tol_z and col_label not in node["columns_up"]:
                node["columns_up"].append(col_label)
            if z_bot < z_joint - tol_z and col_label not in node["columns_down"]:
                node["columns_down"].append(col_label)

        if sum(len(v) for v in node["beams"].values()) > 0:
            joint_model[name] = node

    return joint_model


def get_analysis_joints(topology: TopologyResult) -> List[Dict[str, Any]]:
    """
    API/report friendly summary of design-relevant frame joints.
    """
    joint_model = build_joint_model(topology)
    result: List[Dict[str, Any]] = []

    for jt_name, node in joint_model.items():
        beam_dirs = [d for d in ["+X", "-X", "+Y", "-Y"] if node["beams"][d]]
        has_opp_x = bool(node["beams"]["+X"] and node["beams"]["-X"])
        has_opp_y = bool(node["beams"]["+Y"] and node["beams"]["-Y"])

        if has_opp_x and has_opp_y:
            confinement = "CONFINED"
        elif has_opp_x or has_opp_y:
            confinement = "PARTIAL"
        elif beam_dirs:
            confinement = "UNCONFINED"
        else:
            confinement = "UNKNOWN"

        result.append({
            "joint_name": jt_name,
            "story": node["story"],
            "x": round(node["coord"][0], 3),
            "y": round(node["coord"][1], 3),
            "z": round(node["coord"][2], 3),
            "beam_directions": beam_dirs,
            "has_opposing_x": has_opp_x,
            "has_opposing_y": has_opp_y,
            "columns_up": node["columns_up"],
            "columns_down": node["columns_down"],
            "connected_columns": node["connected_columns"],
            "connected_beams": sorted(set(sum((node["beams"][d] for d in ["+X", "-X", "+Y", "-Y"]), []))),
            "confinement": confinement,
            "n_beams": sum(len(v) for v in node["beams"].values()),
            "n_columns": len(set(node["columns_up"] + node["columns_down"] + node["connected_columns"])),
        })

    return result


def get_column_beam_mapping_summary(topology: TopologyResult) -> List[Dict[str, Any]]:
    """
    Column-based beam connection summary, with signed beam directions and beam end.
    The 'items' entries are used by SCWB to pick the correct i/j beam end moment.
    """
    joint_model = build_joint_model(topology)
    mapping: List[Dict[str, Any]] = []

    def _empty_axis_payload(axis: str) -> Dict[str, Any]:
        if axis == "X":
            return {"+X": [], "-X": [], "beams": [], "items": [], "count": 0, "has_opposing": False}
        return {"+Y": [], "-Y": [], "beams": [], "items": [], "count": 0, "has_opposing": False}

    def _payload_for_node(node: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        payload = {"X": _empty_axis_payload("X"), "Y": _empty_axis_payload("Y")}
        if not node:
            return payload

        for signed in ["+X", "-X", "+Y", "-Y"]:
            axis = "X" if signed.endswith("X") else "Y"
            for label in node["beams"][signed]:
                payload[axis][signed].append(label)
                payload[axis]["beams"].append(label)
            for item in node["beam_items"][signed]:
                payload[axis]["items"].append(item.copy())

        payload["X"]["count"] = len(payload["X"]["beams"])
        payload["Y"]["count"] = len(payload["Y"]["beams"])
        payload["X"]["has_opposing"] = bool(payload["X"]["+X"] and payload["X"]["-X"])
        payload["Y"]["has_opposing"] = bool(payload["Y"]["+Y"] and payload["Y"]["-Y"])
        return payload

    for col in topology.columns:
        item = {
            "column": col.label,
            "story": col.story,
            "section": col.section,
            "joint_top": col.top_joint,
            "joint_bot": col.bottom_joint,
            "beams_at_top": _payload_for_node(joint_model.get(col.top_joint or "")),
            "beams_at_bot": _payload_for_node(joint_model.get(col.bottom_joint or "")),
        }
        mapping.append(item)

    return mapping


def recompute_confinement_for_analysis(topology: TopologyResult) -> Dict[str, str]:
    """
    Recompute confinement on analysis/design joints only.
    """
    joint_model = build_joint_model(topology)
    result: Dict[str, str] = {}

    for jt_name, node in joint_model.items():
        has_x_pos = bool(node["beams"]["+X"])
        has_x_neg = bool(node["beams"]["-X"])
        has_y_pos = bool(node["beams"]["+Y"])
        has_y_neg = bool(node["beams"]["-Y"])

        x_confined = has_x_pos and has_x_neg
        y_confined = has_y_pos and has_y_neg

        if x_confined and y_confined:
            result[jt_name] = "CONFINED"
        elif x_confined or y_confined:
            result[jt_name] = "PARTIAL"
        elif has_x_pos or has_x_neg or has_y_pos or has_y_neg:
            result[jt_name] = "UNCONFINED"
        else:
            result[jt_name] = "UNKNOWN"

    return result

