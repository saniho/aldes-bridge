"""API web (FastAPI) : config, etat, SSE temps reel, envoi de commandes, mode.

Decoupe en routers :
  - core       : config, state, logs, SSE, mode, raw, send, consigne, disconnect, clear, test/inject
  - history    : historisation SQLite (keys, series, table)
  - aldes_compat : rejeu API Aldes (token, products, thermostats, commands)
  - profiles   : gestion des profils device
  - settings   : parametres persistants
  - ha         : Home Assistant MQTT Auto-Discovery
  - diagnostics: check-up systeme
"""
import asyncio
import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from .version import read_ui_version
from .routers import core, history, aldes_compat, profiles, settings, ha, diagnostics

_log = logging.getLogger("aldes-api")


def create_app(state, engine, web_dir):
    app = FastAPI(title="Aldes Bridge", docs_url=None, redoc_url=None)
    web_dir = os.path.abspath(web_dir)
    state.ui_version = read_ui_version(web_dir)

    # Expose state/engine aux routers via request.app.extra
    app.extra["state"] = state
    app.extra["engine"] = engine

    @app.on_event("startup")
    async def _startup():
        state.events.attach_loop(asyncio.get_running_loop())

    @app.on_event("shutdown")
    async def _shutdown():
        state.persist_telemetry()

    # --- Health endpoints (doivent etre declares AVANT les routers /api/*) ---
    @app.get("/healthz")
    def healthz():
        """Endpoint leger pour probes Kubernetes/docker-compose."""
        return Response(status_code=200)

    @app.get("/api/health")
    def api_health(request: Request):
        """Endpoint detaille pour diagnostics orchestration."""
        st = request.app.extra["state"]
        ha_client = getattr(st, "_ha_client", None)
        mqtt_connected = ha_client._sock is not None if ha_client else None
        box_connected = st.connected
        uptime = time.time() - st._start_time
        if box_connected:
            status = "ok"
        elif mqtt_connected is False:
            status = "degraded"
        else:
            status = "ok" if mqtt_connected is None else "degraded"
        return JSONResponse({
            "status": status,
            "uptime": round(uptime, 1),
            "mqtt_connected": mqtt_connected,
            "box_connected": box_connected,
        })

    # Include routers
    app.include_router(core.router)
    app.include_router(history.router)
    app.include_router(aldes_compat.router)
    app.include_router(profiles.router)
    app.include_router(settings.router)
    app.include_router(ha.router)
    app.include_router(diagnostics.router)

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
