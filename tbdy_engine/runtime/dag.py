from __future__ import annotations
from graphlib import TopologicalSorter
from typing import Any, Dict, Iterable, List, Optional, Set

class EvaluationDAG:
    """Sync DAG. Bridge v1 returns flat topological order, not parallel groups."""

    def __init__(self, evaluations_config: Dict[str, Any], enabled_evaluation_ids: Optional[Iterable[str]] = None) -> None:
        self.config = evaluations_config or {}
        self.enabled_evaluation_ids = set(enabled_evaluation_ids or [])
        self.graph: Dict[str, Set[str]] = {}
        self._build_graph()

    def _evaluations(self) -> Dict[str, Any]:
        return self.config.get("evaluations", {}) or {}

    def _is_enabled(self, eval_name: str) -> bool:
        conf = self._evaluations().get(eval_name, {}) or {}
        if not conf.get("enabled", True):
            return False
        if self.enabled_evaluation_ids:
            return eval_name in self.enabled_evaluation_ids
        return True

    def _build_graph(self) -> None:
        evaluations = self._evaluations()
        for eval_name, eval_conf in evaluations.items():
            if not self._is_enabled(eval_name):
                continue
            deps = set()
            for dep in eval_conf.get("depends_on_results", []) or []:
                if dep in evaluations and self._is_enabled(dep):
                    deps.add(dep)
            self.graph[eval_name] = deps

    def get_execution_order(self) -> List[str]:
        return list(TopologicalSorter(self.graph).static_order())
