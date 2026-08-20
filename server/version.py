"""Versions du bridge : backend (package) + UI (fichier généré au build).

La version backend vit dans ``server/__init__.py`` (``__version__``).
La version UI est écrite par le build frontend dans ``dist/version.json``
(``{"ui": "x.y.z"}``) ; on la lit à côté du dossier web servi.
"""
import json
import os

from . import __version__ as SERVER_VERSION


def read_ui_version(web_dir):
    """Version UI lue depuis ``{web_dir}/version.json``, 'dev' si absent."""
    try:
        with open(os.path.join(web_dir, "version.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        v = str(data.get("ui", "dev")).strip()
        return v or "dev"
    except (OSError, ValueError, AttributeError):
        return "dev"