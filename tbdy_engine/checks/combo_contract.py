"""
tbdy_engine/checks/combo_contract.py

TBDY 2018 kombinasyon sözleşmesi loader.
YAML dosyalarını okur, sorgulama API'si sunar.
"""

from __future__ import annotations

import os
import re
import yaml
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ComboDefinition:
    """Tek bir kombinasyon tanımı"""
    combo_id: str
    group: str
    formula: str
    description: str
    section_type: str  # GROSS / CRACKED
    capacity_factor: float = 1.0
    etabs_aliases: List[str] = field(default_factory=list)

    @property
    def is_cracked(self) -> bool:
        return self.section_type == "CRACKED"

    @property
    def is_capacity(self) -> bool:
        return self.capacity_factor > 1.0


@dataclass
class ComboContract:
    """Tam kombinasyon sözleşmesi"""
    version: str
    combos: Dict[str, ComboDefinition]
    usage_matrix: Dict[str, Dict[str, List[str]]]
    check_requirements: Dict[str, List[str]]
    etabs_patterns: Dict[str, List[str]]
    abbreviations: Dict[str, str]

    def get_combo(self, combo_id: str) -> Optional[ComboDefinition]:
        return self.combos.get(combo_id)

    def get_combos_for_element(self, element_type: str) -> Dict[str, List[str]]:
        """Bir eleman tipi için tüm kombinasyonları döndür"""
        return self.usage_matrix.get(element_type, {})

    def get_combos_for_check(self, check_name: str) -> List[str]:
        """Bir check için gerekli kombinasyonları döndür"""
        return self.check_requirements.get(check_name, [])

    def get_combos_by_group(self, group: str) -> List[ComboDefinition]:
        """Bir gruptaki tüm kombinasyonları döndür"""
        return [c for c in self.combos.values() if c.group == group]

    def resolve_etabs_combo(self, etabs_name: str) -> Optional[str]:
        """ETABS combo adını canonical ID'ye çevir"""
        for combo_id, patterns in self.etabs_patterns.items():
            for pattern in patterns:
                if re.search(pattern, etabs_name, re.IGNORECASE):
                    return combo_id
        return None

    def get_usage_for_combo_element(self, combo_id: str, element_type: str) -> List[str]:
        """Bir kombinasyonun bir elemanda ne amaçla kullanıldığını döndür"""
        element_usage = self.usage_matrix.get(element_type, {})
        return element_usage.get(combo_id, [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "combo_count": len(self.combos),
            "groups": list(set(c.group for c in self.combos.values())),
            "element_types": list(self.usage_matrix.keys()),
            "check_count": len(self.check_requirements),
        }


# =============================================================================
# LOADER
# =============================================================================

def _get_yaml_path(filename: str) -> str:
    """YAML dosyasının tam yolunu döndür"""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, filename)


def load_combo_contract() -> ComboContract:
    """
    İki YAML dosyasını okuyup ComboContract oluşturur.

    Returns:
        ComboContract
    """
    # 1. combo_contract.yaml
    contract_path = _get_yaml_path("combo_contract.yaml")
    with open(contract_path, "r", encoding="utf-8") as f:
        contract_data = yaml.safe_load(f)

    # 2. combo_usage_matrix.yaml
    matrix_path = _get_yaml_path("combo_usage_matrix.yaml")
    with open(matrix_path, "r", encoding="utf-8") as f:
        matrix_data = yaml.safe_load(f)

    # Combo tanımlarını parse et
    combos: Dict[str, ComboDefinition] = {}
    for combo_id, data in contract_data.get("combos", {}).items():
        combos[combo_id] = ComboDefinition(
            combo_id=combo_id,
            group=data.get("group", ""),
            formula=data.get("formula", ""),
            description=data.get("description", ""),
            section_type=data.get("section_type", "GROSS"),
            capacity_factor=data.get("capacity_factor", 1.0),
            etabs_aliases=data.get("etabs_aliases", []),
        )

    # Kısaltmalar
    abbreviations = contract_data.get("abbreviations", {})

    # Usage matrix
    usage_matrix = matrix_data.get("usage_matrix", {})

    # Check requirements
    check_requirements = matrix_data.get("check_combo_requirements", {})

    # ETABS patterns
    etabs_patterns = matrix_data.get("etabs_combo_patterns", {})

    return ComboContract(
        version=contract_data.get("version", "1.0.0"),
        combos=combos,
        usage_matrix=usage_matrix,
        check_requirements=check_requirements,
        etabs_patterns=etabs_patterns,
        abbreviations=abbreviations,
    )


# =============================================================================
# GLOBAL SINGLETON
# =============================================================================

_combo_contract: Optional[ComboContract] = None


def get_combo_contract() -> ComboContract:
    """Global singleton"""
    global _combo_contract
    if _combo_contract is None:
        _combo_contract = load_combo_contract()
    return _combo_contract


# =============================================================================
# CONVENIENCE
# =============================================================================

def get_required_combos(check_name: str) -> List[str]:
    """Bir check için gerekli kombinasyon ID'leri"""
    return get_combo_contract().get_combos_for_check(check_name)


def get_element_combos(element_type: str) -> Dict[str, List[str]]:
    """Bir eleman tipi için kombinasyon→kullanım mapping'i"""
    return get_combo_contract().get_combos_for_element(element_type)


def resolve_etabs_combo_name(etabs_name: str) -> Optional[str]:
    """ETABS combo adını canonical ID'ye çevir"""
    return get_combo_contract().resolve_etabs_combo(etabs_name)