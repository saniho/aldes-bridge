"""Etat applicatif partage entre le moteur MQTT (threads) et l'API web (asyncio)."""
import threading
from datetime import datetime, timezone

from .events import EventBus


def _iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def decode_payload(payload):
    """Decode un payload PUBLISH : bytes -> str, JSON joliment formate si possible."""
    if payload is None:
        return ""
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8", errors="replace")
        except Exception:
            payload = payload.hex()
    payload = payload.strip()
    if payload.startswith(("{", "[")):
        try:
            import json
            return json.dumps(json.loads(payload), indent=2, ensure_ascii=False)
        except Exception:
            pass
    return payload


def emit_message(state, direction, mtype, topic=None, payload=None, qos=None, **extra):
    ev = {
        "kind": "message",
        "ts": _iso(),
        "direction": direction,
        "type": mtype,
        "mode": state.mode,
    }
    if topic is not None:
        ev["topic"] = topic
    if payload is not None:
        ev["payload"] = decode_payload(payload)
    if qos is not None:
        ev["qos"] = qos
    ev.update(extra)
    state.events.publish(ev)


class AppState:
    MODES = ("proxy", "bridge")

    def __init__(self, real_host, real_port, events):
        self.events = events if events is not None else EventBus()
        self._lock = threading.Lock()
        self.real_host = real_host
        self.real_port = real_port
        self._mode = "proxy"
        self._connected = False
        self._client_id = None
        self._topics = set()
        self._last_error = None

    @property
    def mode(self):
        with self._lock:
            return self._mode

    def set_mode(self, mode):
        if mode not in self.MODES:
            raise ValueError("mode inconnu: %r (attendu: %s)" % (mode, "/".join(self.MODES)))
        with self._lock:
            prev, self._mode = self._mode, mode
        self.events.publish({
            "kind": "status", "mode": mode, "prev_mode": prev, "ts": _iso(),
        })
        return mode

    def session_up(self, client_id):
        with self._lock:
            self._connected = True
            self._client_id = client_id
            self._topics = set()
            self._last_error = None
        self.events.publish({
            "kind": "status", "connected": True, "client_id": client_id, "ts": _iso(),
        })

    def session_down(self):
        with self._lock:
            self._connected = False
            self._client_id = None
            self._topics = set()
        self.events.publish({
            "kind": "status", "connected": False, "client_id": None, "ts": _iso(),
        })

    def set_error(self, message):
        with self._lock:
            self._last_error = message
        self.events.publish({
            "kind": "status", "last_error": message, "ts": _iso(),
        })

    def add_topic(self, topic):
        with self._lock:
            self._topics.add(topic)
            topics = sorted(self._topics)
        self.events.publish({"kind": "status", "subscribed_topics": topics})

    def snapshot(self):
        with self._lock:
            return {
                "mode": self._mode,
                "connected": self._connected,
                "client_id": self._client_id,
                "topics": sorted(self._topics),
                "last_error": self._last_error,
            }