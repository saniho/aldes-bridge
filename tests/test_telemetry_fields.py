#!/usr/bin/env python3
"""Tests de lecture des champs telemetrie depuis le profil device.

Le bloc ``telemetry`` de profiles/*.yaml declare les noms de champs (UAM,
UDM, NED, NpiH, Dvac/Fvac, prefixes de zone, zone_count). Le code doit les
lire via device_profile.telemetry_field / telemetry_key_for et non en dur.
"""
import json
import threading
from datetime import datetime, timezone

from server.aldes import build_product, build_thermostats, build_products, capture_telemetry
from server.appstate import AppState
from server.device_profile import load_profile, telemetry_field, telemetry_key_for
from server.events import EventBus
from server.ha.client import HADiscoveryClient
from server.ha.discovery_config import _air_mode_code, _get_min_max, detect_active_zones

# Champs renommes : la box envoie d'autres noms que les defauts Aldes.
CUSTOM_TELEMETRY = {
    "modem_field": "MODEM123",
    "serial_field": "SERIAL123_TONE",
    "date_field": 1786635200.0,
    "ModeIdx": 5,
    "ModeEau": 1,
    "NiveauECS": 80,
    "NbrePers": 4,
    "VacDeb": 1796140800.0,
    "VacFin": 1796227200.0,
    "TempZ0": 21.5, "TempZ1": 22.5, "TempZ2": 23.5, "TempZ3": 24.5,
    "TempZ4": 25.5,
    "ConsigneZ0": 20.0, "ConsigneZ1": 21.0, "ConsigneZ2": 22.0,
    "ConsigneZ3": 23.0, "ConsigneZ4": 24.0,
    # Cles Aldes "historiques" : le profil doit les ignorer.
    "modemid": "OLD_MODEM",
    "productid": "OLD_SERIAL",
    "dt": 1,
    "UAM": 0,
    "UDM": 0,
    "NED": 10,
    "NpiH": 0,
    "Dvac": 1,
    "Fvac": 1,
    "MT0": 99.0,
    "UsC0": 99.0,
}


def _custom_profile():
    profile = load_profile("tone-aquaair")
    for legacy in ("modemid", "productid", "dt"):
        profile.telemetry.pop(legacy, None)
    profile.telemetry.update({
        "modem_field": "product.modem",
        "serial_field": "product.serial_number",
        "date_field": "product.lastUpdatedDate",
        "air_mode_field": "ModeIdx",
        "water_mode_field": "ModeEau",
        "hot_water_field": "NiveauECS",
        "people_field": "NbrePers",
        "vacation_start_field": "VacDeb",
        "vacation_end_field": "VacFin",
        "zone_temp_prefix": "TempZ",
        "zone_setpoint_prefix": "ConsigneZ",
        "zone_count": 4,
    })
    return profile


def _state(profile=None):
    state = AppState("127.0.0.1", 8883, EventBus())
    state.profile = profile
    return state


def _client(state):
    published = []

    class FakeSock:
        def sendall(self, data):
            published.append(data)

    client = HADiscoveryClient(state)
    client._sock = FakeSock()
    client._send_lock = threading.Lock()
    return client, published


def _frames(published):
    return {p[4:4 + p[3]].decode(): p[6 + p[3]:].decode() for p in published}


# --- Helpers ---


def test_telemetry_field_defaults_without_profile():
    assert telemetry_field(None, "air_mode_field", "UAM") == "UAM"
    assert telemetry_field(None, "zone_count", 10) == 10
    assert telemetry_key_for(None, "product.modem", "modemid") == "modemid"


def test_telemetry_field_reads_profile_or_falls_back():
    profile = _custom_profile()
    assert telemetry_field(profile, "air_mode_field", "UAM") == "ModeIdx"
    assert telemetry_field(profile, "zone_temp_prefix", "MT") == "TempZ"
    assert telemetry_field(profile, "zone_count", 10) == 4
    assert telemetry_field(profile, "inconnu", "defaut") == "defaut"
    assert telemetry_field(load_profile("inspirair-home-s"), "zone_count", 10) == 10


def test_telemetry_key_for_resolves_destination():
    profile = _custom_profile()
    assert telemetry_key_for(profile, "product.modem", "modemid") == "modem_field"
    assert telemetry_key_for(profile, "product.serial_number", "productid") == "serial_field"
    assert telemetry_key_for(profile, "product.lastUpdatedDate", "dt") == "date_field"
    assert telemetry_key_for(profile, "product.inconnu", "dt") == "dt"


# --- build_product / build_thermostats ---


def test_build_product_reads_every_renamed_field():
    product = build_product(CUSTOM_TELEMETRY, True, _custom_profile())
    indicator = product["indicator"]

    assert product["modem"] == "MODEM123"
    assert product["serial_number"] == "SERIAL123_TONE"
    assert product["reference"] == "TONE_AQUA_AIR"
    assert product["lastUpdatedDate"] != ""
    assert indicator["current_air_mode"] == "F"
    assert indicator["current_water_mode"] == "M"
    assert indicator["qte_eau_chaude"] == 80
    assert indicator["settings"]["people"] == 4
    assert indicator["tmp_principal"] == 21.5
    assert len(indicator["thermostats"]) == 4


def test_build_product_vacation_fields_follow_profile():
    product = build_product(CUSTOM_TELEMETRY, True, _custom_profile())
    indicator = product["indicator"]

    def iso_date(epoch):
        return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")

    assert indicator["date_debut_vac"] is not None
    assert indicator["date_fin_vac"] is not None
    assert indicator["date_debut_vac"].startswith(iso_date(1796140800.0))


def test_build_thermostats_profile_prefixes_and_zone_count():
    thermostats = build_thermostats(CUSTOM_TELEMETRY, _custom_profile())
    assert [t["ThermostatId"] for t in thermostats] == ["0", "1", "2", "3"]
    assert thermostats[0]["CurrentTemperature"] == 21.5
    assert thermostats[0]["TemperatureSet"] == 20.0
    # TempZ4 existe mais zone_count = 4 : hors perimetre.
    assert all(t["Name"] != "Zone 5" for t in thermostats)


def test_build_thermostats_without_profile_keeps_legacy_prefixes():
    thermostats = build_thermostats({"MT0": 20.0, "UsC0": 19.0})
    assert thermostats == [{
        "ThermostatId": "0",
        "thermostatId": "0",
        "Name": "Zone 1",
        "CurrentTemperature": 20.0,
        "CurrentHumidity": None,
        "TemperatureSet": 19.0,
    }]


def test_build_products_uses_state_profile():
    state = _state(_custom_profile())
    state.telemetry["SERIAL123_TONE"] = dict(CUSTOM_TELEMETRY)
    products = build_products(state)
    assert len(products) == 1
    assert products[0]["serial_number"] == "SERIAL123_TONE"
    assert products[0]["indicator"]["qte_eau_chaude"] == 80


def test_capture_telemetry_pid_uses_profile_keys():
    state = _state(_custom_profile())
    capture_telemetry(state, json.dumps(CUSTOM_TELEMETRY))
    assert "SERIAL123_TONE" in state.telemetry
    assert "OLD_SERIAL" not in state.telemetry


# --- Discovery HA ---


def test_detect_active_zones_profile_prefixes_and_count():
    data = {f"TempZ{i}": 21.0 for i in range(5)}
    data.update({f"ConsigneZ{i}": 20.0 for i in range(5)})
    assert detect_active_zones(data, _custom_profile()) == [0, 1, 2, 3]
    assert detect_active_zones({"MT0": 21.0, "UsC0": 20.0}) == [0]
    assert detect_active_zones(None, _custom_profile()) == []


def test_air_mode_code_and_min_max_read_profile_field():
    profile = _custom_profile()
    data = {"ModeIdx": 5, "CMiST": 10, "CMaST": 30, "FMiST": 15, "FMaST": 25}
    assert _air_mode_code(data, profile) == "F"
    assert _air_mode_code({"UAM": 5}, profile) == ""
    assert _get_min_max(data, profile) == (15, 25)
    heat = dict(data, ModeIdx=1)
    assert _get_min_max(heat, profile) == (10, 30)


# --- Client HA ---


def test_water_mode_code_reads_profile_field():
    client = _client(_state(_custom_profile()))[0]
    assert client._get_water_mode_code({"ModeEau": 1}) == "M"
    assert client._get_water_mode_code({"UDM": 1}) is None


def test_publish_telemetry_data_reads_profile_fields():
    client, published = _client(_state(_custom_profile()))
    client._publish_telemetry_data(CUSTOM_TELEMETRY, include_zone_aliases=True)
    frames = _frames(published)

    assert frames["aldes/state/sensor/NED"] == "80"
    assert frames["aldes/state/people"] == "6"
    assert frames["aldes/state/ecs"] == "On"
    assert frames["aldes/state/zone0/temperature"] == "21.5"
    assert frames["aldes/state/zone0/consigne"] == "20.0"
    assert frames["aldes/state/zone3/temperature"] == "24.5"
    # Les topics HA restent stables : seul le champ lu suit le profil.
    assert frames["aldes/state/sensor/MT0"] == "21.5"


def test_publish_vacation_state_reads_profile_fields():
    client, published = _client(_state(_custom_profile()))
    client._publish_vacation_state(CUSTOM_TELEMETRY)
    frames = _frames(published)

    expected = datetime.fromtimestamp(1796140800.0, tz=timezone.utc).strftime("%Y-%m-%d")
    assert frames["aldes/state/vacation_start"] == expected
    assert frames["aldes/state/vacation_enable"] == "on"


# --- Confirmation de consigne ---


def test_confirm_consignes_uses_profile_setpoint_prefix():
    state = _state(_custom_profile())
    state.request_consigne("0", 20.0)
    with state._lock:
        state._confirm_consignes_from({"ConsigneZ0": 20.0, "UsC0": 99.0})
    assert state._consignes["0"]["confirmed"] is True

    state.request_consigne("1", 21.0)
    with state._lock:
        # L'ancien prefixe UsC ne doit pas confirmer.
        state._confirm_consignes_from({"UsC1": 21.0})
    assert state._consignes["1"]["confirmed"] is False
