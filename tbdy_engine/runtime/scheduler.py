from __future__ import annotations
import importlib
import time
from typing import Any, Dict, Iterable, Optional
from tbdy_engine.runtime.dag import EvaluationDAG
from tbdy_engine.runtime.module_cache import ModuleExecutionCache

class RuntimeScheduler:
    """
    Sync Runtime Scheduler.
    Only evaluations referenced by enabled runtime checks are executed.
    """

    def __init__(self, ctx: Any, evaluations_config: Dict[str, Any], cache: Optional[ModuleExecutionCache] = None, enabled_evaluation_ids: Optional[Iterable[str]] = None) -> None:
        self.ctx = ctx
        self.evaluations_config = evaluations_config or {}
        self.evaluations = self.evaluations_config.get("evaluations", {}) or {}
        self.enabled_evaluation_ids = set(enabled_evaluation_ids or [])
        self.dag = EvaluationDAG(self.evaluations_config, enabled_evaluation_ids=self.enabled_evaluation_ids)
        self.cache = cache or ModuleExecutionCache()
        self.results: Dict[str, Any] = {}
        self.errors: Dict[str, str] = {}
        self.skipped: Dict[str, str] = {}

    def run_all(self) -> Dict[str, Any]:
        start = time.time()
        execution_order = self.dag.get_execution_order()

        for eval_name in execution_order:
            conf = self.evaluations.get(eval_name, {}) or {}
            if not conf.get("enabled", True):
                self.skipped[eval_name] = conf.get("reason", "disabled")
                continue
            if self.enabled_evaluation_ids and eval_name not in self.enabled_evaluation_ids:
                self.skipped[eval_name] = "not referenced by enabled runtime checks"
                continue

            cache_key = conf.get("cache_key", eval_name)
            if self.cache.has(cache_key):
                self.results[eval_name] = self.cache.get(cache_key)
                continue

            try:
                result = self._run_evaluation(eval_name, conf)
                self.cache.set(cache_key, result)
                self.results[eval_name] = result
            except Exception as exc:
                self.errors[eval_name] = f"{type(exc).__name__}: {exc}"
                self.results[eval_name] = {"status": "ERROR", "evaluation": eval_name, "error": str(exc), "exception_type": type(exc).__name__}

        for eval_name, conf in self.evaluations.items():
            if not conf.get("enabled", True):
                self.skipped.setdefault(eval_name, conf.get("reason", "disabled"))
            elif self.enabled_evaluation_ids and eval_name not in self.enabled_evaluation_ids:
                self.skipped.setdefault(eval_name, "not referenced by enabled runtime checks")

        return {
            "results": self.results,
            "errors": self.errors,
            "skipped": self.skipped,
            "execution_order": execution_order,
            "cache_stats": self.cache.stats(),
            "duration_sec": round(time.time() - start, 3),
        }

    def _run_evaluation(self, eval_name: str, conf: Dict[str, Any]) -> Any:
        module_path = conf["module"]
        method_name = conf.get("method", "run")
        module_name, class_name = module_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        instance = cls(self.ctx)
        return getattr(instance, method_name)()
