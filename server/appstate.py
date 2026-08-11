"""Etat applicatif partage entre le moteur MQTT (threads) et l'API web (asyncio)."""
import threading
from datetime import datetime, timezone

from .events import EventBus

# Contexte de connexion : taggé par le thread qui gère une session box.
_CONN_CTX = threading.local()


def set_conn_ctx(session=None, host=None):
    """Enregistre la session courante (thread du handler) pour tagger les events."""
    _CONN_CTX.session = session
    _CONN_CTX.host = host


def clear_conn_ctx():
    _CONN_CTX.session = None
    _CONN_CTX.host = None


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
    session = getattr(_CONN_CTX, "session", None)
    host = getattr(_CONN_CTX, "host", None)
    if session is not None:
        ev["session"] = session
    if host is not None:
        ev["host"] = host
    ev.update(extra)
    state.events.publish(ev)


class AppState:
    MODES = ("proxy", "bridge", "raw")

    DEFAULT_RAW = {
        "enabled": False,
        "host": "127.0.0.1",
        "port": 1883,
        "tls": True,
        "client_id": "aldes-bridge",
        "cmd_topic": "aldes/vmc/cmd/devices/MAC_AIR/messages/devicebound",
        "evt_topic": "devices_MAC_AIR/messages/events",
    }

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
        self._raw = dict(AppState.DEFAULT_RAW)

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

    # --- Configuration du mode "raw" (client MQTT natif vers un broker) ---
    def raw_config(self, fields=None):
        with self._lock:
            if fields is None:
                return dict(self._raw)
            update = {k: v for k, v in fields.items() if k in self._raw}
            self._raw.update(update)
            return dict(self._raw)

    def snapshot(self):
        with self._lock:
            return {
                "mode": self._mode,
                "connected": self._connected,
                "client_id": self._client_id,
                "topics": sorted(self._topics),
                "last_error": self._last_error,
                "raw": dict(self._raw),
            }