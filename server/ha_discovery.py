"""Wrapper backward-compatible : redirige vers le package server.ha.

Les modules internes ont ete refactorises dans server/ha/ :
  - mode_mappings : dictionnaires de conversion Aldes ↔ HA
  - discovery_config : construction des configs HA auto-discovery
  - broker_detection : détection du broker MQTT via Supervisor
  - client : HADiscoveryClient

Ce fichier maintient la compatibilité avec les imports existants
(e.g. tests) en re-exportsant les symboles depuis les nouveaux modules.
"""
from .ha.mode_mappings import (
    ALDES_TO_HA_MODE,
    HA_MODE_TO_ALDES,
    ALDES_TO_HA_PRESET,
    HA_PRESET_TO_ALDES,
    WATER_MODE_INDEX_TO_CODE,
    WATER_MODE_CODE_TO_INDEX,
    ALDES_WATER_TO_HA,
    HA_WATER_TO_ALDES,
    get_zone_count,
    get_min_max_temp,
    get_temp_step,
    get_icon,
    profile_mode_labels,
    profile_code_for_label,
    profile_label_for_code,
    rebuild_from_profile,
)
from .ha.discovery_config import (
    build_discovery_config as _build_discovery_config,
    detect_active_zones,
)
from .ha.broker_detection import detect_mqtt_broker
from .ha.client import HADiscoveryClient

__all__ = [
    "HADiscoveryClient",
    "detect_mqtt_broker",
    "ALDES_TO_HA_MODE",
    "HA_MODE_TO_ALDES",
    "ALDES_TO_HA_PRESET",
    "HA_PRESET_TO_ALDES",
    "ALDES_WATER_TO_HA",
    "HA_WATER_TO_ALDES",
    "_build_discovery_config",
    "detect_active_zones",
    "rebuild_from_profile",
]
