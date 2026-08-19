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


class ListenHandler(ProxyHandler):
    """Comme ProxyHandler, mais la direction Azure -> box filtre les PUBLISH."""

    def _forward_real_to_box(self):
        reader = MQTTReader(self.real_tls)
        # ids des PUBLISH QoS2 bloques en attente de leur PUBREL -> PUBCOMP.
        blocked_qos2 = set()
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
                if ptype == PT_PUBLISH:
                    topic, qos, pkt_id, payload = parse_publish_full(body, flags)
                    emit_message(
                        self.state, "out", "PUBLISH",
                        topic=topic, payload=payload, qos=qos,
                        blocked=True,
                    )
                    # Acquitter cote Azure (le cloud croit livre) mais ne RIEN
                    # envoyer a la box. QoS2 : PUBREC, puis on attendra le PUBREL.
                    if qos == QOS_AT_LEAST_ONCE and pkt_id is not None:
                        self.real_tls.sendall(build_puback(pkt_id))
                    elif qos == QOS_EXACTLY_ONCE and pkt_id is not None:
                        blocked_qos2.add(pkt_id)
                        self.real_tls.sendall(build_pubrec(pkt_id))
                elif ptype == PT_PUBREL:
                    # PUBREL venant d'Azure = suite d'un PUBLISH QoS2 bloque :
                    # on clot avec PUBCOMP, on ne transmet pas a la box.
                    pkt_id = struct.unpack_from(">H", body)[0] if len(body) >= 2 else 0
                    blocked_qos2.discard(pkt_id)
                    self.real_tls.sendall(build_pubcomp(pkt_id))
                else:
                    emit_message(self.state, "out", MQTT_TYPES.get(ptype, "PTYPE_%d" % ptype))
                    self._send_box(raw)
            except Exception as exc:
                self.state.set_error("listen-real2box[%s]: %s" % (ptype, exc))
                try:
                    self._send_box(raw)
                except Exception:
                    break
        self._teardown()
