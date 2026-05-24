from __future__ import annotations

from pathlib import Path
import shutil
import yaml

ROOT = Path.cwd()
contracts = ROOT / "tbdy_engine" / "contracts"

evaluations_path = contracts / "evaluations.yaml"
checks_path = contracts / "checks.yaml"

backup_dir = contracts / "backup_scwb_activation"
backup_dir.mkdir(parents=True, exist_ok=True)

shutil.copy2(evaluations_path, backup_dir / "evaluations.yaml.bak")
shutil.copy2(checks_path, backup_dir / "checks.yaml.bak")


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data):
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


def get_or_create_evaluation(evaluations_container, eval_id: str):
    """
    Supports:
      evaluations:
        SCWB_CHECK: {...}

    and:
      evaluations:
        - id: SCWB_CHECK
          ...
    """
    if isinstance(evaluations_container, dict):
        return evaluations_container.setdefault(eval_id, {})

    if isinstance(evaluations_container, list):
        for item in evaluations_container:
            if isinstance(item, dict) and item.get("id") == eval_id:
                return item
        item = {"id": eval_id}
        evaluations_container.append(item)
        return item

    raise TypeError(f"Unsupported evaluations type: {type(evaluations_container).__name__}")


def get_or_create_check(checks_container, check_id: str):
    """
    Supports:
      checks:
        column_capacity_hierarchy: {...}

    and:
      checks:
        - id: column_capacity_hierarchy
          ...
    """
    if isinstance(checks_container, dict):
        chk = checks_container.setdefault(check_id, {})
        chk.setdefault("id", check_id)
        return chk

    if isinstance(checks_container, list):
        for item in checks_container:
            if isinstance(item, dict) and item.get("id") == check_id:
                return item
        item = {"id": check_id}
        checks_container.append(item)
        return item

    raise TypeError(f"Unsupported checks type: {type(checks_container).__name__}")


evaluations_doc = load_yaml(evaluations_path)
checks_doc = load_yaml(checks_path)

if "evaluations" not in evaluations_doc:
    evaluations_doc["evaluations"] = {}

if "checks" not in checks_doc:
    checks_doc["checks"] = []

evaluations = evaluations_doc["evaluations"]
checks = checks_doc["checks"]

# Activate SCWB_CHECK as runtime evaluation.
scwb = get_or_create_evaluation(evaluations, "SCWB_CHECK")
scwb.update({
    "id": "SCWB_CHECK",
    "enabled": True,
    "experimental": True,
    "module": "tbdy_engine.design.joints.scwb_projection.ScwbProjectionModule",
    "method": "run",
    "requires": [
        "topology",
        "column_forces",
        "beam_forces",
        "column_rebar",
        "beam_rebar",
    ],
    "produces": [
        "column_capacity_hierarchy",
        "beam_capacity_hierarchy",
    ],
    "depends_on_results": [
        "COLUMN_DESIGN",
        "BEAM_DESIGN",
    ],
})

# Route hierarchy checks to SCWB_CHECK for runner_v2 projection.
patched_checks = {}
for check_id, output_key in {
    "column_capacity_hierarchy": "column_capacity_hierarchy",
    "beam_capacity_hierarchy": "beam_capacity_hierarchy",
}.items():
    chk = get_or_create_check(checks, check_id)
    chk["id"] = check_id
    chk["evaluation"] = "SCWB_CHECK"
    chk["output_key"] = output_key
    chk["runner_enabled"] = True
    patched_checks[check_id] = chk

save_yaml(evaluations_path, evaluations_doc)
save_yaml(checks_path, checks_doc)

print("PATCHED:", evaluations_path)
print("PATCHED:", checks_path)
print("BACKUP:", backup_dir)

print("\nSCWB_CHECK:")
print(yaml.safe_dump(scwb, allow_unicode=True, sort_keys=False))

for check_id, chk in patched_checks.items():
    print(f"{check_id}:")
    print(yaml.safe_dump(chk, allow_unicode=True, sort_keys=False))
