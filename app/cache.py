from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    """
    Cache simples in-memory.
    - Boa para reduzir chamadas repetidas do Delphi.
    - Se você usar múltiplos workers (uvicorn --workers > 1),
      cada worker terá seu próprio cache (ok na prática).
    """
    def __init__(self, default_ttl_seconds: int = 3600):
        self.default_ttl_seconds = default_ttl_seconds
        self._data: Dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._data.get(key)
        if not entry:
            return None
        if entry.expires_at < time.time():
            self._data.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        self._data[key] = CacheEntry(value=value, expires_at=time.time() + ttl)

    def clear(self) -> None:
        self._data.clear()


def make_cache_key(*parts: Any) -> str:
    return "|".join(str(p).strip().upper() for p in parts)
