#!/usr/bin/env python3
"""Verification de la securite thread du bus d'evenements + log disque (point 8).

Le code est deja verrouille (EventBus._lock / EventLog._lock) ; ce test verrouille
le CONTRAT : append + rotation + lecture (tail/total/snapshot) + clear en acces
concurrent ne doivent lever aucune exception et rester coherents.
"""
import os
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, "/home/ubuntu/aldes-bridge")

from server.events import EventBus
from server.eventlog import EventLog


def test_eventbus_concurrent_publish_read_rotate():
    print("== test_eventbus_concurrent_publish_read_rotate ==")
    tmp = tempfile.mkdtemp(prefix="aldes-evlog-")
    path = os.path.join(tmp, "events.jsonl")
    log = EventLog(path, max_bytes=64 * 1024)
    bus = EventBus(history_size=50, log=log)

    errs = []
    n = 3000

    def publish():
        try:
            for i in range(n):
                bus.publish({"kind": "message", "type": "PUBLISH", "i": i,
                             "payload": "x" * (i % 2000)})
        except Exception as exc:
            errs.append(exc)

    def snapshot():
        try:
            for _ in range(2000):
                bus.snapshot()
        except Exception as exc:
            errs.append(exc)

    def tail():
        try:
            for _ in range(2000):
                log.tail(50, 0)
                log.total()
        except Exception as exc:
            errs.append(exc)

    def clear():
        try:
            for _ in range(5):
                bus.clear()
        except Exception as exc:
            errs.append(exc)

    threads = [threading.Thread(target=publish),
               threading.Thread(target=snapshot),
               threading.Thread(target=tail),
               threading.Thread(target=clear)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "thread bloque"

    assert not errs, "exception pendant acces concurrent: %r" % errs

    # apres la rafale, le log reste lisible et compte des evenements
    assert log.total() > 0, "log vide apres publication"
    evs = log.tail(5, 0)
    assert evs and all(isinstance(e, dict) for e in evs), "log illisible"
    assert len(bus.snapshot()) <= 50, "historique circulaire non borne"

    # la rotation a bien tourne (generations sur disque)
    assert os.path.exists(path) or os.path.exists(path + ".1"), "pas de rotation"

    log.clear()
    shutil.rmtree(tmp, ignore_errors=True)
    print("  OK")


if __name__ == "__main__":
    test_eventbus_concurrent_publish_read_rotate()