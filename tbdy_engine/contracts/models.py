from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
try:
    from pydantic import ConfigDict  # type: ignore
except Exception:
    ConfigDict = None  # type: ignore

def model_to_dict(model: Any) -> Dict[str, Any]:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()

def model_json_schema_compat(model_cls: Any) -> Dict[str, Any]:
    return model_cls.model_json_schema() if hasattr(model_cls, "model_json_schema") else model_cls.schema()

if ConfigDict is not None:
    class ContractBaseModel(BaseModel):
        model_config = ConfigDict(extra="allow")  # type: ignore
else:
    class ContractBaseModel(BaseModel):
        class Config:
            extra = "allow"

class DatasetSpec(ContractBaseModel):
    source: Union[str, Dict[str, Any]]
    required: bool = False
    used_by: List[str] = Field(default_factory=list)
    key_fields: List[str] = Field(default_factory=list)
    description: str = ""

class DatasetsContract(ContractBaseModel):
    version: str = "3.1-alpha"
    datasets: Dict[str, DatasetSpec] = Field(default_factory=dict)

class EvaluationDependsOn(ContractBaseModel):
    datasets: List[str] = Field(default_factory=list)
    optional: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)

class EvaluationSpec(ContractBaseModel):
    enabled: bool = True
    experimental: bool = False
    reason: str = ""
    module: str
    method: str = "run"
    cache_key: Optional[str] = None
    depends_on: Union[EvaluationDependsOn, Dict[str, Any]] = Field(default_factory=EvaluationDependsOn)
    depends_on_results: List[str] = Field(default_factory=list)
    produces: List[str] = Field(default_factory=list)
    output: str = "EvaluationPackage"
    def dataset_dependencies(self) -> List[str]:
        if isinstance(self.depends_on, EvaluationDependsOn):
            return list(self.depends_on.datasets)
        if isinstance(self.depends_on, dict):
            return list(self.depends_on.get("datasets", []) or [])
        return []

class EvaluationsContract(ContractBaseModel):
    version: str = "3.1-alpha"
    evaluations: Dict[str, EvaluationSpec] = Field(default_factory=dict)

class CheckSpec(ContractBaseModel):
    id: str
    evaluation: str
    evaluation_field: str = ""
    fallback_evaluation: str = ""
    fallback_fields: List[str] = Field(default_factory=list)
    tbdy_ref: str = "N/A"
    severity: str = "MEDIUM"
    category: str = "UNCATEGORIZED"
    report_section: str = ""
    uses_combo: List[str] = Field(default_factory=list)
    combo_families: List[str] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list)
    depends_on_checks: List[str] = Field(default_factory=list)
    fail_blocks: List[str] = Field(default_factory=list)
    experimental: bool = False
    implementation_status: str = ""
    runner_enabled: Optional[bool] = None
    required_tables: List[str] = Field(default_factory=list)
    required_context: List[str] = Field(default_factory=list)
    required_datasets: List[str] = Field(default_factory=list)
    report_outputs: List[str] = Field(default_factory=list)
    sub_checks: List[str] = Field(default_factory=list)
    legacy_contract_id: str = ""
    legacy_canonical_check_name: str = ""
    legacy_matrix_key: str = ""
    formula: str = ""
    formula_detail: str = ""
    etabs_canonical: str = ""
    cross_check: bool = False
    tolerance: Dict[str, Any] = Field(default_factory=dict)
    design_required: List[str] = Field(default_factory=list)
    screening_required: List[str] = Field(default_factory=list)
    design_table_required: List[str] = Field(default_factory=list)
    manual_design_required: List[str] = Field(default_factory=list)
    data_source_policy: List[str] = Field(default_factory=list)
    legacy_notes: str = ""
    source_files: List[str] = Field(default_factory=list)
    def normalized_uses_combo(self) -> List[str]:
        out: List[str] = []
        for value in list(self.uses_combo or []) + list(self.combo_families or []):
            if value and value not in out:
                out.append(value)
        return out

class ChecksContract(ContractBaseModel):
    version: str = "3.1-alpha"
    checks: List[CheckSpec] = Field(default_factory=list)

class ComboFamilySpec(ContractBaseModel):
    description: str = ""
    combos: List[str] = Field(default_factory=list)
    legacy_groups: List[str] = Field(default_factory=list)
    aliases: Dict[str, str] = Field(default_factory=dict)
    cracked: Optional[bool] = None
    seismic: Optional[bool] = None
    vertical_eq: Optional[bool] = None
    serviceability: Optional[bool] = None

class CombosContract(ContractBaseModel):
    version: str = "3.1-alpha"
    combo_families: Dict[str, ComboFamilySpec] = Field(default_factory=dict)

class ReportSpec(ContractBaseModel):
    formats: List[str] = Field(default_factory=lambda: ["json"])
    include: List[str] = Field(default_factory=list)
    sections: List[str] = Field(default_factory=list)
    filters: Dict[str, Any] = Field(default_factory=dict)
    include_fields: List[str] = Field(default_factory=list)
    metrics: List[str] = Field(default_factory=list)

class ReportsContract(ContractBaseModel):
    version: str = "3.1-alpha"
    reports: Dict[str, ReportSpec] = Field(default_factory=dict)

class RuntimeCheckCatalogItem(ContractBaseModel):
    id: str
    evaluation: str
    evaluation_field: str = ""
    fallback_evaluation: str = ""
    fallback_fields: List[str] = Field(default_factory=list)
    category: str = "UNCATEGORIZED"
    severity: str = "MEDIUM"
    tbdy_ref: str = "N/A"
    implementation_status: str = ""
    runner_enabled: bool = True
    experimental: bool = False
    required_datasets: List[str] = Field(default_factory=list)
    required_tables: List[str] = Field(default_factory=list)
    required_context: List[str] = Field(default_factory=list)
    uses_combo: List[str] = Field(default_factory=list)
    report_outputs: List[str] = Field(default_factory=list)
    sub_checks: List[str] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list)
    depends_on_checks: List[str] = Field(default_factory=list)
    formula: str = ""
    formula_detail: str = ""
    etabs_canonical: str = ""
    cross_check: bool = False
    tolerance: Dict[str, Any] = Field(default_factory=dict)
    data_source_policy: List[str] = Field(default_factory=list)
    design_required: List[str] = Field(default_factory=list)
    screening_required: List[str] = Field(default_factory=list)
    legacy_contract_id: str = ""
    legacy_canonical_check_name: str = ""
    legacy_matrix_key: str = ""
    legacy_notes: str = ""
    source_files: List[str] = Field(default_factory=list)

class RuntimeCatalog(ContractBaseModel):
    version: str = "3.1-alpha"
    checks: Dict[str, RuntimeCheckCatalogItem] = Field(default_factory=dict)
    evaluations: Dict[str, EvaluationSpec] = Field(default_factory=dict)
    datasets: Dict[str, DatasetSpec] = Field(default_factory=dict)
    combo_families: Dict[str, ComboFamilySpec] = Field(default_factory=dict)
    reports: Dict[str, ReportSpec] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)

class ContractBundle(ContractBaseModel):
    datasets: DatasetsContract
    evaluations: EvaluationsContract
    checks: ChecksContract
    combos: CombosContract
    reports: ReportsContract
    legacy_raw: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    def as_runtime_configs(self) -> Dict[str, Dict[str, Any]]:
        return {
            "datasets": model_to_dict(self.datasets),
            "evaluations": model_to_dict(self.evaluations),
            "checks": model_to_dict(self.checks),
            "combos": model_to_dict(self.combos),
            "reports": model_to_dict(self.reports),
        }
