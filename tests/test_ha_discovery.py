"""Tests du module Home Assistant MQTT Auto-Discovery."""
import json
import socket
import struct
import threading
import time

import pytest

from server.appstate import AppState
from server.events import EventBus
from server.device_profile import load_profile
from server.ha_discovery import (
    HADiscoveryClient,
    detect_mqtt_broker,
    ALDES_TO_HA_MODE,
    HA_MODE_TO_ALDES,
    ALDES_TO_HA_PRESET,
    HA_PRESET_TO_ALDES,
    ALDES_WATER_TO_HA,
    HA_WATER_TO_ALDES,
    _build_discovery_config,
)


# --- Tests des mappings ---

def test_aldes_to_ha_mode_mapping():
    assert ALDES_TO_HA_MODE["A"] == "off"
    assert ALDES_TO_HA_MODE["B"] == "heat"
    assert ALDES_TO_HA_MODE["C"] == "heat"
    assert ALDES_TO_HA_MODE["D"] == "heat"
    assert ALDES_TO_HA_MODE["I"] == "cool"
    assert ALDES_TO_HA_MODE["H"] == "cool"


def test_ha_to_aldes_mode_mapping():
    assert HA_MODE_TO_ALDES["off"] == "A"
    assert HA_MODE_TO_ALDES["heat"] == "B"
    assert HA_MODE_TO_ALDES["cool"] == "F"


def test_aldes_to_ha_preset_mapping():
    assert ALDES_TO_HA_PRESET["A"] == "Arrêt"
    assert ALDES_TO_HA_PRESET["C"] == "Éco"
    assert ALDES_TO_HA_PRESET["D"] == "Chauffage programme A"
    assert ALDES_TO_HA_PRESET["F"] == "Climatisation"


def test_ha_to_aldes_preset_mapping():
    assert HA_PRESET_TO_ALDES["Éco"] == "C"
    assert HA_PRESET_TO_ALDES["Climatisation"] == "F"
    assert HA_PRESET_TO_ALDES["Confort"] == "B"


# --- Tests de la config discovery ---

def test_build_discovery_config_returns_list():
    configs = _build_discovery_config("test_device", None)
    assert isinstance(configs, list)
    assert len(configs) > 0


def test_build_discovery_config_topics():
    configs = _build_discovery_config("test_device", None)
    topics = [t for t, _ in configs]
    assert topics[0].startswith("homeassistant/")  # prefix HA par défaut
    assert any("climate" in t for t, _ in configs)
    assert any("sensor" in t for t, _ in configs)
    assert any("binary_sensor" in t for t, _ in configs)


def test_build_discovery_config_climate_valid():
    profile = load_profile("tone-aquaair")
    configs = _build_discovery_config("dev123", profile)
    climate_topic = None
    climate_payload = None
    for topic, payload in configs:
        if "climate" in topic and payload:
            climate_topic = topic
            climate_payload = json.loads(payload)
            break

    assert climate_topic is not None
    assert climate_payload["name"] == "PAC Aldes"
    assert climate_payload["unique_id"] == "aldes_dev123_climate"
    assert "off" in climate_payload["modes"]
    assert "heat" in climate_payload["modes"]
    assert climate_payload["modes"] == ["off", "heat", "cool"]
    assert "mode_state_topic" in climate_payload
    assert "mode_command_topic" in climate_payload
    assert "temperature_state_topic" in climate_payload
    assert "temperature_command_topic" in climate_payload
    assert "current_temperature_topic" in climate_payload
    assert "preset_modes" in climate_payload
    assert climate_payload["preset_modes"] == [
        "Arrêt",
        "Confort",
        "Éco",
        "Chauffage programme A",
        "Chauffage programme B",
        "Climatisation",
        "Climatisation boost",
        "Climatisation programme C",
        "Climatisation programme D",
    ]
    assert climate_payload["precision"] == 0.1
    assert climate_payload["temp_step"] == 1
    assert "availability_topic" in climate_payload


def test_build_discovery_config_device_info():
    configs = _build_discovery_config("dev123", None)
    for _, payload_str in configs:
        if not payload_str:
            continue
        payload = json.loads(payload_str)
        if "device" in payload:
            device = payload["device"]
            assert "aldes_dev123" in device["identifiers"]
            assert device["manufacturer"] == "Aldes"
            break


# --- Tests du client HA discovery (sans broker reel) ---

def test_ha_client_init():
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    client = HADiscoveryClient(state, host="127.0.0.1", port=19999)
    assert client.host == "127.0.0.1"
    assert client.port == 19999
    assert client.prefix == "aldes"
    assert not client.is_alive()


def test_ha_client_stop():
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    client = HADiscoveryClient(state, host="127.0.0.1", port=19999)
    client.stop()
    # Pas d'erreur si stoppe sans etre demarre


def test_ha_client_connection_refused():
    """Le client doit gerer proprement un broker indisponible."""
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    client = HADiscoveryClient(state, host="127.0.0.1", port=19999)
    client.start()
    time.sleep(0.5)  # laisse le temps de tenter la connexion
    assert not client._sock  # pas connecte
    client.stop()


# --- Tests des helpers de parsing ---

def test_get_air_mode_code_valid():
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    client = HADiscoveryClient(state)
    assert client._get_air_mode_code({"UAM": "3"}) == "D"
    assert client._get_air_mode_code({"UAM": "0"}) == "A"
    assert client._get_air_mode_code({"UAM": "8"}) == "I"


def test_get_air_mode_code_invalid():
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    client = HADiscoveryClient(state)
    assert client._get_air_mode_code({}) is None
    assert client._get_air_mode_code({"UAM": "99"}) is None
    assert client._get_air_mode_code({"UAM": "abc"}) is None


def test_get_float():
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    client = HADiscoveryClient(state)
    assert client._get_float({"MT0": "21.5"}, "MT0") == 21.5
    assert client._get_float({"MT0": 22.0}, "MT0") == 22.0
    assert client._get_float({}, "MT0") is None
    assert client._get_float({"MT0": "abc"}, "MT0") is None


# --- Tests des mappings ECS (eau chaude sanitaire) ---

def test_aldes_water_to_ha_mapping():
    assert ALDES_WATER_TO_HA["L"] == "Arrêt"
    assert ALDES_WATER_TO_HA["M"] == "Marche"
    assert ALDES_WATER_TO_HA["N"] == "Boost"


def test_ha_water_to_aldes_mapping():
    assert HA_WATER_TO_ALDES["Arrêt"] == "L"
    assert HA_WATER_TO_ALDES["Marche"] == "M"
    assert HA_WATER_TO_ALDES["Boost"] == "N"


def test_get_water_mode_code_valid():
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    client = HADiscoveryClient(state)
    assert client._get_water_mode_code({"UDM": "0"}) == "L"
    assert client._get_water_mode_code({"UDM": "1"}) == "M"
    assert client._get_water_mode_code({"UDM": "2"}) == "N"


def test_get_water_mode_code_invalid():
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    client = HADiscoveryClient(state)
    assert client._get_water_mode_code({}) is None
    assert client._get_water_mode_code({"UDM": "99"}) is None
    assert client._get_water_mode_code({"UDM": "abc"}) is None


# --- Tests des configs ECS et vacances ---

def test_build_discovery_config_has_ecs_select():
    configs = _build_discovery_config("dev123", load_profile("tone-aquaair"))
    ecs_topic = None
    for topic, payload_str in configs:
        if "ecs" in topic and "select" in topic:
            ecs_topic = topic
            payload = json.loads(payload_str)
            assert payload["name"] == "PAC Aldes Eau Chaude"
            assert payload["options"] == ["Arrêt", "Marche", "Boost"]
            assert "command_topic" in payload
            assert "state_topic" in payload
            break
    assert ecs_topic is not None


def test_profile_program_commands_are_converted_to_aldes_codes():
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    state.profile = load_profile("tone-aquaair")
    injected = []
    state._ha_inject_hook = lambda topic, payload, qos: injected.append(json.loads(payload))
    client = HADiscoveryClient(state, dry_run=False)

    client._handle_preset_command("Climatisation boost")
    client._handle_ecs_command("Boost")

    assert injected == [
        {"id": 1, "jsonrpc": "2.0", "method": "changeMode", "params": ["G"]},
        {"id": 1, "jsonrpc": "2.0", "method": "changeMode", "params": ["N"]},
    ]


def test_build_discovery_config_has_vacation_entities():
    configs = _build_discovery_config("dev123", None)
    topics = [t for t, _ in configs]
    assert any("vacation_start" in t and "date" in t for t in topics)
    assert any("vacation_end" in t and "date" in t for t in topics)
    assert any("vacation_enable" in t and "switch" in t for t in topics)


def test_build_discovery_config_vacation_dates():
    configs = _build_discovery_config("dev123", None)
    for topic, payload_str in configs:
        if "vacation_start" in topic and "date" in topic:
            payload = json.loads(payload_str)
            assert "command_topic" in payload
            assert "state_topic" in payload
            assert "Vacances Début" in payload["name"]
            break


def test_build_discovery_config_vacation_switch():
    configs = _build_discovery_config("dev123", None)
    for topic, payload_str in configs:
        if "vacation_enable" in topic and "switch" in topic:
            payload = json.loads(payload_str)
            assert payload["payload_on"] == "on"
            assert payload["payload_off"] == "off"
            assert "command_topic" in payload
            break


# --- Tests des helpers vacances ---

def test_epoch_to_date_str():
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    client = HADiscoveryClient(state)
    # 2024-07-15 00:00:00 UTC
    assert client._epoch_to_date_str(1721001600) == "2024-07-15"
    assert client._epoch_to_date_str(0) is None
    assert client._epoch_to_date_str(None) is None
    assert client._epoch_to_date_str("abc") is None
    assert client._epoch_to_date_str(-1) is None


def test_store_vacation_date():
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    client = HADiscoveryClient(state)
    client._vacation_dates = {}

    # Stocke la date de debut
    client._store_vacation_date("start", "2024-07-15")
    assert client._vacation_dates == {"start": "2024-07-15"}

    # Stocke la date de fin -> la commande devrait etre envoyee
    # (mais pas de hook d'injection, donc on teste juste le stockage)
    client._store_vacation_date("end", "2024-07-25")
    # Apres les deux dates, le dict est vide (reset)
    assert client._vacation_dates == {} or client._vacation_dates.get("start") is None


# --- Tests du mode dry-run ---

def test_ha_client_dry_run_default():
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    client = HADiscoveryClient(state)
    assert client.dry_run is True


def test_ha_client_dry_run_enabled():
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    client = HADiscoveryClient(state, dry_run=True)
    assert client.dry_run is True


def test_ha_client_dry_run_disabled():
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    client = HADiscoveryClient(state, dry_run=False)
    assert client.dry_run is False


def test_dry_run_inject_does_not_call_hook():
    """En dry-run, _inject_aldes_command ne doit pas appeler le hook."""
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    hook_called = []

    def fake_hook(topic, payload, qos):
        hook_called.append((topic, payload, qos))

    state._ha_inject_hook = fake_hook

    client = HADiscoveryClient(state, dry_run=True)
    client._inject_aldes_command("changeMode", {"code": "D"})

    # Le hook ne doit pas etre appele
    assert hook_called == []


def test_dry_run_inject_logs(caplog):
    """En dry-run, _inject_aldes_command doit logger la commande simulee."""
    import logging
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)

    client = HADiscoveryClient(state, dry_run=True)
    with caplog.at_level(logging.INFO, logger="aldes-ha-discovery"):
        client._inject_aldes_command("changeMode", {"code": "D"})

    assert "DRY-RUN" in caplog.text
    assert "changeMode" in caplog.text


def test_non_dry_run_inject_calls_hook():
    """Sans dry-run, _inject_aldes_command doit appeler le hook."""
    events = EventBus()
    state = AppState("127.0.0.1", 8883, events)
    hook_called = []

    def fake_hook(topic, payload, qos):
        hook_called.append((topic, payload, qos))

    state._ha_inject_hook = fake_hook

    client = HADiscoveryClient(state, dry_run=False)
    client._inject_aldes_command("changeMode", {"code": "D"})

    assert len(hook_called) == 1
    assert hook_called[0][0] == "devices/aldes_bridge/messages/devicebound"


# ============================================================
# Tests detect_mqtt_broker
# ============================================================

def test_detect_mqtt_broker_no_token(monkeypatch):
    """Sans SUPERVISOR_TOKEN, retourne None."""
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    from server.ha_discovery import detect_mqtt_broker
    assert detect_mqtt_broker() is None


def test_detect_mqtt_broker_success(monkeypatch):
    """Avec SUPERVISOR_TOKEN valide, retourne host/port."""
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")

    fake_response = json.dumps({
        "data": {"host": "core-mosquitto", "port": 1883}
    }).encode()

    class FakeResp:
        def read(self):
            return fake_response
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    def fake_urlopen(req, timeout=None):
        assert "Bearer test-token" in req.get_header("Authorization")
        return FakeResp()

    import server.ha_discovery as hd
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = detect_mqtt_broker()
    assert result == {"host": "core-mosquitto", "port": 1883}


def test_detect_mqtt_broker_http_error(monkeypatch):
    """Erreur HTTP → retourne None."""
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")

    def fake_urlopen(req, timeout=None):
        raise ConnectionError("refused")

    import server.ha_discovery as hd
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = detect_mqtt_broker()
    assert result is None


def test_detect_mqtt_broker_missing_fields(monkeypatch):
    """Réponse Supervisor sans host/port → retourne None."""
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")

    fake_response = json.dumps({"data": {}}).encode()

    class FakeResp:
        def read(self):
            return fake_response
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    def fake_urlopen(req, timeout=None):
        return FakeResp()

    import server.ha_discovery as hd
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = detect_mqtt_broker()
    assert result is None
