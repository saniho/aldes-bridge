"""Mode proxy transparent : MITM entre la box et le vrai Azure IoT Hub + injection boxward."""
import json
import logging
import socket
import threading

from .mqtt import (
    MQTTReader, MQTTError, MQTT_TYPES,
    PT_CONNECT, PT_PUBLISH, PT_SUBSCRIBE, PT_PINGREQ,
    parse_publish_full, parse_subscribe,
)
from .appstate import emit_message, emit_connect, MQTTEndpoint
from .tls import client_context, resolve

_log = logging.getLogger("aldes-proxy")


RELAY_TIMEOUT = 180.0  # s ; silence >= 3 min d'un cote -> dechirure du relais


class ProxyHandler(MQTTEndpoint):
    """Relaye box <-> vrai Azure et permet d'injecter des trames PUBLISH vers la box."""

    def __init__(self, state, box_sock, addr, session=None, real_to_box_fn=None):
        self.box_sock = box_sock
        self.state = state
        self.addr = addr
        self.session = session
        self.real_sock = None
        self.real_tls = None
        self._box_write_lock = threading.Lock()
        self._closed = False
        self.stale = False  # marque par l'engine quand une nouvelle connexion prend le relai
        self._pkt_id = 0
        self._real_to_box_fn = real_to_box_fn

    # --- vie ---
    def run(self):
        try:
            real_ip = resolve(self.state.real_host, self.state.real_port)
            self.state.set_azure_ip(real_ip)
            self.state.events.publish({"kind": "status", "ts": "now", "note": "Azure DNS: %s -> %s" % (self.state.real_host, real_ip)})
            self.real_sock = socket.create_connection((real_ip, self.state.real_port), timeout=20)
            self.real_tls = client_context().wrap_socket(
                self.real_sock, server_hostname=self.state.real_host
            )
            self.state.events.publish({"kind": "status", "ts": "now", "note": "Azure TLS OK: %s:%d" % (real_ip, self.state.real_port)})
            # Dead peer detecte : la box pingue ~toutes les 58 s, Azure repond
            # donc en moyenne chaque minute. Un silence plus long qu'un tour
            # complet de keepalive = lien mort (ou boite partie) -> dechirure.
            self.real_tls.settimeout(RELAY_TIMEOUT)
            self.box_sock.settimeout(RELAY_TIMEOUT)
        except Exception as exc:
            self.state.set_error("connexion Azure: %s" % exc)
            return

        self.state.cloud_up(azure_ip=real_ip)

        t1 = threading.Thread(target=self._forward_box_to_real, daemon=True)
        t2 = threading.Thread(target=self._forward_real_to_box, daemon=True)
        t1.start(); t2.start()
        try:
            t1.join(); t2.join()
        finally:
            if not self.stale:
                self.state.cloud_down()

    def _teardown(self):
        """Dechire tout le relais quand un cote meurt : shutdown() de chaque
        socket pour reveiller les threads bloques en recv/sendall (un simple
        close() depuis un autre thread ne reveille pas un recv sous Linux),
        puis fermeture."""
        self._closed = True
        for s in (self.real_sock, self.real_tls, self.box_sock):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
        for s in (self.real_sock, self.real_tls, self.box_sock):
            try:
                s.close()
            except Exception:
                pass

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
        return self._inject_raw(topic, payload, 0)

    def send_publish(self, data):
        self._send_box(data)

    # --- relay box -> real ---
    def _forward_box_to_real(self):
        reader = MQTTReader(self.box_sock)
        while not self._closed:
            try:
                packet = reader.read_packet()
            except MQTTError:
                break
            except OSError:  # socket.timeout / connexion coupee
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
        self._teardown()

    def _log_box(self, ptype, flags, body, raw):
        if ptype == PT_CONNECT:
            emit_connect(self.state, body)
        elif ptype == PT_PUBLISH:  # telemetrie
            topic, qos, _pid, payload = parse_publish_full(body, flags)
            _log.debug("proxy: <-- BOX PUBLISH topic=%s qos=%d payload=%s", topic, qos, payload[:100] if isinstance(payload, str) else payload)
            emit_message(self.state, "in", "PUBLISH", topic=topic, payload=payload, qos=qos)
        elif ptype == PT_SUBSCRIBE:  # memoriser pour proposer les topics dans l'UI
            pkt_id, topics = parse_subscribe(body)
            for t, _q in topics:
                self.state.add_topic(t)
            emit_message(self.state, "in", "SUBSCRIBE", payload=json.dumps(topics, ensure_ascii=False))
        elif ptype == PT_PINGREQ:
            pass
        elif ptype in MQTT_TYPES:
            emit_message(self.state, "in", MQTT_TYPES[ptype])

    # --- forward real -> box ---
    def _forward_real_to_box(self):
        if self._real_to_box_fn is not None:
            return self._real_to_box_fn(self)
        reader = MQTTReader(self.real_tls)
        while not self._closed:
            try:
                packet = reader.read_packet()
            except MQTTError:
                break
            except OSError:  # socket.timeout / Azure parti
                break
            if packet is None:
                break
            ptype, flags, body, raw = packet
            try:
                if ptype == PT_PUBLISH:  # commandes cloud
                    topic, qos, _pid, payload = parse_publish_full(body, flags)
                    emit_message(self.state, "out", "PUBLISH", topic=topic, payload=payload, qos=qos)
                else:
                    emit_message(self.state, "out", MQTT_TYPES.get(ptype, "PTYPE_%d" % ptype))
            except Exception as exc:
                self.state.set_error("real2box[%s]: %s" % (ptype, exc))
            try:
                self._send_box(raw)
            except Exception:
                break
        self._teardown()