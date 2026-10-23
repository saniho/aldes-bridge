from server.main import _resolve_ha_mqtt_dry_run, build_parser


class StubConfig:
    def __init__(self, dry_run):
        self.dry_run = dry_run

    def get(self, key):
        assert key == "ha_mqtt_dry_run"
        return self.dry_run


def test_ha_mqtt_dry_run_env_overrides_persisted_config(monkeypatch):
    monkeypatch.setenv("HA_MQTT_DRY_RUN", "false")

    args = build_parser().parse_args([])

    assert _resolve_ha_mqtt_dry_run(args, StubConfig(True)) is False


def test_ha_mqtt_dry_run_uses_persisted_config_without_override(monkeypatch):
    monkeypatch.delenv("HA_MQTT_DRY_RUN", raising=False)

    args = build_parser().parse_args([])

    assert _resolve_ha_mqtt_dry_run(args, StubConfig(False)) is False


def test_ha_mqtt_dry_run_cli_overrides_persisted_config(monkeypatch):
    monkeypatch.delenv("HA_MQTT_DRY_RUN", raising=False)

    args = build_parser().parse_args(["--ha-mqtt-no-dry-run"])

    assert _resolve_ha_mqtt_dry_run(args, StubConfig(True)) is False


def test_explicit_broker_does_not_use_supervisor_credentials(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from server.main import _setup_ha_client

    discovery = Mock(return_value={"host": "core-mosquitto", "port": 1883,
                                   "username": "supervisor", "password": "other"})
    client = Mock()
    monkeypatch.setattr("server.ha.broker_detection.detect_mqtt_broker", discovery)
    monkeypatch.setattr("server.ha.client.HADiscoveryClient", client)
    args = build_parser().parse_args([
        "--ha-mqtt-host", "broker.example", "--ha-mqtt-port", "1884",
        "--ha-mqtt-user", "configured", "--ha-mqtt-password", "configured-secret",
        "--ha-mqtt-dry-run",
    ])
    _setup_ha_client(SimpleNamespace(on_publish_in=None), Mock(), args, StubConfig(False))
    discovery.assert_not_called()
    assert client.call_args.kwargs["host"] == "broker.example"
    assert client.call_args.kwargs["port"] == 1884
    assert client.call_args.kwargs["username"] == "configured"
    assert client.call_args.kwargs["password"] == "configured-secret"
    assert client.call_args.kwargs["dry_run"] is True
