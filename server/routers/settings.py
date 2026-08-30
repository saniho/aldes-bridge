"""Routes settings (parametres persistants)."""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..utils import iso
from .schemas import SettingsBody

_log = logging.getLogger("aldes-api")

router = APIRouter(prefix="/api", tags=["settings"])


def _state(request: Request):
    return request.app.extra["state"]


@router.get("/settings")
def api_settings_get(request: Request):
    cfg = _state(request).config.get() if _state(request).config else {}
    return {"settings": cfg}


@router.put("/settings")
def api_settings_set(request: Request, body: SettingsBody):
    st = _state(request)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return JSONResponse(status_code=400, content={"error": "aucun parametre fourni"})
    if st.config is None:
        return JSONResponse(status_code=500, content={"error": "config non initialisee"})
    st.config.set(updates)
    st._purge_now()
    if "ha_mqtt_dry_run" in updates:
        ha_client = getattr(st, "_ha_client", None)
        if ha_client is not None:
            ha_client.dry_run = updates["ha_mqtt_dry_run"]
            _log.info("ha-discovery: dry_run=%s (toggle UI)", updates["ha_mqtt_dry_run"])
    st.events.publish({
        "kind": "status", "ts": iso(),
        "note": f"settings mis a jour : {list(updates.keys())}",
    })
    return {"settings": st.config.get()}
