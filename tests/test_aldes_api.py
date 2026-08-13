#!/usr/bin/env python3
"""Tests du rejeu de l'API Aldes (server.aldes + endpoints api.py)."""
import json
import sys
import threading
import time
import urllib.request
import urllib.parse
import urllib.error

sys.path.insert(0, "/home/ubuntu/aldes-bridge")

from server.aldes import (
    AIR_MODES, WATER_MODES, FRIENDLY_NAMES,
    build_products, build_product, build_thermostats, capture_telemetry, make_token,
)
from server.appstate import AppState
from server.events import EventBus

# Telemetrie reelle capturee sur la box (valeurs du payload observe).
TELEMETRY = {
    "modemid": "ABCDEF123456",
    "productid": "ABCDEF123456_TONE",
    "Vers_W": "21",
    "RSSI": "--%%",
    "Dvac": 0.0,
    "Fvac": 0.0,
    "HPC": 0,
    "dt": 1786635200.0,
    "MT0": 25.87, "MT1": 26.25, "MT2": 26.93, "MT3": 24.81, "MT4": 25.62,
    "MT5": 0.0,
    "UAM": 5,
    "UDM": 1,
    "UsC0": 26.0, "UsC1": 24.0, "UsC2": 22.0, "UsC3": 25.0,
    "NED": 75,
    "NpiH": 4,
    "Vers_UC": 53,
}
TELEMETRY_JSON = json.dumps(TELEMETRY)


def make_state():
    return AppState("aldesiotsuite.azure-devices.net", 8883, EventBus())


# --- Tests unitaires du mapping telemetrie -> product ----------------------

def test_capture_telemetry_merges_by_product():
    state = make_state()
    capture_telemetry(state, json.dumps({"productid": "X_TONE", "MT0": 20.0}))
    capture_telemetry(state, json.dumps({"productid": "X_TONE", "UAM": 3}))
    assert set(state.telemetry) == {"X_TONE"}
    assert state.telemetry["X_TONE"]["MT0"] == 20.0
    assert state.telemetry["X_TONE"]["UAM"] == 3


def test_capture_telemetry_ignores_non_telemetry():
    state = make_state()
    capture_telemetry(state, "pas du json")
    capture_telemetry(state, json.dumps({"foo": "bar"}))
    capture_telemetry(state, b"\x00\x01")
    assert state.telemetry == {}


def test_capture_parses_prefixed_by_binary_header():
    # La box prefixe ses telemetries d'un octet de sequence (\x00F, \x00E...).
    state = make_state()
    capture_telemetry(state, b"\x00F" + json.dumps(TELEMETRY).encode())
    assert set(state.telemetry) == {"ABCDEF123456_TONE"}


def test_store_tracks_server_update_time():
    import os
    import tempfile
    from datetime import datetime, timezone

    d = tempfile.mkdtemp()
    tf = os.path.join(d, "telemetry.json")
    state = AppState("h", 8883, EventBus(), telemetry_file=tf)
    capture_telemetry(state, json.dumps({"productid": "P_TONE", "MT0": 21.5}))
    p = build_products(state)[0]
    assert p["updatedAt"]  # horodatage de mise a jour cote serveur
    ts = datetime.fromisoformat(p["updatedAt"]).astimezone(timezone.utc)
    assert abs((datetime.now(timezone.utc) - ts).total_seconds()) < 60

    # Les dernieres valeurs survivent au redemarrage (recharge du fichier).
    state2 = AppState("h", 8883, EventBus(), telemetry_file=tf)
    p2 = build_products(state2)[0]
    assert p2["serial_number"] == "P_TONE"
    assert p2["indicator"]["thermostats"][0]["CurrentTemperature"] == 21.5
    assert p2["updatedAt"]


def test_decode_payload_skips_binary_header():
    from server.appstate import decode_payload
    raw = b"\x00F" + json.dumps({"productid": "X"}).encode()
    out = decode_payload(raw)
    assert out.startswith("{")
    assert "\n" in out


def test_reference_aqua_air_when_water_fields():
    assert build_product(TELEMETRY, True)["reference"] == "TONE_AQUA_AIR"
    assert build_product({}, True)["reference"] == "TONE_AIR"


def test_modes_letters():
    product = build_product(TELEMETRY, True)
    ind = product["indicator"]
    assert ind["current_air_mode"] == "F"          # UAM=5
    assert ind["current_water_mode"] == "M"        # UDM=1
    assert ind["hors_gel"] is False
    # index hors bornes -> None (pas de crash HA)
    bad = build_product({**TELEMETRY, "UAM": 99, "UDM": -1}, True)
    assert bad["indicator"]["current_air_mode"] is None
    assert bad["indicator"]["current_water_mode"] is None


def test_people_isf_home_composition_index():
    # NpiH=4 personnes -> index enum (people+2 affiche = 4)
    assert build_product(TELEMETRY, True)["indicator"]["settings"]["people"] == 2
    assert build_product({**TELEMETRY, "NpiH": 2}, True)["indicator"]["settings"]["people"] == 0
    assert build_product({**TELEMETRY, "NpiH": 9}, True)["indicator"]["settings"]["people"] == 4


def test_thermostats_from_MT_UsC():
    ts = build_thermostats(TELEMETRY)
    assert len(ts) == 5  # MT0..MT4 non nuls
    assert ts[0] == {
        "ThermostatId": "0", "thermostatId": "0", "Name": "Zone 1",
        "CurrentTemperature": 25.9, "CurrentHumidity": None, "TemperatureSet": 26.0,
    }
    # zone sans consigne -> TemperatureSet None
    assert ts[4]["TemperatureSet"] is None
    # libelle consigne au format attendu par saniho climate (ThermostatId)
    assert all(t["ThermostatId"] == t["thermostatId"] for t in ts)


def test_product_fields():
    p = build_product(TELEMETRY, True)
    assert p["modem"] == "ABCDEF123456"
    assert p["serial_number"] == "ABCDEF123456_TONE"
    assert p["name"] == FRIENDLY_NAMES["TONE_AQUA_AIR"]
    assert p["isConnected"] is True
    assert p["indicator"]["qte_eau_chaude"] == 75
    assert p["indicator"]["tmp_principal"] == 25.87
    assert p["lastUpdatedDate"].startswith("2026-")


def test_dt_interpreted_in_box_timezone():
    # La box envoie dt comme son heure locale (Europe/Paris, UTC+2 en ete) ;
    # l'epoch 1786635200 correspond au cadran 15:33 heure de Paris, donc 13:33 UTC.
    p = build_product(TELEMETRY, True)
    assert p["lastUpdatedAt"] == "2026-08-13T13:33:20+00:00"
    assert p["lastUpdatedDate"] == "2026-08-13T13:33:20+00:00"


def test_dt_zero_or_missing_is_off():
    off = build_product({**TELEMETRY, "dt": 0}, True)
    assert off["lastUpdatedAt"] is None
    assert off["lastUpdatedDate"] == ""


def test_build_products_empty_fallback():
    state = make_state()
    products = build_products(state)
    assert isinstance(products, list) and len(products) == 1
    assert products[0]["modem"] == "N/A"
    assert products[0]["serial_number"] == "N/A"


def test_build_products_sorted():
    state = make_state()
    capture_telemetry(state, json.dumps(TELEMETRY))
    products = build_products(state)
    assert len(products) == 1
    assert products[0]["serial_number"] == "ABCDEF123456_TONE"


def test_make_token():
    t = make_token("aldes")
    assert t["token_type"] == "Bearer"
    assert t["expires_in"] == 3600
    assert len(t["access_token"]) == 32


# --- Tests HTTP des endpoints (uvicorn + urllib, sans httpx) ---------------

class _StubEngine:
    def set_mode(self, mode):
        pass

    def set_raw(self):
        pass

    def inject(self, *a, **k):
        return True


def _start_web(state):
    import uvicorn
    from server.api import create_app
    app = create_app(state, _StubEngine(), "/nonexistent")
    _start_web._next = getattr(_start_web, "_next", 0) + 1
    port = 18080 + _start_web._next
    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(cfg)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    return port


def _request(port, path, method="GET", body=None, as_json=True):
    url = f"http://127.0.0.1:{port}{path}"
    data = None
    headers = {}
    if isinstance(body, dict):
        data = urllib.parse.urlencode(body).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif isinstance(body, str):
        data = body.encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read()
    return (json.loads(raw) if as_json else raw) if raw else None


def test_oauth_token_and_products():
    state = make_state()
    capture_telemetry(state, TELEMETRY_JSON)
    port = _start_web(state)
    token = _request(port, "/oauth2/token", "POST", {
        "grant_type": "password", "username": "aldes", "password": "aldes",
    })
    assert token["token_type"] == "Bearer"
    assert token["access_token"]

    products = _request(port, "/aldesoc/v5/users/me/products", "GET")
    assert isinstance(products, list) and products[0]["modem"] == "ABCDEF123456"
    assert products[0]["indicator"]["current_air_mode"] == "F"


def test_oauth_token_empty_credentials_rejected():
    state = make_state()
    port = _start_web(state)
    import urllib.error as ue
    try:
        _request(port, "/oauth2/token", "POST", {"username": "", "password": ""})
        raise AssertionError("devait etre rejete")
    except ue.HTTPError as e:
        assert e.code == 400


def test_write_endpoints_accepted():
    state = make_state()
    port = _start_web(state)
    r1 = _request(port, "/aldesoc/v5/users/me/products/ABCDEF123456/updateThermostats",
                  "PATCH", body=json.dumps(
                      [{"ThermostatId": "0", "Name": "Zone 1", "TemperatureSet": 22}]))
    assert r1["success"] is True
    r2 = _request(port, "/aldesoc/v5/users/me/products/ABCDEF123456/commands",
                  "POST", body=json.dumps({"method": "changeMode", "params": ["V"]}))
    assert r2["success"] is True
    # les commandes sont journalisees dans le bus d'evenements
    kinds = [e.get("type") for e in state.events.snapshot()
             if e.get("kind") == "message" and e.get("type") == "ALDES_WRITE"]
    assert len(kinds) == 2


if __name__ == "__main__":
    import traceback
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  %s" % name)
            except Exception:
                failures += 1
                print("FAIL %s" % name)
                traceback.print_exc()
    print("\n%d pompes en echec" % failures)
    sys.exit(1 if failures else 0)