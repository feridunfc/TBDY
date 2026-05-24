from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict
import yaml
from .migrator import LegacyContractMigrator
from .models import ChecksContract, CombosContract, ContractBundle, DatasetsContract, EvaluationsContract, ReportsContract, model_to_dict
from .runtime_catalog import RuntimeCatalogBuilder
RUNTIME_FILES = {"datasets": "datasets.yaml", "evaluations": "evaluations.yaml", "checks": "checks.yaml", "combos": "combos.yaml", "reports": "reports.yaml"}
LEGACY_FILES = ["check_contract.yaml", "detailed_checklist.yaml", "combo_contract.yaml", "combo_usage_matrix.yaml"]
def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists(): return {}
    with path.open("r", encoding="utf-8-sig") as f:
        data = yaml.safe_load(f)
    if data is None: return {}
    if not isinstance(data, dict): raise ValueError(f"YAML root must be a mapping: {path}")
    return data
class EngineContractLoader:
    def __init__(self, contracts_dir: str | Path, project_root: str | Path | None = None):
        self.contracts_dir = Path(contracts_dir)
        self.project_root = Path(project_root) if project_root is not None else self.contracts_dir.resolve().parents[1]
    @classmethod
    def from_project_root(cls, project_root: str | Path | None = None) -> "EngineContractLoader":
        root = Path(project_root or Path.cwd())
        return cls(root / "tbdy_engine" / "contracts", project_root=root)
    def load(self, include_legacy: bool = True) -> ContractBundle:
        warnings: list[str] = []
        bundle = ContractBundle(
            datasets=DatasetsContract(**_read_yaml(self.contracts_dir / RUNTIME_FILES["datasets"])),
            evaluations=EvaluationsContract(**_read_yaml(self.contracts_dir / RUNTIME_FILES["evaluations"])),
            checks=ChecksContract(**_read_yaml(self.contracts_dir / RUNTIME_FILES["checks"])),
            combos=CombosContract(**_read_yaml(self.contracts_dir / RUNTIME_FILES["combos"])),
            reports=ReportsContract(**_read_yaml(self.contracts_dir / RUNTIME_FILES["reports"])),
            legacy_raw=self._load_legacy_raw(warnings) if include_legacy else {},
            warnings=warnings)
        if include_legacy and bundle.legacy_raw:
            bundle = LegacyContractMigrator().enrich_bundle(bundle)
        return bundle
    def build_runtime_catalog(self, include_legacy: bool = True):
        return RuntimeCatalogBuilder(self.load(include_legacy=include_legacy)).build()
    def _load_legacy_raw(self, warnings: list[str]) -> Dict[str, Any]:
        raw: Dict[str, Any] = {}
        for fn in LEGACY_FILES:
            for directory in [self.contracts_dir / "legacy", self.project_root / "tbdy_engine" / "checks"]:
                path = directory / fn
                if path.exists():
                    try: raw[fn] = _read_yaml(path)
                    except Exception as exc: warnings.append(f"Could not load legacy YAML {path}: {exc}")
                    break
        return raw
def dump_runtime_catalog_json(catalog: Any, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(model_to_dict(catalog), f, ensure_ascii=False, indent=2)
