import json

from server.device_profile import load_profile
from server.ha.discovery_config import build_discovery_config


def test_tflow_profile_loads_as_read_only_water_heater():
    profile = load_profile("tflow-hygro-200-collectif")
    assert profile is not None
    assert profile.type == "water_heater"
    assert profile.commands == []


def test_tflow_discovery_has_observed_sensors_and_no_pac_controls():
    profile = load_profile("tflow-hygro-200-collectif")
    configs = build_discovery_config("tflow-test", profile, prefix="aldes")
    topics = [topic for topic, _ in configs]
    payloads = [json.loads(payload) for _, payload in configs if payload]

    assert any(topic.endswith("/sensor/tflow_usr_setpt_tpt/config") for topic in topics)
    assert any(topic.endswith("/sensor/tflow_ctn_h_bal/config") for topic in topics)
    assert not any("/climate/" in topic for topic in topics)
    assert not any("/water_heater/" in topic for topic in topics)
    assert all("command_topic" not in payload for payload in payloads)
