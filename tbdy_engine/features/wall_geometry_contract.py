"""Canonical data-only wall geometry fact contract for P2.10 and later checks."""
from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        "wall_is_basement": {
            "element_type": "wall", "type": "bool", "unit": "", "semantic_role": "APPLICABILITY",
            "source": {"table_key": None, "field_aliases": [], "filters": [], "aggregation": "none"},
            "custom_resolver": "wall_geometry_fact_resolver",
            "evidence_fields": ["source_table", "source_column", "resolved_value"],
        },
        "wall_body_classification": {
            "element_type": "wall", "type": "string", "unit": "", "semantic_role": "GEOMETRY_CLASSIFICATION",
            "source": {"table_key": None, "field_aliases": [], "filters": [], "aggregation": "none"},
            "custom_resolver": "wall_geometry_fact_resolver",
            "evidence_fields": ["source_table", "source_column", "resolved_value"],
        },
        "wall_special_branch_7_6_1_3_applies": {
            "element_type": "wall", "type": "bool", "unit": "", "semantic_role": "APPLICABILITY",
            "source": {"table_key": None, "field_aliases": [], "filters": [], "aggregation": "none"},
            "custom_resolver": "wall_geometry_fact_resolver",
            "evidence_fields": ["source_table", "source_column", "resolved_value"],
        },
        "unrestrained_plan_length_mm": {
            "element_type": "wall", "type": "float", "unit": "mm", "semantic_role": "GEOMETRY",
            "source": {"table_key": None, "field_aliases": [], "filters": [], "aggregation": "none"},
            "custom_resolver": "wall_geometry_fact_resolver",
            "evidence_fields": ["source_table", "source_column", "raw_value", "normalized_value", "unit"],
        },
        "wall_geometry_classification": {
            "element_type": "wall", "type": "string", "unit": "", "semantic_role": "GEOMETRY_CLASSIFICATION",
            "source": {"table_key": None, "field_aliases": [], "filters": [], "aggregation": "none"},
            "custom_resolver": "wall_geometry_fact_resolver",
            "evidence_fields": ["source_table", "source_column", "resolved_value"],
        },
        "wall_both_ends_laterally_restrained": {
            "element_type": "wall", "type": "bool", "unit": "", "semantic_role": "TOPOLOGY",
            "source": {"table_key": None, "field_aliases": [], "filters": [], "aggregation": "none"},
            "custom_resolver": "wall_geometry_fact_resolver",
            "evidence_fields": ["source_table", "source_column", "resolved_value"],
        },
    }
)

__all__ = ["WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS"]
