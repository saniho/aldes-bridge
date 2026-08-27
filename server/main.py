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
from .config import ConfigStore
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
DEFAULT_CONFIG_FILE = os.path.join(APP_ROOT, "logs", "config.json")
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
                    default=os.environ.get("ALDES_MODE") or None,
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
    ap.add_argument("--config-file", default=os.environ.get("ALDES_CONFIG_FILE", DEFAULT_CONFIG_FILE),
                    help="fichier de configuration persistante (survit au redemarrage)")
    # Home Assistant MQTT Auto-Discovery
    ap.add_argument("--ha-mqtt", action="store_true",
                    default=os.environ.get("HA_MQTT_ENABLED", "").lower() in ("1", "true", "yes"),
                    help="activer la decouverte MQTT Home Assistant")
    ap.add_argument("--ha-mqtt-host", default=os.environ.get("HA_MQTT_HOST", "127.0.0.1"),
                    help="hote du broker MQTT local (defaut: 127.0.0.1)")
    ap.add_argument("--ha-mqtt-port", type=int,
                    default=int(os.environ.get("HA_MQTT_PORT", "1883")),
                    help="port du broker MQTT local (defaut: 1883)")
    ap.add_argument("--ha-mqtt-user", default=os.environ.get("HA_MQTT_USER", None),
                    help="utilisateur MQTT (optionnel)")
    ap.add_argument("--ha-mqtt-password", default=os.environ.get("HA_MQTT_PASSWORD", None),
                    help="mot de passe MQTT (optionnel)")
    ap.add_argument("--ha-mqtt-prefix", default=os.environ.get("HA_MQTT_PREFIX", "aldes"),
                    help="prefixe des topics HA (defaut: aldes)")
    ap.add_argument("--ha-mqtt-dry-run", action="store_true",
                    default=os.environ.get("HA_MQTT_DRY_RUN", "true").lower() in ("1", "true", "yes"),
                    help="mode dry-run : log les commandes sans les envoyer (defaut: active)")
    ap.add_argument("--ha-mqtt-no-dry-run", action="store_true",
                    default=os.environ.get("HA_MQTT_DRY_RUN", "").lower() in ("0", "false", "no"),
                    help="desactive le dry-run : les commandes HA sont envoyees reellement a la box")
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

    config = ConfigStore(args.config_file)

    history = None
    if args.history_file:
        history = HistoryDB(args.history_file, retention_days=config.history_retention())
        if log is not None and not args.no_history_backfill:
            _backfill_history(history, log)

    state = AppState(args.real_host, args.real_port, events,
                     mode_file=args.mode_file, telemetry_file=args.telemetry_file,
                     consigne_file=args.consigne_file, history=history,
                     profile_file=args.profile_file, config=config)
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
    # Priorite : CLI explicite (depuis config HAOS) > mode.json (WebUI) > defaut bridge.
    state.set_mode(args.mode or read_persisted_mode(args.mode_file) or "bridge")

    # Resolution DNS Azure au demarrage (tous les modes).
    try:
        from .tls import resolve
        azure_ip = resolve(args.real_host, args.real_port)
        state.set_azure_ip(azure_ip)
        _log.info("Azure DNS: %s -> %s", args.real_host, azure_ip)
    except Exception as exc:
        _log.warning("Azure DNS resolution failed: %s", exc)

    # Purge automatique periodique (toutes les heures).
    state.start_purge_timer()

    engine = Engine(state, mqtt_port=args.mqtt_port, bind=args.bind)
    engine.start()
    state.set_error("ecoute MQTT sur %s:%d, web sur %s:%d" % (args.bind, args.mqtt_port, args.bind, args.web_port))

    # Home Assistant MQTT Auto-Discovery
    ha_client = None
    if args.ha_mqtt:
        from .ha_discovery import HADiscoveryClient, detect_mqtt_broker
        # Détection auto du broker MQTT via Supervisor API
        mqtt_host = args.ha_mqtt_host
        mqtt_port = args.ha_mqtt_port
        mqtt_source = "cli"
        detected = detect_mqtt_broker()
        if detected:
            mqtt_host = detected["host"]
            mqtt_port = detected["port"]
            mqtt_source = "supervisor"
        elif args.ha_mqtt_host == "127.0.0.1":
            mqtt_source = "fallback"
        state._ha_mqtt_resolved = {
            "host": mqtt_host,
            "port": mqtt_port,
            "source": mqtt_source,
        }
        ha_client = HADiscoveryClient(
            state,
            host=mqtt_host,
            port=mqtt_port,
            username=args.ha_mqtt_user,
            password=args.ha_mqtt_password,
            prefix=args.ha_mqtt_prefix,
            dry_run=args.ha_mqtt_dry_run and not args.ha_mqtt_no_dry_run,
        )
        # Hook d'injection : les commandes HA → box passent par engine.inject
        def _ha_inject(topic, payload, qos):
            return engine.inject(topic, payload, qos)
        state._ha_inject_hook = _ha_inject
        # Hook telemetrie : met a jour les topics HA a chaque trame
        _original_on_publish_in = state.on_publish_in
        _hook_count = [0]
        def _on_publish_in_with_ha(state, payload):
            _hook_count[0] += 1
            if _original_on_publish_in:
                _original_on_publish_in(state, payload)
            try:
                from .aldes import _parse_telemetry_payload
                data = _parse_telemetry_payload(payload)
                if data:
                    ha_client.publish_telemetry(data)
                elif _hook_count[0] <= 5:
                    _log.info("ha-discovery: hook #%d - payload non-JSON/telemetry ignore (len=%d)",
                              _hook_count[0], len(payload) if payload else 0)
            except Exception as exc:
                _log.warning("ha-discovery: hook #%d - erreur: %s", _hook_count[0], exc)
        state.on_publish_in = _on_publish_in_with_ha
        ha_client.start()
        state._ha_client = ha_client
        dry_run_msg = " [DRY-RUN]" if (args.ha_mqtt_dry_run and not args.ha_mqtt_no_dry_run) else ""
        _log.info("HA MQTT auto-discovery active%s: %s:%d via %s (prefix: %s)",
                  dry_run_msg, mqtt_host, mqtt_port, mqtt_source, args.ha_mqtt_prefix)

    from .api import create_app
    app = create_app(state, engine, args.web_dir)
    uvicorn.run(app, host=args.bind, port=args.web_port, log_level="info")


if __name__ == "__main__":
    main()