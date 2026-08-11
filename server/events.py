"""Bus d'evenements thread-safe : historique circulaire + diffusion SSE."""

import asyncio
import threading
from collections import deque

from .eventlog import EventLog


class EventBus:
    def __init__(self, history_size=500, log=None):
        self._history = deque(maxlen=history_size)
        self._log = log  # EventLog ou None (pas de persistance)
        self._subs = []
        self._lock = threading.Lock()
        self._loop = None

    @property
    def log(self):
        return self._log

    def restore_from_log(self, n=500):
        """Recharge l'historique depuis le log disque (apres un redemarrage)."""
        if self._log is None:
            return 0
        n = max(0, min(n, self._log.total()))
        evs = self._log.tail_oldest_first(n)
        with self._lock:
            for ev in evs:
                self._history.append(ev)
        return len(evs)

    def attach_loop(self, loop):
        """Attache la loop asyncio du serveur web (appele au startup FastAPI)."""
        self._loop = loop

    def subscribe(self):
        q = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def snapshot(self):
        with self._lock:
            return list(self._history)

    def clear(self):
        with self._lock:
            self._history.clear()
        if self._log is not None:
            self._log.clear()

    def publish(self, event):
        """Publie un evenement. Appele depuis les threads MQTT et l'API."""
        if self._log is not None:
            self._log.append(event)
        with self._lock:
            self._history.append(event)
            subs = list(self._subs)
        loop = self._loop
        if loop is None:
            # pas encore de boucle : on ne diffuse que l'historique
            return
        for q in subs:
            if q.full():
                try:
                    q.get_nowait()
                except Exception:
                    pass
            loop.call_soon_threadsafe(q.put_nowait, event)