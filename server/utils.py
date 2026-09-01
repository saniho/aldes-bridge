"""Utilitaires partages entre les modules du serveur."""
import json
import os
from datetime import datetime, timezone


def iso():
    """Horodatage ISO local avec millisecondes."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def atomic_write_json(path, data):
    """Ecrit `data` sous forme JSON de facon atomique (tmp + os.replace).

    Ne leve jamais (persistance best-effort) et ne casse pas le runtime.
    """
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except OSError:
        pass


def read_json(path, default=None):
    """Lit un fichier JSON ; renvoie `default` si absent ou invalide."""
    if not path:
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def safe_float(value, default=None):
    """Convertit `value` en float ; renvoie `default` si impossible."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def parse_json_payload(raw):
    """Parse un payload MQTT (bytes ou str) et renvoie le dict JSON ou None.

    La box Aldes prefixe ses telemetries d'un en-tete binaire : cette
    fonction coupe tout ce qui precede le premier '{' avant de parser.
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8", errors="replace")
        except Exception:
            return None
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    pos = raw.find("{")
    if pos < 0:
        return None
    if pos > 0:
        raw = raw[pos:]
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None
