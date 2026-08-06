#!/usr/bin/env python3
"""Tests locaux du moteur (modes bridge & proxy) avec de faux pairs MQTT/TLS."""
import socket
import ssl
import sys
import threading
import time

sys.path.insert(0, "/home/ubuntu/aldes-bridge")

from server.appstate import AppState
from server.events import EventBus
from server.engine import Engine
from server.mqtt import (
    MQTTReader, MQTTError,
    build_connect, build_subscribe, build_publish,
)
from server.tls import client_context, server_context

BOX_CN = "aldesiotsuite.azure-devices.net"


def box_socket(port, tries=40):
    ctx = client_context()
    t0 = time.time()
    last = None
    while time.time() - t0 < 8:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=3)
            tls = ctx.wrap_socket(s, server_hostname=BOX_CN)
            return tls
        except (ConnectionRefusedError, ssl.SSLError, OSError) as exc:
            last = exc
            time.sleep(0.2)
    raise last


def read_packet(tls):
    return MQTTReader(tls).read_packet()


class FakeRealBroker(threading.Thread):
    """Faux 'Azure': accepte une connexion TLS, repond CONNACK/SUBACK, renvoie un PUBLISH."""

    def __init__(self, port):
        super().__init__(daemon=True)
        self.port = port
        self.received = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(4)

    def run(self):
        self.sock.settimeout(8)
        try:
            c, a = self.sock.accept()
        except socket.timeout:
            return
        ctx = server_context(BOX_CN)
        tls = ctx.wrap_socket(c, server_side=True)
        tls.settimeout(8)
        reader = MQTTReader(tls)
        while True:
            try:
                pkt = reader.read_packet()
            except MQTTError:
                break
            if pkt is None:
                break
            ptype, flags, body, raw = pkt
            self.received.append(ptype)
            if ptype == 1:
                tls.sendall(b"\x20\x02\x00\x00")  # CONNACK
            elif ptype == 8:
                import struct as _s
                pid = _s.unpack_from(">H", body, 0)[0]
                codes = bytes([0]) * ((len(body) - 2) // 3)
                tls.sendall(b"\x90" + bytes([len(codes) + 2]) + _s.pack(">H", pid) + codes)
            elif ptype == 3:
                # renvoie un PUBLISH de confirmation sur le meme topic (simule le cloud)
                topic, o = 0, 0
                from server.mqtt import parse_publish
                topic, o = parse_publish(body)
                tls.sendall(build_publish(topic, "{\"cloud\":\"reply\"}", qos=0))
            elif ptype == 12:
                tls.sendall(b"\xD0\x00")
        tls.close()


def wait_state(state, attr, value, timeout=5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if state.snapshot().get(attr) == value:
            return True
        time.sleep(0.1)
    return False


def test_bridge_inject():
    print("== test_bridge_inject ==")
    events = EventBus()
    state = AppState("fake-host", 9999, events)
    state.set_mode("bridge")
    eng = Engine(state, mqtt_port=18883)
    eng.start()
    time.sleep(0.5)

    tls = box_socket(18883)
    tls.sendall(build_connect("box-test-bridge"))
    assert read_packet(tls)[0] == 2, "attendu CONNACK"
    assert wait_state(state, "connected", True), "session non up"
    assert state.snapshot()["client_id"] == "box-test-bridge"

    tls.sendall(build_subscribe(1, [("dev/box/messages/devicebound/#", 1)]))
    assert read_packet(tls)[0] == 9, "attendu SUBACK"
    assert "dev/box/messages/devicebound/#" in state.snapshot()["topics"], "topic non enregistre"

    res = eng.inject("dev/box/messages/devicebound/1", '{"cmd":"hello"}', 1)
    assert res["ok"], res
    ptype, flags, body, _ = read_packet(tls)
    assert ptype == 3, "attendu PUBLISH injecte"
    from server.mqtt import parse_publish
    topic, o = parse_publish(body)
    assert topic == "dev/box/messages/devicebound/1"
    assert body[o + 2:].decode() == '{"cmd":"hello"}'  # qos1 -> 2 octets packet id

    # verifier que l'evenement est journalise
    msgs = [e for e in events.snapshot() if e.get("kind") == "message"]
    out = [m for m in msgs if m["direction"] == "out" and m["type"] == "PUBLISH"]
    assert out, "commande envoyee non journalisee"
    import json as _json
    assert _json.loads(out[-1]["payload"]) == {"cmd": "hello"}

    tls.close()
    eng.stop()
    time.sleep(0.3)
    assert wait_state(state, "connected", False), "session non down"
    print("  OK")


def test_proxy_relay_inject():
    print("== test_proxy_relay_inject ==")
    fake = FakeRealBroker(18886)
    fake.start()
    time.sleep(0.3)

    events = EventBus()
    state = AppState("127.0.0.1", 18886, events)
    state.set_mode("proxy")
    eng = Engine(state, mqtt_port=18885)
    eng.start()
    time.sleep(0.5)

    tls = box_socket(18885)
    tls.sendall(build_connect("box-test-proxy"))
    assert read_packet(tls)[0] == 2, "attendu CONNACK (relaye du fake Azure)"
    assert wait_state(state, "connected", True), "snapshot=%s" % state.snapshot()
    assert state.snapshot()["client_id"] == "box-test-proxy"

    tls.sendall(build_subscribe(1, [("dev/box/messages/devicebound/#", 1)]))
    assert read_packet(tls)[0] == 9, "attendu SUBACK (relaye)"
    assert "dev/box/messages/devicebound/#" in state.snapshot()["topics"]

    # injection boxward
    res = eng.inject("dev/box/messages/devicebound/9", '{"cmd":"proxy"}', 1)
    assert res["ok"], res
    ptype, flags, body, _ = read_packet(tls)
    assert ptype == 3
    from server.mqtt import parse_publish
    topic, o = parse_publish(body)
    assert topic == "dev/box/messages/devicebound/9"
    assert body[o:].decode() == '{"cmd":"proxy"}'

    # telemetrie box->real relayee : le fake Azure doit recevoir le PUBLISH
    tls.sendall(build_publish("dev/box/messages/telemetry", '{"t":21}', qos=0))
    time.sleep(0.5)
    assert 3 in fake.received, "PUBLISH non relaye vers le cloud"

    tls.close()
    eng.stop()
    fake.sock.close()
    print("  OK")


if __name__ == "__main__":
    test_bridge_inject()
    test_proxy_relay_inject()
    print("TOUS LES TESTS PASSENT")
