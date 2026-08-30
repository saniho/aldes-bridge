"""Modeles Pydantic pour l'API web Aldes Bridge."""
from pydantic import BaseModel


class SendBody(BaseModel):
    topic: str
    payload: str = ""
    qos: int = 0


class ModeBody(BaseModel):
    mode: str


class RawBody(BaseModel):
    host: str = ""
    port: int = 1883
    tls: bool = True
    client_id: str = ""
    cmd_topic: str = ""
    evt_topic: str = ""


class ConsigneBody(BaseModel):
    zone: str
    value: float


class ConsigneEntry(BaseModel):
    requested: float
    confirmed: bool
    ts: str


class RawConfig(BaseModel):
    enabled: bool
    host: str
    port: int
    tls: bool
    client_id: str
    cmd_topic: str
    evt_topic: str


class ConfigSnapshot(BaseModel):
    mode: str
    connected: bool
    client_id: str | None = None
    topics: list[str] = []
    last_error: str | None = None
    raw: RawConfig
    mode_file: str | None = None
    box_since: float | None = None
    cloud_since: float | None = None
    azure_ip: str | None = None
    consignes: dict[str, ConsigneEntry] = {}
    server_version: str = "dev"
    ui_version: str = "dev"
    history_days: int | None = None
    profile: dict | None = None


class StateSnapshot(BaseModel):
    config: ConfigSnapshot
    messages: list[dict] = []


class LogPage(BaseModel):
    total: int
    limit: int
    offset: int
    events: list[dict] = []


class SendResult(BaseModel):
    ok: bool
    error: str | None = None
    topic: str | None = None
    qos: int | None = None
    bytes: int | None = None


class ConsigneList(BaseModel):
    consignes: dict[str, ConsigneEntry] = {}


class ModeResult(BaseModel):
    mode: str
    takeEffect: str


class OkResult(BaseModel):
    ok: bool


class DisconnectResult(BaseModel):
    ok: bool
    session: str | None = None


class ProfileBody(BaseModel):
    profile_id: str


class SettingsBody(BaseModel):
    history_retention_days: int = None
    log_retention_max_bytes: int = None
    ha_mqtt_dry_run: bool = None


class TestInjectBody(BaseModel):
    topic: str = "test/msg"
    payload: str = '{"test":true}'
    qos: int = 0
