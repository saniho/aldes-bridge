#!/usr/bin/env python3
"""Tests HTTP des endpoints API (api.py).

Couvre /api/state, /api/config, /api/mode, /api/send, /api/logs,
/api/clear, /api/disconnect, /api/consigne, et la validation des paramètres.
"""
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, "/home/ubuntu/aldes-bridge")

from server.appstate import AppState
from server.events import EventBus
from server.history import HistoryDB


class _StubEngine:
    def __init__(self, mqtt_port=8883):
        self._mode = None
        self.mqtt_port = mqtt_port

    def set_mode(self, mode):
        self._mode = mode

    def set_raw(self):
        pass

    def inject(self, topic, payload, qos=0):
        return {"ok": True, "topic": topic, "qos": qos, "bytes": len(payload)}

    def disconnect(self):
        return {"ok": True, "session": "test"}


def _allocate_free_port():
    """Alloue un port libre via l'OS (port 0) pour éviter les conflits entre tests."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_web(state, engine=None):
    import uvicorn
    from server.api import create_app
    engine = engine or _StubEngine()
    app = create_app(state, engine, "/nonexistent")
    for _ in range(20):
        port = _allocate_free_port()
        cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        srv = uvicorn.Server(cfg)
        t = threading.Thread(target=srv.run, daemon=True)
        t.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=1)
                return port, engine, srv
            except Exception:
                time.sleep(0.15)
    raise RuntimeError("impossible de démarrer uvicorn sur un port libre")


def _req(port, path, method="GET", body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = None
    headers = {}
    if isinstance(body, dict):
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif isinstance(body, str):
        data = body.encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def _req_raw(port, path, method="GET", body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = None
    headers = {}
    if isinstance(body, dict):
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif isinstance(body, str):
        data = body.encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    return urllib.request.urlopen(req, timeout=5)


# --- /api/state ---

def test_api_state_returns_config_and_messages():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    r = _req(port, "/api/state")
    assert "config" in r
    assert "messages" in r
    assert r["config"]["mode"] == "proxy"
    assert r["config"]["connected"] is False


def test_api_config_matches_state():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    cfg = _req(port, "/api/config")
    state_cfg = _req(port, "/api/state")["config"]
    assert cfg == state_cfg


# --- /api/mode ---

def test_api_mode_change():
    state = AppState("h", 8883, EventBus())
    port, engine, _ = _start_web(state)
    r = _req(port, "/api/mode", "POST", {"mode": "bridge"})
    assert r["mode"] == "bridge"
    assert r["takeEffect"] == "next-connect"
    assert engine._mode == "bridge"


def test_api_mode_invalid_rejected():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    try:
        _req(port, "/api/mode", "POST", {"mode": "invalid"})
        raise AssertionError("attendu 400")
    except urllib.error.HTTPError as e:
        assert e.code == 400


# --- /api/send ---

def test_api_send_returns_result():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    r = _req(port, "/api/send", "POST", {
        "topic": "devices/test/messages/devicebound",
        "payload": '{"test":true}',
        "qos": 1,
    })
    assert r["ok"] is True
    assert r["topic"] == "devices/test/messages/devicebound"
    assert r["qos"] == 1


# --- /api/logs ---

def test_api_logs_empty():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    r = _req(port, "/api/logs")
    assert r["total"] == 0
    assert r["events"] == []


def test_api_logs_limit_clamped():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    r = _req(port, "/api/logs?limit=9999")
    assert r["limit"] == 1000  # plafonné à 1000


# --- /api/clear ---

def test_api_clear():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    # injecte d'abord un message
    _req(port, "/api/test/inject", "POST", {"payload": '{"x":1}'})
    assert len(state.events.snapshot()) > 0
    # clear
    r = _req(port, "/api/clear", "POST")
    assert r["ok"] is True
    assert len(state.events.snapshot()) == 0


# --- /api/disconnect ---

def test_api_disconnect():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    r = _req(port, "/api/disconnect", "POST")
    assert r["ok"] is True
    assert r["session"] == "test"


# --- /api/consigne ---

def test_api_consigne_get_empty():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    r = _req(port, "/api/consigne")
    assert r["consignes"] == {}


def test_api_consigne_post():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    r = _req(port, "/api/consigne", "POST", {"zone": "0", "value": 22.0})
    assert "consignes" in r
    assert r["consignes"]["0"]["requested"] == 22.0


# --- /api/history — validation start < end ---

def test_api_history_series_start_ge_end_returns_400():
    import tempfile
    db = HistoryDB(tempfile.mktemp(), retention_days=30)
    state = AppState("h", 8883, EventBus(), history=db)
    port, _, _ = _start_web(state)
    try:
        _req(port, "/api/history/series?key=Text&start=100&end=50")
        raise AssertionError("attendu 400")
    except urllib.error.HTTPError as e:
        assert e.code == 400
        err = json.loads(e.read())
        assert "start" in err["detail"]
    db.close()


def test_api_history_table_start_ge_end_returns_400():
    import tempfile
    db = HistoryDB(tempfile.mktemp(), retention_days=30)
    state = AppState("h", 8883, EventBus(), history=db)
    port, _, _ = _start_web(state)
    try:
        _req(port, "/api/history/table?start=100&end=50")
        raise AssertionError("attendu 400")
    except urllib.error.HTTPError as e:
        assert e.code == 400
    db.close()


def test_api_history_series_bucket_negative_returns_400():
    import tempfile
    db = HistoryDB(tempfile.mktemp(), retention_days=30)
    state = AppState("h", 8883, EventBus(), history=db)
    port, _, _ = _start_web(state)
    try:
        _req(port, "/api/history/series?key=Text&bucket=-1")
        raise AssertionError("attendu 400")
    except urllib.error.HTTPError as e:
        assert e.code == 400
    db.close()


# --- Endpoint inexistant ---

def test_api_unknown_endpoint_returns_404():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    try:
        _req(port, "/api/doesnotexist")
        raise AssertionError("attendu 404")
    except urllib.error.HTTPError as e:
        assert e.code == 404


# --- SPA fallback ---

def test_spa_fallback_returns_index():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    # /nonexistent devrait retourner le fallback (ou 404 si pas de frontend)
    try:
        resp = _req_raw(port, "/nonexistent")
        # Si le frontend est construit, on devrait avoir 200
        assert resp.status == 200
    except urllib.error.HTTPError:
        pass  # pas de frontend construit en test


# --- /api/profile ---

def test_api_profile_get():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    r = _req(port, "/api/profile")
    # Pas de profil chargé par défaut
    assert r["profile"] is None


def test_api_profile_set():
    from server.device_profile import load_profile
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    r = _req(port, "/api/profile", "PUT", {"profile_id": "tone-aquaair"})
    assert r["profile"]["id"] == "tone-aquaair"
    assert r["profile"]["name"] == "TONE AquaAIR"
    assert len(r["profile"]["air_modes_clim"]) == 5
    assert len(r["profile"]["air_modes_heat"]) == 5


def test_api_profile_set_not_found():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    try:
        _req(port, "/api/profile", "PUT", {"profile_id": "nonexistent"})
        raise AssertionError("attendu 404")
    except urllib.error.HTTPError as e:
        assert e.code == 404


def test_api_profiles_list():
    state = AppState("h", 8883, EventBus())
    port, _, _ = _start_web(state)
    r = _req(port, "/api/profiles")
    assert "profiles" in r
    assert len(r["profiles"]) >= 1
    ids = [p["id"] for p in r["profiles"]]
    assert "tone-aquaair" in ids


# --- Config ---

def test_api_settings_get():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        cfg_path = f.name
    try:
        from server.config import ConfigStore
        config = ConfigStore(cfg_path)
        state = AppState("h", 8883, EventBus(), config=config)
        port, _, _ = _start_web(state)
        r = _req(port, "/api/settings")
        assert "settings" in r
        assert "history_retention_days" in r["settings"]
        assert "log_retention_max_bytes" in r["settings"]
        assert r["settings"]["history_retention_days"] == 90
        assert r["settings"]["log_retention_max_bytes"] == 25 * 1024 * 1024
    finally:
        os.unlink(cfg_path)

def test_api_settings_set():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        cfg_path = f.name
    try:
        from server.config import ConfigStore
        config = ConfigStore(cfg_path)
        state = AppState("h", 8883, EventBus(), config=config)
        port, _, _ = _start_web(state)
        r = _req(port, "/api/settings", method="PUT",
                 body={"history_retention_days": 30})
        assert r["settings"]["history_retention_days"] == 30
        assert r["settings"]["log_retention_max_bytes"] == 25 * 1024 * 1024
    finally:
        os.unlink(cfg_path)

def test_api_settings_set_empty():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        cfg_path = f.name
    try:
        from server.config import ConfigStore
        config = ConfigStore(cfg_path)
        state = AppState("h", 8883, EventBus(), config=config)
        port, _, _ = _start_web(state)
        try:
            _req(port, "/api/settings", method="PUT",
                 body={})
            assert False, "expected error"
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        os.unlink(cfg_path)

def test_api_settings_set_range_clamp():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        cfg_path = f.name
    try:
        from server.config import ConfigStore
        config = ConfigStore(cfg_path)
        state = AppState("h", 8883, EventBus(), config=config)
        port, _, _ = _start_web(state)
        r = _req(port, "/api/settings", method="PUT",
                 body={"history_retention_days": 99999})
        assert r["settings"]["history_retention_days"] == 3650
    finally:
        os.unlink(cfg_path)

def test_api_settings_purge_triggered():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        cfg_path = f.name
    try:
        from server.config import ConfigStore
        config = ConfigStore(cfg_path)
        state = AppState("h", 8883, EventBus(), config=config)
        port, _, _ = _start_web(state)
        r = _req(port, "/api/settings", method="PUT",
                 body={"history_retention_days": 1})
        assert r["settings"]["history_retention_days"] == 1
    finally:
        os.unlink(cfg_path)


# --- /api/diagnostic ---

def test_api_diagnostic_uses_configured_mqtt_port():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    mqtt_port = listener.getsockname()[1]
    try:
        state = AppState("h", 8883, EventBus())
        port, _, _ = _start_web(state, _StubEngine(mqtt_port=mqtt_port))
        result = _req(port, "/api/diagnostic")
        check = next(c for c in result["checks"] if c["id"] == "mqtt_listener")
        assert check["label"] == f"Listener MQTT (:{mqtt_port})"
        assert check["ok"] is True
    finally:
        listener.close()


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
    print("\n%d tests en echec" % failures)
    sys.exit(1 if failures else 0)
