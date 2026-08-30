"""Routes profils device."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..device_profile import list_profiles, load_profile
from . import get_state
from ..ha.mode_mappings import rebuild_from_profile
from ..utils import iso
from .schemas import ProfileBody

router = APIRouter(prefix="/api", tags=["profiles"])


@router.get("/profiles")
def api_profiles():
    return {"profiles": list_profiles()}


@router.get("/profile")
def api_profile(request: Request):
    p = getattr(get_state(request), "profile", None)
    if p is None:
        return {"profile": None}
    return {"profile": p.to_dict()}


@router.put("/profile")
def api_profile_set(request: Request, body: ProfileBody):
    st = get_state(request)
    p = load_profile(body.profile_id)
    if p is None:
        return JSONResponse(status_code=404, content={"error": f"profil '{body.profile_id}' introuvable"})
    st.set_profile(p)
    rebuild_from_profile(p)
    st.events.publish({
        "kind": "status", "ts": iso(),
        "note": f"profil device changé : {p.id} ({p.name})",
    })
    return {"profile": p.to_dict()}
