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
    build_connect, build_subscribe, build_publish, build_pubrel,
    build_suback, build_puback, parse_publish,
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


class FakeRawBroker(threading.Thread):
    """Faux broker : accepte le client du bridge (mode raw), CONNACK+SUBACK,
    renvoie un PUBLISH (evenement) et capte les PUBLISH de commande recus."""

    def __init__(self, port):
        super().__init__(daemon=True)
        self.port = port
        self.recv = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(4)

    def run(self):
        import struct as _s
        self.sock.settimeout(8)
        try:
            c, a = self.sock.accept()
        except socket.timeout:
            return
        c.settimeout(8)
        reader = MQTTReader(c)
        try:
            if reader.read_packet()[0] != 1:
                c.close()
                return
            c.sendall(b"\x20\x02\x00\x00")  # CONNACK
            spkt = reader.read_packet()     # SUBSCRIBE
            pid = _s.unpack_from(">H", spkt[2], 0)[0]
            c.sendall(build_suback(pid, [1]))
            # evenement serveur -> client
            c.sendall(build_publish("devices/MAC_AIR/messages/events", '{"evt":"ok"}', qos=0))
            while True:
                pkt = reader.read_packet()
                if pkt is None:
                    break
                ptype, flags, body, raw = pkt
                if ptype == 3:
                    topic, o = parse_publish(body)
                    q = (flags >> 1) & 0x03
                    plen = o + 2 if q else o
                    self.recv.append((topic, body[plen:]))
                    if (flags >> 1) & 0x03 == 1:
                        pid = _s.unpack_from(">H", body, o)[0]
                        c.sendall(build_puback(pid))
                elif ptype == 12:
                    c.sendall(b"\xD0\x00")
        except MQTTError:
            pass
        c.close()


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

    # verifier que l'evenement est journalise et marque "injected"
    msgs = [e for e in events.snapshot() if e.get("kind") == "message"]
    out = [m for m in msgs if m["direction"] == "out" and m["type"] == "PUBLISH"]
    assert out, "commande envoyee non journalisee"
    import json as _json
    assert _json.loads(out[-1]["payload"]) == {"cmd": "hello"}
    assert out[-1].get("injected") is True, "injection non marquee injected=True"

    # telemetrie box->bridge : PUBACK attendu, evenement NON marque injected
    tls.sendall(build_publish("dev/box/telemetry", '{"t":1}', qos=1))
    assert read_packet(tls)[0] == 4, "attendu PUBACK"
    time.sleep(0.3)
    up = [m for m in events.snapshot()
          if m.get("kind") == "message" and m["direction"] == "in" and m["type"] == "PUBLISH"]
    assert up, "telemetrie non journalisee"
    assert up[-1].get("injected") is None, "telemetrie ne doit pas etre injected"

    tls.close()
    eng.stop()
    time.sleep(0.3)
    assert wait_state(state, "connected", False), "session non down"
    print("  OK")


def test_bridge_qos2():
    print("== test_bridge_qos2 ==")
    events = EventBus()
    state = AppState("fake-host", 9999, events)
    state.set_mode("bridge")
    eng = Engine(state, mqtt_port=18887)
    eng.start()
    time.sleep(0.5)

    tls = box_socket(18887)
    tls.sendall(build_connect("box-qos2"))
    assert read_packet(tls)[0] == 2, "attendu CONNACK"

    # PUBLISH QoS2 -> on doit repondre PUBREC (type 5), pas PUBACK (type 4)
    tls.sendall(build_publish("dev/box/qos2", '{"x":2}', qos=2))
    assert read_packet(tls)[0] == 5, "attendu PUBREC pour un QoS2"
    # PUBREL -> on doit repondre PUBCOMP (type 7)
    tls.sendall(build_pubrel(1))
    assert read_packet(tls)[0] == 7, "attendu PUBCOMP apres PUBREL"

    tls.close()
    eng.stop()
    time.sleep(0.3)
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

    msgs = [e for e in events.snapshot() if e.get("kind") == "message" and e["type"] == "PUBLISH"]
    injected = [m for m in msgs if m.get("injected")]
    assert injected and injected[-1].get("injected") is True, "injection proxy non marquee injected"

    # telemetrie box->real relayee : le fake Azure doit recevoir le PUBLISH
    tls.sendall(build_publish("dev/box/messages/telemetry", '{"t":21}', qos=0))
    time.sleep(0.5)
    assert 3 in fake.received, "PUBLISH non relaye vers le cloud"

    tls.close()
    eng.stop()
    fake.sock.close()
    print("  OK")


def test_raw_native():
    print("== test_raw_native ==")
    fake = FakeRawBroker(18888)
    fake.start()
    time.sleep(0.3)

    events = EventBus()
    state = AppState("fake-host", 9999, events)
    state.set_mode("raw")
    state.raw_config({
        "host": "127.0.0.1", "port": 18888, "tls": False,
        "client_id": "raw-test", "cmd_topic": "aldes/vmc/cmd/dev/1", "evt_topic": "devices_1/messages/events",
    })
    eng = Engine(state, mqtt_port=18889)
    eng.start()
    time.sleep(1.0)

    assert wait_state(state, "connected", True), "client raw non connecte: %s" % state.snapshot()
    assert state.snapshot()["client_id"] == "raw-test"

    # l'evenement serveur doit etre journalise en direction 'in', PAS marque injected
    msgs = [e for e in events.snapshot() if e.get("kind") == "message" and e["type"] == "PUBLISH"]
    inbound = [m for m in msgs if m["direction"] == "in"]
    assert inbound, "evenement broker non journalise"
    assert inbound[-1].get("injected") is None, "evenement reel ne doit pas etre injected"

    # injection : doit publier sur le broker (topic saisi)
    res = eng.inject("alds/test/dev/1", '{"cmd":"x"}', 1)
    assert res["ok"], res
    time.sleep(0.5)
    assert fake.recv, "commande non recue par le broker"
    topic, payload = fake.recv[-1]
    assert topic == "alds/test/dev/1" and payload.decode() == '{"cmd":"x"}', (topic, payload)
    out = [m for m in events.snapshot()
           if m.get("kind") == "message" and m["direction"] == "out" and m["type"] == "PUBLISH"]
    assert out and out[-1].get("injected") is True, "injection raw non marquee injected"

    # disconnect() ne doit pas tuer la boucle de reconnexion
    r = eng.disconnect()
    assert r["ok"] and r["session"] == "dropped", r
    time.sleep(0.3)
    assert not wait_state(state, "connected", False), "doit etre decroche apres disconnect"
    assert wait_state(state, "connected", True), "le client raw doit se reconnecter au broker"

    eng.stop()
    eng.join(timeout=3)
    fake.sock.close()
    print("  OK")


if __name__ == "__main__":
    test_bridge_inject()
    test_bridge_qos2()
    test_proxy_relay_inject()
    test_raw_native()
    print("TOUS LES TESTS PASSENT")
