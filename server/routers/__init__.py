"""Routers FastAPI pour l'API web."""
from starlette.requests import Request


def get_state(request: Request):
    """Extrait l'AppState depuis la requete FastAPI."""
    return request.app.extra["state"]


def get_engine(request: Request):
    """Extrait l'Engine depuis la requete FastAPI."""
    return request.app.extra["engine"]
