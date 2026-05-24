from __future__ import annotations
from typing import Any, Dict

class ModuleExecutionCache:
    def __init__(self) -> None:
        self._cache: Dict[str, Any] = {}

    def has(self, key: str) -> bool:
        return key in self._cache

    def get(self, key: str) -> Any:
        return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = value

    def clear(self) -> None:
        self._cache.clear()

    def stats(self) -> dict:
        return {"cached_items": len(self._cache), "keys": list(self._cache.keys())}
