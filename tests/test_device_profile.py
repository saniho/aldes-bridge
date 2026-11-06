#!/usr/bin/env python3
"""Tests du systeme de profils device (server/device_profile.py)."""
import os
import sys
import tempfile
import yaml

sys.path.insert(0, "/home/ubuntu/aldes-bridge")

from server.device_profile import (
    DeviceProfile,
    air_mode_code,
    list_profiles,
    load_profile,
    water_mode_code,
)
from server.appstate import AppState, read_persisted_profile
from server.config import ConfigStore
from server.events import EventBus
from server.aldes import build_product, build_products, build_thermostats, capture_telemetry
import json


# --- Tests du chargeur de profils ---

def test_load_profile_default():
    p = load_profile()
    assert p is not None
    assert p.id == "tone-aquaair"
    assert p.name == "TONE AquaAIR"
    assert p.type == "pac"

def test_load_profile_by_id():
    p = load_profile("tone-aquaair")
    assert p is not None
    assert p.id == "tone-aquaair"

def test_load_profile_not_found():
    assert load_profile("nonexistent") is None

def test_list_profiles():
    profiles = list_profiles()
    assert len(profiles) >= 1
    assert any(p["id"] == "tone-aquaair" for p in profiles)

def test_profile_products():
    p = load_profile("tone-aquaair")
    assert "TONE_AQUA_AIR" in p.products
    assert "TONE_AIR" in p.products
    assert p.products["TONE_AQUA_AIR"]["name"] == "T.One\u00ae AquaAIR"

def test_profile_air_modes():
    p = load_profile("tone-aquaair")
    assert p.air_modes_clim == [
        {"index": 0, "code": "A", "label": "Off"},
        {"index": 5, "code": "F", "label": "Confort"},
        {"index": 6, "code": "G", "label": "Boost"},
        {"index": 7, "code": "H", "label": "Programme C"},
        {"index": 8, "code": "I", "label": "Programme D"},
    ]
    assert p.air_modes_heat == [
        {"index": 0, "code": "A", "label": "Off"},
        {"index": 1, "code": "B", "label": "Confort"},
        {"index": 2, "code": "C", "label": "Éco"},
        {"index": 3, "code": "D", "label": "Programme A"},
        {"index": 4, "code": "E", "label": "Programme B"},
    ]

def test_profile_water_modes():
    p = load_profile("tone-aquaair")
    assert p.water_modes == [
        {"index": 0, "code": "L", "label": "Off"},
        {"index": 1, "code": "M", "label": "On"},
        {"index": 2, "code": "N", "label": "Boost"},
    ]

def test_get_air_mode_label():
    p = load_profile("tone-aquaair")
    assert p.get_air_mode_label("A") == "Off"
    assert p.get_air_mode_label("F") == "Confort"
    assert p.get_air_mode_label("Z") == "Z"

def test_get_water_mode_label():
    p = load_profile("tone-aquaair")
    assert p.get_water_mode_label("L") == "Off"
    assert p.get_water_mode_label("M") == "On"
    assert p.get_water_mode_label("N") == "Boost"

def test_resolve_reference():
    p = load_profile("tone-aquaair")
    assert p.resolve_reference({"NED": 75, "UDM": 2}) == "TONE_AQUA_AIR"
    assert p.resolve_reference({"NED": 75}) == "TONE_AIR"
    assert p.resolve_reference({}) == "TONE_AIR"

def test_to_dict():
    p = load_profile("tone-aquaair")
    d = p.to_dict()
    assert d["id"] == "tone-aquaair"
    assert "air_modes" in d
    assert "water_modes" in d
    assert "commands" in d
    assert "ui" in d


# --- Resolution des codes de mode (air_mode_code / water_mode_code) ---

def test_air_mode_code_index_resolved_by_profile():
    p = load_profile("tone-aquaair")
    assert air_mode_code(0, p) == "A"
    assert air_mode_code("5", p) == "F"
    assert air_mode_code(8, p) == "I"
    assert air_mode_code(5.0, p) == "F"
    # index hors bornes / valeur absente -> None (pas de crash HA)
    assert air_mode_code(9, p) is None
    assert air_mode_code(-1, p) is None
    assert air_mode_code(None, p) is None
    assert air_mode_code("", p) is None

def test_air_mode_code_letter_only_when_declared():
    tone = load_profile("tone-aquaair")
    vmc = load_profile("inspirair-home-s")
    # PAC : UAM est numerique, une lettre inconnue n'est jamais un code plausible
    assert air_mode_code("F", tone) == "F"
    assert air_mode_code("abc", tone) is None
    # VMC : la telemetrie envoie deja le code (current_mode: "X")
    assert air_mode_code("X", vmc) == "X"
    assert air_mode_code("x", vmc) == "X"
    assert air_mode_code("A", vmc) is None
    # sans profil : repli sur les circuits A-I
    assert air_mode_code("F", None) == "F"
    assert air_mode_code("X", None) is None
    assert air_mode_code(5, None) == "F"

def test_air_mode_code_vmc_indexes():
    vmc = load_profile("inspirair-home-s")
    assert air_mode_code(0, vmc) == "V"
    assert air_mode_code(4, vmc) == "Z"
    assert air_mode_code(5, vmc) is None

def test_water_mode_code():
    p = load_profile("tone-aquaair")
    assert water_mode_code(0, p) == "L"
    assert water_mode_code("1", p) == "M"
    assert water_mode_code(2, p) == "N"
    assert water_mode_code(3, p) is None
    assert water_mode_code("abc", p) is None
    assert water_mode_code(None, None) is None

def test_build_product_vmc_air_mode_from_code():
    vmc = load_profile("inspirair-home-s")
    product = build_product(
        {"modemid": "AABBCC", "productid": "AABBCC_AIR", "current_mode": "Y"},
        True,
        profile=vmc,
    )
    ind = product["indicator"]
    assert ind["current_air_mode"] == "Y"
    assert ind["current_water_mode"] is None
    assert ind["hors_gel"] is False
    assert ind["thermostats"] == []
    assert ind["ventilation"] is None


# --- Non-regression: mapping telemetrie identique ---

TELEMETRY = {
    "modemid": "ABCDEF123456",
    "productid": "ABCDEF123456_TONE",
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

def test_backward_compat_build_product():
    p = build_product(TELEMETRY, True)
    assert p["modem"] == "ABCDEF123456"
    assert p["serial_number"] == "ABCDEF123456_TONE"
    assert p["reference"] == "TONE_AQUA_AIR"
    assert p["indicator"]["current_air_mode"] == "F"
    assert p["indicator"]["current_water_mode"] == "M"
    assert p["indicator"]["qte_eau_chaude"] == 75
    assert p["indicator"]["tmp_principal"] == 25.87
    assert len(p["indicator"]["thermostats"]) == 5

def test_backward_compat_build_products():
    state = AppState("h", 8883, EventBus())
    capture_telemetry(state, json.dumps(TELEMETRY))
    products = build_products(state)
    assert len(products) == 1
    assert products[0]["reference"] == "TONE_AQUA_AIR"

def test_backward_compat_empty_telemetry():
    state = AppState("h", 8883, EventBus())
    products = build_products(state)
    assert len(products) == 1
    assert products[0]["modem"] == "N/A"

def test_backward_compat_thermostats():
    ts = build_thermostats(TELEMETRY)
    assert len(ts) == 5
    assert ts[0]["CurrentTemperature"] == 25.9
    assert ts[0]["TemperatureSet"] == 26.0


# --- AppState avec profile ---

def test_appstate_profile_none_by_default():
    state = AppState("h", 8883, EventBus())
    assert state.profile is None
    snap = state.snapshot()
    assert "profile" not in snap

def test_appstate_profile_in_snapshot():
    state = AppState("h", 8883, EventBus())
    state.profile = load_profile("tone-aquaair")
    snap = state.snapshot()
    assert "profile" in snap
    assert snap["profile"]["id"] == "tone-aquaair"

def test_custom_profile_from_yaml():
    data = {
        "id": "vmc-123",
        "name": "VMC Test",
        "description": "Test VMC",
        "type": "vmc",
        "products": {"VMC_TEST": {"name": "VMC Test", "reference_fields": []}},
        "air_modes": [{"index": 0, "code": "A", "label": "Off"}, {"index": 1, "code": "B", "label": "On"}],
        "water_modes": [],
        "commands": [],
        "ui": {"show_thermostats": False},
    }
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False, dir="/tmp") as f:
        yaml.dump(data, f)
        path = f.name
    try:
        d = tempfile.mkdtemp()
        p = load_profile("vmc-123", profiles_dir=d)
        assert p is None
        p = load_profile("vmc-123", profiles_dir=os.path.dirname(path))
        assert p is not None
        assert p.id == "vmc-123"
        assert p.type == "vmc"
        assert len(p.air_modes) == 2
    finally:
        os.unlink(path)


# --- Persistance du profil ---

def test_persist_profile_none():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        state = AppState("h", 8883, EventBus(), profile_file=path)
        state.set_profile(None)
        assert read_persisted_profile(path) is None
    finally:
        os.unlink(path)

def test_persist_profile_set():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        state = AppState("h", 8883, EventBus(), profile_file=path)
        p = load_profile("tone-aquaair")
        state.set_profile(p)
        assert read_persisted_profile(path) == "tone-aquaair"
    finally:
        os.unlink(path)

def test_persist_profile_change():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        state = AppState("h", 8883, EventBus(), profile_file=path)
        p = load_profile("tone-aquaair")
        state.set_profile(p)
        assert read_persisted_profile(path) == "tone-aquaair"
        state.set_profile(None)
        assert read_persisted_profile(path) is None
    finally:
        os.unlink(path)

def test_read_persisted_profile_missing_file():
    assert read_persisted_profile("/tmp/nonexistent_profile.json") is None

def test_read_persisted_profile_invalid_json():
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        f.write("not json")
        path = f.name
    try:
        assert read_persisted_profile(path) is None
    finally:
        os.unlink(path)

def test_read_persisted_profile_empty():
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        f.write("{}")
        path = f.name
    try:
        assert read_persisted_profile(path) is None
    finally:
        os.unlink(path)


# --- ConfigStore ---

def test_config_store_defaults():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        cfg = ConfigStore(path)
        assert cfg.get("history_retention_days") == 90
        assert cfg.get("log_retention_max_bytes") == 25 * 1024 * 1024
    finally:
        os.unlink(path)

def test_config_store_set():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        cfg = ConfigStore(path)
        cfg.set({"history_retention_days": 30})
        assert cfg.get("history_retention_days") == 30
        assert cfg.get("log_retention_max_bytes") == 25 * 1024 * 1024
    finally:
        os.unlink(path)

def test_config_store_persist():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        cfg = ConfigStore(path)
        cfg.set({"history_retention_days": 60})
        cfg2 = ConfigStore(path)
        assert cfg2.get("history_retention_days") == 60
    finally:
        os.unlink(path)

def test_config_store_range_clamp():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        cfg = ConfigStore(path)
        cfg.set({"history_retention_days": 99999})
        assert cfg.get("history_retention_days") == 3650
        cfg.set({"history_retention_days": 0})
        assert cfg.get("history_retention_days") == 1
    finally:
        os.unlink(path)

def test_config_store_unknown_key():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        cfg = ConfigStore(path)
        cfg.set({"unknown_key": 123})
        assert cfg.get("unknown_key") is None
    finally:
        os.unlink(path)

def test_config_store_helpers():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        cfg = ConfigStore(path)
        assert cfg.history_retention() == 90
        assert cfg.log_retention_bytes() == 25 * 1024 * 1024
    finally:
        os.unlink(path)
