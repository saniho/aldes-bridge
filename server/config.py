"""Configuration persistante de l'application.

Stocke les paramètres modifiables par l'utilisateur dans logs/config.json.
Fournit des valeurs par défaut et validation basique.
"""
import json
import os
import threading

DEFAULTS = {
    "history_retention_days": 90,
    "log_retention_max_bytes": 25 * 1024 * 1024,
    "ha_mqtt_dry_run": False,
}

RANGES = {
    "history_retention_days": (1, 3650),
    "log_retention_max_bytes": (1024 * 1024, 500 * 1024 * 1024),
}


def _atomic_write(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


class ConfigStore:
    def __init__(self, path):
        self._path = os.path.abspath(path)
        self._lock = threading.Lock()
        self._data = dict(DEFAULTS)
        self._load()

    def _load(self):
        stored = _read_json(self._path)
        for k, v in stored.items():
            if k in DEFAULTS:
                self._data[k] = v

    def get(self, key=None):
        with self._lock:
            if key is None:
                return dict(self._data)
            return self._data.get(key, DEFAULTS.get(key))

    def set(self, updates):
        with self._lock:
            for k, v in updates.items():
                if k not in DEFAULTS:
                    continue
                lo, hi = RANGES.get(k, (None, None))
                if isinstance(v, (int, float)) and lo is not None:
                    v = type(DEFAULTS[k])(max(lo, min(hi, v)))
                self._data[k] = v
            self._save()
        return dict(self._data)

    def _save(self):
        _atomic_write(self._path, self._data)

    def history_retention(self):
        return self.get("history_retention_days")

    def log_retention_bytes(self):
        return self.get("log_retention_max_bytes")
