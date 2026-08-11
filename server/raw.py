"""Mode 'raw' : client MQTT natif (QoS1) se connectant a un broker local.

Difference avec proxy/bridge : ici c'est NOUS qui nous connectons au broker en
client — on publie les commandes sur <cmd_topic> et on reçoit réponses/telemetrie
sur <evt_topic>. Pas de MITM TLS de la box : schema box <-> broker <-> bridge(client).
"""
import socket
import struct
import threading
import time

from . import mqtt
from .appstate import emit_message, set_conn_ctx, clear_conn_ctx
from .tls import client_context


class RawClient(threading.Thread):
    KEEPALIVE = 30

    def __init__(self, state, cfg):
        super().__init__(daemon=True, name="rawclient")
        self.state = state
        self.cfg = cfg
        self._stop = threading.Event()
        self._sock = None
        self._reader = None
        self._send_lock = threading.Lock()
        self._pkt = 0
        self._pending = {}  # pkt_id -> threading.Event() (PUBACK / PUBCOMP)

    # --- cycle de vie ---
    def stop(self):
        self._stop.set()
        self.drop()

    def drop(self):
        """Ferme la session courante sans tuer la boucle de reconnexion."""
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    def run(self):
        backoff = 0.5
        while not self._stop.is_set():
            ok = self._session()
            backoff = 0.5 if ok else min(backoff * 2, 10)
            time.sleep(backoff)

    def _session(self):
        cfg = self.cfg
        try:
            s = socket.create_connection((cfg["host"], int(cfg["port"])), timeout=6)
            if cfg.get("tls"):
                s = client_context().wrap_socket(s, server_hostname=cfg["host"])
            s.settimeout(self.KEEPALIVE / 3)
        except Exception as exc:
            self.state.set_error("raw: %s" % exc)
            return False

        reader = mqtt.MQTTReader(s)
        try:
            s.sendall(mqtt.build_connect(cfg["client_id"], keepalive=self.KEEPALIVE))
            pkt = reader.read_packet()
            if pkt is None or pkt[0] != 2 or (pkt[3][2] if len(pkt[3]) > 2 else -1) != 0:
                self.state.set_error("raw: CONNACK refuse")
                s.close()
                return False
            evt = (cfg.get("evt_topic") or "").strip()
            if evt:
                s.sendall(mqtt.build_subscribe(1, [(evt, 1)]))
                self.state.add_topic(evt)
        except Exception as exc:
            self.state.set_error("raw: %s" % exc)
            try:
                s.close()
            except Exception:
                pass
            return False

        self._sock = s
        self._reader = reader
        self._pending.clear()
        set_conn_ctx("raw", cfg.get("host"))
        self.state.session_up(cfg["client_id"])

        last_ping = time.time()
        try:
            while not self._stop.is_set():
                try:
                    pkt = reader.read_packet()
                except socket.timeout:
                    if time.time() - last_ping >= self.KEEPALIVE / 2:
                        self._send(mqtt.build_pingreq())
                        last_ping = time.time()
                    continue
                except (mqtt.MQTTError, OSError):
                    break
                if pkt is None:
                    break
                self._handle(pkt)
        finally:
            self._teardown()
        return True

    def _send(self, data):
        sock = self._sock
        if sock is None:
            return False
        with self._send_lock:
            try:
                sock.sendall(data)
                return True
            except (OSError, socket.timeout):
                return False

    def _teardown(self):
        sock, self._sock = self._sock, None
        self._reader = None
        for ev in self._pending.values():
            ev.set()
        self._pending.clear()
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        self.state.session_down()
        clear_conn_ctx()

    # -- lecture d'un packet entrant ---
    def _handle(self, pkt):
        ptype, flags, body, raw = pkt
        if ptype == 3:  # PUBLISH (telemetrie / reponse de la box)
            topic, o = mqtt.parse_publish(body)
            qos = (flags >> 1) & 0x3
            off = o + (2 if qos else 0)
            payload = body[off:] if off < len(body) else b""
            if qos == 1:
                pid = struct.unpack_from(">H", body, o)[0]
                self._send(mqtt.build_puback(pid))
            elif qos == 2:
                pid = struct.unpack_from(">H", body, o)[0]
                self._send(mqtt.build_pubrec(pid))
            emit_message(self.state, "in", "PUBLISH", topic=topic, payload=payload, qos=qos)
        elif ptype == 5:  # PUBREC (pour nos PUBLISH QoS2)
            pid = struct.unpack_from(">H", body, 0)[0]
            self._send(mqtt.build_pubrel(pid))
        elif ptype in (4, 7):  # PUBACK / PUBCOMP -> leve l'attente
            pid = struct.unpack_from(">H", body, 0)[0]
            evt = self._pending.pop(pid, None)
            if evt:
                evt.set()
        elif ptype == 6:  # PUBREL
            pid = struct.unpack_from(">H", body, 0)[0]
            self._send(mqtt.build_pubcomp(pid))

    # -- injection d'une commande (boxward) ---
    def inject(self, topic, payload, qos):
        cfg = self.cfg
        if self._sock is None:
            return {"ok": False, "error": "broker non connecte"}
        if not topic or not topic.strip():
            topic = (cfg.get("cmd_topic") or "").strip()
        if not topic:
            return {"ok": False, "error": "topic vide"}
        topic = topic.strip()

        with self._lock_pkt():
            self._pkt += 1
            pid = self._pkt
        qos = qos if qos in (1, 2) else 1
        evt = None
        if qos:
            evt = threading.Event()
            self._pending[pid] = evt
        ok = self._send(mqtt.build_publish(topic, payload, qos=qos, pkt_id=pid))
        if not ok:
            self._pending.pop(pid, None)
            return {"ok": False, "error": "envoi impossible"}
        if evt is not None:
            evt.wait(2)
            self._pending.pop(pid, None)
        emit_message(self.state, "out", "PUBLISH", topic=topic, payload=payload, qos=qos, injected=True)
        return {"ok": True, "topic": topic, "qos": qos, "bytes": len(payload.encode("utf-8"))}

    def _lock_pkt(self):
        return self._send_lock