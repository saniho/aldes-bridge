# Aldes Bridge

Pont MQTT over TLS pour intercepter, analyser **et commander** une box **Aldes Connect**
(qui remonte vers Azure IoT Hub), avec une Web UI React.

Deux modes (bascule possible à chaud depuis la Web UI, appliquée à la prochaine connexion de la box) :

- **proxy** — transparent : le pont relaie réellement la box vers `aldesiotsuite.azure-devices.net`,
  tout en affichant/sniffant chaque trame, et permet d'injecter des commandes vers la box (QoS0).
- **bridge** — faux broker : la box se connecte au pont qui joue le rôle d'Azure ; messages observés,
  commandes injectées en QoS1 ; *aucune* communication avec le vrai cloud.

Un unique listener TLS sur le port 8883 sert les deux modes ; le choix du mode est dans `AppState`

## Stack

- **Backend** : Python 3.11, FastAPI + uvicorn (API HTTP + SSE), aucune lib MQTT externe (codec maison dans `server/mqtt.py`).
- **Frontend** : React 18 + Vite + TypeScript (`web/`), construit puis servi statique par FastAPI.
- **Docker** : multi-stage (build node → runtime python), réseau host.

## Structure

```
server/
  main.py        # point d'entrée CLI (python3 -m server.main)
  engine.py      # listener TLS unique + dispatch par AppState.mode
  appstate.py    # mode, connexion, historique de trames, snapshots SSE
  bridge.py      # faux broker + injection (QoS1)
  proxy.py       # MITM vers Azure réel + injection boxward (QoS0)
  tls.py         # certificats auto-signés per-connexion, ctx permissif
  mqtt.py        # codec MQTT 3.1.1 (CONNECT/PUBLISH/SUBSCRIBE/...)
  events.py      # EventBus ring + export SSE
  api.py         # FastAPI : /api/* + SPA fallback
web/             # frontend React/Vite
tests/           # test_engine.py (bridge + proxy MITM)
Dockerfile
docker-compose.yml
```

## Démarrage

### Docker (déploiement)

```bash
docker compose up -d --build
```

- MQTT/TLS : `0.0.0.0:8883` (la box s'y connecte)
- WebUI/API : `0.0.0.0:8080`

### Sans Docker (dev)

```bash
pip install -r requirements.txt
cd web && npm install && npm run build && cd ..
python3 -m server.main --web-dir ./web/dist
```

### Développement frontend (proxy vers l'API)

```bash
python3 -m server.main --web-port 8080 --mqtt-port 8883 &
cd web && npm run dev   # http://localhost:5173, /api proxy → 8080
```

## API

| Méthode | Chemin | Description |
|---|---|---|
| GET | `/api/config` | mode actuel |
| GET | `/api/state` | config + derniers messages (snapshot) |
| GET | `/api/events` | flux SSE (snapshot initial puis messages/status temps réel) |
| POST | `/api/mode` | `{"mode":"proxy"\|"bridge"}` — effet à la prochaine connexion |
| POST | `/api/send` | `{"topic","payload","qos"}` — injecte une commande vers la box |
| POST | `/api/disconnect` | force la session (pour appliquer le mode tout de suite) |
| POST | `/api/clear` | vide l'historique affiché |
| GET | `/` | SPA (frontend construit) |

La WebUI a deux onglets : **🌊 flux** (trames MQTT en temps réel / historique) et **🌡 températures**
(vue des produits Aldes : temp. principale, ECS, modes air/ECS, table des thermostats réel/consigne,
alimentée par `/aldesoc/v5/users/me/products`, refresh 5 s).

### Rejeu de l'API Aldes (pour l'intégration Home Assistant « saniho-ha »)

Le pont réexpose les télémetries T.ONE captées sur le MQTT sous un format identique à
`aldesiotsuite-aldeswebapi.azurewebsites.net`, pour que `custom_components/aldes` puisse être
redirigé vers le pont (ex. `API_URL_BASE = "http://<pont>:8080"` dans `api.py` de l'intégration) :

| Méthode | Chemin | Description |
|---|---|---|
| POST | `/oauth2/token` | `grant_type=password` — tout identifiant/mot de passe non vide → `access_token` (Bearer) |
| GET | `/aldesoc/v5/users/me/products` | liste des produits déduits des télémetries captées |
| PATCH | `/aldesoc/v5/users/me/products/{modem}/updateThermostats` | consigne thermostat (journalisée, non renvoyée à la box) |
| POST | `/aldesoc/v5/users/me/products/{modem}/commands` | commande (journalisée, non renvoyée à la box) |

Mapping télémetrie → product (voir `server/aldes.py`) :

- `modemid` → `modem`, `productid` → `serial_number`
- `MT0..MT9` → `indicator.thermostats[].CurrentTemperature`, `UsC0..UsC9` → `TemperatureSet`
- `UAM` (0-8) → `current_air_mode` (`"A".."I"`, cf. enum TOneMode de l'app), `UDM` (0-2) → `current_water_mode` (`"L"/"M"/"N"`)
- `NED` → `qte_eau_chaude` (%), `NpiH` → `settings.people` (index de `HomeComposition`, l'intégration affiche `people + 2`)
- `dt` → `lastUpdatedDate`, `Dvac`/`Fvac` (epoch, 0 = off) → `date_debut_vac`/`date_fin_vac`.
  La box envoie ces valeurs comme l'heure de **son** cadran (Europe/Paris par défaut) :
  elles sont réinterprétées dans ce fuseau puis exposées en UTC (`lastUpdatedAt` correct).
  Fuseau configurable via `ALDES_BOX_TZ` (ex. `Europe/Paris`).
- `updatedAt` → horodatage **serveur** de la dernière mise à jour de la télémetrie
  (affiché « mise à jour » dans l'onglet températures, distinct du `dt` fourni par la box).
- Les dernières télémetries captées sont persistées dans `logs/telemetry.json`
  (volume monté) : les températures restent disponibles entre deux flux et après
  redémarrage du conteneur, jusqu'à l'arrivée d'un nouveau flux.
- `reference` dérivé : `TONE_AQUA_AIR` si la box a de l'ECS (`NED`/`UDM`), sinon `TONE_AIR`

Les écritures (`updateThermostats`, `commands`) sont acceptées et journalisées dans le bus
d'événements (`ALDES_WRITE`) mais pas encore renvoyées à la box : le format exact de commande
`devicebound` attendu par celle-ci reste à confirmer (voir dépôt `/tmp/opencode/saniho-ha`).

## Paramètres CLI (`python3 -m server.main --help`)

- `--mode proxy|bridge` (défaut `bridge`, ou env `ALDES_MODE`) — mode initial, changeable depuis la WebUI
- `--mode-file logs/mode.json` — persistance du mode : un changement fait via la WebUI est
  rejoué au redémarrage du conteneur (le fichier persistant prime sur `--mode`/`ALDES_MODE`)
- `--bind 0.0.0.0`, `--mqtt-port 8883`, `--web-port 8080`
- `--real-host aldesiotsuite.azure-devices.net`, `--real-port 8883`
- `--web-dir <dist>` (frontend construit)
- `--history-size 200`

## Tests

```bash
python3 tests/test_engine.py
python3 tests/test_aldes_api.py
python3 tests/test_mode_persist.py
```

## Notes / historique

- Anciens scripts legacy : `dump_mqtt.py` (faux broker simple), `mqtt_proxy.py` (proxy promo initial),
  `monitor_proxy.py`, `setup-dns.sh`.
- La box doit pointer vers cette machine (rediriger `aldesiotsuite.azure-devices.net:8883` vers le pont,
  dans le DNS ou le NAT) pour se connecter au pont — soit réellement au cloud.
- Mode **bridge** : la box ne "répond" pas de vrai AWS; les __commandes__ vers la box passent par `devices/<boxid>/messages/devicebound`.