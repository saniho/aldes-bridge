"""API web (FastAPI) : config, etat, SSE temps reel, envoi de commandes, mode."""
import asyncio
import json
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel


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


def create_app(state, engine, web_dir):
    app = FastAPI(title="Aldes Bridge", docs_url=None, redoc_url=None)
    web_dir = os.path.abspath(web_dir)

    @app.on_event("startup")
    async def _startup():
        state.events.attach_loop(asyncio.get_running_loop())

    # --- API ---
    @app.get("/api/config")
    def api_config():
        return state.snapshot()

    @app.get("/api/state")
    def api_state():
        return {"config": state.snapshot(), "messages": state.events.snapshot()}

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

    @app.post("/api/mode")
    def api_mode(body: ModeBody):
        try:
            mode = state.set_mode(body.mode)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        engine.set_mode(mode)
        return {"mode": mode, "takeEffect": "next-connect"}

    @app.get("/api/raw")
    def api_raw_get():
        return state.raw_config()

    @app.post("/api/raw")
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

    @app.post("/api/send")
    def api_send(body: SendBody):
        qos = body.qos if body.qos in (0, 1, 2) else 0
        return engine.inject(body.topic, body.payload, qos)

    @app.post("/api/disconnect")
    def api_disconnect():
        return engine.disconnect()

    @app.post("/api/clear")
    def api_clear():
        state.events.clear()
        return {"ok": True}

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
        return JSONResponse(status_code=204, content=None)

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