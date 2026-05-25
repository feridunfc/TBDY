from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.runtime.dataset_validator import DatasetValidator
from tbdy_engine.runtime.evaluation_dag import EvaluationDAG, EvaluationDAGError, EvaluationNode


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_IMPORT_PREFIXES = (
    "tbdy_engine.design",
    "tbdy_engine.etabs",
    "tbdy_engine.engine.context_builder",
    "tbdy_engine.adapters",
    "tbdy_engine.reports",
    "tbdy_engine.runner",
    "tbdy_engine.runner_v2",
)


@dataclass(frozen=True)
class FakeEvaluation:
    enabled: bool = True
    experimental: bool = False
    depends_on_results: tuple[str, ...] = ()


@dataclass(frozen=True)
class FakeCatalog:
    evaluations: dict[str, FakeEvaluation]


def _catalog():
    return EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()


def _node_by_name(dag: EvaluationDAG) -> dict[str, EvaluationNode]:
    return {node.evaluation: node for node in dag.nodes}


def test_from_catalog_builds_deterministic_nodes():
    dag = EvaluationDAG.from_catalog(_catalog())

    assert dag.nodes
    assert dag.evaluations == tuple(sorted(dag.evaluations))

    for node in dag.nodes:
        assert isinstance(node.evaluation, str)
        assert isinstance(node.depends_on, tuple)
        assert isinstance(node.enabled, bool)
        assert isinstance(node.experimental, bool)


def test_topological_order_includes_enabled_evaluations_with_dependencies_first():
    dag = EvaluationDAG.from_catalog(_catalog())

    order = dag.topological_order(enabled_only=True)
    repeated_order = dag.topological_order(enabled_only=True)
    enabled_names = set(dag.enabled_evaluations)
    position = {evaluation: index for index, evaluation in enumerate(order)}

    assert isinstance(order, tuple)
    assert order == repeated_order
    assert set(order) == enabled_names

    for node in dag.nodes:
        if not node.enabled:
            continue
        for dependency in node.depends_on:
            dependency_node = _node_by_name(dag).get(dependency)
            if dependency_node is not None and dependency_node.enabled:
                assert position[dependency] < position[node.evaluation]


def test_fake_catalog_dependency_ordering():
    dag = EvaluationDAG.from_catalog(
        FakeCatalog(
            evaluations={
                "A": FakeEvaluation(depends_on_results=()),
                "B": FakeEvaluation(depends_on_results=("A",)),
                "C": FakeEvaluation(depends_on_results=("B",)),
            }
        )
    )

    assert dag.topological_order(enabled_only=True) == ("A", "B", "C")


def test_fake_catalog_detects_cycle():
    dag = EvaluationDAG.from_catalog(
        FakeCatalog(
            evaluations={
                "A": FakeEvaluation(depends_on_results=("B",)),
                "B": FakeEvaluation(depends_on_results=("A",)),
            }
        )
    )

    with pytest.raises(EvaluationDAGError, match="Cycle detected"):
        dag.topological_order(enabled_only=True)


def test_fake_catalog_detects_unknown_dependency():
    dag = EvaluationDAG.from_catalog(
        FakeCatalog(
            evaluations={
                "B": FakeEvaluation(depends_on_results=("MISSING",)),
            }
        )
    )

    with pytest.raises(EvaluationDAGError, match="MISSING"):
        dag.topological_order(enabled_only=True)


def test_disabled_evaluation_behavior():
    dag = EvaluationDAG.from_catalog(
        FakeCatalog(
            evaluations={
                "A": FakeEvaluation(enabled=True),
                "B": FakeEvaluation(enabled=False),
                "C": FakeEvaluation(enabled=True, depends_on_results=("A", "B")),
            }
        ),
        enabled_only=True,
    )

    assert "B" not in dag.evaluations
    assert "C" in dag.evaluations

    order = dag.topological_order(enabled_only=True)
    assert "B" not in order
    assert order.index("A") < order.index("C")


def test_to_dict_has_stable_shape():
    dag = EvaluationDAG.from_catalog(
        FakeCatalog(
            evaluations={
                "A": FakeEvaluation(enabled=True, experimental=False),
                "B": FakeEvaluation(enabled=True, experimental=True, depends_on_results=("A",)),
            }
        )
    )

    assert dag.to_dict() == {
        "nodes": [
            {
                "evaluation": "A",
                "depends_on": [],
                "enabled": True,
                "experimental": False,
            },
            {
                "evaluation": "B",
                "depends_on": ["A"],
                "enabled": True,
                "experimental": True,
            },
        ],
        "topological_order": ["A", "B"],
    }


def test_evaluation_dag_has_no_forbidden_imports():
    source_path = ROOT / "tbdy_engine" / "runtime" / "evaluation_dag.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    forbidden_imports = sorted(
        module_name
        for module_name in imported_modules
        if any(
            module_name == prefix or module_name.startswith(prefix + ".")
            for prefix in FORBIDDEN_IMPORT_PREFIXES
        )
    )

    assert forbidden_imports == []


def test_runtime_interface_audit_sees_evaluation_dag_importable():
    from tests import test_runtime_interface_audit as audit

    assert audit.RUNTIME_INTERFACE_STATUS["EvaluationDAG"] == "PRESENT_IMPORTABLE"


def test_dataset_validator_and_evaluation_dag_import_independently():
    assert DatasetValidator.__name__ == "DatasetValidator"
    assert EvaluationDAG.__name__ == "EvaluationDAG"
