from __future__ import annotations
from typing import List
from .models import ContractBundle, RuntimeCatalog, RuntimeCheckCatalogItem
def _merge_unique(*lists: List[str]) -> List[str]:
    out: List[str] = []
    for vals in lists:
        for v in vals or []:
            if v and v not in out: out.append(v)
    return out
class RuntimeCatalogBuilder:
    def __init__(self, bundle: ContractBundle):
        self.bundle = bundle
        self.warnings: List[str] = list(bundle.warnings or [])
    def build(self) -> RuntimeCatalog:
        evs = self.bundle.evaluations.evaluations
        datasets = self.bundle.datasets.datasets
        combos = self.bundle.combos.combo_families
        checks = {}
        for c in self.bundle.checks.checks:
            ev = evs.get(c.evaluation)
            if not ev:
                self.warnings.append(f"Check '{c.id}' references missing evaluation '{c.evaluation}'.")
                eval_datasets, eval_enabled, eval_exp = [], False, False
            else:
                eval_datasets, eval_enabled, eval_exp = ev.dataset_dependencies(), ev.enabled, ev.experimental
            uses = c.normalized_uses_combo()
            for fam in uses:
                if fam not in combos:
                    self.warnings.append(f"Check '{c.id}' uses combo family '{fam}', but it is not defined in combos.yaml.")
            req_ds = _merge_unique(c.required_datasets, eval_datasets)
            for ds in req_ds:
                root = str(ds).split(".", 1)[0]
                if root not in datasets:
                    self.warnings.append(f"Check '{c.id}' requires dataset '{ds}', but '{root}' is not defined in datasets.yaml.")
            runner_enabled = eval_enabled if c.runner_enabled is None else bool(c.runner_enabled)
            if runner_enabled and not eval_enabled:
                self.warnings.append(f"Check '{c.id}' is runner_enabled but evaluation '{c.evaluation}' is disabled.")
            checks[c.id] = RuntimeCheckCatalogItem(
                id=c.id, evaluation=c.evaluation, evaluation_field=c.evaluation_field,
                fallback_evaluation=c.fallback_evaluation, fallback_fields=c.fallback_fields,
                category=c.category, severity=c.severity, tbdy_ref=c.tbdy_ref or "N/A",
                implementation_status=c.implementation_status, runner_enabled=runner_enabled,
                experimental=bool(c.experimental or eval_exp), required_datasets=req_ds,
                required_tables=c.required_tables, required_context=c.required_context,
                uses_combo=uses, report_outputs=c.report_outputs, sub_checks=c.sub_checks,
                aliases=c.aliases, depends_on_checks=c.depends_on_checks,
                formula=c.formula, formula_detail=c.formula_detail, etabs_canonical=c.etabs_canonical,
                cross_check=c.cross_check, tolerance=c.tolerance, data_source_policy=c.data_source_policy,
                design_required=c.design_required, screening_required=c.screening_required,
                legacy_contract_id=c.legacy_contract_id, legacy_canonical_check_name=c.legacy_canonical_check_name,
                legacy_matrix_key=c.legacy_matrix_key, legacy_notes=c.legacy_notes, source_files=c.source_files)
        return RuntimeCatalog(checks=checks, evaluations=evs, datasets=datasets,
                              combo_families=combos, reports=self.bundle.reports.reports,
                              warnings=_merge_unique(self.warnings))
