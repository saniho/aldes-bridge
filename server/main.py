#!/usr/bin/env python3
"""Point d'entree Aldes Bridge.

Le mode (proxy | bridge) s'active par defaut ici mais est surtout changeable depuis
la Web UI (POST /api/mode). Le listener MQTT/TLS reste identique pour les deux modes.
"""
import argparse
import os

from .appstate import AppState, read_persisted_mode
from .events import EventBus
from .engine import Engine
from .eventlog import EventLog

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_MODE_FILE = os.path.join(APP_ROOT, "logs", "mode.json")
DEFAULT_TELEMETRY_FILE = os.path.join(APP_ROOT, "logs", "telemetry.json")


def _default_web_dir():
    for cand in ("dist", "web/dist"):
        p = os.path.join(APP_ROOT, cand)
        if os.path.isdir(p) and os.path.exists(os.path.join(p, "index.html")):
            return p
    return os.path.join(APP_ROOT, "dist")


def build_parser():
    ap = argparse.ArgumentParser(prog="aldes-bridge", description="Bridge Aldes (proxy MITM / faux broker) + WebUI.")
    ap.add_argument("--mode", choices=["proxy", "bridge", "raw"],
                    default=os.environ.get("ALDES_MODE", "bridge"),
                    help="mode initial (changeable depuis la WebUI)")
    ap.add_argument("--mode-file", default=DEFAULT_MODE_FILE,
                    help="persistance du mode (reste pris en compte si ce fichier existe)")
    ap.add_argument("--bind", default="0.0.0.0", help="adresse de bind (MQTT + web)")
    ap.add_argument("--mqtt-port", type=int, default=8883, help="port MQTT/TLS (defaut 8883)")
    ap.add_argument("--web-port", type=int, default=8080, help="port de la WebUI/API (defaut 8080)")
    ap.add_argument("--real-host", default="aldesiotsuite.azure-devices.net",
                    help="hote Azure reel (mode proxy)")
    ap.add_argument("--real-port", type=int, default=8883)
    ap.add_argument("--web-dir", default=_default_web_dir(), help="dossier du frontend construit")
    ap.add_argument("--history-size", type=int, default=200, help="nb de messages gardes")
    ap.add_argument("--log-file", default=os.path.join(APP_ROOT, "logs", "events.log.jsonl"),
                    help="fichier de log persistant (JSONL), vide pour desactiver")
    ap.add_argument("--log-max", type=int, default=25 * 1024 * 1024,
                    help="taille max (octets) du fichier de log avant rotation")
    ap.add_argument("--telemetry-file", default=os.environ.get("ALDES_TELEMETRY_FILE", DEFAULT_TELEMETRY_FILE),
                    help="persistance des dernieres telemetries capturees (JSON), vide pour desactiver")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        import uvicorn
    except ImportError:
        import sys
        sys.stderr.write("Paquet manquant: fastapi + uvicorn. Installez avec:\n"
                         "  pip install fastapi 'uvicorn[standard]'\n")
        raise SystemExit(2)

    log = None
    if args.log_file:
        log = EventLog(args.log_file, max_bytes=args.log_max)
    events = EventBus(args.history_size, log=log)
    restored = events.restore_from_log(args.history_size)
    state = AppState(args.real_host, args.real_port, events,
                     mode_file=args.mode_file, telemetry_file=args.telemetry_file)
    # Le mode persiste (mode.json) prime sur le mode CLI/env au redemarrage.
    state.set_mode(read_persisted_mode(args.mode_file) or args.mode)

    engine = Engine(state, mqtt_port=args.mqtt_port, bind=args.bind)
    engine.start()
    state.set_error("ecoute MQTT sur %s:%d, web sur %s:%d" % (args.bind, args.mqtt_port, args.bind, args.web_port))

    from .api import create_app
    app = create_app(state, engine, args.web_dir)
    uvicorn.run(app, host=args.bind, port=args.web_port, log_level="info")


if __name__ == "__main__":
    main()