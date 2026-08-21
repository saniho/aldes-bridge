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
    UAM (0..8)  -> indicator.current_air_mode ("A".."I")
    UDM (0..2)  -> indicator.current_water_mode ("L"/"M"/"N")
    NED         -> indicator.qte_eau_chaude (%)
    NpiH        -> indicator.settings.people (index HomeComposition, 0..4)
    dt          -> lastUpdatedDate / lastUpdatedAt
    Dvac/Fvac   -> indicator.date_debut_vac / date_fin_vac (epoch, 0 = off)
"""
import json
import os
import uuid
from datetime import datetime, timezone

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
AIR_MODES = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
# Modes eau chaude sanitaire (index = valeur UDM).
WATER_MODES = ["L", "M", "N"]

# people = index de l'enum HomeComposition (TWO=0..SIX_AND_MORE=4),
# l'integration HA affiche people + 2 pour retrouver le nombre reel.
_HOME_COMPOSITION_MAX = 5  # nombre de valeurs de l'enum


def capture_telemetry(state, payload):
    """Capture un payload PUBLISH boxward s'il s'agit d'une telemetrie T.ONE.

    Fusionne les champs dans state.telemetry[productid] pour reconstruire
    une vue complete d'un product (les telemetries arrivent en plusieurs
    messages : temperatures, settings, mode...).
    """
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8", errors="replace")
        except Exception:
            return
    if not isinstance(payload, str):
        return
    payload = payload.strip()
    # La box prefixe chaque telemetrie d'un en-tete binaire (octet de sequence,
    # ex: \x00F). On coupe tout ce qui precede le debut du JSON.
    pos = payload.find("{")
    if pos < 0:
        return
    if pos > 0:
        payload = payload[pos:]
    try:
        data = json.loads(payload)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    pid = data.get("productid") or data.get("modemid")
    if not pid:
        return
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


def _derive_reference(telemetry):
    """reference du product : la box possede de l'ECS (UAM/UDM/NED) ->
    AquaAIR, sinon TONE_AIR."""
    if any(k in telemetry for k in ("NED", "UDM")):
        return "TONE_AQUA_AIR"
    return "TONE_AIR"


def build_thermostats(telemetry):
    """Construit la liste des thermostats depuis MTx/UsCx.

    Un thermostat est actif si sa temperature mesuree (MTx) est non nulle.
    L'id (ThermostatId) est l'index de zone, stable entre 2 appels.
    """
    thermostats = []
    for i in range(10):
        measured = _num(telemetry.get("MT%d" % i))
        if measured is None or measured <= 0:
            continue
        setpoint = _num(telemetry.get("UsC%d" % i))
        thermostats.append({
            "ThermostatId": str(i),
            "thermostatId": str(i),
            "Name": "Zone %d" % (i + 1),
            "CurrentTemperature": round(measured, 1),
            "CurrentHumidity": None,
            "TemperatureSet": round(setpoint, 1) if setpoint else None,
        })
    return thermostats


def build_product(telemetry, connected):
    """Construit un product au format consomme par l'integration HA."""
    reference = _derive_reference(telemetry)
    air_index = int(_num(telemetry.get("UAM"), -1))
    water_index = int(_num(telemetry.get("UDM"), -1))
    air_mode = AIR_MODES[air_index] if 0 <= air_index < len(AIR_MODES) else None
    water_mode = WATER_MODES[water_index] if 0 <= water_index < len(WATER_MODES) else None
    people = _num(telemetry.get("NpiH"))
    if people is not None:
        people = max(0, min(_HOME_COMPOSITION_MAX - 1, int(people) - 2))
    temp = _num(telemetry.get("MT0"))

    return {
        "modem": telemetry.get("modemid") or "N/A",
        "serial_number": telemetry.get("productid") or "N/A",
        "reference": reference,
        "name": FRIENDLY_NAMES.get(reference, reference),
        "type": reference,
        "isConnected": bool(connected),
        "lastUpdatedDate": _epoch_to_iso(telemetry.get("dt")) or "",
        "lastUpdatedAt": _epoch_to_iso(telemetry.get("dt")),
        "updatedAt": _utc_iso(telemetry.get("_upd_at")),
        "gpsLatitude": 0.0,
        "gpsLongitude": 0.0,
        "indicator": {
            "qte_eau_chaude": _num(telemetry.get("NED"), 0),
            "tmp_principal": temp,
            "current_air_mode": air_mode,
            "current_water_mode": water_mode,
            "date_debut_vac": _epoch_to_iso(telemetry.get("Dvac")),
            "date_fin_vac": _epoch_to_iso(telemetry.get("Fvac")),
            "hors_gel": air_mode == "H",
            "settings": {
                "people": people,
            },
            "thermostats": build_thermostats(telemetry),
        },
    }


def build_products(state):
    """Liste des products exposes : une entree par telemetrie capturee.

    Sans telemetrie, renvoie un product vide (modem "N/A") pour eviter un
    crash de l'integration HA, qui itere toujours la liste.
    """
    try:
        telemetry = dict(state.telemetry)
    except AttributeError:
        telemetry = {}
    products = [build_product(data, state.connected) for data in telemetry.values()]
    if not products:
        products = [build_product({}, state.connected)]
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
