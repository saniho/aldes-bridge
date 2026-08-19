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
        # Un seul ecrivain a la fois sur le socket TLS (sendall concurrent sur un
        # objet SSL depuis 2 threads corrompt l'etat et peut segfaulter a la fin).
        self._send_lock = threading.Lock()

    def _send(self, data):
        with self._send_lock:
            self.conn.sendall(data)

    def run(self):
        self.sock.settimeout(8)
        try:
            c, a = self.sock.accept()
        except socket.timeout:
            return
        ctx = server_context(BOX_CN)
        tls = ctx.wrap_socket(c, server_side=True)
        tls.settimeout(8)
        self.conn = tls
        reader = MQTTReader(tls)
        while True:
            try:
                pkt = reader.read_packet()
            except (MQTTError, OSError):
                break
            if pkt is None:
                break
            ptype, flags, body, raw = pkt
            self.received.append(ptype)
            if ptype == 1:
                self._send(b"\x20\x02\x00\x00")  # CONNACK
            elif ptype == 8:
                import struct as _s
                pid = _s.unpack_from(">H", body, 0)[0]
                codes = bytes([0]) * ((len(body) - 2) // 3)
                self._send(b"\x90" + bytes([len(codes) + 2]) + _s.pack(">H", pid) + codes)
            elif ptype == 3:
                # renvoie un PUBLISH de confirmation sur le meme topic (simule le cloud)
                topic, o = 0, 0
                from server.mqtt import parse_publish
                topic, o = parse_publish(body)
                self._send(build_publish(topic, "{\"cloud\":\"reply\"}", qos=0))
            elif ptype == 12:
                self._send(b"\xD0\x00")
        tls.close()

    def kill(self):
        """Mort silencieuse d'Azure : ferme la connexion sans DISCONNECT."""
        if self.conn is not None:
            try:
                self.conn.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.conn.close()
            except Exception:
                pass


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


def test_listen_blocks_cloud():
    """Mode listen : la telemetrie box -> Azure est relayee, mais les PUBLISH
    Azure -> box (commandes devicebound) sont bloques : journalises (blocked=True),
    acquittes cote Azure (PUBACK / PUBREC+PUBCOMP) et jamais livres a la box."""
    print("== test_listen_blocks_cloud ==")
    fake = FakeRealBroker(18897)
    fake.start()
    time.sleep(0.3)

    events = EventBus()
    state = AppState("127.0.0.1", 18897, events)
    state.set_mode("listen")
    eng = Engine(state, mqtt_port=18898)
    eng.start()
    time.sleep(0.5)

    tls = box_socket(18898)
    tls.sendall(build_connect("box-listen"))
    assert read_packet(tls)[0] == 2, "attendu CONNACK (relaye du fake Azure)"
    assert wait_state(state, "connected", True), "snapshot=%s" % state.snapshot()

    tls.sendall(build_subscribe(1, [("dev/box/messages/devicebound/#", 1)]))
    assert read_packet(tls)[0] == 9, "attendu SUBACK (relaye)"

    # telemetrie box -> Azure : relayee comme en proxy
    tls.sendall(build_publish("dev/box/messages/telemetry", '{"t":21}', qos=0))
    time.sleep(0.5)
    assert 3 in fake.received, "telemetrie non relayee vers le cloud"

    # le cloud repond par un PUBLISH devicebound QoS1 (pkt_id 42) :
    # ListenHandler doit le bloquer — jamais envoye a la box — et l'acquitter.
    fake._send(build_publish("dev/box/messages/devicebound/1", '{"cmd":"off"}', qos=1, pkt_id=42))
    time.sleep(0.5)

    # la box ne doit RIEN recevoir (ni la commande, ni un acquittement parasite)
    tls.settimeout(1.0)
    try:
        pkt = read_packet(tls)
    except (MQTTError, OSError):
        pkt = None
    assert pkt is None, "la box ne doit pas recevoir la commande bloquee: %r" % (pkt,)

    # le bridge doit avoir acquitte cote Azure : PUBACK (type 4) recu par le fake
    assert 4 in fake.received, "le bridge doit acquitter la commande cote Azure (PUBACK)"

    # commande devicebound QoS2 (pkt_id 43) : PUBREC puis PUBCOMP, jamais a la box
    fake._send(build_publish("dev/box/messages/devicebound/2", '{"cmd":"warm"}', qos=2, pkt_id=43))
    time.sleep(0.3)
    assert 5 in fake.received, "le bridge doit repondre PUBREC (QoS2)"
    fake._send(build_pubrel(43))
    time.sleep(0.3)
    assert 7 in fake.received, "le bridge doit repondre PUBCOMP apres PUBREL"
    tls.settimeout(1.0)
    try:
        pkt = read_packet(tls)
    except (MQTTError, OSError):
        pkt = None
    assert pkt is None, "la box ne doit pas recevoir le QoS2 bloque: %r" % (pkt,)

    # les commandes bloquees doivent etre journalisees avec blocked=True
    msgs = [e for e in events.snapshot()
            if e.get("kind") == "message" and e["type"] == "PUBLISH" and e["direction"] == "out"]
    blocked = [m for m in msgs if m.get("blocked")]
    assert len(blocked) >= 2, "commandes bloquees non journalisees: %d" % len(blocked)
    assert blocked[-1].get("topic") == "dev/box/messages/devicebound/2", blocked[-1]
    import json as _json
    assert _json.loads(blocked[-1]["payload"]) == {"cmd": "warm"}, blocked[-1]

    # la telemetrie (direction in) ne doit PAS etre marquee blocked
    allpub = [e for e in events.snapshot()
              if e.get("kind") == "message" and e["type"] == "PUBLISH"]
    up = [m for m in allpub if m["direction"] == "in" and m.get("blocked")]
    assert not up, "la telemetrie ne doit pas etre marquee blocked"

    # l'injection locale (WebUI) reste AUTORISEE en mode listen : livree a la box
    res = eng.inject("dev/box/messages/devicebound/9", '{"cmd":"local"}', 1)
    assert res["ok"], res
    ptype, flags, body, _ = read_packet(tls)
    assert ptype == 3, "la commande locale doit etre livree a la box"
    from server.mqtt import parse_publish
    topic, o = parse_publish(body)
    assert topic == "dev/box/messages/devicebound/9"
    assert body[o:].decode() == '{"cmd":"local"}', "injection listen livree telle quelle"

    tls.close()
    eng.stop()
    fake.sock.close()
    print("  OK")


def test_proxy_silent_azure_death():
    print("== test_proxy_silent_azure_death ==")
    fake = FakeRealBroker(18891)
    fake.start()
    time.sleep(0.3)

    events = EventBus()
    state = AppState("127.0.0.1", 18891, events)
    state.set_mode("proxy")
    eng = Engine(state, mqtt_port=18892)
    eng.start()
    time.sleep(0.5)

    tls = box_socket(18892)
    tls.sendall(build_connect("box-test-death"))
    assert read_packet(tls)[0] == 2, "attendu CONNACK (relaye du fake Azure)"
    assert wait_state(state, "connected", True), "snapshot=%s" % state.snapshot()
    assert state.snapshot()["cloud_since"] is not None

    # Azure meurt en silence (fermeture de socket, pas de DISCONNECT MQTT).
    fake.kill()

    # Le relais doit dechirer : la box voit la fermeture et l'etat repasse a deconnecte.
    assert wait_state(state, "connected", False, timeout=6), \
        "connected doit redescendre apres la mort d'Azure: %s" % state.snapshot()
    assert state.snapshot()["cloud_since"] is None, "cloud_down doit etre pose"
    tls.settimeout(5)
    try:
        pkt = read_packet(tls)
    except (MQTTError, OSError):
        pkt = None
    assert pkt is None, "la box doit voir la fermeture du lien (pas de nouvelle trame)"

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


class FakeConnHandler:
    """Faux handler : bloque dans run() jusqu'a relachement, sans reseau."""

    def __init__(self, state, cs, addr, session=None):
        self.state = state
        self.cs = cs
        self.stale = False
        self.entered = threading.Event()
        self.release = threading.Event()

    def run(self):
        self.entered.set()
        self.release.wait()
        self.release.clear()


def test_stale_handler_does_not_reset_connected():
    print("== test_stale_handler_does_not_reset_connected ==")
    import server.engine as eng_mod

    events = EventBus()
    state = AppState("fake-host", 9999, events)
    state.set_mode("proxy")

    orig_proxy = eng_mod.ProxyHandler
    eng_mod.ProxyHandler = FakeConnHandler
    try:
        eng = Engine(state, mqtt_port=18890)

        s1, c1 = socket.socketpair()
        s2, c2 = socket.socketpair()

        # connexion A : devient la session active, CONNECT -> connected=True
        t_a = threading.Thread(target=eng._handle, args=(c1, ("10.0.0.1", 40001)))
        t_a.start()
        a = eng.current_handler
        assert a.entered.wait(2), "handler A non demarre"
        state.session_up("ABCDEF123456_TONE")
        assert state.snapshot()["connected"] is True

        # connexion B arrive pendant que A tourne encore : B devient courant, A stale
        t_b = threading.Thread(target=eng._handle, args=(c2, ("10.0.0.2", 40002)))
        t_b.start()
        b = eng.current_handler
        assert b.entered.wait(2), "handler B non demarre"
        assert a.stale is True, "A doit etre marque stale quand B prend le relai"

        # A se termine APRES que B soit courant : il ne doit PAS ecraser l'etat
        a.release.set()
        t_a.join(timeout=3)
        assert not t_a.is_alive()
        assert state.snapshot()["connected"] is True, "l'ancien handler a ecrase connected=True"
        assert eng.current_handler is b, "A ne doit pas retirer B de current"

        # B se termine normalement : lui seul declenche session_down
        b.release.set()
        t_b.join(timeout=3)
        assert not t_b.is_alive()
        assert state.snapshot()["connected"] is False, "le handler courant doit poser session_down"
        assert eng.current_handler is None

        for s in (s1, s2):
            s.close()
    finally:
        eng_mod.ProxyHandler = orig_proxy
    print("  OK")


def test_session_ids_unique_across_reconnects():
    """Caracterisation : deux reconnexions reelles ont des ids de session distincts."""
    print("== test_session_ids_unique_across_reconnects ==")
    events = EventBus()
    state = AppState("fake-host", 9999, events)
    state.set_mode("bridge")
    eng = Engine(state, mqtt_port=18901)
    eng.start()
    time.sleep(0.5)

    tls1 = box_socket(18901)
    tls1.sendall(build_connect("box-seq-1"))
    assert read_packet(tls1)[0] == 2, "attendu CONNACK"
    assert wait_state(state, "connected", True)
    tls1.close()
    assert wait_state(state, "connected", False)

    tls2 = box_socket(18901)
    tls2.sendall(build_connect("box-seq-2"))
    assert read_packet(tls2)[0] == 2, "attendu CONNACK"
    assert wait_state(state, "connected", True)
    tls2.close()

    connects = [e for e in events.snapshot()
                if e.get("kind") == "message" and e.get("type") == "CONNECT"]
    sids = [e.get("session") for e in connects if e.get("session") is not None]
    assert len(sids) == 2, "attendu 2 sessions CONNECT: %s" % sids
    assert all(isinstance(s, int) for s in sids), "session id doit etre un entier"
    assert sids[0] != sids[1], "ids de session doivent etre distincts: %s" % sids

    eng.stop()
    time.sleep(0.3)
    print("  OK")


def test_session_registry_lifecycle():
    """Unitaire du SessionRegistry (TDD) : prise de relai / stale / release."""
    print("== test_session_registry_lifecycle ==")
    from server.engine import SessionRegistry
    reg = SessionRegistry()
    assert reg.current is None

    h1 = FakeConnHandler(None, None, None)
    id1 = reg.register(h1)
    assert isinstance(id1, int) and id1 >= 1
    assert reg.current is h1

    h2 = FakeConnHandler(None, None, None)
    id2 = reg.register(h2)
    assert id2 != id1, "ids de session distincts"
    assert h1.stale is True, "la session remplacee doit etre marquee stale"
    assert reg.current is h2

    # l'ancienne session qui se termine ne retire pas la session vivante
    assert reg.release(h1) is False
    assert reg.current is h2

    # la session vivante qui se termine fait le menage
    assert reg.release(h2) is True
    assert reg.current is None

    # idempotence : une release supplementaire ne fait rien
    assert reg.release(h2) is False
    print("  OK")


def test_raw_pending_thread_safety():
    """Point 6 : _pending doit etre protege par un verrou dedie. Sans lui,
    teardown() qui itere pendant qu'une injection ajoute/retire leve
    RuntimeError (dictionnaire modifie pendant iteration) et tue le thread
    rawclient. Ici l'acces concurrent se fait SOUS _pending_lock."""
    print("== test_raw_pending_thread_safety ==")
    from server.raw import RawClient
    events = EventBus()
    state = AppState("fake-host", 9999, events)
    raw = RawClient(state, {
        "host": "127.0.0.1", "port": 1883, "tls": False,
        "client_id": "raw-pending", "cmd_topic": "t/cmd", "evt_topic": "t/evt",
    })
    raw._pending = {i: threading.Event() for i in range(2000)}
    errs = []

    def teardown():
        try:
            raw._teardown()
        except Exception as exc:
            errs.append(exc)

    def mutator():
        try:
            for i in range(5000):
                with raw._pending_lock:
                    raw._pending[5000 + i] = threading.Event()
                    raw._pending.pop(5000 + i, None)
        except Exception as exc:
            errs.append(exc)

    t1 = threading.Thread(target=teardown)
    t2 = threading.Thread(target=mutator)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not errs, "course sur _pending: %r" % errs
    print("  OK")


if __name__ == "__main__":
    test_bridge_inject()
    test_bridge_qos2()
    test_proxy_relay_inject()
    test_listen_blocks_cloud()
    test_proxy_silent_azure_death()
    test_raw_native()
    print("TOUS LES TESTS PASSENT")
