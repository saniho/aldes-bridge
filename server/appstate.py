"""Etat applicatif partage entre le moteur MQTT (threads) et l'API web (asyncio)."""
import json
import logging
import threading
import time

from .events import EventBus
from .mqtt import build_publish, parse_connect
from .utils import atomic_write_json, iso, read_json

_log = logging.getLogger("aldes-appstate")
from .version import SERVER_VERSION

# Contexte de connexion : taggé par le thread qui gère une session box.
_CONN_CTX = threading.local()


def set_conn_ctx(session=None, host=None):
    """Enregistre la session courante (thread du handler) pour tagger les events."""
    _CONN_CTX.session = session
    _CONN_CTX.host = host


def read_persisted_mode(path):
    """Lit le mode persiste (JSON {"mode": ...}), None si absent/invalide."""
    data = read_json(path)
    mode = data.get("mode") if isinstance(data, dict) else None
    return mode if mode in AppState.MODES else None


def read_persisted_profile(path):
    """Lit le profil persiste (JSON {"profile_id": ...}), None si absent/invalide."""
    data = read_json(path)
    profile_id = data.get("profile_id") if isinstance(data, dict) else None
    return profile_id if isinstance(profile_id, str) and profile_id else None


def clear_conn_ctx():
    _CONN_CTX.session = None
    _CONN_CTX.host = None


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
    # les re-exposer via l'API Aldes : hook branche par main.py (decouplage
    # appstate/infrastructure <-> aldes/metier, plus d'import par trame).
    if direction == "in" and mtype == "PUBLISH":
        hook = getattr(state, "on_publish_in", None)
        if hook is not None:
            hook(state, payload)
    ev = {
        "kind": "message",
        "ts": iso(),
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


def emit_connect(state, body):
    """Journalise un CONNECT entrant (sans le mot de passe) et leve la session.

    Partagé par bridge.py et proxy.py, qui traitaient jusque-là le même packet
    (parse_connect + scrubbing password + emit_message + session_up) en double.
    """
    info = parse_connect(body)
    clean = {k: v for k, v in info.items() if k not in ("password",)}
    emit_message(state, "in", "CONNECT", payload=json.dumps(clean, ensure_ascii=False))
    state.session_up(info.get("client_id"))
    return info


class MQTTEndpoint:
    """Base commune aux handlers bridge/proxy : injection d'un PUBLISH boxward.

    Les sous-classes implementent `send_publish(data)` (envoi cadence par leur
    propre verrou) ; `_inject_raw(topic, payload, qos)` construit, envoie,
    journalise l'evenement (marque `injected`) et renvoie le resultat.
    """

    def _inject_raw(self, topic, payload, qos):
        _log.info("_inject_raw: topic=%s payload=%s qos=%d", topic, payload[:200] if isinstance(payload, str) else payload, qos)
        self._pkt_id = getattr(self, "_pkt_id", 0) + 1
        pkt = build_publish(topic, payload, qos=qos, pkt_id=self._pkt_id)
        self.send_publish(pkt)
        _log.info("_inject_raw: PUBLISH envoye (%d octets)", len(pkt))
        emit_message(
            self.state, "out", "PUBLISH",
            topic=topic, payload=payload, qos=qos,
            injected=True,
            session=getattr(self, "session", None),
            host=(self.addr[0] if getattr(self, "addr", None) else None),
        )
        return {"ok": True, "bytes": len(pkt)}

    def send_publish(self, data):
        raise NotImplementedError


class AppState:
    MODES = ("proxy", "bridge", "listen", "raw")

    # telemetry.json n'est qu'un cache de survie au redemarrage : inutile de le
    # reecrire a chaque trame (2-3/min), au plus toutes les TELEMETRY_SAVE_INTERVAL s.
    TELEMETRY_SAVE_INTERVAL = 30.0

    DEFAULT_RAW = {
        "enabled": False,
        "host": "127.0.0.1",
        "port": 1883,
        "tls": True,
        "client_id": "aldes-bridge",
        "cmd_topic": "aldes/vmc/cmd/devices/MAC_AIR/messages/devicebound",
        "evt_topic": "devices_MAC_AIR/messages/events",
    }

    def __init__(self, real_host, real_port, events, mode_file=None, telemetry_file=None, consigne_file=None, history=None, profile_file=None, config=None):
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
        # Consignes thermostats demandees (en attente de confirmation box).
        # zone (str "0".."9") -> {"requested": float, "confirmed": bool, "ts": iso}
        self._consignes = {}
        # Horodatages de connexion (epoch secondes) pour afficher les durees en haut.
        self._box_since = None
        self._cloud_since = None
        self._azure_ip = None
        # Fichier de persistance du mode (survite au redemarrage du conteneur).
        self._mode_file = mode_file
        # Persistance des telemetries captees : les dernieres valeurs restent
        # disponibles entre deux flux (et meme apres un redemarrage).
        self._telemetry_file = telemetry_file
        # Persistance des consignes demandees (survit au redemarrage du conteneur).
        self._consigne_file = consigne_file
        # Persistance du profil device (survit au redemarrage du conteneur).
        self._profile_file = profile_file
        # Configuration persistante (logs/config.json).
        self.config = config
        # Timer de purge automatique.
        self._purge_timer = None
        # Base d'historisation des valeurs (HistoryDB ou None). Remplie par
        # main.py ; branchee ici pour capter telemetries + connexions.
        self.history = history
        # Version de l'UI servie (mise a jour par create_app depuis web_dir).
        self.ui_version = "dev"
        self.server_version = SERVER_VERSION
        # Hook appele sur chaque PUBLISH entrant (capture telemetrie). Branche par
        # main.py sur server/aldes.py::capture_telemetry pour decoupler les modules.
        self.on_publish_in = None
        # Profil device charge depuis les fichiers YAML (DeviceProfile ou None).
        self.profile = None
        # Derniere persistance telemetrie (epoch) — throttle d'ecriture.
        self._last_telemetry_save = 0.0
        self._start_time = time.time()
        self._load_telemetry()
        self._load_consignes()

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
            "kind": "status", "mode": mode, "prev_mode": prev, "ts": iso(),
        })
        return mode

    def set_profile(self, profile):
        """Change le profil device et persiste le choix."""
        self.profile = profile
        self._persist_profile()

    def _persist_profile(self):
        """Ecrit le profil courant dans profile_file (atomique, ne casse jamais le runtime)."""
        if self.profile is None:
            atomic_write_json(self._profile_file, {"profile_id": None})
        else:
            atomic_write_json(self._profile_file, {"profile_id": self.profile.id})

    def start_purge_timer(self):
        """Demarre le timer de purge automatique (toutes les heures)."""
        self._purge_now()
        self._purge_timer = threading.Timer(3600.0, self._purge_loop)
        self._purge_timer.daemon = True
        self._purge_timer.start()

    def _purge_loop(self):
        self._purge_now()
        self._purge_timer = threading.Timer(3600.0, self._purge_loop)
        self._purge_timer.daemon = True
        self._purge_timer.start()

    def _purge_now(self):
        """Execute la purge de l'historique selon la config courante."""
        if self.history is None or self.config is None:
            return
        days = self.config.history_retention()
        self.history._days = days
        try:
            n = self.history.purge(days)
            if n > 0:
                _log.info("purge history: %d echantillons supprimes (retention %d jours)", n, days)
        except Exception as exc:
            _log.warning("purge history echouee: %s", exc)

    def _persist_mode(self):
        """Ecrit le mode courant dans mode_file (atomique, ne casse jamais le runtime)."""
        atomic_write_json(self._mode_file, {"mode": self._mode})

    def _load_telemetry(self):
        """Recharge les dernieres telemetries capturees depuis telemetry_file."""
        data = read_json(self._telemetry_file)
        if isinstance(data, dict):
            self.telemetry = {k: v for k, v in data.items() if isinstance(v, dict)}

    def _save_telemetry(self):
        """Persiste les telemetries (a appeler sous self._lock)."""
        atomic_write_json(self._telemetry_file, self.telemetry)

    def store_telemetry(self, pid, data):
        """Mes des champs d'une telemetrie T.ONE dans state.telemetry[pid].

        Memorisera la derniere valeur connue (survit au prochain flux et au
        redemarrage) et horodate la mise a jour cote serveur (_upd_at, epoch UTC).
        """
        with self._lock:
            current = dict(self.telemetry.get(pid, {}))
            # Log les changements de temperature/consigne
            temp_keys = [k for k in data if k.startswith("MT") or k.startswith("UsC")]
            if temp_keys:
                changes = {k: data[k] for k in temp_keys if str(data.get(k)) != str(current.get(k))}
                if changes:
                    _log.info("store_telemetry: pid=%s changements: %s", pid, changes)
            current.update(data)
            current["_pid"] = pid
            current["_upd_at"] = time.time()
            self.telemetry[pid] = current
            self._maybe_save_telemetry()
            self._confirm_consignes_from(data)
        if self.history is not None:
            self.history.record_telemetry(data)

    def _maybe_save_telemetry(self):
        """Persiste telemetry.json au plus toutes les TELEMETRY_SAVE_INTERVAL s.

        A appeler sous self._lock. Le fichier ne sert que de cache pour survivre
        a un redemarrage ; la box renvoie ses valeurs en continu, perdre les
        dernieres secondes est sans consequence. persist_telemetry() force l'ecriture.
        """
        now = time.time()
        if now - self._last_telemetry_save >= self.TELEMETRY_SAVE_INTERVAL:
            self._save_telemetry()
            self._last_telemetry_save = now

    def persist_telemetry(self):
        """Ecrit telemetry.json immediatement (flush, ex. a l'arret du processus)."""
        with self._lock:
            self._save_telemetry()
            self._last_telemetry_save = time.time()

    def _load_consignes(self):
        """Recharge les consignes demandees depuis consigne_file."""
        data = read_json(self._consigne_file)
        if isinstance(data, dict):
            self._consignes = {k: v for k, v in data.items()
                               if isinstance(v, dict) and "requested" in v}

    def _save_consignes(self):
        """Persiste les consignes demandees (a appeler sous self._lock)."""
        atomic_write_json(self._consigne_file, self._consignes)

    def request_consigne(self, zone, value):
        """Enregistre une consigne demandee pour une zone (en attente box)."""
        with self._lock:
            prev = self._consignes.get(zone)
            entry = {"requested": float(value), "confirmed": False, "ts": iso()}
            self._consignes[zone] = entry
            self._save_consignes()
        if prev is None or prev.get("requested") != entry["requested"]:
            self.events.publish({
                "kind": "consigne", "zone": zone,
                "requested": entry["requested"], "confirmed": False, "ts": entry["ts"],
            })

    def _confirm_consignes_from(self, data):
        """Confirme les consignes dont la box a rejoue la valeur dans une telemetrie.

        A appeler sous self._lock : pour chaque zone dont une UsC<n> est presente
        dans la trame, si elle correspond a une consigne demandee, on la marque
        confirmee (la box a bien applique la valeur) et on persiste.
        """
        changed = []
        for zone, entry in self._consignes.items():
            if entry.get("confirmed"):
                continue
            try:
                got = float(data.get("UsC%s" % zone))
            except (TypeError, ValueError):
                continue
            _log.debug("confirm_consigne: zone %s requested=%.1f got=%.1f (diff=%.2f)",
                       zone, entry["requested"], got, abs(got - entry["requested"]))
            if abs(got - entry["requested"]) < 0.01:
                entry["confirmed"] = True
                entry["ts"] = iso()
                changed.append(zone)
                _log.info("confirm_consigne: zone %s CONFIRMEE -> %.1f", zone, got)
        if not changed:
            return
        self._save_consignes()
        if changed:
            for zone in changed:
                entry = self._consignes[zone]
                self.events.publish({
                    "kind": "consigne", "zone": zone,
                    "requested": entry["requested"], "confirmed": True, "ts": entry["ts"],
                })

    def consignes_state(self):
        with self._lock:
            return {k: dict(v) for k, v in self._consignes.items()}

    def session_up(self, client_id):
        with self._lock:
            self._connected = True
            self._client_id = client_id
            self._topics = set()
            self._last_error = None
            self._box_since = time.time()
        self.events.publish({
            "kind": "status", "connected": True, "client_id": client_id, "ts": iso(),
        })
        if self.history is not None:
            self.history.record_status("box", True)

    def session_down(self):
        with self._lock:
            self._connected = False
            self._client_id = None
            self._topics = set()
            self._box_since = None
        self.events.publish({
            "kind": "status", "connected": False, "client_id": None, "ts": iso(),
        })
        if self.history is not None:
            self.history.record_status("box", False)

    def cloud_up(self, azure_ip=None):
        """Connexion du leg bridge -> Azure IoT Hub etablie (mode proxy)."""
        with self._lock:
            self._cloud_since = time.time()
            if azure_ip:
                self._azure_ip = azure_ip
        self.events.publish({
            "kind": "status", "cloud_connected": True, "ts": iso(),
        })
        if self.history is not None:
            self.history.record_status("cloud", True)

    def cloud_down(self):
        with self._lock:
            self._cloud_since = None

    def set_azure_ip(self, ip):
        """Stocke l'IP Azure resolue (meme si la connexion echoue)."""
        with self._lock:
            self._azure_ip = ip
        self.events.publish({
            "kind": "status", "cloud_connected": False, "ts": iso(),
        })
        if self.history is not None:
            self.history.record_status("cloud", False)

    def set_error(self, message):
        with self._lock:
            self._last_error = message
        self.events.publish({
            "kind": "status", "last_error": message, "ts": iso(),
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
            snap = {
                "mode": self._mode,
                "connected": self._connected,
                "client_id": self._client_id,
                "topics": sorted(self._topics),
                "last_error": self._last_error,
                "raw": dict(self._raw),
                "mode_file": self._mode_file,
                "box_since": self._box_since,
                "cloud_since": self._cloud_since,
                "azure_ip": self._azure_ip,
                "consignes": {k: dict(v) for k, v in self._consignes.items()},
                "server_version": self.server_version,
                "ui_version": self.ui_version,
                "history_days": self.history.retention_days if self.history is not None else None,
            }
            if self.profile is not None:
                snap["profile"] = self.profile.to_dict()
            return snap
