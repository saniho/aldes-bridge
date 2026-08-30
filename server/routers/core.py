"""Routes core : config, state, logs, SSE, mode, raw, send, consigne, disconnect, clear."""
import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ..utils import iso
from .schemas import (
    ConfigSnapshot, StateSnapshot, LogPage, ModeBody, ModeResult,
    RawBody, RawConfig, SendBody, SendResult,
    ConsigneBody, ConsigneList, OkResult, DisconnectResult,
)

_log = logging.getLogger("aldes-api")

router = APIRouter(prefix="/api", tags=["core"])


def _state(request: Request):
    return request.app.extra["state"]


def _engine(request: Request):
    return request.app.extra["engine"]


@router.get("/config", response_model=ConfigSnapshot)
def api_config(request: Request):
    return _state(request).snapshot()


@router.get("/state", response_model=StateSnapshot)
def api_state(request: Request):
    st = _state(request)
    return {"config": st.snapshot(), "messages": st.events.snapshot()}


@router.get("/logs", response_model=LogPage)
def api_logs(request: Request, limit: int = 200, offset: int = 0):
    st = _state(request)
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    log = st.events.log
    if log is None:
        return {"total": 0, "limit": limit, "offset": offset, "events": []}
    events = log.tail(limit, offset)
    return {
        "total": log.total(),
        "limit": limit,
        "offset": offset,
        "events": events,
    }


@router.get("/events")
async def api_events(request: Request):
    st = _state(request)
    q = st.events.subscribe()

    async def gen():
        try:
            snap = {
                "kind": "snapshot",
                "config": st.snapshot(),
                "messages": st.events.snapshot(),
            }
            yield "data: %s\n\n" % json.dumps(snap, ensure_ascii=False)
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=20)
                    yield "data: %s\n\n" % json.dumps(ev, ensure_ascii=False)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            st.events.unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/mode", response_model=ModeResult)
def api_mode(request: Request, body: ModeBody):
    st = _state(request)
    eng = _engine(request)
    try:
        mode = st.set_mode(body.mode)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    eng.set_mode(mode)
    return {"mode": mode, "takeEffect": "next-connect"}


@router.get("/raw", response_model=RawConfig)
def api_raw_get(request: Request):
    return _state(request).raw_config()


@router.post("/raw", response_model=RawConfig)
def api_raw_set(request: Request, body: RawBody):
    st = _state(request)
    eng = _engine(request)
    fields = {
        "host": body.host,
        "port": body.port,
        "tls": body.tls,
        "client_id": body.client_id,
        "cmd_topic": body.cmd_topic,
        "evt_topic": body.evt_topic,
    }
    st.raw_config(fields)
    eng.set_raw()
    return st.raw_config()


@router.post("/send", response_model=SendResult)
def api_send(request: Request, body: SendBody):
    eng = _engine(request)
    qos = body.qos if body.qos in (0, 1, 2) else 0
    return eng.inject(body.topic, body.payload, qos)


@router.get("/consigne", response_model=ConsigneList)
def api_consigne_get(request: Request):
    return {"consignes": _state(request).consignes_state()}


@router.post("/consigne", response_model=ConsigneList)
def api_consigne_post(request: Request, body: ConsigneBody):
    st = _state(request)
    st.request_consigne(body.zone, body.value)
    return {"ok": True, "consignes": st.consignes_state()}


@router.post("/disconnect", response_model=DisconnectResult)
def api_disconnect(request: Request):
    return _engine(request).disconnect()


@router.post("/clear", response_model=OkResult)
def api_clear(request: Request):
    _state(request).events.clear()
    return {"ok": True}


class _TestInjectBody(BaseModel):
    topic: str = "test/msg"
    payload: str = '{"test":true}'
    qos: int = 0


@router.post("/test/inject", response_model=OkResult)
def api_test_inject(request: Request, body: _TestInjectBody = _TestInjectBody()):
    st = _state(request)
    st.events.publish({
        "kind": "message",
        "ts": iso(),
        "direction": "in",
        "type": "PUBLISH",
        "mode": st.mode,
        "topic": body.topic,
        "payload": body.payload,
        "qos": body.qos,
        "injected": True,
    })
    h = getattr(st, "history", None)
    if h is not None:
        h.record_telemetry(body.payload)
    return {"ok": True}
