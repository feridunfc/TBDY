from __future__ import annotations

from typing import Any, Dict, List


def _to_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if hasattr(obj, "as_dict"):
        return obj.as_dict()
    if hasattr(obj, "__dict__"):
        return dict(vars(obj))
    return {}


class EngineContractValidator:
    """
    Backward-compatible validator.

    Supports both call forms:
      EngineContractValidator(runtime_catalog)
      EngineContractValidator(contract_bundle, runtime_catalog)
    """

    def __init__(self, contract_obj: Any, runtime_catalog: Any | None = None):
        self.contract_obj = runtime_catalog if runtime_catalog is not None else contract_obj
        self.bundle = contract_obj if runtime_catalog is not None else None

    def _catalog_dict(self) -> Dict[str, Any]:
        data = _to_dict(self.contract_obj)

        # RuntimeCatalog shape
        if "checks" in data and "evaluations" in data:
            return data

        # ContractBundle shape fallback
        checks = _to_dict(getattr(self.contract_obj, "checks", None))
        evaluations = _to_dict(getattr(self.contract_obj, "evaluations", None))
        datasets = _to_dict(getattr(self.contract_obj, "datasets", None))
        combos = _to_dict(getattr(self.contract_obj, "combos", None))
        reports = _to_dict(getattr(self.contract_obj, "reports", None))

        return {
            "checks": checks.get("checks", {}),
            "evaluations": evaluations.get("evaluations", {}),
            "datasets": datasets.get("datasets", {}),
            "combo_families": combos.get("combo_families", {}),
            "reports": reports.get("reports", {}),
            "warnings": data.get("warnings", []),
        }

    def validate(self) -> List[str]:
        errors: List[str] = []
        catalog = self._catalog_dict()

        checks_raw = catalog.get("checks", {}) or {}
        evaluations = catalog.get("evaluations", {}) or {}
        datasets = catalog.get("datasets", {}) or {}
        combo_families = catalog.get("combo_families", {}) or {}

        # checks may be dict[id -> item] or list[CheckSpec]
        if isinstance(checks_raw, list):
            checks = {}
            seen = set()
            for item in checks_raw:
                item_d = _to_dict(item)
                cid = item_d.get("id")
                if not cid:
                    errors.append("Check item missing id")
                    continue
                if cid in seen:
                    errors.append(f"Duplicate check id: {cid}")
                seen.add(cid)
                checks[cid] = item_d
        else:
            checks = {k: _to_dict(v) for k, v in checks_raw.items()}

        for check_id, check in checks.items():
            evaluation = check.get("evaluation")
            if not evaluation:
                errors.append(f"{check_id}: missing evaluation")
                continue

            if evaluation not in evaluations:
                errors.append(f"{check_id}: evaluation not found: {evaluation}")

            tbdy_ref = check.get("tbdy_ref", "N/A")
            if not tbdy_ref:
                errors.append(f"{check_id}: missing tbdy_ref")

            uses_combo = check.get("uses_combo") or check.get("combo_families") or []
            if isinstance(uses_combo, str):
                uses_combo = [uses_combo]

            for family in uses_combo:
                if family not in combo_families:
                    errors.append(f"{check_id}: combo family not found: {family}")

            required_datasets = check.get("required_datasets") or []
            if isinstance(required_datasets, str):
                required_datasets = [required_datasets]

            for ds in required_datasets:
                if ds not in datasets:
                    errors.append(f"{check_id}: dataset not found: {ds}")

            runner_enabled = check.get("runner_enabled", True)
            if runner_enabled and evaluation in evaluations:
                ev_d = _to_dict(evaluations[evaluation])
                if not ev_d.get("enabled", True):
                    errors.append(
                        f"{check_id}: runner_enabled=True but evaluation {evaluation} is disabled"
                    )

        for eval_id, evaluation in evaluations.items():
            ev_d = _to_dict(evaluation)
            if ev_d.get("enabled", True):
                if not ev_d.get("module"):
                    errors.append(f"{eval_id}: enabled evaluation missing module")
                if not ev_d.get("method"):
                    errors.append(f"{eval_id}: enabled evaluation missing method")

        return errors

    def health_report(self) -> Dict[str, Any]:
        errors = self.validate()
        catalog = self._catalog_dict()
        return {
            "check_count": len(catalog.get("checks", {}) or {}),
            "evaluation_count": len(catalog.get("evaluations", {}) or {}),
            "dataset_count": len(catalog.get("datasets", {}) or {}),
            "combo_family_count": len(catalog.get("combo_families", {}) or {}),
            "warnings": catalog.get("warnings", []) or [],
            "errors": errors,
        }
