"""Client MQTT pour la discovery HA et le publishing des données PAC."""
import json
import logging
import os
import socket
import struct
import threading
import time
from datetime import datetime, timezone

from .. import mqtt
from ..utils import iso, safe_float
from .mode_mappings import (
    ALDES_TO_HA_MODE, HA_MODE_TO_ALDES,
    ALDES_TO_HA_PRESET, HA_PRESET_TO_ALDES,
    ALDES_WATER_TO_HA, HA_WATER_TO_ALDES,
    profile_code_for_label, profile_label_for_code,
)
from .discovery_config import build_discovery_config, detect_active_zones

_log = logging.getLogger("aldes-ha-discovery")


class HADiscoveryClient(threading.Thread):
    """Client MQTT qui connecte au broker local pour publier la decouverte HA.

    Thread daemon qui maintient la connexion et repond aux commandes HA.
    """

    KEEPALIVE = 30
    PUBLISH_INTERVAL = 60

    def __init__(self, state, host="127.0.0.1", port=1883, username=None, password=None, prefix="aldes", dry_run=True, zones_file=None):
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
        self._zones_file = zones_file
        self._last_active_zones = self._load_zones()
        if dry_run:
            _log.warning("ha-discovery: *** DRY-RUN active *** les commandes HA ne seront PAS envoyees a la box")
            _log.warning("ha-discovery: pour activer, passez HA_MQTT_DRY_RUN=false ou --ha-mqtt-no-dry-run")

    def _load_zones(self):
        if not self._zones_file:
            return []
        try:
            with open(self._zones_file, "r") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_zones(self, zones):
        if not self._zones_file:
            return
        try:
            with open(self._zones_file, "w") as f:
                json.dump(zones, f)
        except OSError as exc:
            _log.warning("ha-discovery: impossible de sauvegarder les zones: %s", exc)

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
        try:
            while not self._stop.is_set():
                ok = self._session()
                backoff = 1.0 if ok else min(backoff * 2, 10)
                if not self._stop.is_set():
                    time.sleep(backoff)
        except Exception as exc:
            _log.exception("ha-discovery: thread crashed: %s", exc)

    def _session(self):
        _log.info("ha-discovery: tentative connexion vers %s:%d (user=%s)",
                  self.host, self.port, self.username or "(none)")
        try:
            s = socket.create_connection((self.host, self.port), timeout=6)
            s.settimeout(self.KEEPALIVE / 3)
        except Exception as exc:
            _log.warning("ha-discovery: connexion impossible vers %s:%d: %s", self.host, self.port, exc)
            return False

        reader = mqtt.MQTTReader(s)
        try:
            s.sendall(mqtt.build_connect(
                "aldes-ha-discovery",
                username=self.username,
                password=self.password,
                keepalive=self.KEEPALIVE,
                will_topic=f"{self.prefix}/state/available",
                will_payload="offline",
                will_qos=1,
                will_retain=True,
            ))
            pkt = reader.read_packet()
            if pkt is None or pkt[0] != mqtt.PT_CONNACK or (pkt[3][2] if len(pkt[3]) > 2 else -1) != 0:
                rc = pkt[3][2] if pkt and len(pkt[3]) > 2 else -1
                _log.warning("ha-discovery: CONNACK refuse (rc=%d) — broker=%s:%d", rc, self.host, self.port)
                s.close()
                return False
            _log.info("ha-discovery: CONNACK OK — connecte a %s:%d", self.host, self.port)
        except Exception as exc:
            _log.warning("ha-discovery: erreur handshake: %s", exc)
            try:
                s.close()
            except Exception:
                pass
            return False

        self._sock = s

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
        topic_list = [t for t, _ in cmd_topics]
        _log.info("ha-discovery: souscription a %d topics: %s", len(topic_list), topic_list)
        try:
            s.sendall(mqtt.build_subscribe(1, cmd_topics))
        except Exception as exc:
            _log.warning("ha-discovery: subscribe echoue: %s", exc)
            s.close()
            return False

        try:
            suback = reader.read_packet()
            if suback and suback[0] == mqtt.PT_SUBACK:
                _log.info("ha-discovery: SUBACK recu — souscription OK")
            else:
                _log.warning("ha-discovery: pas de SUBACK (recu: %s)", suback)
        except Exception as exc:
            _log.warning("ha-discovery: erreur SUBACK: %s", exc)

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
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8", errors="replace")
            _log.info("ha-discovery: <-- MQTT PUBLISH topic=%s payload=%s", topic, payload[:200])
            if qos == mqtt.QOS_AT_LEAST_ONCE:
                self._safe_send(mqtt.build_puback(pid))
            elif qos == mqtt.QOS_EXACTLY_ONCE:
                self._safe_send(mqtt.build_pubrec(pid))
            self._handle_command(topic, payload)
        elif ptype == mqtt.PT_PUBREC:
            pid = struct.unpack_from(">H", body, 0)[0]
            self._safe_send(mqtt.build_pubrel(pid))
        elif ptype == mqtt.PT_SUBACK:
            _log.info("ha-discovery: <-- MQTT SUBACK")
        elif ptype in (mqtt.PT_PUBACK, mqtt.PT_PUBCOMP):
            pass
        else:
            _log.debug("ha-discovery: packet type=%d", ptype)

    def _handle_command(self, topic, payload):
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="replace")
        payload = payload.strip()
        _log.info("ha-discovery: COMMANDE RECUE topic=%s payload=%s", topic, payload)

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
        ha_mode = payload.lower().strip()
        aldes_code = HA_MODE_TO_ALDES.get(ha_mode)
        if not aldes_code:
            _log.warning("ha-discovery: mode HA inconnu: %s", ha_mode)
            return
        self._inject_aldes_command("changeMode", [aldes_code])
        _log.info("ha-discovery: mode %s -> Aldes %s", ha_mode, aldes_code)

    def _handle_consigne_command(self, payload, zone=0):
        try:
            temp = float(payload)
        except ValueError:
            _log.warning("ha-discovery: consigne invalide: %s", payload)
            return
        self._inject_aldes_command(f"changeConsigneC{zone}", [str(temp)])
        self.state.request_consigne(str(zone), temp)
        self._safe_send(mqtt.build_publish(
            f"{self.prefix}/state/zone{zone}/consigne",
            f"{temp:.1f}", qos=1, retain=True,
        ))
        if zone == 0:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/consigne",
                f"{temp:.1f}", qos=1, retain=True,
            ))
        _log.info("ha-discovery: consigne zone %d -> %.1f°C", zone, temp)

    def _handle_preset_command(self, payload):
        preset = payload.strip()
        profile = getattr(self.state, "profile", None)
        aldes_code = profile_code_for_label(
            profile, ["air_modes_clim", "air_modes_heat"], preset, HA_PRESET_TO_ALDES
        )
        if not aldes_code:
            _log.warning("ha-discovery: preset inconnu: %s", preset)
            return
        self._inject_aldes_command("changeMode", [aldes_code])
        _log.info("ha-discovery: preset %s -> Aldes %s", preset, aldes_code)

    def _handle_ecs_command(self, payload):
        mode = payload.strip()
        profile = getattr(self.state, "profile", None)
        aldes_code = profile_code_for_label(
            profile, "water_modes", mode, HA_WATER_TO_ALDES
        )
        if not aldes_code:
            _log.warning("ha-discovery: mode ECS inconnu: %s", mode)
            return
        self._inject_aldes_command("changeMode", [aldes_code])
        _log.info("ha-discovery: ECS %s -> Aldes %s", mode, aldes_code)

    def _handle_vacation_start_command(self, payload):
        self._store_vacation_date("start", payload.strip())

    def _handle_vacation_end_command(self, payload):
        self._store_vacation_date("end", payload.strip())

    def _store_vacation_date(self, which, date_str):
        if not hasattr(self, "_vacation_dates"):
            self._vacation_dates = {}
        self._vacation_dates[which] = date_str
        start = self._vacation_dates.get("start")
        end = self._vacation_dates.get("end")
        if start and end:
            self._send_vacation_command(start, end)
            self._vacation_dates = {}

    def _send_vacation_command(self, start_str, end_str):
        try:
            start_epoch = int(datetime.strptime(start_str, "%Y-%m-%d").replace(
                tzinfo=timezone.utc).timestamp())
            end_epoch = int(datetime.strptime(end_str, "%Y-%m-%d").replace(
                tzinfo=timezone.utc).timestamp())
        except ValueError:
            _log.warning("ha-discovery: format date vacances invalide: %s / %s", start_str, end_str)
            return
        self._inject_aldes_command("changeVacation", [str(start_epoch), str(end_epoch)])
        _log.info("ha-discovery: vacances %s -> %s", start_str, end_str)

    def _handle_vacation_enable_command(self, payload):
        enable = payload.lower().strip() == "on"
        if enable:
            if not hasattr(self, "_vacation_dates"):
                self._vacation_dates = {}
            start = self._vacation_dates.get("start")
            end = self._vacation_dates.get("end")
            if start and end:
                self._send_vacation_command(start, end)
            else:
                _log.info("ha-discovery: vacances activee (dates non definies, utilisez les topics date)")
        else:
            self._inject_aldes_command("changeVacation", ["0", "0"])
            _log.info("ha-discovery: vacances desactivees")

    def _inject_aldes_command(self, method, params):
        body = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": method,
            "params": params if isinstance(params, list) else [params],
        }
        dry_run = self.state.config.get("ha_mqtt_dry_run") if self.state.config else self.dry_run
        if dry_run:
            _log.info("ha-discovery [DRY-RUN]: commande simulée: %s", json.dumps(body, ensure_ascii=False))
            return
        hook = getattr(self.state, "_ha_inject_hook", None)
        if hook:
            hook(
                f"devices/{self._device_id}/messages/devicebound",
                json.dumps(body, ensure_ascii=False),
                1,
            )
        else:
            _log.warning("ha-discovery: pas de hook d'injection disponible")

    def _publish_discovery(self):
        with self.state._lock:
            telemetry = dict(self.state.telemetry)
        data = next(iter(telemetry.values()), {}) if telemetry else None
        profile = getattr(self.state, "profile", None)
        active_zones = detect_active_zones(data) if data else []
        configs = build_discovery_config(
            self._device_id, profile, self.prefix, data,
            previous_active_zones=self._last_active_zones,
        )
        for topic, payload in configs:
            self._safe_send(mqtt.build_publish(topic, payload, qos=1, retain=True))
        self._last_active_zones = active_zones
        self._save_zones(active_zones)

    def _publish_state(self):
        with self.state._lock:
            telemetry = dict(self.state.telemetry)
            connected = self.state._connected

        availability = "online" if connected else "offline"
        self._safe_send(mqtt.build_publish(
            f"{self.prefix}/state/available", availability, qos=1, retain=True
        ))

        if not telemetry:
            return

        data = next(iter(telemetry.values()), {})
        if not data:
            return

        self._publish_telemetry_data(data, include_zone_aliases=True)

    def publish_telemetry(self, data):
        if not self._sock:
            return

        air_mode_code = self._get_air_mode_code(data)
        if air_mode_code:
            ha_mode = ALDES_TO_HA_MODE.get(air_mode_code, "off")
            if self._last_mode is not None and self._last_mode != ha_mode:
                _log.info("ha-discovery: mode change %s -> %s, republish discovery", self._last_mode, ha_mode)
                self._publish_discovery()
            self._last_mode = ha_mode

        self._publish_telemetry_data(data, include_zone_aliases=False)

    def _publish_telemetry_data(self, data, include_zone_aliases=False):
        air_mode_code = self._get_air_mode_code(data)
        if air_mode_code:
            ha_mode = ALDES_TO_HA_MODE.get(air_mode_code, "off")
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/mode", ha_mode, qos=1, retain=True
            ))
            profile = getattr(self.state, "profile", None)
            preset = profile_label_for_code(
                profile, ["air_modes_clim", "air_modes_heat"], air_mode_code, ALDES_TO_HA_PRESET
            )
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/preset", preset, qos=1, retain=True
            ))

        consignes = self.state.consignes_state()
        active_zones = detect_active_zones(data)
        for zone_idx in active_zones:
            temp = safe_float(data.get(f"MT{zone_idx}"))
            if temp is not None:
                self._safe_send(mqtt.build_publish(
                    f"{self.prefix}/state/zone{zone_idx}/temperature",
                    f"{temp:.1f}", qos=1, retain=True
                ))
                if include_zone_aliases and zone_idx == 0:
                    self._safe_send(mqtt.build_publish(
                        f"{self.prefix}/state/sensor/MT0",
                        f"{temp:.1f}", qos=1, retain=True
                    ))

            consigne = safe_float(data.get(f"UsC{zone_idx}"))
            entry = consignes.get(str(zone_idx))
            if entry and not entry.get("confirmed"):
                consigne = float(entry["requested"])
            if consigne is not None:
                self._safe_send(mqtt.build_publish(
                    f"{self.prefix}/state/zone{zone_idx}/consigne",
                    f"{consigne:.1f}", qos=1, retain=True
                ))
                if include_zone_aliases and zone_idx == 0:
                    self._safe_send(mqtt.build_publish(
                        f"{self.prefix}/state/consigne",
                        f"{consigne:.1f}", qos=1, retain=True
                    ))

        outdoor_temp = safe_float(data.get("Text"))
        if outdoor_temp is not None:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/sensor/Text", f"{outdoor_temp:.1f}", qos=1, retain=True
            ))

        if air_mode_code:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/sensor/UAM", air_mode_code, qos=1, retain=True
            ))

        mf_ac = data.get("MfAc")
        if mf_ac is not None:
            compressor_state = "1" if str(mf_ac) not in ("0", "", "null") else "0"
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/sensor/MfAc", compressor_state, qos=1, retain=True
            ))

        water_mode_code = self._get_water_mode_code(data)
        if water_mode_code:
            profile = getattr(self.state, "profile", None)
            ha_water = profile_label_for_code(
                profile, "water_modes", water_mode_code, ALDES_WATER_TO_HA
            )
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/ecs", ha_water, qos=1, retain=True
            ))

        ned = safe_float(data.get("NED"))
        if ned is not None:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/sensor/NED", f"{ned:.0f}", qos=1, retain=True
            ))

        tbb = safe_float(data.get("TBBa"))
        if tbb is not None:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/sensor/TBBa", f"{tbb:.1f}", qos=1, retain=True
            ))

        tbh = safe_float(data.get("TBHa"))
        if tbh is not None:
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/sensor/TBHa", f"{tbh:.1f}", qos=1, retain=True
            ))

        anti_l = data.get("AntiL")
        if anti_l is not None:
            antil_state = "1" if str(anti_l) not in ("0", "", "null") else "0"
            self._safe_send(mqtt.build_publish(
                f"{self.prefix}/state/sensor/AntiL", antil_state, qos=1, retain=True
            ))

        self._publish_vacation_state(data)

    def _publish_vacation_state(self, data):
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

        vacation_active = bool(start_date and end_date)
        self._safe_send(mqtt.build_publish(
            f"{self.prefix}/state/vacation_enable",
            "on" if vacation_active else "off",
            qos=1, retain=True,
        ))

    def _epoch_to_date_str(self, value):
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

    def _get_air_mode_code(self, data):
        try:
            index = int(float(data.get("UAM", -1)))
            modes = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
            if 0 <= index < len(modes):
                return modes[index]
        except (TypeError, ValueError):
            pass
        return None

    def _get_water_mode_code(self, data):
        try:
            index = int(float(data.get("UDM", -1)))
            codes = ["L", "M", "N"]
            if 0 <= index < len(codes):
                return codes[index]
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
