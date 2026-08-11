"""Mode bridge : faux broker MQTT/TLS. La box se connecte a nous, on injecte direct."""
import json
import struct
import threading

from .mqtt import (
    MQTTReader, MQTTError, MQTT_TYPES,
    parse_connect, parse_publish, parse_subscribe,
    build_connack, build_suback, build_puback, build_pubrec, build_pubcomp,
    build_pingresp, build_publish,
)
from .appstate import emit_message


class BridgeHandler:
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
            except MQTTError:
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
        self._pkt_id += 1
        pkt = build_publish(topic, payload, qos=qos, pkt_id=self._pkt_id)
        self._send(pkt)
        emit_message(
            self.state, "out", "PUBLISH",
            topic=topic, payload=payload, qos=qos,
            injected=True, session=self.session, host=(self.addr[0] if self.addr else None),
        )
        return {"ok": True, "bytes": len(pkt)}

    # --- protocole ---
    def _handle(self, ptype, flags, body):
        if ptype == 1:  # CONNECT
            info = parse_connect(body)
            clean = {k: v for k, v in info.items() if k not in ("password",)}
            emit_message(self.state, "in", "CONNECT", payload=json.dumps(clean, ensure_ascii=False))
            self.state.session_up(info.get("client_id"))
            self._send(build_connack(0))
        elif ptype == 3:  # PUBLISH
            topic, o = parse_publish(body)
            qos = (flags >> 1) & 3
            if qos:
                pkt_id = struct.unpack_from(">H", body, o)[0]
                o += 2
            else:
                pkt_id = None
            payload = body[o:]
            emit_message(self.state, "in", "PUBLISH", topic=topic, payload=payload, qos=qos)
            if qos == 1:
                self._send(build_puback(pkt_id))
            elif qos == 2:
                # QoS2 : on ne repond qu'avec un PUBREC ; le PUBCOMP viendra apres le PUBREL.
                self._send(build_pubrec(pkt_id))
        elif ptype == 6:  # PUBREL (fin du handshake QoS2) -> PUBCOMP
            if len(body) >= 2:
                pkt_id = struct.unpack_from(">H", body)[0]
            else:
                pkt_id = 0
            self._send(build_pubcomp(pkt_id))
        elif ptype == 8:  # SUBSCRIBE
            pkt_id, topics = parse_subscribe(body)
            for t, _q in topics:
                self.state.add_topic(t)
            emit_message(self.state, "in", "SUBSCRIBE", payload=json.dumps(topics, ensure_ascii=False))
            self._send(build_suback(pkt_id, [min(q, 2) for _, q in topics]))
        elif ptype == 12:  # PINGREQ
            self._send(build_pingresp())
        elif ptype == 14:  # DISCONNECT
            return False
        else:
            emit_message(self.state, "in", MQTT_TYPES.get(ptype, "PTYPE_%d" % ptype))
        return True