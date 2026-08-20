#!/usr/bin/env python3
"""Tests de l'historisation des valeurs (server.history + endpoints /api/history)."""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, "/home/ubuntu/aldes-bridge")

from server.appstate import AppState
from server.events import EventBus
from server.history import HistoryDB


def make_db(tmp=None, days=90):
    d = tmp or tempfile.mkdtemp()
    return HistoryDB(os.path.join(d, "history.db"), retention_days=days)


class _StubEngine:
    def set_mode(self, mode):
        pass

    def set_raw(self):
        pass

    def inject(self, *a, **k):
        return {"ok": True}

    def disconnect(self):
        return {"ok": True}


def _start_web(state):
    import uvicorn
    from server.api import create_app
    app = create_app(state, _StubEngine(), "/nonexistent")
    _start_web._next = getattr(_start_web, "_next", 0) + 1
    port = 18090 + _start_web._next
    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(cfg)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    return port


def _request(port, path, method="GET", body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = None
    headers = {}
    if isinstance(body, str):
        data = body.encode()
        headers["Content-Type"] = "application/json"
    elif isinstance(body, dict):
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


# --- Tests unitaires de la couche DB ----------------------------------------

def test_record_telemetry_stores_numeric_fields():
    db = make_db()
    n = db.record_telemetry('{"Text":21.5,"MT0":24.1,"label":"chaud"}')
    assert n == 2  # seuls les champs numeriques
    keys = {k["key"]: k["samples"] for k in db.keys()}
    assert keys == {"MT0": 1, "Text": 1}
    db.close()


def test_record_telemetry_ignores_garbage():
    db = make_db()
    assert db.record_telemetry("pas du json") == 0
    assert db.record_telemetry('{"foo":"bar"}') == 0
    assert db.record_telemetry("") == 0
    assert db.count() == 0
    db.close()


def test_record_telemetry_handles_binary_prefix():
    db = make_db()
    n = db.record_telemetry(b"\x00F{\"Text\":19.8}")
    assert n == 1
    db.close()


def test_record_status_boolean():
    db = make_db()
    db.record_status("box", True)
    db.record_status("cloud", False)
    keys = {k["key"]: k["samples"] for k in db.keys()}
    assert keys == {"box": 1, "cloud": 1}
    db.close()


def test_series_raw_and_bucketed():
    db = make_db()
    t0 = time.time()
    for i, v in enumerate((10.0, 20.0, 30.0)):
        db.record_telemetry('{"Text":%s}' % v)
    raw = db.series("Text")
    assert [round(p["value"], 1) for p in raw] == [10.0, 20.0, 30.0]
    # bucket large : tous dans le meme bucket -> min/max/avg
    bucketed = db.series("Text", start=t0 - 60, end=time.time() + 60, bucket=3600)
    assert len(bucketed) >= 1
    b = bucketed[-1]
    assert b["min"] == 10.0 and b["max"] == 30.0
    assert abs(b["avg"] - 20.0) < 0.01
    assert b["n"] == 3
    db.close()


def test_series_window_filtering():
    db = make_db()
    # deux valeurs d'epoques distinctes (1h d'ecart) via insert direct
    t0 = time.time()
    with db._lock:
        db._conn.execute(
            "INSERT INTO samples (ts, kind, key, value) VALUES (?, 'telemetry', 'Text', ?)",
            (t0 - 3600, 10.0),
        )
        db._conn.execute(
            "INSERT INTO samples (ts, kind, key, value) VALUES (?, 'telemetry', 'Text', ?)",
            (t0, 20.0),
        )
        db._conn.commit()
    only = db.series("Text", start=t0 - 5, end=t0 + 5)
    assert [round(p["value"], 1) for p in only] == [20.0]
    db.close()


def test_purge_removes_old_samples():
    db = make_db()
    db.record_telemetry('{"Text":10.0}')
    # injecte une valeur vieille de 100 jours via sql direct
    old = time.time() - 100 * 86400
    with db._lock:
        db._conn.execute(
            "INSERT INTO samples (ts, kind, key, value) VALUES (?, 'telemetry', 'Text', ?)",
            (old, 99.0),
        )
        db._conn.commit()
    removed = db.purge(days=90)
    assert removed == 1
    assert db.count() == 1
    db.close()


def test_count_and_retention_days():
    db = make_db(days=45)
    assert db.retention_days == 45
    assert db.count() == 0
    db.close()


# --- Tests endpoints API ----------------------------------------------------

def test_api_history_endpoints(tmp_path):
    db = make_db(tmp_path, days=30)
    state = AppState("h", 8883, EventBus(), history=db)
    port = _start_web(state)

    # injection simulee -> alimente l'historique
    _request(port, "/api/test/inject", "POST", {"payload": '{"Text":21.5,"MT0":24.1}'})
    _request(port, "/api/test/inject", "POST", {"payload": '{"Text":22.0,"MT0":24.3}'})

    keys = _request(port, "/api/history/keys")["keys"]
    by_key = {k["key"]: k["samples"] for k in keys}
    assert by_key == {"MT0": 2, "Text": 2}

    series = _request(port, "/api/history/series?key=Text")["samples"]
    assert len(series) == 2

    bucketed = _request(
        port, "/api/history/series?key=Text&bucket=3600"
    )["samples"]
    assert len(bucketed) == 1
    assert bucketed[0]["n"] == 2

    table = _request(port, "/api/history/table?limit=50")
    assert table["total"] == 4
    assert len(table["samples"]) == 4
    assert table["samples"][0]["key"] in ("MT0", "Text")

    cfg = _request(port, "/api/config")
    assert cfg["history_days"] == 30
    db.close()


def test_api_history_disabled_returns_503():
    from urllib.error import HTTPError
    state = AppState("h", 8883, EventBus(), history=None)
    port = _start_web(state)
    try:
        _request(port, "/api/history/keys")
        raise AssertionError("attendu 503")
    except HTTPError as e:
        assert e.code == 503
    assert _request(port, "/api/config")["history_days"] is None


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