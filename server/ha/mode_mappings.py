"""Mapping des modes Aldes ↔ HA, piloté par le profil device.

Ce module fournit les dictionnaires de conversion entre les codes Aldes
(circuits A-I pour l'air, L-N pour l'eau) et les modes/presets Home Assistant,
en se basant sur le profil YAML quand disponible, avec fallback sur des
valeurs par défaut.
"""

# ──────────────────────────────────────────────────────────────────
# Fallback hardcodé (utilisé quand aucun profil n'est chargé)
# ──────────────────────────────────────────────────────────────────
_FALLBACK_ALDES_TO_HA_MODE = {
    "A": "off", "B": "heat", "C": "heat", "D": "heat", "E": "heat",
    "F": "cool", "G": "cool", "H": "cool", "I": "cool",
}

_FALLBACK_HA_MODE_TO_ALDES = {
    "off": "A", "heat": "B", "cool": "F",
}

_FALLBACK_AIR_MODES = [
    {"index": 0, "code": "A", "label": "Off"},
    {"index": 1, "code": "B", "label": "Confort"},
    {"index": 2, "code": "C", "label": "Éco"},
    {"index": 3, "code": "D", "label": "Programme A"},
    {"index": 4, "code": "E", "label": "Programme B"},
    {"index": 5, "code": "F", "label": "Confort"},
    {"index": 6, "code": "G", "label": "Boost"},
    {"index": 7, "code": "H", "label": "Programme C"},
    {"index": 8, "code": "I", "label": "Programme D"},
]

_FALLBACK_WATER_MODES = [
    {"index": 0, "code": "L", "label": "Arrêt"},
    {"index": 1, "code": "M", "label": "Marche"},
    {"index": 2, "code": "N", "label": "Boost"},
]

_DEFAULT_MIN_TEMP = 5
_DEFAULT_MAX_TEMP = 30
_MAX_ZONES = 10


# ──────────────────────────────────────────────────────────────────
# Dictionnaires construits dynamiquement depuis le profil
# ──────────────────────────────────────────────────────────────────
def _build_aldes_to_ha_mode(profile):
    """Aldes code → HA HVAC mode (depuis profile.ha_discovery.mode_mapping)."""
    if profile:
        hd = profile.ha_discovery if isinstance(profile.ha_discovery, dict) else {}
        mapping = hd.get("mode_mapping")
        if mapping and isinstance(mapping, dict):
            return dict(mapping)
    return dict(_FALLBACK_ALDES_TO_HA_MODE)


def _build_ha_mode_to_aldes(profile):
    """HA HVAC mode → Aldes code (reverse)."""
    direct = _build_aldes_to_ha_mode(profile)
    return {ha: aldes for aldes, ha in direct.items()}


def _build_aldes_to_ha_preset(profile):
    """Aldes code → label preset HA (depuis profile.air_modes_clim + air_modes_heat)."""
    all_modes = []
    for field in ["air_modes_clim", "air_modes_heat"]:
        modes = getattr(profile, field, None) if profile else None
        if modes:
            all_modes.extend(modes)
    if all_modes:
        return {m["code"]: m["label"] for m in all_modes}
    return {m["code"]: m["label"] for m in _FALLBACK_AIR_MODES}


def _build_ha_preset_to_aldes(profile):
    """Label preset HA → Aldes code (reverse)."""
    direct = _build_aldes_to_ha_preset(profile)
    return {label: code for code, label in direct.items()}


def _build_water_mode_dicts(profile):
    """Aldes code → HA label eau chaude, et reverse."""
    modes = getattr(profile, "water_modes", None) if profile else None
    if modes:
        aldes_to_ha = {m["code"]: m["label"] for m in modes}
    else:
        aldes_to_ha = {m["code"]: m["label"] for m in _FALLBACK_WATER_MODES}
    ha_to_aldes = {label: code for code, label in aldes_to_ha.items()}
    return aldes_to_ha, ha_to_aldes


def _build_water_index_dicts(profile):
    """Index → code eau chaude, et reverse."""
    modes = getattr(profile, "water_modes", None) if profile else None
    if modes:
        index_to_code = {m["index"]: m["code"] for m in modes}
    else:
        index_to_code = {m["index"]: m["code"] for m in _FALLBACK_WATER_MODES}
    code_to_index = {code: idx for idx, code in index_to_code.items()}
    return index_to_code, code_to_index


# ──────────────────────────────────────────────────────────────────
# Dictionnaires publics (reconstruits quand un profil est chargé)
# Ces dicts sont maintenus pour la compatibilité avec le code existant
# qui importe depuis ha_discovery / ha/mode_mappings.
# ──────────────────────────────────────────────────────────────────
ALDES_TO_HA_MODE = dict(_FALLBACK_ALDES_TO_HA_MODE)
HA_MODE_TO_ALDES = dict(_FALLBACK_HA_MODE_TO_ALDES)
ALDES_TO_HA_PRESET = {m["code"]: m["label"] for m in _FALLBACK_AIR_MODES}
HA_PRESET_TO_ALDES = {v: k for k, v in ALDES_TO_HA_PRESET.items()}
WATER_MODE_INDEX_TO_CODE, WATER_MODE_CODE_TO_INDEX = _build_water_index_dicts(None)
ALDES_WATER_TO_HA, HA_WATER_TO_ALDES = _build_water_mode_dicts(None)


def rebuild_from_profile(profile):
    """Reconstruit les dictionnaires publics depuis un profil charge.

    A appeler apres le chargement du profil pour que les mappings
    refleterent les valeurs du fichier YAML.
    """
    global ALDES_TO_HA_MODE, HA_MODE_TO_ALDES
    global ALDES_TO_HA_PRESET, HA_PRESET_TO_ALDES
    global WATER_MODE_INDEX_TO_CODE, WATER_MODE_CODE_TO_INDEX
    global ALDES_WATER_TO_HA, HA_WATER_TO_ALDES

    ALDES_TO_HA_MODE = _build_aldes_to_ha_mode(profile)
    HA_MODE_TO_ALDES = _build_ha_mode_to_aldes(profile)
    ALDES_TO_HA_PRESET = _build_aldes_to_ha_preset(profile)
    HA_PRESET_TO_ALDES = _build_ha_preset_to_aldes(profile)
    WATER_MODE_INDEX_TO_CODE, WATER_MODE_CODE_TO_INDEX = _build_water_index_dicts(profile)
    ALDES_WATER_TO_HA, HA_WATER_TO_ALDES = _build_water_mode_dicts(profile)


# ──────────────────────────────────────────────────────────────────
# Helpers pur profil
# ──────────────────────────────────────────────────────────────────
def get_zone_count(profile):
    """Nombre de zones supportées (défini dans le profil, max 10)."""
    if profile:
        try:
            return min(int(profile.telemetry.get("zone_count", _MAX_ZONES)), _MAX_ZONES)
        except (TypeError, ValueError):
            pass
    return _MAX_ZONES


def get_min_max_temp(profile):
    """Retourne (min_temp, max_temp) depuis le profil ou fallback."""
    if profile:
        hd = profile.ha_discovery if isinstance(profile.ha_discovery, dict) else {}
        entities = hd.get("entities", {}) or {}
        climate = entities.get("climate", []) or []
        if climate:
            return int(climate[0].get("min_temp", _DEFAULT_MIN_TEMP)), int(climate[0].get("max_temp", _DEFAULT_MAX_TEMP))
    return _DEFAULT_MIN_TEMP, _DEFAULT_MAX_TEMP


def get_temp_step(profile):
    """Pas de température depuis le profil ou fallback 1."""
    if profile:
        hd = profile.ha_discovery if isinstance(profile.ha_discovery, dict) else {}
        entities = hd.get("entities", {}) or {}
        climate = entities.get("climate", []) or []
        if climate:
            return climate[0].get("temp_step", 1)
    return 1


def get_icon(profile, entity_key, default):
    """Icone depuis le profil ou fallback."""
    if profile:
        hd = profile.ha_discovery if isinstance(profile.ha_discovery, dict) else {}
        entities = hd.get("entities", {}) or {}
        for group in ("sensors", "select", "date", "switch"):
            items = entities.get(group, []) or []
            for item in items:
                item_id = item.get("key") or item.get("id")
                if item_id == entity_key:
                    return item.get("icon", default)
    return default


def profile_mode_labels(profile, field, fallback):
    """Retourne les labels des modes depuis le profil ou le fallback dict."""
    modes = getattr(profile, field, None) if profile else None
    if modes:
        return [mode["label"] for mode in modes]
    return list(fallback.values()) if isinstance(fallback, dict) else list(fallback)


def profile_code_for_label(profile, field, label, fallback):
    """Lookup inverse : label → code via profil ou fallback dict."""
    normalized = label.casefold()
    fields = [field] if isinstance(field, str) else field
    for f in fields:
        modes = getattr(profile, f, None) if profile else None
        if modes:
            for mode in modes:
                if mode.get("label", "").casefold() == normalized:
                    return mode.get("code")
    if isinstance(fallback, dict):
        for candidate, code in fallback.items():
            if candidate.casefold() == normalized:
                return code
    return None


def profile_label_for_code(profile, field, code, fallback):
    """Code → label via profil ou fallback dict."""
    fields = [field] if isinstance(field, str) else field
    for f in fields:
        modes = getattr(profile, f, None) if profile else None
        if modes:
            for mode in modes:
                if mode.get("code") == code:
                    return mode.get("label")
    if isinstance(fallback, dict):
        return fallback.get(code)
    return None


def get_air_mode_codes(profile):
    """Retourne la liste ordonnée des codes air (A-I) depuis le profil."""
    all_modes = []
    for field in ["air_modes_clim", "air_modes_heat", "air_modes"]:
        modes = getattr(profile, field, None) if profile else None
        if modes:
            all_modes.extend(modes)
    if all_modes:
        return [m["code"] for m in sorted(all_modes, key=lambda m: m.get("index", 0))]
    return [m["code"] for m in _FALLBACK_AIR_MODES]


def get_water_mode_codes(profile):
    """Retourne la liste ordonnée des codes eau (L, M, N) depuis le profil."""
    modes = getattr(profile, "water_modes", None) if profile else None
    if modes:
        return [m["code"] for m in sorted(modes, key=lambda m: m.get("index", 0))]
    return [m["code"] for m in _FALLBACK_WATER_MODES]
