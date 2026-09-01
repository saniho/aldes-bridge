"""Rejeu de l'API Aldes pour l'integration HA 'saniho-ha'."""
import json
import logging
import urllib.parse

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..aldes import build_products, make_token
from . import get_state
from ..utils import iso

_log = logging.getLogger("aldes-api")

router = APIRouter(tags=["aldes-compat"])


@router.post("/oauth2/token")
async def aldes_token(request: Request):
    st = get_state(request)
    raw = await request.body()
    try:
        form = urllib.parse.parse_qs(raw.decode("utf-8", errors="replace"))
    except Exception:
        form = {}
    username = (form.get("username") or [""])[0].strip()
    password = (form.get("password") or [""])[0].strip()
    if not username or not password:
        return JSONResponse(status_code=400, content={"error": "invalid_grant"})
    st.events.publish({
        "kind": "status", "ts": iso(), "note": "authentification Aldes (token emis)",
        "username": username,
    })
    return make_token(username=username)


@router.get("/aldesoc/v5/users/me/products")
def aldes_products(request: Request):
    return build_products(get_state(request))


@router.patch("/aldesoc/v5/users/me/products/{modem}/updateThermostats")
async def aldes_update_thermostats(request: Request, modem: str):
    st = get_state(request)
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "corps JSON invalide"})
    st.events.publish({
        "kind": "message", "type": "ALDES_WRITE",
        "topic": "devices/%s/messages/devicebound" % modem,
        "payload": json.dumps(body, ensure_ascii=False),
        "note": "consigne thermostat recue (non renvoyee a la box)",
    })
    return {"success": True, "modem": modem, "thermostats": body}


@router.post("/aldesoc/v5/users/me/products/{modem}/commands")
async def aldes_commands(request: Request, modem: str):
    st = get_state(request)
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "corps JSON invalide"})
    st.events.publish({
        "kind": "message", "type": "ALDES_WRITE",
        "topic": "devices/%s/messages/devicebound" % modem,
        "payload": json.dumps(body, ensure_ascii=False),
        "note": "commande recue (non renvoyee a la box)",
    })
    return {"success": True, "modem": modem, "command": body}
