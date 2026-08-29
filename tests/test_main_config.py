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
