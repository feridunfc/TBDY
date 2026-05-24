from __future__ import annotations

class ActionSummaryBuilder:
    def build(self, checks):
        return [
            {
                "check_id": c.check_id,
                "element_label": c.element_label,
                "story": c.story,
                "status": c.status,
                "ratio": c.ratio,
                "message": c.message,
                "action": c.action,
                "tbdy_ref": c.tbdy_ref,
                "evaluation_level": c.evaluation_level,
                "source": c.source,
                "severity": c.severity,
                "category": c.category,
            }
            for c in checks
            if c.status in {"FAIL", "WARNING", "ERROR", "PARTIAL"}
        ]
