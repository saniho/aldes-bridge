"""Mode proxy transparent : MITM entre la box et le vrai Azure IoT Hub + injection boxward."""
import json
import socket
import struct
import threading

from .mqtt import (
    MQTTReader, MQTTError, MQTT_TYPES,
    parse_connect, parse_publish, parse_subscribe, build_publish,
)
from .appstate import emit_message
from .tls import client_context, resolve


class ProxyHandler:
    """Relaye box <-> vrai Azure et permet d'injecter des trames PUBLISH vers la box."""

    def __init__(self, state, box_sock, addr, session=None):
        self.state = state
        self.box_sock = box_sock
        self.addr = addr
        self.session = session
        self.real_sock = None
        self.real_tls = None
        self._box_write_lock = threading.Lock()
        self._closed = False
        self.stale = False  # marque par l'engine quand une nouvelle connexion prend le relai
        self._pkt_id = 0

    # --- vie ---
    def run(self):
        try:
            real_ip = resolve(self.state.real_host, self.state.real_port)
            self.real_sock = socket.create_connection((real_ip, self.state.real_port), timeout=20)
            self.real_tls = client_context().wrap_socket(
                self.real_sock, server_hostname=self.state.real_host
            )
            self.real_tls.settimeout(None)
        except Exception as exc:
            self.state.set_error("connexion Azure: %s" % exc)
            return

        self.state.cloud_up()

        t1 = threading.Thread(target=self._forward_box_to_real, daemon=True)
        t2 = threading.Thread(target=self._forward_real_to_box, daemon=True)
        t1.start(); t2.start()
        try:
            t1.join(); t2.join()
        finally:
            if not self.stale:
                self.state.cloud_down()

    def shutdown(self):
        self._closed = True
        for s in (self.box_sock, self.real_tls, self.real_sock):
            try:
                s.close()
            except Exception:
                pass

    def _send_box(self, data):
        with self._box_write_lock:
            if not self._closed:
                self.box_sock.sendall(data)

    def inject(self, topic, payload, qos):
        # En mode proxy, on force QoS 0 pour ne pas fuiter un PUBACT vers le vrai cloud.
        qos = 0
        self._pkt_id += 1
        pkt = build_publish(topic, payload, qos=0, pkt_id=self._pkt_id)
        self._send_box(pkt)
        emit_message(self.state, "out", "PUBLISH", topic=topic, payload=payload, qos=0,
                 injected=True, session=self.session, host=(self.addr[0] if self.addr else None))
        return {"ok": True, "direction": "out", "qos": 0}

    # --- relay box -> real ---
    def _forward_box_to_real(self):
        reader = MQTTReader(self.box_sock)
        while not self._closed:
            try:
                packet = reader.read_packet()
            except MQTTError:
                break
            if packet is None:
                break
            ptype, flags, body, raw = packet
            try:
                self._log_box(ptype, flags, body, raw)
            except Exception as exc:
                self.state.set_error("box2real[%s]: %s" % (ptype, exc))
            try:
                self.real_tls.sendall(raw)
            except Exception:
                break

    def _log_box(self, ptype, flags, body, raw):
        if ptype == 1:  # CONNECT
            info = parse_connect(body)
            clean = {k: v for k, v in info.items() if k not in ("password",)}
            emit_message(self.state, "in", "CONNECT", payload=json.dumps(clean, ensure_ascii=False))
            self.state.session_up(info.get("client_id"))
        elif ptype == 3:  # PUBLISH box->real (telemetrie)
            topic, o = parse_publish(body)
            qos = (flags >> 1) & 3
            emit_message(self.state, "in", "PUBLISH", topic=topic, payload=body[o:], qos=qos)
        elif ptype == 8:  # SUBSCRIBE : memoriser pour proposer les topics dans l'UI
            pkt_id, topics = parse_subscribe(body)
            for t, _q in topics:
                self.state.add_topic(t)
            emit_message(self.state, "in", "SUBSCRIBE", payload=json.dumps(topics, ensure_ascii=False))
        elif ptype == 12:
            pass
        elif ptype in MQTT_TYPES:
            emit_message(self.state, "in", MQTT_TYPES[ptype])

    # --- forward real -> box ---
    def _forward_real_to_box(self):
        reader = MQTTReader(self.real_tls)
        while not self._closed:
            try:
                packet = reader.read_packet()
            except MQTTError:
                break
            if packet is None:
                break
            ptype, flags, body, raw = packet
            try:
                if ptype == 3:  # PUBLISH real->box (commandes cloud)
                    topic, o = parse_publish(body)
                    qos = (flags >> 1) & 3
                    emit_message(self.state, "out", "PUBLISH", topic=topic, payload=body[o:], qos=qos)
                else:
                    emit_message(self.state, "out", MQTT_TYPES.get(ptype, "PTYPE_%d" % ptype))
            except Exception as exc:
                self.state.set_error("real2box[%s]: %s" % (ptype, exc))
            try:
                self._send_box(raw)
            except Exception:
                break