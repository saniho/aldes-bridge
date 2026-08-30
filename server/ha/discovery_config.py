"""Construction des configs HA auto-discovery pour une PAC Aldes."""
import json
import logging

from ..utils import safe_float
from .mode_mappings import (
    ALDES_TO_HA_PRESET, ALDES_WATER_TO_HA,
    profile_mode_labels,
)

_log = logging.getLogger("aldes-ha-discovery")


def _get_min_max(data):
    if data is None:
        return 5, 30
    air_mode = str(data.get("UAM", ""))
    is_cooling = air_mode in ("F",)
    if is_cooling:
        mi = safe_float(data.get("CMiST"))
        ma = safe_float(data.get("CMaST"))
    else:
        mi = safe_float(data.get("FMiST"))
        ma = safe_float(data.get("FMaST"))
    if mi is None:
        mi = min(
            safe_float(data.get("CMiST")) or 5,
            safe_float(data.get("FMiST")) or 5,
        )
    if ma is None:
        ma = max(
            safe_float(data.get("CMaST")) or 30,
            safe_float(data.get("FMaST")) or 30,
        )
    return int(mi), int(ma)


def detect_active_zones(data):
    if data is None:
        return []
    zones = []
    for i in range(10):
        mt = data.get(f"MT{i}")
        usc = data.get(f"UsC{i}")
        if mt is not None and usc is not None:
            zones.append(i)
    return zones


def build_discovery_config(device_id, profile, prefix="aldes", data=None,
                           previous_active_zones=None):
    configs = []
    discovery_prefix = "homeassistant"

    device_info = {
        "identifiers": [f"aldes_{device_id}"],
        "name": "Aldes T.ONE",
        "manufacturer": "Aldes",
        "model": profile.name if profile else "T.ONE AquaAIR",
    }

    min_temp, max_temp = _get_min_max(data)

    active_zones = detect_active_zones(data)
    air_programs = profile_mode_labels(profile, "air_modes", ALDES_TO_HA_PRESET)
    water_programs = profile_mode_labels(profile, "water_modes", ALDES_WATER_TO_HA)

    ha_entities = (profile.ha_discovery.get("entities", {}) if profile else {}) or {}
    climate_entities = ha_entities.get("climate", []) or []
    temp_step = climate_entities[0].get("temp_step", 1) if climate_entities else 1

    if previous_active_zones is not None:
        deactivated = set(previous_active_zones) - set(active_zones)
        for zi in deactivated:
            configs.append((f"{discovery_prefix}/climate/aldes_zone{zi}/config", ""))

    for zone_idx in active_zones:
        zone_label = f"Zone {zone_idx + 1}"

        climate_config = {
            "name": zone_label,
            "unique_id": f"aldes_{device_id}_climate_zone{zone_idx}",
            "device": device_info,
            "modes": ["off", "heat", "cool"],
            "mode_state_topic": f"{prefix}/state/mode",
            "mode_command_topic": f"{prefix}/set/mode",
            "temperature_state_topic": f"{prefix}/state/zone{zone_idx}/consigne",
            "temperature_command_topic": f"{prefix}/set/zone{zone_idx}/consigne",
            "current_temperature_topic": f"{prefix}/state/zone{zone_idx}/temperature",
            "temp_unit": "C",
            "min_temp": min_temp,
            "max_temp": max_temp,
            "temp_step": temp_step,
            "precision": 0.1,
            "preset_modes": air_programs,
            "preset_mode_state_topic": f"{prefix}/state/preset",
            "preset_mode_command_topic": f"{prefix}/set/preset",
            "availability_topic": f"{prefix}/state/available",
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:heat-pump",
        }
        configs.append((
            f"{discovery_prefix}/climate/aldes_zone{zone_idx}/config",
            json.dumps(climate_config, ensure_ascii=False),
        ))

    if not active_zones:
        climate_config = {
            "name": "PAC Aldes",
            "unique_id": f"aldes_{device_id}_climate",
            "device": device_info,
            "modes": ["off", "heat", "cool"],
            "mode_state_topic": f"{prefix}/state/mode",
            "mode_command_topic": f"{prefix}/set/mode",
            "temperature_state_topic": f"{prefix}/state/consigne",
            "temperature_command_topic": f"{prefix}/set/consigne",
            "current_temperature_topic": f"{prefix}/state/temperature",
            "temp_unit": "C",
            "min_temp": min_temp,
            "max_temp": max_temp,
            "temp_step": temp_step,
            "precision": 0.1,
            "preset_modes": air_programs,
            "preset_mode_state_topic": f"{prefix}/state/preset",
            "preset_mode_command_topic": f"{prefix}/set/preset",
            "availability_topic": f"{prefix}/state/available",
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:heat-pump",
        }
        configs.append((f"{discovery_prefix}/climate/aldes/config", json.dumps(climate_config, ensure_ascii=False)))

    outdoor_config = {
        "name": "PAC Aldes Extérieur",
        "unique_id": f"aldes_{device_id}_outdoor_temp",
        "state_topic": f"{prefix}/state/sensor/Text",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
        "device": {"identifiers": [f"aldes_{device_id}"]},
        "icon": "mdi:thermometer",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/sensor/outdoor_temp/config", json.dumps(outdoor_config, ensure_ascii=False)))

    indoor_config = {
        "name": "PAC Aldes Intérieur",
        "unique_id": f"aldes_{device_id}_indoor_temp",
        "state_topic": f"{prefix}/state/sensor/MT0",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
        "device": {"identifiers": [f"aldes_{device_id}"]},
        "icon": "mdi:thermometer",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/sensor/indoor_temp/config", json.dumps(indoor_config, ensure_ascii=False)))

    mode_config = {
        "name": "PAC Aldes Mode Air",
        "unique_id": f"aldes_{device_id}_air_mode",
        "state_topic": f"{prefix}/state/sensor/UAM",
        "device": {"identifiers": [f"aldes_{device_id}"]},
        "icon": "mdi:fog",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/sensor/air_mode/config", json.dumps(mode_config, ensure_ascii=False)))

    compressor_config = {
        "name": "PAC Aldes Compresseur",
        "unique_id": f"aldes_{device_id}_compressor",
        "state_topic": f"{prefix}/state/sensor/MfAc",
        "payload_on": "1",
        "payload_off": "0",
        "device_class": "running",
        "device": {"identifiers": [f"aldes_{device_id}"]},
        "icon": "mdi:cog",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/binary_sensor/compressor/config", json.dumps(compressor_config, ensure_ascii=False)))

    ecs_config = {
        "name": "PAC Aldes Eau Chaude",
        "unique_id": f"aldes_{device_id}_ecs_mode",
        "state_topic": f"{prefix}/state/ecs",
        "command_topic": f"{prefix}/set/ecs",
        "options": water_programs,
        "device": {"identifiers": [f"aldes_{device_id}"]},
        "icon": "mdi:water-boiler",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/select/ecs_mode/config", json.dumps(ecs_config, ensure_ascii=False)))

    vacation_start_config = {
        "name": "PAC Aldes Vacances Début",
        "unique_id": f"aldes_{device_id}_vacation_start",
        "state_topic": f"{prefix}/state/vacation_start",
        "command_topic": f"{prefix}/set/vacation_start",
        "device": {"identifiers": [f"aldes_{device_id}"]},
        "icon": "mdi:calendar-start",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/date/vacation_start/config", json.dumps(vacation_start_config, ensure_ascii=False)))

    vacation_end_config = {
        "name": "PAC Aldes Vacances Fin",
        "unique_id": f"aldes_{device_id}_vacation_end",
        "state_topic": f"{prefix}/state/vacation_end",
        "command_topic": f"{prefix}/set/vacation_end",
        "device": {"identifiers": [f"aldes_{device_id}"]},
        "icon": "mdi:calendar-end",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/date/vacation_end/config", json.dumps(vacation_end_config, ensure_ascii=False)))

    vacation_enable_config = {
        "name": "PAC Aldes Vacances",
        "unique_id": f"aldes_{device_id}_vacation_enable",
        "state_topic": f"{prefix}/state/vacation_enable",
        "command_topic": f"{prefix}/set/vacation_enable",
        "payload_on": "on",
        "payload_off": "off",
        "device": {"identifiers": [f"aldes_{device_id}"]},
        "icon": "mdi:beach",
        "availability_topic": f"{prefix}/state/available",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    configs.append((f"{discovery_prefix}/switch/vacation_enable/config", json.dumps(vacation_enable_config, ensure_ascii=False)))

    return configs
