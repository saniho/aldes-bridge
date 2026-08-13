"""Etat applicatif partage entre le moteur MQTT (threads) et l'API web (asyncio)."""
import json
import os
import threading
import time
from datetime import datetime, timezone

from .events import EventBus

# Contexte de connexion : taggé par le thread qui gère une session box.
_CONN_CTX = threading.local()


def set_conn_ctx(session=None, host=None):
    """Enregistre la session courante (thread du handler) pour tagger les events."""
    _CONN_CTX.session = session
    _CONN_CTX.host = host


def read_persisted_mode(path):
    """Lit le mode persiste (JSON {"mode": ...}), None si absent/invalide."""
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    mode = data.get("mode") if isinstance(data, dict) else None
    return mode if mode in AppState.MODES else None


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
    if not payload.startswith(("{", "[")):
        # La box prefixe ses telemetries d'un en-tete binaire : on ne garde
        # que le JSON qui suit, sinon l'affichage montre le bruit brut.
        for marker in ("{", "["):
            pos = payload.find(marker)
            if pos > 0:
                payload = payload[pos:]
                break
    if payload.startswith(("{", "[")):
        try:
            import json
            return json.dumps(json.loads(payload), indent=2, ensure_ascii=False)
        except Exception:
            pass
    return payload


def emit_message(state, direction, mtype, topic=None, payload=None, qos=None, **extra):
    # Capte les telemetries T.ONE publiees par la box (direction "in") pour
    # les re-exposer via l'API Aldes (server/aldes.py).
    if direction == "in" and mtype == "PUBLISH":
        from .aldes import capture_telemetry
        capture_telemetry(state, payload)
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

    def __init__(self, real_host, real_port, events, mode_file=None, telemetry_file=None):
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
        self.telemetry = {}
        # Horodatages de connexion (epoch secondes) pour afficher les durees en haut.
        self._box_since = None
        self._cloud_since = None
        # Fichier de persistance du mode (survite au redemarrage du conteneur).
        self._mode_file = mode_file
        # Persistance des telemetries captees : les dernieres valeurs restent
        # disponibles entre deux flux (et meme apres un redemarrage).
        self._telemetry_file = telemetry_file
        self._load_telemetry()

    @property
    def mode(self):
        with self._lock:
            return self._mode

    @property
    def connected(self):
        with self._lock:
            return self._connected

    def set_mode(self, mode):
        if mode not in self.MODES:
            raise ValueError("mode inconnu: %r (attendu: %s)" % (mode, "/".join(self.MODES)))
        with self._lock:
            prev, self._mode = self._mode, mode
        self._persist_mode()
        self.events.publish({
            "kind": "status", "mode": mode, "prev_mode": prev, "ts": _iso(),
        })
        return mode

    def _persist_mode(self):
        """Ecrit le mode courant dans mode_file (atomique, ne casse jamais le runtime)."""
        path = self._mode_file
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"mode": self._mode}, f)
            os.replace(tmp, path)
        except OSError:
            pass

    def _load_telemetry(self):
        """Recharge les dernieres telemetries capturees depuis telemetry_file."""
        path = self._telemetry_file
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            self.telemetry = {k: v for k, v in data.items() if isinstance(v, dict)}

    def _save_telemetry(self):
        """Persiste les telemetries (a appeler sous self._lock)."""
        path = self._telemetry_file
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.telemetry, f)
            os.replace(tmp, path)
        except OSError:
            pass

    def store_telemetry(self, pid, data):
        """Mes des champs d'une telemetrie T.ONE dans state.telemetry[pid].

        Memorisera la derniere valeur connue (survit au prochain flux et au
        redemarrage) et horodate la mise a jour cote serveur (_upd_at, epoch UTC).
        """
        with self._lock:
            current = dict(self.telemetry.get(pid, {}))
            current.update(data)
            current["_pid"] = pid
            current["_upd_at"] = time.time()
            self.telemetry[pid] = current
            self._save_telemetry()

    def session_up(self, client_id):
        with self._lock:
            self._connected = True
            self._client_id = client_id
            self._topics = set()
            self._last_error = None
            self._box_since = time.time()
        self.events.publish({
            "kind": "status", "connected": True, "client_id": client_id, "ts": _iso(),
        })

    def session_down(self):
        with self._lock:
            self._connected = False
            self._client_id = None
            self._topics = set()
            self._box_since = None
        self.events.publish({
            "kind": "status", "connected": False, "client_id": None, "ts": _iso(),
        })

    def cloud_up(self):
        """Connexion du leg bridge -> Azure IoT Hub etablie (mode proxy)."""
        with self._lock:
            self._cloud_since = time.time()
        self.events.publish({
            "kind": "status", "cloud_connected": True, "ts": _iso(),
        })

    def cloud_down(self):
        with self._lock:
            self._cloud_since = None
        self.events.publish({
            "kind": "status", "cloud_connected": False, "ts": _iso(),
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
                "mode_file": self._mode_file,
                "box_since": self._box_since,
                "cloud_since": self._cloud_since,
            }