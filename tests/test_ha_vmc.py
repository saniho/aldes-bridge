"""Tests du profil VMC (InspirAIR) pour la discovery HA."""
import json
import threading

from server.appstate import AppState
from server.device_profile import load_profile
from server.events import EventBus
from server.ha.client import HADiscoveryClient
from server.ha.discovery_config import build_discovery_config

TELEMETRY = {
    "modemid": "AABBCCDDEEFF",
    "productid": "AABBCCDDEEFF_AIR",
    "outside_tpt": 22.5,
    "extf_flw": 141,
    "current_mode": "X",
    "dep_ind": 0,
    "Start_date_mode": "",
    "RSSI": "--%%",
}


def _state(profile="inspirair-home-s"):
    state = AppState("127.0.0.1", 8883, EventBus())
    state.profile = load_profile(profile)
    return state


def test_vmc_discovery_has_mode_select_and_profile_sensors_only():
    configs = dict(build_discovery_config("dev", load_profile("inspirair-home-s")))
    select = json.loads(configs["homeassistant/select/aldes_vmc_mode/config"])
    assert select["options"] == ["Daily", "Holidays", "Guest", "Boost", "Air Prog"]
    sensor = json.loads(configs["homeassistant/sensor/aldes_extf_flw/config"])
    assert sensor["state_topic"] == "aldes/state/sensor/extf_flw"
    assert sensor["unit_of_measurement"] == "m³/h"
    assert not any("/climate/" in t or "/water_heater/" in t for t in configs)


def test_vmc_mode_command_targets_connected_box():
    state = _state()
    state._client_id = "AABBCCDDEEFF_AIR"
    injected = []
    state._ha_inject_hook = lambda topic, payload, qos: injected.append((topic, json.loads(payload)))
    client = HADiscoveryClient(state, dry_run=False)

    client._handle_vmc_mode_command("Boost")
    client._handle_vmc_mode_command("Unknown")

    assert injected == [(
        "devices/AABBCCDDEEFF_AIR/messages/devicebound",
        {"id": 1, "jsonrpc": "2.0", "method": "changeMode", "params": ["Y"]},
    )]


def test_dry_run_wins_over_config_default():
    state = _state()
    state.config = {"ha_mqtt_dry_run": False}
    injected = []
    state._ha_inject_hook = lambda *a: injected.append(a)

    HADiscoveryClient(state, dry_run=True)._handle_vmc_mode_command("Boost")

    assert injected == []


def test_vmc_telemetry_publishes_mode_label_and_sensors():
    state = _state()
    published = []

    class FakeSock:
        def sendall(self, data):
            published.append(data)

    client = HADiscoveryClient(state)
    client._sock = FakeSock()
    client._send_lock = threading.Lock()
    client.publish_telemetry(TELEMETRY)

    # MQTT PUBLISH QoS1 frame: topic, 2-byte packet id, payload.
    frames = {p[4:4 + p[3]].decode(): p[6 + p[3]:].decode() for p in published}
    assert frames["aldes/state/vmc_mode"] == "Guest"
    assert frames["aldes/state/sensor/outside_tpt"] == "22.5"
    assert frames["aldes/state/sensor/modemid"] == TELEMETRY["modemid"]
    assert frames["aldes/state/sensor/dep_ind"] == "0"
    assert frames["aldes/state/sensor/Start_date_mode"] == ""
    assert frames["aldes/state/sensor/RSSI"] == "--%%"
    assert "aldes/state/sensor/UAM" not in frames


def test_holidays_command_includes_configurable_utc_window():
    from datetime import datetime, timezone, timedelta

    state = _state()
    state.profile.ha_discovery["holiday_duration_hours"] = 48
    injected = []
    state._ha_inject_hook = lambda topic, payload, qos: injected.append(json.loads(payload))
    before = datetime.now(timezone.utc).replace(microsecond=0)
    HADiscoveryClient(state, dry_run=False)._handle_vmc_mode_command("Holidays")
    value = injected[0]["params"][0]
    assert value.startswith("W")
    start = datetime.strptime(value[1:16], "%Y%m%d%H%M%SZ").replace(tzinfo=timezone.utc)
    end = datetime.strptime(value[16:], "%Y%m%d%H%M%SZ").replace(tzinfo=timezone.utc)
    assert before <= start <= datetime.now(timezone.utc)
    assert end - start == timedelta(hours=48)


def test_raw_diagnostics_do_not_claim_numeric_measurements():
    configs = dict(build_discovery_config("dev", load_profile("inspirair-home-s")))
    diagnostics = [
        json.loads(payload) for payload in configs.values()
        if json.loads(payload).get("entity_category") == "diagnostic"
    ]
    assert len(diagnostics) == 12
    assert all("state_class" not in config for config in diagnostics)
    assert all("unit_of_measurement" not in config for config in diagnostics)
    temperature = json.loads(configs["homeassistant/sensor/aldes_outside_tpt/config"])
    assert temperature["state_class"] == "measurement"
    for key in ("RSSI", "Start_date_mode", "End_date_mode"):
        config = json.loads(configs[f"homeassistant/sensor/aldes_{key}/config"])
        assert "unknown" in config["value_template"]
