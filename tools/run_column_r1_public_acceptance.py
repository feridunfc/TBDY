"""One supervisor-run live acceptance of an exact offline Column candidate.

Not run by the offline worker. Reviewed inputs are supplied separately; this
harness never creates engineering values, calls StartDesign itself, or opens
the protected source for writing. All execution goes through execute_project.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages" / "etabs_gateway" / "src")]
SOURCE = Path(r"C:\tmp\B-BLOK_Revised.EDB")
SOURCE_SHA256 = "5AA83947C46AE886DD43E8BD2270DAEAC6117AE60BAD1F8CB9ED9874CD3E2A44"


def _git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def _sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def _json(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if callable(getattr(value, "as_dict", None)):
        return _json(value.as_dict())
    if is_dataclass(value):
        return {item.name: _json(getattr(value, item.name)) for item in fields(value)
                if not item.name.startswith("_")}
    if isinstance(value, Mapping):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unserializable acceptance artifact: {type(value).__name__}")


def _is_ready(column):
    return column.readiness_binding is not None and column.readiness_binding.readiness.status == "READY"


def _observations(result):
    return dict(project_id=result.project_id, status=result.status, population_state=result.population_state,
                columns=[dict(component_id=c.component_id, status=c.status, blockers=c.blockers,
                              readiness=None if c.readiness_binding is None else c.readiness_binding.readiness,
                              design_state=c.design_state, design_result_identity=c.design_result_identity,
                              selected_rebar=c.selected_rebar,
                              detailing=None if c.longitudinal_runtime is None else c.longitudinal_runtime.detailing,
                              axial=c.column_axial_vs5, transverse=c.transverse_confinement,
                              p7=c.column_shear_p7, limited_shear=c.column_shear_limited)
                         for c in result.columns],
                A38=result.column_denominator, A39=result.reconciliation, A40=result.building_report_model)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--reviewed-inputs", type=Path, required=True,
                        help="Approved Python file with load_inputs() -> (ProjectExecutionRequest, keyword_dependencies)")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--execute-live", action="store_true")
    args = parser.parse_args()
    if not args.execute_live:
        parser.error("Live execution is deferred; supervisor must explicitly supply --execute-live")
    if sys.platform != "win32":
        parser.error("Live acceptance requires the supervisor's Windows ETABS host")
    head, tree = _git("rev-parse", "HEAD"), _git("rev-parse", "HEAD^{tree}")
    if (head, tree) != (args.expected_sha, args.expected_tree) or _git("status", "--porcelain"):
        raise RuntimeError("Exact candidate SHA/tree and clean worktree are required")
    before = _sha(SOURCE)
    if before != SOURCE_SHA256:
        raise RuntimeError("Protected source SHA256 does not match the accepted source")
    output = args.output_dir.resolve()
    if output == ROOT or ROOT in output.parents:
        raise RuntimeError("Acceptance output must be outside the candidate worktree")
    output.mkdir(parents=True, exist_ok=False)
    receipt = dict(candidate_sha=head, tree=tree, protected_model=str(SOURCE), source_sha256_pre=before,
                   reviewed_inputs_sha256=_sha(args.reviewed_inputs), live_executed=False)
    session = None
    try:
        spec = importlib.util.spec_from_file_location("column_acceptance_reviewed_inputs", args.reviewed_inputs)
        if spec is None or spec.loader is None:
            raise RuntimeError("Reviewed inputs cannot be loaded")
        config = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = config
        spec.loader.exec_module(config)
        request, dependencies = config.load_inputs()
        if "verified_session" in dependencies:
            raise RuntimeError("Reviewed inputs may not replace the verified session")
        import tbdy_engine.application.project_execution as project
        import tbdy_engine.application.column_public_a5 as a5
        import tbdy_engine.application.column_execution as column
        import tbdy_engine.integration.etabs_controlled_design_execution as b6
        from tbdy_engine.etabs.safety import attach_verified_to_running_etabs

        session = attach_verified_to_running_etabs(str(SOURCE), pid=args.pid, allow_pid_fallback=False)
        owners = ((project, "create_trusted_live_acquisition_context", "acquisition"),
                  (a5, "create_owned_scratch_context", "scratch"),
                  (a5, "execute_controlled_analysis", "B5"),
                  (column, "execute_controlled_concrete_design", "B6"),
                  (b6, "start_concrete_design_from_session", "StartDesign"))
        with ExitStack() as stack:
            spies = {label: stack.enter_context(patch.object(module, name, wraps=getattr(module, name)))
                     for module, name, label in owners}
            receipt["live_executed"] = True
            try:
                result = project.execute_project(request, verified_session=session, **dependencies)
            finally:
                receipt["owner_calls"] = {label: spy.call_count for label, spy in spies.items()}
        (output / "project-artifact.json").write_text(json.dumps(_json(_observations(result)), indent=2, allow_nan=False), encoding="utf-8")
        denominator, fcr = result.column_denominator, result.reconciliation
        ready = tuple(c for c in result.columns if _is_ready(c))
        population_ids = {c.component_id for c in result.columns}
        design_results = {c.design_result_identity.identity_ref for c in ready if c.design_result_identity is not None}
        receipt.update(component_count=len(result.columns), ready_count=len(ready),
                       outcomes={c.component_id: {"status": c.status, "blockers": c.blockers} for c in result.columns},
                       A38=denominator is not None, A39=fcr is not None, A40=result.building_report_model is not None)
        checks = {
            "one_acquisition_and_scratch": all(receipt["owner_calls"][x] == 1 for x in ("acquisition", "scratch")),
            "shared_B6": receipt["owner_calls"]["B6"] == receipt["owner_calls"]["StartDesign"] == (1 if ready else 0),
            "nonready_no_design": all(c.controlled_design_result is None for c in result.columns if not _is_ready(c)),
            "ready_qualified_design": all(c.controlled_design_result is not None
                and c.controlled_design_result.design_lineage.qualified for c in ready),
            "one_shared_design_result": len(design_results) == (1 if ready else 0),
            "full_design_population": all(c.controlled_design_result is not None
                and set(c.controlled_design_result.factual_design_results.expected_component_ids) == population_ids
                and set(c.controlled_design_result.factual_design_results.captured_component_ids) == population_ids for c in ready),
            "A38_complete": denominator is not None and not any((denominator.silent_missing_count, denominator.duplicate_count, denominator.orphan_count)),
            "A39_reconciled": fcr is not None and fcr.column_population_reconciled,
            "A40_present": result.building_report_model is not None,
        }
        receipt["composition_checks"] = checks
        receipt["composition_pass"] = all(checks.values())
        if not receipt["composition_pass"]:
            raise RuntimeError("Public-root composition acceptance failed; inspect receipt and exact component outcomes")
    except BaseException as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        try:
            if session is not None:
                session.close()
        finally:
            receipt["source_sha256_post"] = _sha(SOURCE)
            receipt["source_unchanged"] = receipt["source_sha256_post"] == before == SOURCE_SHA256
            (output / "receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False), encoding="utf-8")
            if not receipt["source_unchanged"]:
                raise RuntimeError("FAIL: protected source SHA256 changed")


if __name__ == "__main__":
    main()
