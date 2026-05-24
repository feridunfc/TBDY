# runtime/validator.py
from __future__ import annotations

from typing import Any, Dict, List


class ContractValidator:
    def __init__(self, datasets=None, evaluations=None, checks=None, combos=None, reports=None):
        self.datasets = datasets or {}
        self.evaluations = evaluations or {}
        self.checks = checks or {}
        self.combos = combos or {}
        self.reports = reports or {}

    def validate(self) -> List[str]:
        errors: List[str] = []

        if "datasets" not in self.datasets:
            errors.append("datasets.yaml missing root key: datasets")

        if "evaluations" not in self.evaluations:
            errors.append("evaluations.yaml missing root key: evaluations")

        if "checks" not in self.checks:
            errors.append("checks.yaml missing root key: checks")

        if "combo_families" not in self.combos:
            errors.append("combos.yaml missing root key: combo_families")

        evals = self.evaluations.get("evaluations", {}) or {}
        eval_ids = set(evals.keys())

        for eval_id, conf in evals.items():
            if conf.get("enabled", True):
                if not conf.get("module"):
                    errors.append(f"Evaluation {eval_id} missing module")
                if not conf.get("method"):
                    errors.append(f"Evaluation {eval_id} missing method")

        combo_families = set((self.combos.get("combo_families") or {}).keys())

        for check in self.checks.get("checks", []) or []:
            cid = check.get("id", "<unknown>")
            ev = check.get("evaluation")
            fallback_ev = check.get("fallback_evaluation")

            if ev and ev not in eval_ids:
                errors.append(f"Check {cid} references missing evaluation: {ev}")

            if fallback_ev and fallback_ev not in eval_ids:
                errors.append(f"Check {cid} references missing fallback_evaluation: {fallback_ev}")

            for family in check.get("combo_families", []) or []:
                if family not in combo_families:
                    errors.append(f"Check {cid} references missing combo family: {family}")

        return errors
