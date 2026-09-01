"""Route diagnostic (check-up systeme)."""
from fastapi import APIRouter, Request

from ..diagnostic import run_diagnostic
from . import get_state, get_engine

router = APIRouter(prefix="/api", tags=["diagnostics"])





@router.get("/diagnostic")
def api_diagnostic(request: Request):
    return run_diagnostic(get_state(request), get_engine(request))
