"""Codec MQTT 3.1.1 : lecture / analyse / construction de trames (sans librairie externe)."""
import struct

MQTT_TYPES = {
    1: "CONNECT", 2: "CONNACK", 3: "PUBLISH", 4: "PUBACK", 5: "PUBREC",
    6: "PUBREL", 7: "PUBCOMP", 8: "SUBSCRIBE", 9: "SUBACK", 10: "UNSUBSCRIBE",
    11: "UNSUBACK", 12: "PINGREQ", 13: "PINGRESP", 14: "DISCONNECT",
}


class MQTTError(Exception):
    """Erreur / EOF sur le réseau."""


def encode_remaining_length(n):
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n > 0:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def decode_remaining_length(data, o=0):
    mult, rl, shift = 1, 0, 0
    while True:
        if o >= len(data):
            raise MQTTError("remaining length invalide")
        b = data[o]; o += 1
        rl += (b & 0x7F) * mult
        if not (b & 0x80):
            return rl, o
        mult *= 128
        shift += 7
        if shift > 28:
            raise MQTTError("remaining length trop long")
    return rl, o


def _read_exact(sock, n, bufsize=65535):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise MQTTError("EOF")
        buf += chunk
    return buf


class MQTTReader:
    """Lit des trames MQTT depuis un socket (TLS ou TCP). Renvoie aussi le raw pour relayage."""
    def __init__(self, sock):
        self.sock = sock
        self.buf = b""

    def _fill(self):
        data = self.sock.recv(4096)
        if not data:
            raise MQTTError("EOF")
        self.buf += data

    def _read(self, n):
        while len(self.buf) < n:
            self._fill()
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def read_packet(self):
        """Renvoie (ptype, flags, payload, raw) ou None si EOF propre."""
        try:
            h = self._read(1)
        except MQTTError:
            return None
        ptype = (h[0] >> 4) & 0xF
        flags = h[0] & 0xF
        # octets de remaining length (au moins un)
        rl_bytes = b""
        mult, shift, rl = 1, 0, 0
        while True:
            b = self._read(1)[0]
            rl_bytes += bytes([b])
            rl += (b & 0x7F) * mult
            if not (b & 0x80):
                break
            mult *= 128
            shift += 7
            if shift > 28:
                raise MQTTError("remaining length trop long")
        body = self._read(rl) if rl else b""
        raw = h + rl_bytes + body
        return ptype, flags, body, raw


def parse_string(buf, o):
    if o + 2 > len(buf):
        raise MQTTError("trame trop courte")
    n = struct.unpack_from(">H", buf, o)[0]; o += 2
    if o + n > len(buf):
        raise MQTTError("string depasse la trame")
    return buf[o:o + n].decode("utf-8", errors="replace"), o + n


def parse_connect(payload):
    o = 0
    proto, o = parse_string(payload, o)
    level = payload[o]; o += 1
    cflags = payload[o]; o += 1
    keepalive = struct.unpack_from(">H", payload, o)[0]; o += 2
    client_id, o = parse_string(payload, o)
    username = password = None
    if cflags & 0x80:
        username, o = parse_string(payload, o)
    if cflags & 0x40:
        pwlen = struct.unpack_from(">H", payload, o)[0]
        password = payload[o + 2:o + 2 + pwlen].decode("utf-8", errors="replace")
    return {
        "proto": proto, "level": level, "cflags": cflags,
        "keepalive": keepalive, "client_id": client_id,
        "username": username, "password": password,
    }


def parse_publish(payload):
    topic, o = parse_string(payload, o=0)
    return topic, o


def parse_subscribe(payload):
    if len(payload) < 2:
        raise MQTTError("subscribe trop court")
    pkt_id = struct.unpack_from(">H", payload, 0)[0]
    o = 2
    topics = []
    while o < len(payload):
        t, o = parse_string(payload, o)
        qos = payload[o]; o += 1
        topics.append((t, qos))
    return pkt_id, topics


# --- Builders ---
def build_connack(rc=0):
    return b"\x20\x02\x00" + bytes([rc])


def build_puback(pkt_id):
    return b"\x40" + encode_remaining_length(2) + struct.pack(">H", pkt_id)


def build_pubrec(pkt_id):
    return b"\x50" + encode_remaining_length(2) + struct.pack(">H", pkt_id)


def build_pubrel(pkt_id):
    return b"\x62" + encode_remaining_length(2) + struct.pack(">H", pkt_id)


def build_pubcomp(pkt_id):
    return b"\x70" + encode_remaining_length(2) + struct.pack(">H", pkt_id)


def build_pingresp():
    return b"\xD0\x00"


def build_suback(pkt_id, codes):
    body = struct.pack(">H", pkt_id) + bytes(codes)
    return b"\x90" + encode_remaining_length(len(body)) + body


def build_publish(topic, payload, qos=0, pkt_id=1, retain=False, dup=False):
    flags = (1 if dup else 0) << 3 | (qos & 3) << 1 | (1 if retain else 0)
    hdr = 0x30 | flags
    tb = topic.encode("utf-8")
    body = struct.pack(">H", len(tb)) + tb
    if qos:
        body += struct.pack(">H", pkt_id)
    pb = payload if isinstance(payload, bytes) else payload.encode("utf-8")
    body += pb
    return bytes([hdr]) + encode_remaining_length(len(body)) + body


def build_connect(client_id, username=None, password=None, keepalive=60):
    cflags = 0
    payload = struct.pack(">H", len(client_id)) + client_id.encode("utf-8")
    if username is not None:
        cflags |= 0x80
        payload += struct.pack(">H", len(username)) + username.encode("utf-8")
    if password is not None:
        cflags |= 0x40
        pb = password.encode("utf-8")
        payload += struct.pack(">H", len(pb)) + pb
    var = b"\x00\x04MQTT\x04" + bytes([cflags]) + struct.pack(">H", keepalive)
    body = var + payload
    return b"\x10" + encode_remaining_length(len(body)) + body


def build_subscribe(pkt_id, topics):
    body = struct.pack(">H", pkt_id)
    for t, q in topics:
        tb = t.encode("utf-8")
        body += struct.pack(">H", len(tb)) + tb + bytes([q & 3])
    return b"\x82" + encode_remaining_length(len(body)) + body