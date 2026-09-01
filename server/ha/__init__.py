"""Mapping des modes Aldes ↔ HA, piloté par le profil device."""
from .mode_mappings import (
    ALDES_TO_HA_MODE, HA_MODE_TO_ALDES,
    ALDES_TO_HA_PRESET, HA_PRESET_TO_ALDES,
    WATER_MODE_INDEX_TO_CODE, WATER_MODE_CODE_TO_INDEX,
    ALDES_WATER_TO_HA, HA_WATER_TO_ALDES,
    get_zone_count, get_min_max_temp, get_temp_step, get_icon,
    profile_mode_labels, profile_code_for_label, profile_label_for_code,
    get_air_mode_codes, get_water_mode_codes,
    rebuild_from_profile,
)

__all__ = [
    "ALDES_TO_HA_MODE", "HA_MODE_TO_ALDES",
    "ALDES_TO_HA_PRESET", "HA_PRESET_TO_ALDES",
    "WATER_MODE_INDEX_TO_CODE", "WATER_MODE_CODE_TO_INDEX",
    "ALDES_WATER_TO_HA", "HA_WATER_TO_ALDES",
    "get_zone_count", "get_min_max_temp", "get_temp_step", "get_icon",
    "profile_mode_labels", "profile_code_for_label", "profile_label_for_code",
    "get_air_mode_codes", "get_water_mode_codes",
    "rebuild_from_profile",
]
