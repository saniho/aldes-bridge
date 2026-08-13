#!/usr/bin/env python3
"""Tests de la persistance du mode au redemarrage (server.appstate)."""
import os
import sys
import tempfile

sys.path.insert(0, "/home/ubuntu/aldes-bridge")

from server.appstate import AppState, read_persisted_mode
from server.events import EventBus


def test_set_mode_persists():
    d = tempfile.mkdtemp()
    mf = os.path.join(d, "mode.json")
    s = AppState("h", 8883, EventBus(), mode_file=mf)
    s.set_mode("raw")
    assert os.path.isfile(mf)
    assert read_persisted_mode(mf) == "raw"


def test_mode_change_overwrites():
    d = tempfile.mkdtemp()
    mf = os.path.join(d, "mode.json")
    s = AppState("h", 8883, EventBus(), mode_file=mf)
    s.set_mode("raw")
    s.set_mode("proxy")
    assert read_persisted_mode(mf) == "proxy"


def test_restart_uses_persisted_mode():
    d = tempfile.mkdtemp()
    mf = os.path.join(d, "mode.json")
    AppState("h", 8883, EventBus(), mode_file=mf).set_mode("raw")
    # nouveau demarrage : le mode persiste prime sur le defaut
    mode = read_persisted_mode(mf) or "bridge"
    assert mode == "raw"
    assert mode in AppState.MODES


def test_missing_or_invalid_file_returns_none():
    d = tempfile.mkdtemp()
    assert read_persisted_mode(os.path.join(d, "absent.json")) is None
    bad = os.path.join(d, "bad.json")
    with open(bad, "w") as f:
        f.write("{oops")
    assert read_persisted_mode(bad) is None
    assert read_persisted_mode(None) is None


def test_no_mode_file_no_crash():
    s = AppState("h", 8883, EventBus())
    s.set_mode("bridge")
    assert s.mode == "bridge"


def test_snapshot_exposes_mode_file():
    d = tempfile.mkdtemp()
    mf = os.path.join(d, "mode.json")
    s = AppState("h", 8883, EventBus(), mode_file=mf)
    assert s.snapshot()["mode_file"] == mf


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
    print("\n%d pompes en echec" % failures)
    sys.exit(1 if failures else 0)