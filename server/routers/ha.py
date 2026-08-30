"""Route Home Assistant MQTT Auto-Discovery."""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["ha"])


def _state(request: Request):
    return request.app.extra["state"]


@router.get("/ha-discovery")
def api_ha_discovery_get(request: Request):
    """Retourne la config HA discovery et l'etat de la connexion."""
    st = _state(request)
    ha_client = getattr(st, "_ha_client", None)
    p = getattr(st, "profile", None)
    ha_config = p.ha_discovery if p else {}
    return {
        "enabled": ha_client is not None,
        "connected": ha_client._sock is not None if ha_client else False,
        "host": getattr(ha_client, "host", None),
        "port": getattr(ha_client, "port", None),
        "prefix": getattr(ha_client, "prefix", "aldes"),
        "config": ha_config,
    }
