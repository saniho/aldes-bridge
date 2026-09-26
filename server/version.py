"""Versions du bridge : backend (package) + UI (fichier généré au build).

La version backend vit dans ``server/__init__.py`` (``__version__``).
La version UI est écrite par le build frontend dans ``dist/version.json``
(``{"ui": "x.y.z"}``) ; on la lit à côté du dossier web servi.
"""
import json
import os

from . import __version__ as SERVER_VERSION


def read_ui_version(web_dir):
    """Version UI lue depuis ``{web_dir}/version.json``, 'dev' si absent.

    Le build Vite écrit la clé ``ui``. La clé ``version`` est acceptée en
    repli : d'anciennes images d'add-on écrivaient cette clé.
    """
    try:
        with open(os.path.join(web_dir, "version.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        v = str(data.get("ui") or data.get("version") or "dev").strip()
        return v or "dev"
    except (OSError, ValueError, AttributeError):
        return "dev"


def format_version(value, fallback="?"):
    """Version préfixée d'un seul ``v`` ('0.1.0' et 'v0.1.0' -> 'v0.1.0').

    Les valeurs non numériques ('dev', '?') sont renvoyées telles quelles.
    """
    v = str(value or "").strip()
    if not v:
        return fallback
    if v[0].isdigit():
        return f"v{v}"
    return v


def format_banner(server_version, ui_version, addon_version):
    """Ligne de démarrage : un seul préfixe ``v`` par version."""
    return (
        f"=== Aldes Bridge {format_version(server_version)} | "
        f"UI {format_version(ui_version)} | "
        f"Add-on {format_version(addon_version)} ==="
    )