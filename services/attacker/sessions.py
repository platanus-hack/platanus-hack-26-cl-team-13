"""Reconstrucción de sesiones del atacante.

Un ataque fragmentado manda trozos del secreto en requests separados; ninguno
matchea solo. El sink bufferiza por sesión (IP + carril si viene en headers) y
devuelve la cola combinada para escanear junto con el request individual.
"""

from __future__ import annotations

import threading
import time

DEFAULT_TTL_S = 900.0
DEFAULT_MAX_CHARS = 131_072


class SessionStore:
    def __init__(self, ttl_s: float = DEFAULT_TTL_S, max_chars: int = DEFAULT_MAX_CHARS,
                 max_sessions: int = 512) -> None:
        self.ttl_s = ttl_s
        self.max_chars = max_chars
        self.max_sessions = max_sessions
        self._buf: dict[str, list[tuple[float, str]]] = {}
        self._lock = threading.Lock()

    def add(self, key: str, text: str, now: float | None = None) -> str:
        """Agrega `text` a la sesión y devuelve la cola combinada de la sesión."""
        now = now or time.time()
        with self._lock:
            self._prune(now)
            if key not in self._buf and len(self._buf) >= self.max_sessions:
                oldest = min(self._buf, key=lambda k: self._buf[k][-1][0])
                del self._buf[oldest]
            chunks = self._buf.setdefault(key, [])
            chunks.append((now, text))
            joined = ""
            total = 0
            for _, t in reversed(chunks):
                if total + len(t) > self.max_chars:
                    break
                joined = t + joined
                total += len(t)
            return joined

    def _prune(self, now: float) -> None:
        dead = [k for k, v in self._buf.items() if now - v[-1][0] > self.ttl_s]
        for k in dead:
            del self._buf[k]
