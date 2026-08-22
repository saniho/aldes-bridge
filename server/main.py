#!/usr/bin/env python3
"""Point d'entree Aldes Bridge.

Le mode (proxy | bridge | listen | raw) s'active par defaut ici mais est surtout
changeable depuis la Web UI (POST /api/mode). Le listener MQTT/TLS reste identique
pour les modes proxy/bridge/listen (la box se connecte au bridge).
"""
import argparse
import logging
import os
import sys

from .appstate import AppState, read_persisted_mode, read_persisted_profile
from .device_profile import load_profile
from .events import EventBus
from .engine import Engine
from .eventlog import EventLog
from .history import HistoryDB
from .aldes import capture_telemetry

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_log = logging.getLogger("aldes-backfill")

DEFAULT_MODE_FILE = os.path.join(APP_ROOT, "logs", "mode.json")
DEFAULT_TELEMETRY_FILE = os.path.join(APP_ROOT, "logs", "telemetry.json")
DEFAULT_CONSIGNE_FILE = os.path.join(APP_ROOT, "logs", "consigne.json")
DEFAULT_HISTORY_FILE = os.path.join(APP_ROOT, "logs", "history.db")
DEFAULT_PROFILE_FILE = os.path.join(APP_ROOT, "logs", "profile.json")
DEFAULT_HISTORY_DAYS = 90


def _default_web_dir():
    for cand in ("dist", "web/dist"):
        p = os.path.join(APP_ROOT, cand)
        if os.path.isdir(p) and os.path.exists(os.path.join(p, "index.html")):
            return p
    return os.path.join(APP_ROOT, "dist")


def _backfill_history(history, log, n=10000):
    """Rejoue les événements du log persistant dans la base d'historisation.

    Ne reprend que les trames utiles (PUBLISH boxward + status de connexion) et
    les plus récentes dans la fenêtre de rétention. Best-effort : ne lève jamais.
    """
    try:
        events = log.tail_oldest_first(n)
    except Exception as exc:
        _log.warning("backfill: impossible de lire le log: %s", exc)
        return 0
    kept = 0
    for ev in events:
        try:
            kind = ev.get("kind")
            if kind == "message" and ev.get("type") == "PUBLISH" and ev.get("direction") == "in":
                kept += history.record_telemetry(ev.get("payload") or "")
            elif kind == "status" and "connected" in ev:
                history.record_status("box", bool(ev["connected"]))
                kept += 1
            elif kind == "status" and "cloud_connected" in ev:
                history.record_status("cloud", bool(ev["cloud_connected"]))
                kept += 1
        except Exception as exc:
            _log.debug("backfill: evenement ignore: %s", exc)
            continue
    return kept


def build_parser():
    ap = argparse.ArgumentParser(prog="aldes-bridge", description="Bridge Aldes (proxy MITM / faux broker) + WebUI.")
    ap.add_argument("--mode", choices=["proxy", "bridge", "listen", "raw"],
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
    ap.add_argument("--consigne-file", default=os.environ.get("ALDES_CONSIGNE_FILE", DEFAULT_CONSIGNE_FILE),
                    help="persistance des consignes demandees (JSON), vide pour desactiver")
    ap.add_argument("--history-file", default=os.environ.get("ALDES_HISTORY_FILE", DEFAULT_HISTORY_FILE),
                    help="base SQLite d'historisation des valeurs, vide pour desactiver")
    ap.add_argument("--history-days", type=int,
                    default=int(os.environ.get("ALDES_HISTORY_DAYS", DEFAULT_HISTORY_DAYS)),
                    help="retention de l'historique en jours (défaut %d)" % DEFAULT_HISTORY_DAYS)
    ap.add_argument("--no-history-backfill", action="store_true",
                    help="ne pas rejouer le log persistant dans l'historique au demarrage")
    ap.add_argument("--profile", default=os.environ.get("ALDES_PROFILE", None),
                    help="ID du profil device (defaut: tone-aquaair ou le premier disponible)")
    ap.add_argument("--profile-file", default=os.environ.get("ALDES_PROFILE_FILE", DEFAULT_PROFILE_FILE),
                    help="fichier de persistance du profil (survit au redemarrage)")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        import uvicorn
    except ImportError:
        sys.stderr.write("Paquet manquant: fastapi + uvicorn. Installez avec:\n"
                         "  pip install fastapi 'uvicorn[standard]'\n")
        raise SystemExit(2)

    log = None
    if args.log_file:
        log = EventLog(args.log_file, max_bytes=args.log_max)
    events = EventBus(args.history_size, log=log)
    restored = events.restore_from_log(args.history_size)

    history = None
    if args.history_file:
        history = HistoryDB(args.history_file, retention_days=args.history_days)
        if log is not None and not args.no_history_backfill:
            _backfill_history(history, log)

    state = AppState(args.real_host, args.real_port, events,
                     mode_file=args.mode_file, telemetry_file=args.telemetry_file,
                     consigne_file=args.consigne_file, history=history,
                     profile_file=args.profile_file)
    # Chargement du profil device (YAML). Priorite : profil persiste > CLI/env > defaut.
    persisted_profile_id = read_persisted_profile(args.profile_file)
    profile_id = persisted_profile_id or args.profile
    profile = load_profile(profile_id)
    if profile:
        state.profile = profile
        _log.info("profil device charge: %s (%s)", profile.id, profile.name)
    # Capture des telemetries : branchee ici pour decoupler appstate (plomberie
    # d'evenements) de aldes (mapping metier). Appelee sur chaque PUBLISH entrant.
    state.on_publish_in = capture_telemetry
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