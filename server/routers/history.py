"""Routes historisation des valeurs (SQLite)."""
from fastapi import APIRouter, HTTPException, Request

from . import get_state

router = APIRouter(prefix="/api/history", tags=["history"])


def _history(request: Request):
    h = getattr(get_state(request), "history", None)
    if h is None:
        raise HTTPException(status_code=503, detail="historique non activé")
    return h


@router.get("/keys")
def api_history_keys(request: Request):
    h = _history(request)
    return {"keys": h.keys()}


@router.get("/series")
def api_history_series(
    request: Request,
    key: str,
    start: float | None = None,
    end: float | None = None,
    bucket: float | None = None,
):
    h = _history(request)
    if start is not None and end is not None and start >= end:
        raise HTTPException(status_code=400, detail="start doit être inférieur à end")
    if bucket is not None and bucket <= 0:
        raise HTTPException(status_code=400, detail="bucket doit être supérieur à 0")
    return {"key": key, "samples": h.series(key, start=start, end=end, bucket=bucket)}


@router.get("/table")
def api_history_table(
    request: Request,
    start: float | None = None,
    end: float | None = None,
    limit: int = 500,
    offset: int = 0,
):
    h = _history(request)
    if start is not None and end is not None and start >= end:
        raise HTTPException(status_code=400, detail="start doit être inférieur à end")
    return h.table(start=start, end=end, limit=limit, offset=offset)
