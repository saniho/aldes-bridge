"""Mode bridge : faux broker MQTT/TLS. La box se connecte a nous, on injecte direct."""
import json
import logging
import socket
import struct
import threading

from .mqtt import (
    MQTTReader, MQTTError, MQTT_TYPES,
    PT_CONNECT, PT_PUBLISH, PT_PUBREL, PT_SUBSCRIBE, PT_PINGREQ, PT_DISCONNECT,
    QOS_AT_LEAST_ONCE, QOS_EXACTLY_ONCE,
    parse_publish_full, parse_subscribe,
    build_connack, build_suback, build_puback, build_pubrec, build_pubcomp,
    build_pingresp,
)
from .appstate import emit_message, emit_connect, MQTTEndpoint

_log = logging.getLogger("aldes-bridge-mode")


class BridgeHandler(MQTTEndpoint):
    def __init__(self, state, sock, addr, session=None):
        self.state = state
        self.sock = sock
        self.addr = addr
        self.session = session
        self._send_lock = threading.Lock()
        self._pkt_id = 0
        self._closed = False

    # --- cycle de vie ---
    def run(self):
        reader = MQTTReader(self.sock)
        while not self._closed:
            try:
                packet = reader.read_packet()
            except socket.timeout:
                self.state.events.publish({
                    "kind": "status",
                    "ts": "now",
                    "note": "MQTT keepalive expire",
                    "session": self.session,
                })
                break
            except MQTTError:
                break
            except OSError:
                break
            if packet is None:
                break
            ptype, flags, body, _raw = packet
            try:
                if not self._handle(ptype, flags, body):
                    break
            except MQTTError:
                break
            except Exception as exc:  # ne pas faire tomber la connexion sur un parse erratique
                self.state.set_error("bridge: %s" % exc)
                break

    def shutdown(self):
        self._closed = True
        try:
            self.sock.close()
        except Exception:
            pass

    def _send(self, data):
        with self._send_lock:
            if not self._closed:
                self.sock.sendall(data)

    def inject(self, topic, payload, qos):
        return self._inject_raw(topic, payload, qos)

    def send_publish(self, data):
        self._send(data)

    # --- protocole ---
    def _handle(self, ptype, flags, body):
        if ptype == PT_CONNECT:
            info = emit_connect(self.state, body)
            keepalive = info.get("keepalive", 0)
            if keepalive > 0:
                self.sock.settimeout(keepalive * 1.5)
            self._send(build_connack(0))
        elif ptype == PT_PUBLISH:
            topic, qos, pkt_id, payload = parse_publish_full(body, flags)
            _log.debug("bridge: <-- PUBLISH topic=%s qos=%d payload=%s", topic, qos, payload[:100] if isinstance(payload, str) else payload)
            emit_message(self.state, "in", "PUBLISH", topic=topic, payload=payload, qos=qos)
            if qos == QOS_AT_LEAST_ONCE:
                self._send(build_puback(pkt_id))
            elif qos == QOS_EXACTLY_ONCE:
                # QoS2 : on ne repond qu'avec un PUBREC ; le PUBCOMP viendra apres le PUBREL.
                self._send(build_pubrec(pkt_id))
        elif ptype == PT_PUBREL:
            if len(body) >= 2:
                pkt_id = struct.unpack_from(">H", body)[0]
            else:
                pkt_id = 0
            self._send(build_pubcomp(pkt_id))
        elif ptype == PT_SUBSCRIBE:
            pkt_id, topics = parse_subscribe(body)
            for t, _q in topics:
                self.state.add_topic(t)
            emit_message(self.state, "in", "SUBSCRIBE", payload=json.dumps(topics, ensure_ascii=False))
            self._send(build_suback(pkt_id, [min(q, 2) for _, q in topics]))
        elif ptype == PT_PINGREQ:
            self._send(build_pingresp())
        elif ptype == PT_DISCONNECT:
            return False
        else:
            emit_message(self.state, "in", MQTT_TYPES.get(ptype, "PTYPE_%d" % ptype))
        return True
