"""Mode listen : remontee box -> Azure, commandes Azure bloquees.

Comme le proxy (MITM transparent), la box se connecte au bridge qui ouvre sa
propre liaison TLS vers le vrai Azure IoT Hub et la telemetrie box -> Azure
est relayee a l'identique. Difference : les PUBLISH venant d'Azure (commandes
devicebound) sont interceptes et BLOQUES — journalises (blocked=True) et
acquittes cote Azure pour eviter des retries, mais jamais livres a la box.

Les autres trames Azure -> box (CONNACK, SUBACK, PINGRESP, PUBACK/PUBREC/
PUBCOMP des telemetries de la box, ...) sont relayees telles quelles pour que
la session MQTT de la box reste vivante. L'injection locale (WebUI) reste
autorisee (QoS0, direct vers la box comme en proxy).
"""
import struct

from .mqtt import (
    MQTTReader, MQTTError, MQTT_TYPES,
    PT_PUBLISH, PT_PUBREL,
    QOS_AT_LEAST_ONCE, QOS_EXACTLY_ONCE,
    parse_publish_full,
    build_puback, build_pubrec, build_pubcomp,
)
from .appstate import emit_message
from .proxy import ProxyHandler


def _listen_forward_real_to_box(handler):
    """Strategie de forward real->box en mode listen : bloque les PUBLISH cloud."""
    reader = MQTTReader(handler.real_tls)
    blocked_qos2 = set()
    while not handler._closed:
        try:
            packet = reader.read_packet()
        except MQTTError:
            break
        except OSError:
            break
        if packet is None:
            break
        ptype, flags, body, raw = packet
        try:
            if ptype == PT_PUBLISH:
                topic, qos, pkt_id, payload = parse_publish_full(body, flags)
                emit_message(
                    handler.state, "out", "PUBLISH",
                    topic=topic, payload=payload, qos=qos,
                    blocked=True,
                )
                if qos == QOS_AT_LEAST_ONCE and pkt_id is not None:
                    handler.real_tls.sendall(build_puback(pkt_id))
                elif qos == QOS_EXACTLY_ONCE and pkt_id is not None:
                    blocked_qos2.add(pkt_id)
                    handler.real_tls.sendall(build_pubrec(pkt_id))
            elif ptype == PT_PUBREL:
                pkt_id = struct.unpack_from(">H", body)[0] if len(body) >= 2 else 0
                blocked_qos2.discard(pkt_id)
                handler.real_tls.sendall(build_pubcomp(pkt_id))
            else:
                emit_message(handler.state, "out", MQTT_TYPES.get(ptype, "PTYPE_%d" % ptype))
                handler._send_box(raw)
        except Exception as exc:
            handler.state.set_error("listen-real2box[%s]: %s" % (ptype, exc))
            try:
                handler._send_box(raw)
            except Exception:
                break
    handler._teardown()


class ListenHandler:
    """Wrapper : ProxyHandler avec forward real->box en mode listen (commandes bloques)."""

    def __init__(self, state, box_sock, addr, session=None):
        self._proxy = ProxyHandler(
            state, box_sock, addr, session=session,
            real_to_box_fn=_listen_forward_real_to_box,
        )

    def __getattr__(self, name):
        return getattr(self._proxy, name)

    def run(self):
        return self._proxy.run()

    def shutdown(self):
        return self._proxy.shutdown()

    def inject(self, topic, payload, qos):
        return self._proxy.inject(topic, payload, qos)

    def send_publish(self, data):
        return self._proxy.send_publish(data)
