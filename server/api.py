"""API web (FastAPI) : config, etat, SSE temps reel, envoi de commandes, mode."""
import asyncio
import json
import os
import socket
import subprocess
import urllib.parse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from .aldes import build_products, make_token
from .appstate import _iso
from .device_profile import list_profiles, load_profile
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
    azure_ip: str | None = None
    consignes: dict[str, ConsigneEntry] = {}
    server_version: str = "dev"
    ui_version: str = "dev"
    history_days: int | None = None
    profile: dict | None = None


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

    # --- Profils device ---
    @app.get("/api/profiles")
    def api_profiles():
        return {"profiles": list_profiles()}

    @app.get("/api/profile")
    def api_profile():
        p = getattr(state, "profile", None)
        if p is None:
            return {"profile": None}
        return {"profile": p.to_dict()}

    class ProfileBody(BaseModel):
        profile_id: str

    @app.put("/api/profile")
    def api_profile_set(body: ProfileBody):
        p = load_profile(body.profile_id)
        if p is None:
            return JSONResponse(status_code=404, content={"error": f"profil '{body.profile_id}' introuvable"})
        state.set_profile(p)
        state.events.publish({
            "kind": "status", "ts": _iso(),
            "note": f"profil device changé : {p.id} ({p.name})",
        })
        return {"profile": p.to_dict()}

    # --- Settings (paramètres persistants) ---
    @app.get("/api/settings")
    def api_settings_get():
        cfg = state.config.get() if state.config else {}
        return {"settings": cfg}

    class SettingsBody(BaseModel):
        history_retention_days: int = None
        log_retention_max_bytes: int = None
        ha_mqtt_dry_run: bool = None

    @app.put("/api/settings")
    def api_settings_set(body: SettingsBody):
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            return JSONResponse(status_code=400, content={"error": "aucun parametre fourni"})
        if state.config is None:
            return JSONResponse(status_code=500, content={"error": "config non initialisee"})
        state.config.set(updates)
        state._purge_now()
        if "ha_mqtt_dry_run" in updates:
            ha_client = getattr(state, "_ha_client", None)
            if ha_client is not None:
                ha_client.dry_run = updates["ha_mqtt_dry_run"]
                _log.info("ha-discovery: dry_run=%s (toggle UI)", updates["ha_mqtt_dry_run"])
        state.events.publish({
            "kind": "status", "ts": _iso(),
            "note": f"settings mis a jour : {list(updates.keys())}",
        })
        return {"settings": state.config.get()}

    # --- Home Assistant MQTT Auto-Discovery ---
    @app.get("/api/ha-discovery")
    def api_ha_discovery_get():
        """Retourne la config HA discovery et l'etat de la connexion."""
        ha_client = getattr(state, "_ha_client", None)
        p = getattr(state, "profile", None)
        ha_config = p.ha_discovery if p else {}
        return {
            "enabled": ha_client is not None,
            "connected": ha_client._sock is not None if ha_client else False,
            "host": getattr(ha_client, "host", None),
            "port": getattr(ha_client, "port", None),
            "prefix": getattr(ha_client, "prefix", "aldes"),
            "config": ha_config,
        }

    # --- Diagnostic (check-up systeme) ---
    @app.get("/api/diagnostic")
    def api_diagnostic():
        checks = []

        # 1. DNS resolution DoH
        try:
            from .tls import _doh_query
            ip = _doh_query(state.real_host, timeout=5)
            checks.append({
                "id": "dns_doh",
                "label": "DNS DoH (Cloudflare)",
                "detail": f"{state.real_host} → {ip}" if ip else "Pas de réponse A record",
                "ok": ip is not None,
                "ip": ip,
            })
        except Exception as exc:
            checks.append({"id": "dns_doh", "label": "DNS DoH (Cloudflare)", "detail": str(exc), "ok": False})

        # 2. DNS systeme
        try:
            ip_sys = socket.gethostbyname(state.real_host)
            is_local = ip_sys in ("127.0.0.1", "::1", state._azure_ip)
            checks.append({
                "id": "dns_system",
                "label": "DNS systeme (dnsmasq)",
                "detail": f"{state.real_host} → {ip_sys}" + (" ⚠️ résolu vers le bridge !" if is_local else ""),
                "ok": not is_local,
                "ip": ip_sys,
                "warn": is_local,
            })
        except Exception as exc:
            checks.append({"id": "dns_system", "label": "DNS systeme (dnsmasq)", "detail": str(exc), "ok": False})

        # 3. IP Azure stockee
        azure_ip = state._azure_ip
        checks.append({
            "id": "azure_ip",
            "label": "IP Azure résolue",
            "detail": azure_ip or "Non résolue",
            "ok": azure_ip is not None,
            "ip": azure_ip,
        })

        # 4. Connectivite TCP vers Azure (port 8883)
        if azure_ip:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((azure_ip, 8883))
                sock.close()
                checks.append({
                    "id": "tcp_azure",
                    "label": f"TCP Azure ({azure_ip}:8883)",
                    "detail": "Atteignable" if result == 0 else f"Refusé (errno {result})",
                    "ok": result == 0,
                })
            except Exception as exc:
                checks.append({"id": "tcp_azure", "label": f"TCP Azure ({azure_ip}:8883)", "detail": str(exc), "ok": False})
        else:
            checks.append({"id": "tcp_azure", "label": "TCP Azure", "detail": "IP non résolue — test impossible", "ok": False})

        # 5. Listener MQTT (port interne)
        try:
            port = 18883  # port interne du bridge
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            checks.append({
                "id": "mqtt_listener",
                "label": f"Listener MQTT (:{port})",
                "detail": "En écoute" if result == 0 else "Pas en écoute",
                "ok": result == 0,
            })
        except Exception as exc:
            checks.append({"id": "mqtt_listener", "label": "Listener MQTT", "detail": str(exc), "ok": False})

        # 6. iptables PREROUTING
        try:
            out = subprocess.check_output(
                ["iptables", "-t", "nat", "-L", "PREROUTING", "-n", "--line-numbers"],
                stderr=subprocess.STDOUT, timeout=3,
            ).decode(errors="replace")
            has_8883 = "8883" in out
            rules = [l for l in out.splitlines() if "8883" in l]
            checks.append({
                "id": "iptables",
                "label": "iptables PREROUTING",
                "detail": f"{len(rules)} règle(s) REDIRECT 8883" if has_8883 else "Aucune règle 8883",
                "ok": has_8883,
                "rules": rules,
            })
        except FileNotFoundError:
            checks.append({"id": "iptables", "label": "iptables", "detail": "iptables non disponible", "ok": False, "warn": True})
        except Exception as exc:
            checks.append({"id": "iptables", "label": "iptables", "detail": str(exc), "ok": False})

        # 7. Connexion box
        with state._lock:
            box_connected = state._connected
            box_ip = state._client_id
            cloud_connected = state._cloud_since is not None
        checks.append({
            "id": "box_connected",
            "label": "Box Aldes",
            "detail": f"Connectée (client: {box_ip})" if box_connected else "Non connectée",
            "ok": box_connected,
        })

        # 8. Connexion Azure cloud
        checks.append({
            "id": "cloud_connected",
            "label": "Azure IoT Hub (cloud)",
            "detail": "Connecté" if cloud_connected else "Non connecté",
            "ok": cloud_connected,
        })

        # 9. Mode courant
        checks.append({
            "id": "mode",
            "label": "Mode actif",
            "detail": state.mode,
            "ok": state.mode in ("proxy", "bridge"),
        })

        # 9. Version
        checks.append({
            "id": "version",
            "label": "Version",
            "detail": f"Backend {state.server_version} · UI {state.ui_version}",
            "ok": True,
        })

        # 10. Broker MQTT HA (auto-detection)
        ha_mqtt = getattr(state, "_ha_mqtt_resolved", None)
        if ha_mqtt:
            source_label = {"supervisor": "Supervisor API", "cli": "CLI", "fallback": "Fallback"}.get(ha_mqtt["source"], ha_mqtt["source"])
            checks.append({
                "id": "ha_mqtt_broker",
                "label": "Broker MQTT HA",
                "detail": f"{source_label} → {ha_mqtt['host']}:{ha_mqtt['port']}",
                "ok": True,
                "host": ha_mqtt["host"],
                "port": ha_mqtt["port"],
                "source": ha_mqtt["source"],
            })
        else:
            checks.append({
                "id": "ha_mqtt_broker",
                "label": "Broker MQTT HA",
                "detail": "Désactivé (--ha-mqtt non utilisé)",
                "ok": False,
                "warn": True,
            })

        ok_count = sum(1 for c in checks if c.get("ok"))
        total = len(checks)
        return {
            "ok": ok_count == total,
            "passed": ok_count,
            "total": total,
            "checks": checks,
        }

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