"""Rejeu de l'API Aldes (aldesiotsuite.azurewebsites.net) pour l'integration
Home Assistant "saniho-ha" (custom_components/aldes).

Le bridge capte les telemetries reelles que la box T.ONE publie sur le
broker MQTT (vues dans les events boxward), puis les expose sous le format
exact consomme par l'integration HA :
    GET  /aldesoc/v5/users/me/products            -> liste de products
    PATCH /aldesoc/v5/users/me/products/{modem}/updateThermostats
    POST  /aldesoc/v5/users/me/products/{modem}/commands

Mapping de la telemetrie brute (payload PUBLISH boxward) vers le product :
    modemid     -> product["modem"]
    productid   -> product["serial_number"]  (ex: "ABCDEF123456_TONE")
    MT0..MT9    -> thermostats CurrentTemperature
    UsC0..UsC9  -> thermostats TemperatureSet
    UAM (0..8)  -> indicator.current_air_mode ("A".."I", codes declares par le profil)
    UDM (0..2)  -> indicator.current_water_mode ("L"/"M"/"N")
    NED         -> indicator.qte_eau_chaude (%)
    NpiH        -> indicator.settings.people (index HomeComposition, 0..4)
    dt          -> lastUpdatedDate / lastUpdatedAt
    Dvac/Fvac   -> indicator.date_debut_vac / date_fin_vac (epoch, 0 = off)

Ces noms sont ceux par defaut : le profil (bloc telemetry de profiles/*.yaml)
peut les renommer, cf. device_profile.telemetry_field.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from .device_profile import (
    DEFAULT_AIR_MODE_CODES,
    DEFAULT_WATER_MODE_CODES,
    air_mode_code,
    telemetry_field,
    telemetry_key_for,
    water_mode_code,
)
from .utils import parse_json_payload

_log = logging.getLogger("aldes-telemetry")

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

# La box T.ONE envoie dt / Dvac / Fvac comme l'heure de SON cadran (fuseau local,
# Europe/Paris par defaut : +02:00 l'ete, +01:00 l'hiver) mais sous forme d'un
# epoch "naif" lu comme UTC. On les reinterprete dans le fuseau de la box
# (configurable via ALDES_BOX_TZ) avant de fournir l'ISO UTC, sinon l'horodatage
# affiche pointe ~2 h dans le futur. Sans tzdata, on retombe sur l'epoch brut.
_BOX_TZ_NAME = os.environ.get("ALDES_BOX_TZ", "Europe/Paris")
_BOX_TZ = None
if ZoneInfo is not None:
    try:
        _BOX_TZ = ZoneInfo(_BOX_TZ_NAME)
    except Exception:
        _BOX_TZ = None

# --- Types de produit T.ONE connus (cles du mapping des integrations HA) ---
FRIENDLY_NAMES = {
    "TONE_AIR": "T.One\u00ae AIR",
    "TONE_AQUA_AIR": "T.One\u00ae AquaAIR",
}

# Modes air tels qu'ordonnes par l'app (TOneMode): index = valeur UAM.
# A=Off, F=Air Confort (labels dans profiles/tone-aquaair.yaml)
AIR_MODES = DEFAULT_AIR_MODE_CODES
# Modes eau chaude sanitaire (index = valeur UDM).
WATER_MODES = DEFAULT_WATER_MODE_CODES

# people = index de l'enum HomeComposition (TWO=0..SIX_AND_MORE=4),
# l'integration HA affiche people + 2 pour retrouver le nombre reel.
_HOME_COMPOSITION_MAX = 5  # nombre de valeurs de l'enum


def capture_telemetry(state, payload):
    """Capture un payload PUBLISH boxward s'il s'agit d'une telemetrie T.ONE.

    Fusionne les champs dans state.telemetry[productid] pour reconstruire
    une vue complete d'un product (les telemetries arrivent en plusieurs
    messages : temperatures, settings, mode...).
    """
    data = parse_json_payload(payload)
    if data is None:
        _log.debug("capture_telemetry: payload non reconnu (pas du JSON?), len=%d", len(payload) if payload else 0)
        return
    profile = getattr(state, "profile", None)
    pid = (
        data.get(telemetry_key_for(profile, "product.serial_number", "productid"))
        or data.get(telemetry_key_for(profile, "product.modem", "modemid"))
    )
    if not pid:
        _log.debug("capture_telemetry: pid manquant, keys=%s", list(data.keys()))
        return
    # Log les champs temperature/consigne pour debug
    temp_prefix = telemetry_field(profile, "zone_temp_prefix", "MT")
    setpoint_prefix = telemetry_field(profile, "zone_setpoint_prefix", "UsC")
    temp_keys = [k for k in data if k.startswith(temp_prefix) or k.startswith(setpoint_prefix)]
    if temp_keys:
        _log.info("capture_telemetry: pid=%s temp/consigne: %s", pid, {k: data[k] for k in temp_keys})
    # La fusion des champs + horodatage de mise a jour + persistance vivent
    # dans AppState.store_telemetry (sous le verrou, ecriture atomique).
    state.store_telemetry(pid, data)


def _epoch_to_iso(value):
    """Epoch "cadran box" (Europe/Paris par defaut) -> ISO UTC, ou None.

    La valeur est l'heure locale affichee par la box (naive). Pour retrouver
    le vrai instant, on lui attache le fuseau de la box puis on convertit en UTC.
    """
    if not value:
        return None
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    utc_wall = datetime.fromtimestamp(ts, tz=timezone.utc)
    if _BOX_TZ is None:
        return utc_wall.isoformat()
    naive = utc_wall.replace(tzinfo=None)
    return naive.replace(tzinfo=_BOX_TZ).astimezone(timezone.utc).isoformat()


def _utc_iso(value):
    """Epoch UTC reel (horodatage cote serveur) -> ISO UTC, ou None."""
    if not value:
        return None
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _num(value, default=None):
    try:
        f = float(value)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return default


def _derive_reference(telemetry, profile=None):
    """reference du product : la box possede de l'ECS (hot_water/water mode) ->
    AquaAIR, sinon TONE_AIR."""
    fields = (
        telemetry_field(profile, "hot_water_field", "NED"),
        telemetry_field(profile, "water_mode_field", "UDM"),
    )
    if any(k in telemetry for k in fields):
        return "TONE_AQUA_AIR"
    return "TONE_AIR"


def build_thermostats(telemetry, profile=None):
    """Construit la liste des thermostats depuis <temp_prefix>x/<setpoint_prefix>x.

    Un thermostat est actif si sa temperature mesuree est non nulle.
    L'id (ThermostatId) est l'index de zone, stable entre 2 appels.
    """
    temp_prefix = telemetry_field(profile, "zone_temp_prefix", "MT")
    setpoint_prefix = telemetry_field(profile, "zone_setpoint_prefix", "UsC")
    zone_count = int(telemetry_field(profile, "zone_count", 10))
    thermostats = []
    for i in range(zone_count):
        measured = _num(telemetry.get("%s%d" % (temp_prefix, i)))
        if measured is None or measured <= 0:
            continue
        setpoint = _num(telemetry.get("%s%d" % (setpoint_prefix, i)))
        thermostats.append({
            "ThermostatId": str(i),
            "thermostatId": str(i),
            "Name": "Zone %d" % (i + 1),
            "CurrentTemperature": round(measured, 1),
            "CurrentHumidity": None,
            "TemperatureSet": round(setpoint, 1) if setpoint else None,
        })
    return thermostats


def build_ventilation(telemetry):
    """Construit les donnees de ventilation depuis la telemetrie.

    Renvoie un dict avec les cles ou None si aucune donnee n'est presente.
    Les debits (Dno, Dma, Dint, DLN, DPLe, DmCO) sont divises par 10
    car le box Aldes les renvoie en dixieme de m3/h.
    """
    keys = ("RVeI", "Dno", "Dma", "Dint", "DLN", "DPLe", "DmCO")
    vent = {}
    for key in keys:
        val = _num(telemetry.get(key))
        if val is not None and key != "RVeI":
            val = val / 10
        if val is not None:
            vent[key.lower()] = val
    return vent if vent else None


def build_sensors(telemetry, profile):
    """Valeurs des capteurs declares dans ha_discovery.entities.sensors.

    Seules les cles effectivement presentes dans la telemetrie sont
    exposees, sous forme brute : c'est le frontend qui formate.
    Renvoie None sans profil ou quand aucun capteur n'a de valeur.
    """
    if profile is None:
        return None
    entities = profile.ha_discovery.get("entities") or {}
    values = {}
    for sensor in entities.get("sensors") or []:
        key = sensor.get("key")
        if not key or key in values:
            continue
        val = telemetry.get(key)
        if val is not None:
            values[key] = val
    return values or None


def build_product(telemetry, connected, profile=None):
    """Construit un product au format consomme par l'integration HA."""
    reference = _derive_reference(telemetry, profile)
    air_mode = air_mode_code(
        telemetry.get(telemetry_field(profile, "air_mode_field", "UAM")), profile
    )
    water_mode = water_mode_code(
        telemetry.get(telemetry_field(profile, "water_mode_field", "UDM")), profile
    )
    people = _num(telemetry.get(telemetry_field(profile, "people_field", "NpiH")))
    if people is not None:
        people = max(0, min(_HOME_COMPOSITION_MAX - 1, int(people)))
    temp_prefix = telemetry_field(profile, "zone_temp_prefix", "MT")
    temp = _num(telemetry.get("%s0" % temp_prefix))
    dt_field = telemetry_key_for(profile, "product.lastUpdatedDate", "dt")

    return {
        "modem": telemetry.get(telemetry_key_for(profile, "product.modem", "modemid")) or "N/A",
        "serial_number": telemetry.get(telemetry_key_for(profile, "product.serial_number", "productid")) or "N/A",
        "reference": reference,
        "name": FRIENDLY_NAMES.get(reference, reference),
        "type": reference,
        "isConnected": bool(connected),
        "lastUpdatedDate": _epoch_to_iso(telemetry.get(dt_field)) or "",
        "lastUpdatedAt": _epoch_to_iso(telemetry.get(dt_field)),
        "updatedAt": _utc_iso(telemetry.get("_upd_at")),
        "gpsLatitude": 0.0,
        "gpsLongitude": 0.0,
        "indicator": {
            "qte_eau_chaude": _num(telemetry.get(telemetry_field(profile, "hot_water_field", "NED")), 0),
            "tmp_principal": temp,
            "current_air_mode": air_mode,
            "current_water_mode": water_mode,
            "date_debut_vac": _epoch_to_iso(telemetry.get(telemetry_field(profile, "vacation_start_field", "Dvac"))),
            "date_fin_vac": _epoch_to_iso(telemetry.get(telemetry_field(profile, "vacation_end_field", "Fvac"))),
            "hors_gel": air_mode == "H",
            "antilegionelles": str(telemetry.get("AntiL", "")) not in ("0", "", "null"),
            "settings": {
                "people": people,
            },
            "thermostats": build_thermostats(telemetry, profile),
            "ventilation": build_ventilation(telemetry),
            "sensors": build_sensors(telemetry, profile),
        },
    }


def build_products(state):
    """Liste des products exposes : une entree par telemetrie capturee.

    Sans telemetrie, renvoie un product vide (modem "N/A") pour eviter un
    crash de l'integration HA, qui itere toujours la liste.
    """
    profile = getattr(state, "profile", None)
    try:
        telemetry = dict(state.telemetry)
    except AttributeError:
        telemetry = {}
    products = [build_product(data, state.connected, profile) for data in telemetry.values()]
    if not products:
        products = [build_product({}, state.connected, profile)]
    products.sort(key=lambda p: p["serial_number"])
    return products


def make_token(username=None):
    """Cree un jeton OAuth2 (grant_type=password) pour le rejeu."""
    return {
        "access_token": uuid.uuid4().hex,
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "openid",
    }
