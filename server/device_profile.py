"""Chargeur de profils device Aldes.

Un profil decrit un appareil Aldes (PAC, VMC, etc.) : mapping telemetrie,
modes, commandes, labels historique, et configuration UI.

Les profils sont des fichiers YAML dans le dossier profiles/.
"""
import os
import re
import yaml

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_DIR = os.path.join(APP_ROOT, "profiles")


class DeviceProfile:
    """Profil d'un appareil Aldes, charge depuis un fichier YAML."""

    def __init__(self, data, path=None):
        self._data = data
        self.path = path
        self.id = data.get("id", "unknown")
        self.name = data.get("name", self.id)
        self.description = data.get("description", "")
        self.type = data.get("type", "unknown")

    @property
    def products(self):
        return self._data.get("products", {})

    @property
    def telemetry(self):
        return self._data.get("telemetry", {})

    @property
    def air_modes(self):
        return self._data.get("air_modes", [])

    @property
    def water_modes(self):
        return self._data.get("water_modes", [])

    @property
    def commands(self):
        return self._data.get("commands", [])

    @property
    def history_labels(self):
        return self._data.get("history_labels", {})

    @property
    def ui(self):
        return self._data.get("ui", {})

    def get_air_mode_label(self, code):
        for m in self.air_modes:
            if m.get("code") == code:
                return m.get("label", code)
        return code

    def get_water_mode_label(self, code):
        for m in self.water_modes:
            if m.get("code") == code:
                return m.get("label", code)
        return code

    def get_air_mode_by_index(self, index):
        for m in self.air_modes:
            if m.get("index") == index:
                return m.get("code")
        return None

    def get_water_mode_by_index(self, index):
        for m in self.water_modes:
            if m.get("index") == index:
                return m.get("code")
        return None

    def get_quick_modes(self):
        result = []
        for qm in self.ui.get("quick_modes", []):
            field = qm.get("field", "")
            label = qm.get("label", "")
            if field == "air_modes":
                modes = self.air_modes
            elif field == "water_modes":
                modes = self.water_modes
            else:
                modes = []
            result.append({"label": label, "modes": modes})
        return result

    def resolve_reference(self, telemetry):
        for ref, cfg in self.products.items():
            required_fields = cfg.get("reference_fields", [])
            if required_fields and all(k in telemetry for k in required_fields):
                return ref
        refs = list(self.products.keys())
        return refs[-1] if refs else "UNKNOWN"

    def get_product_name(self, reference):
        cfg = self.products.get(reference, {})
        return cfg.get("name", reference)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "air_modes": self.air_modes,
            "water_modes": self.water_modes,
            "commands": self.commands,
            "ui": self.ui,
        }


def load_profile(profile_id=None, profiles_dir=None):
    """Charge un profil par son ID. Si profile_id est None, charge le premier profil disponible."""
    d = profiles_dir or PROFILES_DIR
    if not os.path.isdir(d):
        return None
    for fname in sorted(os.listdir(d)):
        if not fname.endswith((".yaml", ".yml")):
            continue
        path = os.path.join(d, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        pid = data.get("id", "")
        if profile_id is None or pid == profile_id:
            return DeviceProfile(data, path=path)
    return None


def list_profiles(profiles_dir=None):
    """Liste tous les profils disponibles (id, name, type)."""
    d = profiles_dir or PROFILES_DIR
    result = []
    if not os.path.isdir(d):
        return result
    for fname in sorted(os.listdir(d)):
        if not fname.endswith((".yaml", ".yml")):
            continue
        path = os.path.join(d, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        result.append({
            "id": data.get("id", ""),
            "name": data.get("name", ""),
            "type": data.get("type", ""),
            "file": fname,
        })
    return result
