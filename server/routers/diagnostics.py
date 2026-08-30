"""Route diagnostic (check-up systeme)."""
from fastapi import APIRouter, Request

from ..diagnostic import run_diagnostic

router = APIRouter(prefix="/api", tags=["diagnostics"])


def _state(request: Request):
    return request.app.extra["state"]


def _engine(request: Request):
    return request.app.extra["engine"]


@router.get("/diagnostic")
def api_diagnostic(request: Request):
    return run_diagnostic(_state(request), _engine(request))
