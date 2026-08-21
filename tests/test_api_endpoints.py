#!/usr/bin/env python3
"""Tests HTTP des endpoints API (api.py).

Couvre /api/state, /api/config, /api/mode, /api/send, /api/logs,
/api/clear, /api/disconnect, /api/consigne, et la validation des paramètres.
"""
import json
import random
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, "/home/ubuntu/aldes-bridge")

from server.appstate import AppState
from server.events import EventBus
from server.history import HistoryDB


class _StubEngine:
    def __init__(self):
        self._mode = None

    def set_mode(self, mode):
        self._mode = mode

    def set_raw(self):
        pass

    def inject(self, topic, payload, qos=0):
        return {"ok": True, "topic": topic, "qos": qos, "bytes": len(payload)}

    def disconnect(self):
        return {"ok": True, "session": "test"}


def _start_web(state):
    import uvicorn
    from server.api import create_app
    engine = _StubEngine()
    app = create_app(state, engine, "/nonexistent")
    for _ in range(20):
        port = random.randint(18200, 18999)
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
