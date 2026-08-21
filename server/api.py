"""API web (FastAPI) : config, etat, SSE temps reel, envoi de commandes, mode."""
import asyncio
import json
import os
import urllib.parse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from .aldes import build_products, make_token
from .appstate import _iso
from .version import read_ui_version


class SendBody(BaseModel):
    topic: str
    payload: str = ""
    qos: int = 0


class ModeBody(BaseModel):
    mode: str


class RawBody(BaseModel):
    host: str = ""
    port: int = 1883
    tls: bool = True
    client_id: str = ""
    cmd_topic: str = ""
    evt_topic: str = ""


class ConsigneBody(BaseModel):
    zone: str
    value: float


# --- Modèles de réponse (contrat de l'API, schema OpenAPI) ---
class ConsigneEntry(BaseModel):
    requested: float
    confirmed: bool
    ts: str


class RawConfig(BaseModel):
    enabled: bool
    host: str
    port: int
    tls: bool
    client_id: str
    cmd_topic: str
    evt_topic: str


class ConfigSnapshot(BaseModel):
    mode: str
    connected: bool
    client_id: str | None = None
    topics: list[str] = []
    last_error: str | None = None
    raw: RawConfig
    mode_file: str | None = None
    box_since: float | None = None
    cloud_since: float | None = None
    consignes: dict[str, ConsigneEntry] = {}
    server_version: str = "dev"
    ui_version: str = "dev"
    history_days: int | None = None


class StateSnapshot(BaseModel):
    config: ConfigSnapshot
    messages: list[dict] = []


class LogPage(BaseModel):
    total: int
    limit: int
    offset: int
    events: list[dict] = []


class SendResult(BaseModel):
    ok: bool
    error: str | None = None
    topic: str | None = None
    qos: int | None = None
    bytes: int | None = None


class ConsigneList(BaseModel):
    consignes: dict[str, ConsigneEntry] = {}


class ModeResult(BaseModel):
    mode: str
    takeEffect: str


class OkResult(BaseModel):
    ok: bool


class DisconnectResult(BaseModel):
    ok: bool
    session: str | None = None


def create_app(state, engine, web_dir):
    app = FastAPI(title="Aldes Bridge", docs_url=None, redoc_url=None)
    web_dir = os.path.abspath(web_dir)
    state.ui_version = read_ui_version(web_dir)

    @app.on_event("startup")
    async def _startup():
        state.events.attach_loop(asyncio.get_running_loop())

    @app.on_event("shutdown")
    async def _shutdown():
        # Rattrape le throttle telemetrie : telemetry.json a jour a l'arret.
        state.persist_telemetry()

    # --- API ---
    @app.get("/api/config", response_model=ConfigSnapshot)
    def api_config():
        return state.snapshot()

    @app.get("/api/state", response_model=StateSnapshot)
    def api_state():
        return {"config": state.snapshot(), "messages": state.events.snapshot()}

    @app.get("/api/logs", response_model=LogPage)
    def api_logs(limit: int = 200, offset: int = 0):
        """Lecture a posteriori du log disque persistant (plus recent d'abord)."""
        limit = max(1, min(limit, 1000))
        offset = max(0, offset)
        log = state.events.log
        if log is None:
            return {"total": 0, "limit": limit, "offset": offset, "events": []}
        events = log.tail(limit, offset)
        return {
            "total": log.total(),
            "limit": limit,
            "offset": offset,
            "events": events,
        }

    @app.get("/api/events")
    async def api_events():
        q = state.events.subscribe()

        async def gen():
            try:
                snap = {
                    "kind": "snapshot",
                    "config": state.snapshot(),
                    "messages": state.events.snapshot(),
                }
                yield "data: %s\n\n" % json.dumps(snap, ensure_ascii=False)
                while True:
                    try:
                        ev = await asyncio.wait_for(q.get(), timeout=20)
                        yield "data: %s\n\n" % json.dumps(ev, ensure_ascii=False)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                state.events.unsubscribe(q)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.post("/api/mode", response_model=ModeResult)
    def api_mode(body: ModeBody):
        try:
            mode = state.set_mode(body.mode)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        engine.set_mode(mode)
        return {"mode": mode, "takeEffect": "next-connect"}

    @app.get("/api/raw", response_model=RawConfig)
    def api_raw_get():
        return state.raw_config()

    @app.post("/api/raw", response_model=RawConfig)
    def api_raw_set(body: RawBody):
        fields = {
            "host": body.host,
            "port": body.port,
            "tls": body.tls,
            "client_id": body.client_id,
            "cmd_topic": body.cmd_topic,
            "evt_topic": body.evt_topic,
        }
        state.raw_config(fields)
        # force une reconnexion du client raw si le mode raw est actif
        engine.set_raw()
        return state.raw_config()

    @app.post("/api/send", response_model=SendResult)
    def api_send(body: SendBody):
        qos = body.qos if body.qos in (0, 1, 2) else 0
        return engine.inject(body.topic, body.payload, qos)

    @app.get("/api/consigne", response_model=ConsigneList)
    def api_consigne_get():
        return {"consignes": state.consignes_state()}

    @app.post("/api/consigne", response_model=ConsigneList)
    def api_consigne_post(body: ConsigneBody):
        state.request_consigne(body.zone, body.value)
        return {"ok": True, "consignes": state.consignes_state()}

    @app.post("/api/disconnect", response_model=DisconnectResult)
    def api_disconnect():
        return engine.disconnect()

    @app.post("/api/clear", response_model=OkResult)
    def api_clear():
        state.events.clear()
        return {"ok": True}

    # --- Historisation des valeurs (SQLite) ---
    def _history():
        h = getattr(state, "history", None)
        if h is None:
            raise HTTPException(status_code=503, detail="historique non activé")
        return h

    @app.get("/api/history/keys")
    def api_history_keys():
        h = _history()
        return {"keys": h.keys()}

    @app.get("/api/history/series")
    def api_history_series(
        key: str,
        start: float | None = None,
        end: float | None = None,
        bucket: float | None = None,
    ):
        h = _history()
        if start is not None and end is not None and start >= end:
            raise HTTPException(status_code=400, detail="start doit être inférieur à end")
        if bucket is not None and bucket <= 0:
            raise HTTPException(status_code=400, detail="bucket doit être supérieur à 0")
        return {"key": key, "samples": h.series(key, start=start, end=end, bucket=bucket)}

    @app.get("/api/history/table")
    def api_history_table(
        start: float | None = None,
        end: float | None = None,
        limit: int = 500,
        offset: int = 0,
    ):
        h = _history()
        if start is not None and end is not None and start >= end:
            raise HTTPException(status_code=400, detail="start doit être inférieur à end")
        return h.table(start=start, end=end, limit=limit, offset=offset)

    # --- Injection de test (E2E) : pousse un message synthetique dans le bus SSE
    # sans avoir besoin d'une box connectee. Utilise uniquement par les tests E2E.
    class _TestInjectBody(BaseModel):
        topic: str = "test/msg"
        payload: str = '{"test":true}'
        qos: int = 0

    @app.post("/api/test/inject", response_model=OkResult)
    def api_test_inject(body: _TestInjectBody = _TestInjectBody()):
        state.events.publish({
            "kind": "message",
            "ts": _iso(),
            "direction": "in",
            "type": "PUBLISH",
            "mode": state.mode,
            "topic": body.topic,
            "payload": body.payload,
            "qos": body.qos,
            "injected": True,
        })
        # Simule une vraie telemetrie : alimente aussi l'historique (E2E).
        h = getattr(state, "history", None)
        if h is not None:
            h.record_telemetry(body.payload)
        return {"ok": True}

    # --- Rejeu de l'API Aldes pour l'integration HA "saniho-ha" ---

    @app.post("/oauth2/token")
    async def aldes_token(request: Request):
        raw = await request.body()
        try:
            form = urllib.parse.parse_qs(raw.decode("utf-8", errors="replace"))
        except Exception:
            form = {}
        username = (form.get("username") or [""])[0].strip()
        password = (form.get("password") or [""])[0].strip()
        if not username or not password:
            return JSONResponse(status_code=400, content={"error": "invalid_grant"})
        state.events.publish({
            "kind": "status", "ts": _iso(), "note": "authentification Aldes (token emis)",
            "username": username,
        })
        return make_token(username=username)

    @app.get("/aldesoc/v5/users/me/products")
    def aldes_products():
        return build_products(state)

    @app.patch("/aldesoc/v5/users/me/products/{modem}/updateThermostats")
    async def aldes_update_thermostats(modem: str, request: Request):
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "corps JSON invalide"})
        state.events.publish({
            "kind": "message", "type": "ALDES_WRITE",
            "topic": "devices/%s/messages/devicebound" % modem,
            "payload": json.dumps(body, ensure_ascii=False),
            "note": "consigne thermostat recue (non renvoyee a la box)",
        })
        return {"success": True, "modem": modem, "thermostats": body}

    @app.post("/aldesoc/v5/users/me/products/{modem}/commands")
    async def aldes_commands(modem: str, request: Request):
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "corps JSON invalide"})
        state.events.publish({
            "kind": "message", "type": "ALDES_WRITE",
            "topic": "devices/%s/messages/devicebound" % modem,
            "payload": json.dumps(body, ensure_ascii=False),
            "note": "commande recue (non renvoyee a la box)",
        })
        return {"success": True, "modem": modem, "command": body}

    # --- SPA (doit etre declare apres /api/*) ---
    def _build_index():
        return os.path.join(web_dir, "index.html")

    @app.get("/")
    def spa_index():
        idx = _build_index()
        if os.path.isfile(idx):
            return FileResponse(idx)
        return JSONResponse({"msg": "frontend non construit", "build": "cd web && npm run build"})

    @app.get("/favicon.ico")
    def favicon():
        return Response(status_code=204)

    @app.get("/{rest:path}")
    def spa_fallback(rest: str):
        if rest.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": "not found"})
        full = os.path.join(web_dir, rest)
        if os.path.isfile(full):
            return FileResponse(full)
        idx = _build_index()
        if os.path.isfile(idx):
            return FileResponse(idx)
        return JSONResponse({"error": "not found"}, status_code=404)

    return app