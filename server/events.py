"""Bus d'evenements thread-safe : historique circulaire + diffusion SSE."""

import asyncio
import threading
from collections import deque


class EventBus:
    def __init__(self, history_size=500):
        self._history = deque(maxlen=history_size)
        self._subs = []
        self._lock = threading.Lock()
        self._loop = None

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

    def publish(self, event):
        """Publie un evenement. Appele depuis les threads MQTT et l'API."""
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