"""FeatureSnapshot model for C4.

The snapshot is a read-only collection of feature data and evidence for one
component. It is not a CheckResult container.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from tbdy_engine.contracts.models import freeze_data
from tbdy_engine.features.diagnostics import FeatureDiagnostic, FeatureDiagnosticCode, FeatureDiagnosticSeverity
from tbdy_engine.features.evidence import FeatureEvidence
from tbdy_engine.features.value import FeatureValue, validate_feature_name

_FORBIDDEN_IDENTITY_KEYS = {
    "check_id",
    "check_result",
    "check_results",
    "checkresult",
    "checkresults",
    "status_counts",
    "pass_rule",
    "ratio",
    "result_panel",
    "formula_panel",
}


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    component_type: str
    component_id: str
    identity: Mapping[str, Any]
    features: Mapping[str, FeatureValue]
    evidence_by_feature: Mapping[str, tuple[FeatureEvidence, ...]]
    diagnostics: tuple[FeatureDiagnostic, ...] = field(default_factory=tuple)

    def __init__(
        self,
        *,
        component_type: str,
        component_id: str,
        identity: Mapping[str, Any] | None = None,
        features: Mapping[str, FeatureValue] | None = None,
        evidence_by_feature: Mapping[str, Sequence[FeatureEvidence]] | None = None,
        diagnostics: Sequence[FeatureDiagnostic] | None = None,
    ) -> None:
        if not component_type or not component_id:
            raise ValueError("FeatureSnapshot requires component_type and component_id")
        self._reject_forbidden(identity or {}, "identity")
        normalized_features = dict(features or {})
        for feature_name, feature_value in normalized_features.items():
            validate_feature_name(feature_name)
            if not isinstance(feature_value, FeatureValue):
                raise TypeError("FeatureSnapshot.features values must be FeatureValue objects")
            if feature_value.feature_name != feature_name:
                raise ValueError("FeatureSnapshot feature mapping key must match FeatureValue.feature_name")
        normalized_evidence = {
            name: tuple(evidence)
            for name, evidence in (evidence_by_feature or {name: fv.evidence for name, fv in normalized_features.items()}).items()
        }
        normalized_diagnostics = tuple(diagnostics or ())
        if any("checkresult" in type(value).__name__.casefold() for value in normalized_features.values()):
            normalized_diagnostics = normalized_diagnostics + (
                FeatureDiagnostic(
                    severity=FeatureDiagnosticSeverity.ERROR,
                    code=FeatureDiagnosticCode.CHECK_RESULT_FORBIDDEN,
                    message="FeatureSnapshot must not contain check result objects",
                ),
            )
            raise ValueError("FeatureSnapshot must not contain check result objects")
        object.__setattr__(self, "component_type", component_type)
        object.__setattr__(self, "component_id", component_id)
        object.__setattr__(self, "identity", freeze_data(dict(identity or {})))
        object.__setattr__(self, "features", freeze_data(normalized_features))
        object.__setattr__(self, "evidence_by_feature", freeze_data(normalized_evidence))
        object.__setattr__(self, "diagnostics", normalized_diagnostics)

    @staticmethod
    def _reject_forbidden(value: Any, path: str) -> None:
        """Reject check/result semantics by identity key name only.

        Identity values may legitimately contain substrings such as OK, FAIL,
        pass, or fail (for example STORY_SMOKE or OKUL).  The guard must not
        scan value text.  It only blocks explicit identity keys that would leak
        check/result payload structure into the feature layer.
        """
        if isinstance(value, Mapping):
            for key, nested_value in value.items():
                key_text = str(key)
                token = key_text.casefold()
                next_path = f"{path}.{key_text}"
                if token in _FORBIDDEN_IDENTITY_KEYS:
                    raise ValueError(
                        "FeatureSnapshot identity contains forbidden check/result semantics "
                        f"at path={next_path!r}, key={key_text!r}, token={token!r}"
                    )
                FeatureSnapshot._reject_forbidden(nested_value, next_path)
            return
        if isinstance(value, (list, tuple, set)):
            for index, item in enumerate(value):
                FeatureSnapshot._reject_forbidden(item, f"{path}[{index}]")

    def as_dict(self) -> dict[str, Any]:
        return {
            "component_type": self.component_type,
            "component_id": self.component_id,
            "identity": dict(self.identity),
            "features": {name: value.as_dict() for name, value in self.features.items()},
            "evidence_by_feature": {
                name: [ev.as_dict() for ev in evidence]
                for name, evidence in self.evidence_by_feature.items()
            },
            "diagnostics": [diag.as_dict() for diag in self.diagnostics],
        }


__all__ = ["FeatureSnapshot"]
