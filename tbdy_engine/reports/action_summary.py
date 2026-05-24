from __future__ import annotations


class ActionSummaryBuilder:
    CONTRACT_STATUS_FILTER = frozenset({"FAIL", "WARNING"})
    CONTRACT_SEVERITY_FILTER = frozenset({"HIGH", "MEDIUM"})

    def __init__(self, status_filter=None, severity_filter=None):
        self.status_filter = frozenset(status_filter or self.CONTRACT_STATUS_FILTER)
        self.severity_filter = frozenset(severity_filter or self.CONTRACT_SEVERITY_FILTER)

    def build(self, checks):
        return [
            self._to_action_item(c)
            for c in checks
            if self._is_actionable(c)
        ]

    def _is_actionable(self, check) -> bool:
        status = str(getattr(check, "status", "") or "")
        if status not in self.status_filter:
            return False

        severity = getattr(check, "severity", None)
        if severity in (None, ""):
            return True

        return str(severity) in self.severity_filter

    def _to_action_item(self, c):
        return {
            "check_id": getattr(c, "check_id", ""),
            "element_label": getattr(c, "element_label", ""),
            "story": getattr(c, "story", ""),
            "status": getattr(c, "status", ""),
            "ratio": getattr(c, "ratio", 0.0),
            "message": getattr(c, "message", ""),
            "action": getattr(c, "action", ""),
            "tbdy_ref": getattr(c, "tbdy_ref", ""),
            "evaluation_level": getattr(c, "evaluation_level", ""),
            "source": getattr(c, "source", ""),
            "severity": getattr(c, "severity", ""),
            "category": getattr(c, "category", ""),
        }
