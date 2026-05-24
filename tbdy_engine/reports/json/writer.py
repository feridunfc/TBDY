from __future__ import annotations
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from enum import Enum
from typing import Any

def _default(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        return asdict(obj)
    return str(obj)

def write_json(result: Any, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, default=_default, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
