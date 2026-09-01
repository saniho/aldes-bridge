"""Détection du broker MQTT via l'API Supervisor (HA OS)."""
import json
import logging
import os

_log = logging.getLogger("aldes-ha-discovery")


def detect_mqtt_broker():
    """Détecte le broker MQTT via l'API Supervisor (HA OS).

    Retourne {"host": ..., "port": ...} ou None si pas en mode add-on HA.
    """
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        _log.debug("ha-discovery: SUPERVISOR_TOKEN absent, skip detection Supervisor")
        return None
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://supervisor/services/mqtt",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            host = data.get("data", {}).get("host")
            port = data.get("data", {}).get("port")
            if host and port:
                _log.info("ha-discovery: broker MQTT détecté via Supervisor: %s:%d", host, port)
                return {"host": host, "port": int(port)}
    except Exception as exc:
        _log.debug("ha-discovery: détection Supervisor échouée (normal si pas add-on HA): %s", exc)
    return None
