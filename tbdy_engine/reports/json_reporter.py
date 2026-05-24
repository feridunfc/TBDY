from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class JSONReporter:
    def __init__(self, write_history: bool = True) -> None:
        self.write_history = write_history
        self.last_snapshot_path: str | None = None

    def generate(self, checks, eval_results, runtime_catalog=None, output_path="engine_report.json") -> str:
        payload = self.build_payload(checks, eval_results, runtime_catalog=runtime_catalog)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        self.last_snapshot_path = None
        if self.write_history:
            history_dir = path.parent / "history"
            history_dir.mkdir(parents=True, exist_ok=True)
            timestamp = payload["report_metadata"]["generated_at_compact"]
            snapshot = history_dir / f"{timestamp}_{path.name}"
            shutil.copy2(path, snapshot)
            self.last_snapshot_path = str(snapshot)

        return str(path)

    def build_payload(self, checks, eval_results, runtime_catalog=None) -> Dict[str, Any]:
        generated_at = datetime.now().isoformat(timespec="seconds")
        generated_at_compact = datetime.now().strftime("%Y%m%d_%H%M%S")
        return {
            "report_metadata": {
                "schema": "engine_report.v1.1",
                "generated_at": generated_at,
                "generated_at_compact": generated_at_compact,
                "runtime_bridge": "Genesis Runtime Bridge v1.1",
            },
            "summary": {
                "total_checks": len(checks),
                "ok": sum(1 for c in checks if c.status == "OK"),
                "fail": sum(1 for c in checks if c.status == "FAIL"),
                "warning": sum(1 for c in checks if c.status == "WARNING"),
                "no_data": sum(1 for c in checks if c.status == "NO_DATA"),
                "error": sum(1 for c in checks if c.status == "ERROR"),
            },
            "checks": [c.to_dict() for c in checks],
            "evaluation_errors": eval_results.get("errors", {}),
            "evaluation_skipped": eval_results.get("skipped", {}),
            "execution_order": eval_results.get("execution_order", []),
            "cache_stats": eval_results.get("cache_stats", {}),
            "coverage": self._coverage(checks, eval_results),
            "distributions": self._distributions(checks),
        }

    def _coverage(self, checks, eval_results) -> Dict[str, Any]:
        ids = sorted(set(c.check_id for c in checks))
        return {
            "enabled_check_type_count": len(ids),
            "enabled_check_types": ids,
            "detail_result_count": len(checks),
            "executed_evaluations": sorted((eval_results.get("results") or {}).keys()),
            "skipped_evaluations": sorted((eval_results.get("skipped") or {}).keys()),
            "no_data_count": sum(1 for c in checks if c.status == "NO_DATA"),
            "error_count": sum(1 for c in checks if c.status == "ERROR"),
        }

    def _distributions(self, checks) -> Dict[str, Any]:
        return {
            "by_status": dict(Counter(c.status for c in checks)),
            "by_check_id": dict(Counter(c.check_id for c in checks)),
            "by_evaluation_level": dict(Counter(c.evaluation_level for c in checks)),
            "by_source": dict(Counter((c.source or "<empty>") for c in checks)),
            "by_category": dict(Counter(c.category for c in checks)),
        }
