"""Home Assistant MQTT Auto-Discovery.

Connecte le bridge en tant que client MQTT a un broker local (Mosquitto) pour :
  1. Publier les configs de decouverte automatique (homeassistant/.../config)
  2. Exposer l'etat de la PAC via des topics MQTT standardises
  3. Recevoir les commandes HA (mode, consigne, ECS, vacances) et les transmettre a la box

Le broker MQTT local doit etre accessible au meme moment que Home Assistant.
"""
import json
import logging
import os
import socket
import struct
import threading
import time
from datetime import datetime, timezone

from . import mqtt
from .appstate import _iso

_log = logging.getLogger("aldes-ha-discovery")


def detect_mqtt_broker():
    """Détecte le broker MQTT via l'API Supervisor (HA OS).

    Retourne {"host": ..., "port": ...} ou None si pas en mode add-on HA.
    """
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://supervisor/services/mqtt",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            host = data.get("data", {}).get("host")
            port = data.get("data", {}).get("port")
            if host and port:
                _log.info("ha-discovery: broker MQTT détecté via Supervisor: %s:%d", host, port)
                return {"host": host, "port": int(port)}
    except Exception as exc:
        _log.warning("ha-discovery: détection Supervisor échouée: %s", exc)
    return None

# --- Mapping Aldes air modes → HA HVAC modes ---
# A=Off, B=Hors gel, C=Éco, D=Confort, E=Anti-condensation, F=Air Confort, G=Éco nuit, H=Arrêt ventilateur, I=Auto
ALDES_TO_HA_MODE = {
    "A": "off",
    "B": "heat",
    "C": "heat",
    "D": "heat",
    "E": "heat",
    "F": "cool",      # Air Confort = mode froid
    "G": "auto",
    "H": "fan_only",
    "I": "auto",
}

HA_MODE_TO_ALDES = {
    "off": "A",
    "heat": "D",      # Confort par défaut
    "cool": "D",      # PAC air-air : même mode, la PAC gère le sens
    "auto": "I",
    "fan_only": "H",
    "dry": "E",       # Anti-condensation ≈ mode sec
}

# Preset modes HA ↔ Aldes
ALDES_TO_HA_PRESET = {
    "A": None,
    "B": "none",
    "C": "eco",
    "D": "comfort",
    "E": "none",
    "F": "comfort",  # Air Confort
    "G": "eco",
    "H": "none",
    "I": "none",
}

HA_PRESET_TO_ALDES = {
    "none": "D",
    "eco": "C",
    "comfort": "F",     # Air Confort
    "anti_freeze": "B",
}

# --- Mapping modes eau chaude (UDM 0..2) ---
WATER_MODE_INDEX_TO_CODE = {0: "L", 1: "M", 2: "N"}
WATER_MODE_CODE_TO_INDEX = {"L": 0, "M": 1, "N": 2}

ALDES_WATER_TO_HA = {
    "L": "eco",
    "M": "normal",
    "N": "confort",
}

HA_WATER_TO_ALDES = {
    "eco": "L",
    "normal": "M",
    "confort": "N",
}


def _get_float_val(data, key):
    """Extrait un float depuis la telemetry."""
    if data is None:
        return None
    val = data.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _get_min_max(data):
    """Retourne (min_temp, max_temp) selon le mode courant (chauffage vs froid)."""
    if data is None:
        return 5, 30

    air_mode = str(data.get("UAM", ""))
    is_cooling = air_mode in ("F",)

    if is_cooling:
        mi = _get_float_val(data, "CMiST")
        ma = _get_float_val(data, "CMaST")
    else:
        mi = _get_float_val(data, "FMiST")
        ma = _get_float_val(data, "FMaST")

    if mi is None:
        mi = min(
            _get_float_val(data, "CMiST") or 5,
            _get_float_val(data, "FMiST") or 5,
        )
    if ma is None:
        ma = max(
            _get_float_val(data, "CMaST") or 30,
            _get_float_val(data, "FMaST") or 30,
        )

    return int(mi), int(ma)


def _detect_active_zones(data):
    """Detecte les zones actives — require MT{N} (temperature) ET UsC{N} (consigne)."""
    if data is None:
        return []
    zones = []
    for i in range(10):
        mt = data.get(f"MT{i}")
        usc = data.get(f"UsC{i}")
        if mt is not None and usc is not None:
            zones.append(i)
    return zones


def _build_discovery_config(device_id, profile, prefix="aldes", data=None):
    """Construit les configs HA auto-discovery pour une PAC Aldes T.ONE."""
    configs = []

    discovery_prefix = "homeassistant"

    device_info = {
        "identifiers": [f"aldes_{device_id}"],
        "name": "Aldes T.ONE",
        "manufacturer": "Aldes",
        "model": profile.name if profile else "T.ONE AquaAIR",
    }

    # Min/max dynamiques selon le mode courant
    min_temp, max_temp = _get_min_max(data)

    # Detect active zones from UsC0..UsC9
    active_zones = _detect_active_zones(data)

    for zone_idx in active_zones:
        zone_suffix = f"_zone{zone_idx}" if zone_idx > 0 else ""
        zone_label = f"Zone {zone_idx}" if zone_idx > 0 else "PAC Aldes"

        climate_config = {
            "name": zone_label,
            "unique_id": f"aldes_{device_id}_climate{zone_suffix}",
            "device": device_info,
            "modes": ["off", "heat", "cool", "auto", "fan_only"],
            "mode_state_topic": f"{prefix}/state/mode",
            "mode_command_topic": f"{prefix}/set/mode",
            "temperature_state_topic": f"{prefix}/state/zone{zone_idx}/consigne",
            "temperature_command_topic": f"{prefix}/set/zone{zone_idx}/consigne",
            "current_temperature_topic": f"{prefix}/state/zone{zone_idx}/temperature",
            "temp_unit": "C",
            "min_temp": min_temp,
            "max_temp": max_temp,
            "temp_step": 1,
            "precision": 1,
            "preset_modes": ["eco", "comfort", "night", "anti_freeze"],
            "preset_mode_state_topic": f"{prefix}/state/preset",
            "preset_mode_command_topic": f"{prefix}/set/preset",
            "availability_topic": f"{prefix}/state/available",
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:heat-pump",
        }
        configs.append((
            f"{discovery_prefix}/climate/aldes_zone{zone_idx}/config",
            json.dumps(climate_config, ensure_ascii=False),
        ))

    # Si aucune zone détectée, créer au moins zone 0
    if not active_zones:
        climate_config = {
            "name": "PAC Aldes",
            "unique_id": f"aldes_{device_id}_climate",
            "device": device_info,
            "modes": ["off", "heat", "cool", "auto", "fan_only"],
            "mode_state_topic": f"{prefix}/state/mode",
            "mode_command_topic": f"{prefix}/set/mode",
            "temperature_state_topic": f"{prefix}/state/consigne",
            "temperature_command_topic": f"{prefix}/set/consigne",
            "current_temperature_topic": f"{prefix}/state/temperature",
            "temp_unit": "C",
            "min_temp": min_temp,
            "max_temp": max_temp,
            "temp_step": 1,
            "precision": 1,
            "preset_modes": ["eco", "comfort", "night", "anti_freeze"],
            "preset_mode_state_topic": f"{prefix}/state/preset",
            "preset_mode_command_topic": f"{prefix}/set/preset",
            "availability_topic": f"{prefix}/state/available",
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:heat-pump",
        }
        configs.append((f"{discovery_prefix}/climate/aldes/config", json.dumps(climate_config, ensure_ascii=False)))

    # --- Sensor : température extérieure ---
    outdoor_config = {
        "name": "PAC Aldes Extérieur",
        "unique_id": f"aldes_{device_id}_outdoor_temp",
        "state_topic": f"{prefix}/state/sensor/Text",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
        "device": {
            "identifiers": [f"aldes_{device_id}"],
        },
        "icon": "mdi:thermometer",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/sensor/outdoor_temp/config", json.dumps(outdoor_config, ensure_ascii=False)))

    # --- Sensor : température intérieure (zone 0) ---
    indoor_config = {
        "name": "PAC Aldes Intérieur",
        "unique_id": f"aldes_{device_id}_indoor_temp",
        "state_topic": f"{prefix}/state/sensor/MT0",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
        "device": {
            "identifiers": [f"aldes_{device_id}"],
        },
        "icon": "mdi:thermometer",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/sensor/indoor_temp/config", json.dumps(indoor_config, ensure_ascii=False)))

    # --- Sensor : mode air courant ---
    mode_config = {
        "name": "PAC Aldes Mode Air",
        "unique_id": f"aldes_{device_id}_air_mode",
        "state_topic": f"{prefix}/state/sensor/UAM",
        "device": {
            "identifiers": [f"aldes_{device_id}"],
        },
        "icon": "mdi:fog",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/sensor/air_mode/config", json.dumps(mode_config, ensure_ascii=False)))

    # --- Binary sensor : compresseur ---
    compressor_config = {
        "name": "PAC Aldes Compresseur",
        "unique_id": f"aldes_{device_id}_compressor",
        "state_topic": f"{prefix}/state/sensor/MfAc",
        "payload_on": "1",
        "payload_off": "0",
        "device_class": "running",
        "device": {
            "identifiers": [f"aldes_{device_id}"],
        },
        "icon": "mdi:cog",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/binary_sensor/compressor/config", json.dumps(compressor_config, ensure_ascii=False)))

    # --- Select : mode eau chaude sanitaire (ECS) ---
    ecs_config = {
        "name": "PAC Aldes Eau Chaude",
        "unique_id": f"aldes_{device_id}_ecs_mode",
        "state_topic": f"{prefix}/state/ecs",
        "command_topic": f"{prefix}/set/ecs",
        "options": ["eco", "normal", "confort"],
        "device": {
            "identifiers": [f"aldes_{device_id}"],
        },
        "icon": "mdi:water-boiler",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/select/ecs_mode/config", json.dumps(ecs_config, ensure_ascii=False)))

    # --- Date : debut vacances ---
    vacation_start_config = {
        "name": "PAC Aldes Vacances Début",
        "unique_id": f"aldes_{device_id}_vacation_start",
        "state_topic": f"{prefix}/state/vacation_start",
        "command_topic": f"{prefix}/set/vacation_start",
        "device": {
            "identifiers": [f"aldes_{device_id}"],
        },
        "icon": "mdi:calendar-start",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/date/vacation_start/config", json.dumps(vacation_start_config, ensure_ascii=False)))

    # --- Date : fin vacances ---
    vacation_end_config = {
        "name": "PAC Aldes Vacances Fin",
        "unique_id": f"aldes_{device_id}_vacation_end",
        "state_topic": f"{prefix}/state/vacation_end",
        "command_topic": f"{prefix}/set/vacation_end",
        "device": {
            "identifiers": [f"aldes_{device_id}"],
        },
        "icon": "mdi:calendar-end",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/date/vacation_end/config", json.dumps(vacation_end_config, ensure_ascii=False)))

    # --- Switch : activer/desactiver vacances ---
    vacation_enable_config = {
        "name": "PAC Aldes Vacances",
        "unique_id": f"aldes_{device_id}_vacation_enable",
        "state_topic": f"{prefix}/state/vacation_enable",
        "command_topic": f"{prefix}/set/vacation_enable",
        "payload_on": "on",
        "payload_off": "off",
        "device": {
            "identifiers": [f"aldes_{device_id}"],
        },
        "icon": "mdi:beach",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/switch/vacation_enable/config", json.dumps(vacation_enable_config, ensure_ascii=False)))

    return configs


class HADiscoveryClient(threading.Thread):
    """Client MQTT qui connecte au broker local pour publier la decouverte HA.

    Thread daemon quimaintient la connexion et repond aux commandes HA.
    """

    KEEPALIVE = 30
    PUBLISH_INTERVAL = 60  # re-publie les configs toutes les 60s

    def __init__(self, state, host="127.0.0.1", port=1883, username=None, password=None, prefix="aldes", dry_run=True):
        super().__init__(daemon=True, name="ha-discovery")
        self.state = state
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.prefix = prefix
        self.dry_run = dry_run
        self._stop = threading.Event()
        self._sock = None
        self._send_lock = threading.Lock()
        self._pkt = 0
        self._device_id = "aldes_bridge"
        self._last_mode = None

    def stop(self):
        self._stop.set()
        with self._send_lock:
            sock = self._sock
            self._sock = None
        if sock:
            try:
                sock.close()
            except Exception:
                pass

    def run(self):
        backoff = 1.0
        while not self._stop.is_set():
            ok = self._session()
            backoff = 1.0 if ok else min(backoff * 2, 30)
            if not self._stop.is_set():
                time.sleep(backoff)

    def _session(self):
        try:
            s = socket.create_connection((self.host, self.port), timeout=6)
            s.settimeout(self.KEEPALIVE / 3)
        except Exception as exc:
            _log.warning("ha-discovery: connexion impossible vers %s:%d: %s", self.host, self.port, exc)
            return False

        reader = mqtt.MQTTReader(s)
        try:
            _log.info("ha-discovery: connexion MQTT user=%s, password=%s",
                      self.username or "(none)", "***" if self.password else "(none)")
            s.sendall(mqtt.build_connect(
                "aldes-ha-discovery",
                username=self.username,
                password=self.password,
                keepalive=self.KEEPALIVE,
            ))
            pkt = reader.read_packet()
            if pkt is None or pkt[0] != mqtt.PT_CONNACK or (pkt[3][2] if len(pkt[3]) > 2 else -1) != 0:
                rc = pkt[3][2] if pkt and len(pkt[3]) > 2 else -1
                _log.warning("ha-discovery: CONNACK refuse (rc=%d)", rc)
                s.close()
                return False
        except Exception as exc:
            _log.warning("ha-discovery: erreur handshake: %s", exc)
            try:
                s.close()
            except Exception:
                pass
            return False

        self._sock = s

        # Souscrit aux topics de commande
        cmd_topics = [
            (f"{self.prefix}/set/mode", 1),
            (f"{self.prefix}/set/consigne", 1),
            (f"{self.prefix}/set/preset", 1),
            (f"{self.prefix}/set/ecs", 1),
            (f"{self.prefix}/set/vacation_start", 1),
            (f"{self.prefix}/set/vacation_end", 1),
            (f"{self.prefix}/set/vacation_enable", 1),
        ]
        for zi in range(10):
            cmd_topics.append((f"{self.prefix}/set/zone{zi}/consigne", 1))
        try:
            s.sendall(mqtt.build_subscribe(1, cmd_topics))
        except Exception as exc:
            _log.warning("ha-discovery: subscribe echoue: %s", exc)
            s.close()
            return False

        # Publie les configs de decouverte
        self._publish_discovery()
        self._publish_state()

        _log.info("ha-discovery: connecte a %s:%d", self.host, self.port)

        last_ping = time.time()
        last_config_publish = time.time()
        try:
            while not self._stop.is_set():
                try:
                    pkt = reader.read_packet()
                except socket.timeout:
                    if time.time() - last_ping >= self.KEEPALIVE / 2:
                        self._safe_send(mqtt.build_pingreq())
                        last_ping = time.time()
                    # Re-publie les configs periodiquement
                    if time.time() - last_config_publish >= self.PUBLISH_INTERVAL:
                        self._publish_discovery()
                        self._publish_state()
                        last_config_publish = time.time()
                    continue
                except (mqtt.MQTTError, OSError):
                    break
                if pkt is None:
                    break
                self._handle(pkt)
        finally:
            self._teardown()
        return True

    def _handle(self, pkt):
        ptype, flags, body, raw = pkt
        if ptype == mqtt.PT_PUBLISH:
            topic, qos, pid, payload = mqtt.parse_publish_full(body, flags)
            if qos == mqtt.QOS_AT_LEAST_ONCE:
                self._safe_send(mqtt.build_puback(pid))
            elif qos == mqtt.QOS_EXACTLY_ONCE:
                self._safe_send(mqtt.build_pubrec(pid))
            self._handle_command(topic, payload)
        elif ptype == mqtt.PT_PUBREC:
            pid = struct.unpack_from(">H", body, 0)[0]
            self._safe_send(mqtt.build_pubrel(pid))
        elif ptype in (mqtt.PT_PUBACK, mqtt.PT_PUBCOMP, mqtt.PT_SUBACK):
            pass

    def _handle_command(self, topic, payload):
        """Traite une commande recue de HA."""
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="replace")
        payload = payload.strip()

        try:
            if topic == f"{self.prefix}/set/mode":
                self._handle_mode_command(payload)
            elif topic == f"{self.prefix}/set/consigne":
                self._handle_consigne_command(payload, zone=0)
            elif topic.startswith(f"{self.prefix}/set/zone") and topic.endswith("/consigne"):
                zone_str = topic.split("/set/zone")[1].split("/")[0]
                try:
                    zone = int(zone_str)
                except ValueError:
                    zone = 0
                self._handle_consigne_command(payload, zone=zone)
            elif topic == f"{self.prefix}/set/preset":
                self._handle_preset_command(payload)
            elif topic == f"{self.prefix}/set/ecs":
                self._handle_ecs_command(payload)
            elif topic == f"{self.prefix}/set/vacation_start":
                self._handle_vacation_start_command(payload)
            elif topic == f"{self.prefix}/set/vacation_end":
                self._handle_vacation_end_command(payload)
            elif topic == f"{self.prefix}/set/vacation_enable":
                self._handle_vacation_enable_command(payload)
        except Exception as exc:
            _log.warning("ha-discovery: erreur commande %s: %s", topic, exc)

    def _handle_mode_command(self, payload):
        """Convertit un mode HA en commande Aldes et l'envoie a la box."""
        ha_mode = payload.lower().strip()
        aldes_code = HA_MODE_TO_ALDES.get(ha_mode)
        if not aldes_code:
            _log.warning("ha-discovery: mode HA inconnu: %s", ha_mode)
            return

        # Envoie la commande via le hook on_publish_in -> engine.inject
        self._inject_aldes_command("changeMode", {"code": aldes_code})
        _log.info("ha-discovery: mode %s -> Aldes %s", ha_mode, aldes_code)

    def _handle_consigne_command(self, payload, zone=0):
        """Recoit une consigne HA et l'envoie a la box."""
        try:
            temp = float(payload)
        except ValueError:
            _log.warning("ha-discovery: consigne invalide: %s", payload)
            return

        self._inject_aldes_command("changeConsigne", {"zone": f"C{zone}", "temperature": temp})
        _log.info("ha-discovery: consigne zone %d -> %.1f°C", zone, temp)

    def _handle_preset_command(self, payload):
        """Convertit un preset HA en mode Aldes."""
        preset = payload.lower().strip()
        aldes_code = HA_PRESET_TO_ALDES.get(preset)
        if not aldes_code:
            _log.warning("ha-discovery: preset inconnu: %s", preset)
            return

        self._inject_aldes_command("changeMode", {"code": aldes_code})
        _log.info("ha-discovery: preset %s -> Aldes %s", preset, aldes_code)

    def _handle_ecs_command(self, payload):
        """Convertit un mode ECS HA en commande Aldes."""
        mode = payload.lower().strip()
        aldes_code = HA_WATER_TO_ALDES.get(mode)
        if not aldes_code:
            _log.warning("ha-discovery: mode ECS inconnu: %s", mode)
            return

        self._inject_aldes_command("changeMode", {"code": aldes_code})
        _log.info("ha-discovery: ECS %s -> Aldes %s", mode, aldes_code)

    def _handle_vacation_start_command(self, payload):
        """Recoit une date de debut vacances (YYYY-MM-DD) et l'envoie a la box."""
        self._store_vacation_date("start", payload.strip())

    def _handle_vacation_end_command(self, payload):
        """Recoit une date de fin vacances (YYYY-MM-DD) et l'envoie a la box."""
        self._store_vacation_date("end", payload.strip())

    def _store_vacation_date(self, which, date_str):
        """Stocke une date de vacances pour envoi differe (start + end = commande complete)."""
        if not hasattr(self, "_vacation_dates"):
            self._vacation_dates = {}
        self._vacation_dates[which] = date_str
        # Si on a les deux dates, envoie la commande
        start = self._vacation_dates.get("start")
        end = self._vacation_dates.get("end")
        if start and end:
            self._send_vacation_command(start, end)
            self._vacation_dates = {}

    def _send_vacation_command(self, start_str, end_str):
        """Envoie la commande vacances a la box."""
        try:
            start_epoch = int(datetime.strptime(start_str, "%Y-%m-%d").replace(
                tzinfo=timezone.utc).timestamp())
            end_epoch = int(datetime.strptime(end_str, "%Y-%m-%d").replace(
                tzinfo=timezone.utc).timestamp())
        except ValueError:
            _log.warning("ha-discovery: format date vacances invalide: %s / %s", start_str, end_str)
            return

        self._inject_aldes_command("changeVacation", {
            "start": start_epoch,
            "end": end_epoch,
        })
        _log.info("ha-discovery: vacances %s -> %s", start_str, end_str)

    def _handle_vacation_enable_command(self, payload):
        """Active ou desactive le mode vacances."""
        enable = payload.lower().strip() == "on"
        if enable:
            # Active vacances avec les dates courantes (ou defaut demain/j+7)
            if not hasattr(self, "_vacation_dates"):
                self._vacation_dates = {}
            start = self._vacation_dates.get("start")
            end = self._vacation_dates.get("end")
            if start and end:
                self._send_vacation_command(start, end)
            else:
                _log.info("ha-discovery: vacances activee (dates non definies, utilisez les topics date)")
        else:
            # Desactive vacances : envoie start=0 end=0
            self._inject_aldes_command("changeVacation", {"start": 0, "end": 0})
            _log.info("ha-discovery: vacances desactivees")

    def _inject_aldes_command(self, method, params):
        """Envoie une commande Aldes JSON-RPC via le state (engine.inject)."""
        body = {
            "method": method,
            "params": params,
        }
        if self.dry_run:
            _log.info("ha-discovery [DRY-RUN]: commande simulée: %s", json.dumps(body, ensure_ascii=False))
            return
        # Utilise le hook d'injection du engine si disponible
        hook = getattr(self.state, "_ha_inject_hook", None)
        if hook:
            hook(
                f"device/{self._device_id}/messages/devicebound",
                json.dumps(body, ensure_ascii=False),
                1,
            )
        else:
            _log.warning("ha-discovery: pas de hook d'injection disponible")

    def _publish_discovery(self):
        """Publie les configs HA auto-discovery."""
        with self.state._lock:
            telemetry = dict(self.state.telemetry)
        data = next(iter(telemetry.values()), {}) if telemetry else None
        profile = getattr(self.state, "profile", None)
        configs = _build_discovery_config(self._device_id, profile, self.prefix, data)
        for topic, payload in configs:
            self._safe_send(mqtt.build_publish(topic, payload, qos=1, retain=True))

    def _publish_state(self):
        """Publie l'etat courant de la PAC sur les topics HA."""
        with self.state._lock:
            telemetry = dict(self.state.telemetry)
            connected = self.state._connected

        # Availability
        availability = "online" if connected else "offline"
        self._safe_send(mqtt.build_publish(
            f"{self.prefix}/state/available", availability, qos=1, retain=True
        ))

        if not telemetry:
            return

        data = next(iter(telemetry.values()), {})
        if not data:
            return

        # Mode air courant
        air_mode_code = self._get_air_mode_code(data)
        if air_mode_code:
            ha_mode = ALDES_TO_HA_MODE.get(air_mode_code, "off")
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/mode", ha_mode, qos=1, retain=True
            ))
            preset = ALDES_TO_HA_PRESET.get(air_mode_code, "none") or "none"
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/preset", preset, qos=1, retain=True
            ))

        # Temperatures et consignes par zone
        active_zones = _detect_active_zones(data)
        for zone_idx in active_zones:
            temp = self._get_float(data, f"MT{zone_idx}")
            if temp is not None:
                self._safe_send(mqtt.build_publish(
                    f"{self.prefix}/state/zone{zone_idx}/temperature",
                    f"{temp:.1f}", qos=1, retain=True
                ))
                if zone_idx == 0:
                    self._safe_send(mqtt.build_publish(
                        f"{self.prefix}/state/sensor/MT0",
                        f"{temp:.1f}", qos=1, retain=True
                    ))

            consigne = self._get_float(data, f"UsC{zone_idx}")
            if consigne is not None:
                self._safe_send(mqtt.build_publish(
                    f"{self.prefix}/state/zone{zone_idx}/consigne",
                    f"{consigne:.1f}", qos=1, retain=True
                ))
                if zone_idx == 0:
                    self._safe_send(mqtt.build_publish(
                        f"{self.prefix}/state/consigne",
                        f"{consigne:.1f}", qos=1, retain=True
                    ))

        # Temperature exterieure
        outdoor_temp = self._get_float(data, "Text")
        if outdoor_temp is not None:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/sensor/Text",
                f"{outdoor_temp:.1f}", qos=1, retain=True
            ))

        # Mode air label
        if air_mode_code:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/sensor/UAM", air_mode_code, qos=1, retain=True
            ))

        # Compresseur (MfAc)
        mf_ac = data.get("MfAc")
        if mf_ac is not None:
            compressor_state = "1" if str(mf_ac) not in ("0", "", "null") else "0"
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/sensor/MfAc", compressor_state, qos=1, retain=True
            ))

        # Mode eau chaude (UDM)
        water_mode_code = self._get_water_mode_code(data)
        if water_mode_code:
            ha_water = ALDES_WATER_TO_HA.get(water_mode_code, "normal")
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/ecs", ha_water, qos=1, retain=True
            ))

        # Vacances (Dvac/Fvac)
        self._publish_vacation_state(data)

    def _publish_vacation_state(self, data):
        """Publie l'etat des vacances (dates + enable)."""
        dvac = data.get("Dvac")
        fvac = data.get("Fvac")

        start_date = self._epoch_to_date_str(dvac)
        end_date = self._epoch_to_date_str(fvac)

        if start_date:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/vacation_start", start_date, qos=1, retain=True
            ))
        else:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/vacation_start", "", qos=1, retain=True
            ))

        if end_date:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/vacation_end", end_date, qos=1, retain=True
            ))
        else:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/vacation_end", "", qos=1, retain=True
            ))

        # Vacances actives si les deux dates sont definies et non nulles
        vacation_active = bool(start_date and end_date)
        self._safe_send(mqtt.build_publish(
            f"{self.prefix}/state/vacation_enable",
            "on" if vacation_active else "off",
            qos=1, retain=True,
        ))

    def _epoch_to_date_str(self, value):
        """Convertit un epoch (timestamp box) en YYYY-MM-DD, ou None si vide/invalide."""
        if not value:
            return None
        try:
            ts = float(value)
        except (TypeError, ValueError):
            return None
        if ts <= 0:
            return None
        try:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except (OSError, ValueError):
            return None

    def publish_telemetry(self, data):
        """Appelé quand une nouvelle telemetry arrive — met à jour les topics HA."""
        if not self._sock:
            return

        # Mode
        air_mode_code = self._get_air_mode_code(data)
        if air_mode_code:
            ha_mode = ALDES_TO_HA_MODE.get(air_mode_code, "off")

            # Republish discovery si le mode a changé (min/max dynamiques)
            if self._last_mode is not None and self._last_mode != ha_mode:
                _log.info("ha-discovery: mode change %s -> %s, republish discovery", self._last_mode, ha_mode)
                profile = getattr(self.state, "profile", None)
                configs = _build_discovery_config(self._device_id, profile, self.prefix, data)
                for topic, payload in configs:
                    self._safe_send(mqtt.build_publish(topic, payload, qos=1, retain=True))
            self._last_mode = ha_mode

            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/mode", ha_mode, qos=1, retain=True
            ))
            preset = ALDES_TO_HA_PRESET.get(air_mode_code, "none") or "none"
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/preset", preset, qos=1, retain=True
            ))

        # Temperatures et consignes par zone active
        active_zones = _detect_active_zones(data)
        for zone_idx in active_zones:
            temp = self._get_float(data, f"MT{zone_idx}")
            if temp is not None:
                self._safe_send(mqtt.build_publish(
                    f"{self.prefix}/state/zone{zone_idx}/temperature",
                    f"{temp:.1f}", qos=1, retain=True
                ))

            consigne = self._get_float(data, f"UsC{zone_idx}")
            if consigne is not None:
                self._safe_send(mqtt.build_publish(
                    f"{self.prefix}/state/zone{zone_idx}/consigne",
                    f"{consigne:.1f}", qos=1, retain=True
                ))

        # Temperature exterieure
        outdoor_temp = self._get_float(data, "Text")
        if outdoor_temp is not None:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/sensor/Text", f"{outdoor_temp:.1f}", qos=1, retain=True
            ))

        # Mode air label
        if air_mode_code:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/sensor/UAM", air_mode_code, qos=1, retain=True
            ))

        # Compresseur
        mf_ac = data.get("MfAc")
        if mf_ac is not None:
            compressor_state = "1" if str(mf_ac) not in ("0", "", "null") else "0"
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/sensor/MfAc", compressor_state, qos=1, retain=True
            ))

        # Mode eau chaude (UDM)
        water_mode_code = self._get_water_mode_code(data)
        if water_mode_code:
            ha_water = ALDES_WATER_TO_HA.get(water_mode_code, "normal")
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/ecs", ha_water, qos=1, retain=True
            ))

        # Vacances (Dvac/Fvac)
        self._publish_vacation_state(data)

    def _get_air_mode_code(self, data):
        """Extrait le code mode air (A-I) depuis la telemetrie."""
        try:
            index = int(float(data.get("UAM", -1)))
            modes = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
            if 0 <= index < len(modes):
                return modes[index]
        except (TypeError, ValueError):
            pass
        return None

    def _get_water_mode_code(self, data):
        """Extrait le code mode eau chaude (L/M/N) depuis la telemetrie."""
        try:
            index = int(float(data.get("UDM", -1)))
            codes = ["L", "M", "N"]
            if 0 <= index < len(codes):
                return codes[index]
        except (TypeError, ValueError):
            pass
        return None

    def _get_float(self, data, key):
        try:
            v = data.get(key)
            if v is not None:
                return float(v)
        except (TypeError, ValueError):
            pass
        return None

    def _safe_send(self, data):
        with self._send_lock:
            sock = self._sock
            if sock is None:
                return False
            try:
                sock.sendall(data)
                return True
            except (OSError, socket.timeout):
                return False

    def _teardown(self):
        with self._send_lock:
            self._sock = None
        _log.info("ha-discovery: deconnecte")
