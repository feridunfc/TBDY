from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Tuple
from .models import CheckSpec, ComboFamilySpec, CombosContract, ContractBundle

LEGACY_ID_MAP = {
    "COLUMNS02_COLUMN_AXIAL": "column_axial",
    "COLUMNS01_COLUMN_DESIGN_SUMMARY": "column_pmm",
    "COLUMNS03_COLUMN_LONGITUDINAL_REBAR": "column_rebar_minimum",
    "COLUMNS04_COLUMN_SHEAR_CAPACITY": "column_shear",
    "COLUMNS05_SCWB": "column_capacity_hierarchy",
    "B01_BEAM_DESIGN_SUMMARY": "beam_flexure",
    "B02_BEAM_FLEXURE_DUCTILE": "beam_ductility",
    "B03_BEAM_SHEAR_CAPACITY": "beam_shear",
    "W01_WALL_DESIGN_SUMMARY": "wall_axial_flexure",
    "W02_WALL_BOUNDARY_ZONE": "wall_boundary_zone",
    "W03_WALL_SHEAR_CAPACITY": "wall_shear",
    "W04_WALL_MIN_REBAR": "wall_web_reinforcement",
    "J01_JOINT_SHEAR_SUMMARY": "joint_shear",
    "A01_MODAL_MASS_PARTICIPATION": "global_modal_mass",
    "A02_BASE_SHEAR_SCALING": "global_base_shear_scaling",
    "A03_STORY_DRIFT": "global_story_drift",
    "A04_A1_TORSIONAL_IRREGULARITY": "global_a1_torsion",
}
CANONICAL_NAME_MAP = {
    "column_axial_screen": "column_axial",
    "column_design_summary_screen": "column_pmm",
    "beam_design_summary_screen": "beam_flexure",
    "beam_shear_capacity_screen": "beam_shear",
    "wall_shear_capacity_screen": "wall_shear",
    "story_drift_screen": "global_story_drift",
}
def _as_list(v: Any) -> List[Any]:
    if v is None: return []
    if isinstance(v, (list, tuple, set)): return list(v)
    return [v]
def _merge_unique(existing: List[str], values: Iterable[Any]) -> List[str]:
    out = list(existing or [])
    for v in values or []:
        if v is None: continue
        s = str(v)
        if s and s not in out: out.append(s)
    return out
def normalize_runtime_check_id(raw_id: str) -> str:
    if not raw_id: return ""
    if raw_id in LEGACY_ID_MAP: return LEGACY_ID_MAP[raw_id]
    low = raw_id.strip().lower()
    if low in CANONICAL_NAME_MAP: return CANONICAL_NAME_MAP[low]
    return raw_id
def normalize_combo_family(value: str) -> str:
    u = str(value or "").strip().upper()
    if u in {"G_SERV", "G_ULT", "G"}: return "G"
    if u in {"S_E1", "S_E2", "S_E1_U", "S_E2_U", "S_E"}: return "S_E"
    if u in {"K_E1", "K_E2", "K_E1_U", "K_E2_U", "K_E"}: return "K_E"
    if u in {"D_E1", "D_E2", "DISP_X", "DISP_Y", "DRIFT"}: return "DRIFT"
    if u in {"Z_ULT", "Z_UP", "SOIL"}: return "SOIL"
    return u

class LegacyContractMigrator:
    """In-memory enrichment. Runtime YAML files are never overwritten."""
    def __init__(self) -> None:
        self.warnings: List[str] = []
    def enrich_bundle(self, bundle: ContractBundle) -> ContractBundle:
        enriched = deepcopy(bundle)
        self.warnings = list(enriched.warnings or [])
        index = {c.id: c for c in enriched.checks.checks}
        self._merge_check_contract(enriched.legacy_raw.get("check_contract.yaml"), index)
        self._merge_detailed_checklist(enriched.legacy_raw.get("detailed_checklist.yaml"), index)
        self._merge_combo_contract(enriched.legacy_raw.get("combo_contract.yaml"), enriched.combos)
        self._merge_combo_usage(enriched.legacy_raw.get("combo_usage_matrix.yaml"), index)
        enriched.warnings = _merge_unique(enriched.warnings, self.warnings)
        return enriched
    def _iter_records(self, raw: Any):
        records: List[Tuple[str, Dict[str, Any]]] = []
        if raw is None: return records
        if isinstance(raw, dict):
            candidates = raw.get("checks") or raw.get("items") or raw.get("contracts")
            if isinstance(candidates, list):
                for item in candidates:
                    if isinstance(item, dict):
                        records.append((str(item.get("id") or item.get("check_id") or item.get("contract_id") or ""), item))
            elif isinstance(candidates, dict):
                records += [(str(k), v) for k, v in candidates.items() if isinstance(v, dict)]
            else:
                records += [(str(k), v) for k, v in raw.items() if isinstance(v, dict) and k not in {"version", "metadata"}]
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    records.append((str(item.get("id") or item.get("check_id") or item.get("contract_id") or ""), item))
        return records
    def _target(self, key: str, rec: Dict[str, Any]) -> str:
        for c in [key, rec.get("id"), rec.get("check_id"), rec.get("contract_id"), rec.get("legacy_contract_id"), rec.get("canonical_check_name"), rec.get("canonical_name"), rec.get("runtime_check_id")]:
            if c:
                return normalize_runtime_check_id(str(c))
        return ""
    def _merge_check_contract(self, raw: Any, index: Dict[str, CheckSpec]) -> None:
        for key, rec in self._iter_records(raw):
            target = self._target(key, rec)
            check = index.get(target)
            if not check:
                self.warnings.append(f"Legacy check_contract item '{key}' mapped to '{target}', but no runtime parent check exists.")
                continue
            check.implementation_status = str(rec.get("implementation_status") or rec.get("status") or check.implementation_status or "")
            if "runner_enabled" in rec: check.runner_enabled = bool(rec.get("runner_enabled"))
            check.category = str(rec.get("category") or check.category)
            check.tbdy_ref = str(rec.get("tbdy_ref") or rec.get("reference") or check.tbdy_ref or "N/A")
            check.required_tables = _merge_unique(check.required_tables, _as_list(rec.get("required_tables")))
            check.required_context = _merge_unique(check.required_context, _as_list(rec.get("required_context")))
            check.report_outputs = _merge_unique(check.report_outputs, _as_list(rec.get("report_outputs")))
            check.legacy_contract_id = str(rec.get("legacy_contract_id") or rec.get("contract_id") or key or check.legacy_contract_id)
            check.legacy_canonical_check_name = str(rec.get("canonical_check_name") or rec.get("canonical_name") or check.legacy_canonical_check_name)
            check.source_files = _merge_unique(check.source_files, ["check_contract.yaml"])
    def _merge_detailed_checklist(self, raw: Any, index: Dict[str, CheckSpec]) -> None:
        for key, rec in self._iter_records(raw):
            parent = str(rec.get("parent_check") or rec.get("parent") or rec.get("check_id") or rec.get("runtime_check_id") or "")
            target = normalize_runtime_check_id(parent) if parent else self._target(key, rec)
            check = index.get(target)
            if not check:
                self.warnings.append(f"Detailed checklist item '{key}' has no runtime parent check; not added blindly.")
                continue
            sid = str(rec.get("id") or rec.get("sub_check_id") or rec.get("name") or key or "")
            if sid: check.sub_checks = _merge_unique(check.sub_checks, [sid])
            check.source_files = _merge_unique(check.source_files, ["detailed_checklist.yaml"])
    def _merge_combo_contract(self, raw: Any, combos: CombosContract) -> None:
        if raw is None: return
        candidates: Dict[str, Any] = {}
        if isinstance(raw, dict):
            for key in ["combo_families", "combos", "groups"]:
                if isinstance(raw.get(key), dict):
                    candidates.update(raw[key])
            if not candidates:
                candidates = {str(k): v for k, v in raw.items() if isinstance(v, dict) and k not in {"version", "metadata"}}
        for key, rec in candidates.items():
            fam = normalize_combo_family(key)
            if not fam: continue
            cur = combos.combo_families.get(fam) or ComboFamilySpec()
            if isinstance(rec, dict):
                cur.description = str(rec.get("description") or rec.get("name") or cur.description)
                cur.combos = _merge_unique(cur.combos, _as_list(rec.get("combos") or rec.get("combinations") or rec.get("items")))
                cur.legacy_groups = _merge_unique(cur.legacy_groups, [key])
                if isinstance(rec.get("aliases"), dict):
                    cur.aliases.update({str(k): str(v) for k, v in rec["aliases"].items()})
                for bf in ["cracked", "seismic", "vertical_eq", "serviceability"]:
                    if bf in rec: setattr(cur, bf, bool(rec.get(bf)))
            combos.combo_families[fam] = cur
    def _merge_combo_usage(self, raw: Any, index: Dict[str, CheckSpec]) -> None:
        if raw is None: return
        usage = raw.get("check_combo_requirements") or raw.get("combo_usage") or raw.get("usage") or raw.get("checks") or raw if isinstance(raw, dict) else raw
        if isinstance(usage, dict): items = usage.items()
        elif isinstance(usage, list): items = [(str(i.get("check_id") or i.get("id") or ""), i) for i in usage if isinstance(i, dict)]
        else: items = []
        for key, value in items:
            target = normalize_runtime_check_id(str(key))
            check = index.get(target)
            if not check:
                self.warnings.append(f"Combo usage item '{key}' mapped to '{target}', but no runtime check exists.")
                continue
            vals = []
            if isinstance(value, dict):
                vals.extend(_as_list(value.get("uses_combo") or value.get("combo_families") or value.get("families") or value.get("required_combos")))
            else:
                vals.extend(_as_list(value))
            norm = [normalize_combo_family(v) for v in vals if v]
            check.uses_combo = _merge_unique(check.uses_combo, norm)
            check.combo_families = _merge_unique(check.combo_families, norm)
            check.source_files = _merge_unique(check.source_files, ["combo_usage_matrix.yaml"])
