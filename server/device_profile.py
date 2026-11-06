"""Chargeur de profils device Aldes.

Un profil decrit un appareil Aldes (PAC, VMC, etc.) : mapping telemetrie,
modes, commandes, labels historique, et configuration UI.

Les profils sont des fichiers YAML dans le dossier profiles/.
"""
import os
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
    def air_modes_clim(self):
        return self._data.get("air_modes_clim", [])

    @property
    def air_modes_heat(self):
        return self._data.get("air_modes_heat", [])

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

    @property
    def ha_discovery(self):
        return self._data.get("ha_discovery", {})

    def get_air_mode_label(self, code):
        for m in self.air_modes_clim + self.air_modes_heat + self.air_modes:
            if m.get("code") == code:
                return m.get("label", code)
        return code

    def get_water_mode_label(self, code):
        for m in self.water_modes:
            if m.get("code") == code:
                return m.get("label", code)
        return code

    def get_air_mode_by_index(self, index):
        for m in self.air_modes_clim + self.air_modes_heat + self.air_modes:
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
            if field == "air_modes_clim":
                modes = self.air_modes_clim
            elif field == "air_modes_heat":
                modes = self.air_modes_heat
            elif field == "air_modes":
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
            "air_modes_clim": self.air_modes_clim,
            "air_modes_heat": self.air_modes_heat,
            "water_modes": self.water_modes,
            "commands": self.commands,
            "ui": self.ui,
            "ha_discovery": self.ha_discovery,
        }


def telemetry_field(profile, name, default=None):
    """Nom de champ telemetrie declare dans le profil, ou valeur par defaut.

    profile peut etre None (aucun profil charge) : le defaut est alors
    renvoye, ce qui preserve le comportement des installations existantes.
    """
    if profile is None:
        return default
    return profile.telemetry.get(name) or default


def telemetry_key_for(profile, destination, default=None):
    """Cle telemetrie qui alimente une destination du profil (ex: product.modem).

    Certaines entrees du bloc telemetry sont ecrites a l'envers (cle = champ,
    valeur = destination) : on retrouve donc le champ par sa destination.
    """
    if profile is None:
        return default
    for key, value in profile.telemetry.items():
        if value == destination:
            return key
    return default


# Codes de mode par defaut (circuits d'une PAC Aldes), utilises quand le
# profil ne declare aucun mode.
DEFAULT_AIR_MODE_CODES = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
DEFAULT_WATER_MODE_CODES = ["L", "M", "N"]


def _declared_codes(profile, fields):
    """Codes declares par le profil pour les champs de modes donnes."""
    if profile is None:
        return set()
    codes = set()
    for field in fields:
        for mode in getattr(profile, field, None) or []:
            code = mode.get("code")
            if code:
                codes.add(code)
    return codes


def air_mode_code(raw, profile=None):
    """Code air (A-I pour une PAC, V-Z pour une VMC) depuis la valeur brute.

    Un index numerique est resolu dans les modes du profil : quand le profil
    en declare, il fait foi (aucun repli sur les circuits A-I). Sans
    declaration, on retombe sur A-I. Une valeur deja textuelle n'est acceptee
    que si le profil la declare : une donnee corrompue ne devient jamais un
    code plausible.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    declared = _declared_codes(profile, ("air_modes_clim", "air_modes_heat", "air_modes"))
    try:
        index = int(float(text))
    except (TypeError, ValueError):
        known = declared or set(DEFAULT_AIR_MODE_CODES)
        code = text.upper()
        return code if code in known else None
    if declared:
        return profile.get_air_mode_by_index(index)
    if 0 <= index < len(DEFAULT_AIR_MODE_CODES):
        return DEFAULT_AIR_MODE_CODES[index]
    return None


def water_mode_code(raw, profile=None):
    """Code eau chaude (L/M/N) depuis la valeur brute, cf. air_mode_code."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    declared = _declared_codes(profile, ("water_modes",))
    try:
        index = int(float(text))
    except (TypeError, ValueError):
        known = declared or set(DEFAULT_WATER_MODE_CODES)
        code = text.upper()
        return code if code in known else None
    if declared:
        return profile.get_water_mode_by_index(index)
    if 0 <= index < len(DEFAULT_WATER_MODE_CODES):
        return DEFAULT_WATER_MODE_CODES[index]
    return None


DEFAULT_PROFILE_ID = "tone-aquaair"


def load_profile(profile_id=None, profiles_dir=None):
    """Charge un profil par son ID. Si profile_id est None, charge le premier profil disponible."""
    d = profiles_dir or PROFILES_DIR
    if profile_id is None:
        return _load_profile(DEFAULT_PROFILE_ID, d) or _load_profile(None, d)
    return _load_profile(profile_id, d)


def _load_profile(profile_id, d):
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
