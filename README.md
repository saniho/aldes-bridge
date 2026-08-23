# Aldes Bridge

![CI](https://github.com/saniho/aldes-bridge/actions/workflows/ci.yml/badge.svg)
![Coverage](docs/coverage.svg)

> ⚠️ **Avis de non-responsabilité** : ce projet est un projet **indépendant** et **sans aucun lien**
> avec Aldes. Il n'est ni approuvé, ni sponsorisé, ni affilié à Aldes ou à ses filiales.
> Il est fourni « en l'état » et **utilisé à vos propres risques** : aucun support, aucune garantie.
> L'usage de ce pont peut perturber le fonctionnement normal de votre équipement Aldes
> (et potentiellement le cloud Aldes) — assurez-vous de comprendre les risques avant de l'utiliser.

Pont MQTT over TLS pour intercepter, analyser **et commander** une box **Aldes Connect**
(qui remonte vers Azure IoT Hub), avec une Web UI React.

Deux modes (bascule possible à chaud depuis la Web UI, appliquée à la prochaine connexion de la box) :

- **proxy** — transparent : le pont relaie réellement la box vers `aldesiotsuite.azure-devices.net`,
  tout en affichant/sniffant chaque trame, et permet d'injecter des commandes vers la box (QoS0).
- **bridge** — faux broker : la box se connecte au pont qui joue le rôle d'Azure ; messages observés,
  commandes injectées en QoS1 ; *aucune* communication avec le vrai cloud.
- **listen** — remontée seule : la box rejoint Azure comme en proxy (télémétrie relayée), mais les
  commandes **cloud → box sont bloquées** (observées, journalisées, jamais livrées) ; l'injection
  locale WebUI reste possible.
- **raw** — client MQTT natif : le pont se connecte en client au broker local configuré.

Un unique listener TLS sur le port 8883 sert les modes proxy/bridge/listen ; le choix du mode est dans `AppState`

### Schéma — Principe du bridge et du proxy

```
┌──────────────┐            MQTT/TLS :8883            ┌────────────────────────────────┐
│   Box Aldes   │ <──────── CONNECT ─────────＋───────>> │         Machine (le pont)        │
│    T.One      │        (SNI/CN:            │            │                                │
└──────────────┘   aldesiotsuite.azure-...) │            │   listener TLS unique :8883    │
                                            │            │   (server/tls.py, ctx permissif)│
                                            │            └───────────────┬────────────────┘
                                            │                            │  dispatche selon
                                            │                            │  AppState.mode
                                            │                            │
                        ┌───────────────────┴────────────────────┐        │
                        ▼                                       ▼        │
          ┌──────────────────────────┐             ┌────────────────────────────┐
          │   MODE bridge            │             │   MODE proxy               │
          │   (faux broker)         │             │   (transparent / MITM)     │
          │   server/bridge.py       │             │   server/proxy.py           │
          │                          │             │                            │
          │   La box croit parler à  │             │   Le pont relaie réellement │
          │   Azure, mais rien ne    │             │   vers le vrai cloud :      │
          │   sort vers le cloud.    │             │                            │
          │   · télémetries captées  │             │   ┌────────────────────┐    │
          │     et ré-exposées (rejeu│             │   │  Azure IoT Hub     │    │
          │     API Aldes)           │             │   │ aldesiotsuite.     │    │
          │   · commandes injectées  │             │   │ azure-devices.net  │    │
          │     vers la box (QoS1)   │             │   └────────┬───────────┘    │
          └──────────────────────────┘             │    relais │ (QoS0 / snif)   │
                                                    └──────────┴─────────────────┘

   Boucle DNS (maskdns) : la box résout
   aldesiotsuite.azure-devices.net ─────► IP de la machine
   (sans elle, la box irait réellement sur Azure)

   Légende :
     ─────►  flux MQTT (télémetries boxward / commandes devicebound)
     ·····   chemin que prendraient les trames sans le maskdns (cloud réel)
   WebUI / API HTTP :8080 : /api/* + SSE + rejeu API Aldes (intégration HA saniho-ha)
```

> 📐 **Version Mermaid** (rendue nativement par GitHub) : [docs/flux-modes.md](docs/flux-modes.md) —
> les flux des quatre modes (proxy, bridge, listen, raw) en diagrammes interactifs.

Les modes partagent le même listener TLS et la même WebUI ; seule la destination
**des trames** change (faux broker local vs relais vers Azure), d'où la bascule à chaud.

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
  device_profile.py  # chargeur de profils YAML (DeviceProfile, load_profile)
  aldes.py       # mapping telemetrie → indicateurs Aldes
profiles/        # profils device (YAML)
  tone-aquaair.yaml  # profil TONE AquaAIR (PAC air-air)
web/             # frontend React/Vite
tests/           # tests pytest
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

Variables d'environnement (`docker-compose.yml`) :

| Variable | Défaut | Description |
|---|---|---|
| `ALDES_MODE` | `bridge` | Mode initial (proxy/bridge/listen/raw) |
| `ALDES_HISTORY_DAYS` | `90` | Rétention SQLite (jours) |
| `ALDES_PROFILE` | `tone-aquaair` | Profil device à charger |

### Kubernetes / K3s

Le bridge et sa redirection DNS peuvent être déployés directement dans un
cluster Kubernetes, sans machine virtuelle dédiée. Voir le
[guide de déploiement Kubernetes](docs/kubernetes.md).

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

## Installation complète sur une nouvelle machine (maskdns + Docker)

Cette rubrique détaille les étapes pour installer le pont de zéro sur une machine
(le « serveur ») qui remplacera le cloud Aldes pour la box dans le réseau local.
Elle suppose une machine Ubuntu/Debian sur un réseau avec une box internet type Freebox.

Le principe en deux temps :

1. **Le pont** : conteneur Docker qui écoute le MQTT/TLS (`:8883`) et sert la WebUI/API (`:8080`).
2. **Le maskdns** : dnsmasq local qui fait pointer `aldesiotsuite.azure-devices.net` vers la
   machine, pour que la box Aldes (qui résout ce nom à chaque connexion) atterrisse sur le pont
   et non sur le vrai cloud Azure.

> ⚠️ **Indispensable** : la box Aldes se connecte à l'heure actuelle réellement au cloud Azure.
> Tant que le maskdns n'est **pas** en place, la box continue de fonctionner normalement via le
> cloud ; dès qu'il est en place, elle passera par le pont. Les deux ne coexistent pas — le pont
> en mode `proxy` peut néanmoins relayer la box vers le vrai cloud (cf. « Modes » en tête de fichier).

### Étape 0 — Prérequis

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 dnsmasq dnsutils git
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # re-login pour que ça prenne effet
```

Adapter les adresses IP de la machine : remplacer chaque occurrence de `192.168.1.90` (et
éventuellement le `server=192.168.1.254`) par l'adresse de la nouvelle machine et de la box internet.

### Étape 1 — Récupérer le code

```bash
git clone https://github.com/saniho/aldes-bridge.git /opt/aldes-bridge
cd /opt/aldes-bridge
```

### Étape 2 — Configurer le maskdns (dnsmasq)

Le script `setup-dns.sh` installe et configure dnsmasq pour rediriger
`aldesiotsuite.azure-devices.net` vers la machine, puis relayer le reste du DNS vers la box internet :

```bash
sudo bash setup-dns.sh
```

Ce script :

- installe `dnsmasq` (si absent) ;
- écrit `/etc/dnsmasq.d/aldes.conf` : `address=/aldesiotsuite.azure-devices.net/<IP_machine>`
  + `server=<IP_box_internet>` (reste du DNS relayé) + `listen-address=<IP_machine>` ;
- désactive la config dnsmasq par défaut et (re)démarre le service ;
- vérifie avec `dig @127.0.0.1 aldesiotsuite.azure-devices.net +short` (doit renvoyer l'IP de la machine).

> ⚠️ **Configurer le DNS du réseau** : dnsmasq ne sert à rien si les machines du réseau
> ne passent pas par lui. Dans l'interface de la Freebox
> (`http://mafreebox.freebox.fr` → Mode avancé → Réseau local → DHCP), régler le **DNS 1**
> sur l'IP de la machine. La box Aldes (et toute autre machine du réseau) résoudra alors
> `aldesiotsuite.azure-devices.net` via le pont.

### Étape 3 — Lancer le conteneur

```bash
cd /opt/aldes-bridge
sudo docker compose up -d --build
```

Vérifier que le conteneur tourne :

```bash
sudo docker ps --filter name=aldes-bridge
```

- MQTT/TLS : `0.0.0.0:8883` (c'est ce que la box joint via le maskdns)
- WebUI/API : `http://<IP_machine>:8080`

### Étape 4 — Tester que tout est en place

```bash
# 1) DNS : la machine (via dnsmasq) doit renvoyer sa propre IP
dig @127.0.0.1 aldesiotsuite.azure-devices.net +short

# 2) Le pont répond
curl -s http://<IP_machine>:8080/api/config
#   -> {"mode":"proxy","connected":false, ...}

# 3) (optionnel) depuis la box réseau locale, idem : résolution + port 8080 joignable
```

Une fois la box reconnectée (elle se réabonne périodiquement à
`aldesiotsuite.azure-devices.net`), elle apparaît `connected: true` dans `/api/config`
et les trames MQTT s'affichent dans la WebUI (onglet « flux »).

> ⏳ **Patienter après (re)démarrage** : la box ne publie pas sa télémetrie dès sa
> connexion. Elle l'envoie **par rafales**, espacées de plusieurs minutes à quelques
> dizaines de minutes (d'abord les températures `MT*`/`UsC*`, puis les programmes).
> Au démarrage du pont ou du conteneur, il faut donc **attendre la première rafale**
> avant de voir des températures : `connected: true` ne signifie pas des données
> fraîches. L'onglet « températures » l'indique via le badge de fraîcheur
> (`à jour` / `sans données depuis X` / `figée depuis X`, basé sur `updatedAt`).

### Mise à jour

```bash
cd /opt/aldes-bridge
git pull
./deploy.sh main   # ou : sudo docker compose up -d --build
```

## API

| Méthode | Chemin | Description |
|---|---|---|
| GET | `/api/config` | mode actuel |
| GET | `/api/state` | config + derniers messages (snapshot) |
| GET | `/api/events` | flux SSE (snapshot initial puis messages/status temps réel) |
| POST | `/api/mode` | `{"mode":"proxy"\|"bridge"\|"listen"\|"raw"}` — effet à la prochaine connexion |
| POST | `/api/send` | `{"topic","payload","qos"}` — injecte une commande vers la box |
| POST | `/api/disconnect` | force la session (pour appliquer le mode tout de suite) |
| POST | `/api/clear` | vide l'historique affiché |
| GET | `/api/profiles` | liste des profils disponibles (id, name, type, file) |
| GET | `/api/profile` | profil actuellement chargé |
| PUT | `/api/profile` | `{"profile_id":"tone-aquaair"}` — change le profil à la volée |
| GET | `/api/settings` | paramètres (rétention historique, taille max logs) |
| PUT | `/api/settings` | `{"history_retention_days":30, "log_retention_max_bytes":...}` — met à jour |
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

### Profils device

Le pont supporte plusieurs types d'appareils Aldes via un système de **profils YAML**.
Un profil décrit les modes, commandes et le mapping telemetrie d'un appareil spécifique.

**Profils disponibles** (dossier `profiles/`) :

| ID | Appareil | Type | Description |
|---|---|---|---|
| `tone-aquaair` | TONE AquaAIR | PAC air-air | Profil par défaut, 9 modes air, 3 modes eau, 5 commandes |

**API profils** :

| Méthode | Chemin | Description |
|---|---|---|
| GET | `/api/profiles` | liste des profils disponibles (id, name, type, file) |
| GET | `/api/profile` | profil actuellement chargé |
| PUT | `/api/profile` | `{"profile_id":"tone-aquaair"}` — change le profil à la volée |

**Sélecteur UI** : un dropdown « Appareil » dans l'en-tête permet de changer de profil
sans redémarrer le conteneur. Le profil sélectionné influence les modes affichés,
les commandes disponibles et les labels dans la WebUI.

**Format d'un profil YAML** (`profiles/mon-appareil.yaml`) :

```yaml
id: mon-appareil
name: "Mon Appareil"
description: "Description courte"
type: pac  # pac, vmc, etc.

products:
  REFERENCE_1:
    name: "Nom commercial"
    reference_fields: [NED, UDM]  # champs requis pour identifier ce produit
  REFERENCE_2:
    name: "Autre variante"
    reference_fields: []

telemetry:
  modemid: product.modem
  productid: product.serial_number
  dt: product.lastUpdatedDate
  zone_temp_prefix: MT
  zone_count: 10
  zone_setpoint_prefix: UsC
  air_mode_field: UAM
  water_mode_field: UDM
  hot_water_field: NED
  people_field: NpiH
  vac_start_field: Dvac
  vac_end_field: Fvac
  ballon_field: NED

air_modes:
  - index: 0
    code: A
    label: "Arrêt"
  # ... un mode par ligne

water_modes:
  - index: 0
    code: L
    label: "Eco"
  # ...

commands:
  - id: consigne
    label: "changeConsigneC<n> — consigne par zone"
    method: changeConsigneC0
    topic_pattern: "devices/{client_id}/messages/devicebound"
    params:
      - name: temp
        type: number
        min: 5
        max: 30
        step: 0.5
  # ...

ui:
  quick_modes:
    - field: air_modes
      label: "Mode air"
    - field: water_modes
      label: "Mode ECS"
  show_thermostats: true
  show_vacations: true
  show_people: true
  show_hot_water: true

history_labels:
  air_mode:
    keys: ["UAM"]
    patterns: ["^UAM$"]
  # ...
```

**Créer un nouvel appareil** : ajoutez un fichier YAML dans `profiles/`, redémarrez le
conteneur (ou utilisez `PUT /api/profile`), et sélectionnez-le dans le dropdown UI.

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
  C'est lui qui pilote le badge de fraîcheur de l'UI : `à jour` (< 15 min),
  `sans données depuis X` (15–45 min), `figée depuis X` (> 45 min) — rappel : après un
  démarrage, la première télémetrie peut mettre plusieurs minutes à arriver.
- Les dernières télémetries captées sont persistées dans `logs/telemetry.json`
  (volume monté) : les températures restent disponibles entre deux flux et après
  redémarrage du conteneur, jusqu'à l'arrivée d'un nouveau flux.
- `reference` dérivé : `TONE_AQUA_AIR` si la box a de l'ECS (`NED`/`UDM`), sinon `TONE_AIR`

Les écritures (`updateThermostats`, `commands`) sont acceptées et journalisées dans le bus
d'événements (`ALDES_WRITE`) mais pas encore renvoyées à la box.

**Format de commande réel confirmé** (observé sur le cloud Aldes en mode proxy, et rejoué
avec succès — `UsC0`/`Cre<n>` bougent bien dans les télémetries) : pour changer la consigne
d'une zone, la box attend un JSON-RPC sur `devices/<id>/messages/devicebound` avec la méthode
`changeConsigneC<n>` (n = index de zone, 0..9) et la température en **chaîne** dans `params` :

```json
{"id":1,"jsonrpc":"2.0","method":"changeConsigneC0","params":["25"]}
```

Ce format est disponible dans la WebUI : « Commande à la box → Fonction → changeConsigneC<n> »,
et en preset « Change consigne C0 » dans « Envoyer une commande MQTT ».

## Paramètres CLI (`python3 -m server.main --help`)

- `--mode proxy|bridge|listen|raw` (défaut `bridge`, ou env `ALDES_MODE`) — mode initial, changeable depuis la WebUI
- `--mode-file logs/mode.json` — persistance du mode : un changement fait via la WebUI est
  rejoué au redémarrage du conteneur (le fichier persistant prime sur `--mode`/`ALDES_MODE`)
- `--profile <id>` (ou env `ALDES_PROFILE`) — profil device à charger (défaut : premier profil trouvé)
- `--profile-file logs/profile.json` — persistance du profil sélectionné (prime sur `--profile`)
- `--config-file logs/config.json` — persistance des paramètres (rétention, logs)
- `--bind 0.0.0.0`, `--mqtt-port 8883`, `--web-port 8080`
- `--real-host aldesiotsuite.azure-devices.net`, `--real-port 8883`
- `--web-dir <dist>` (frontend construit)
- `--history-size 200`

## Tests

Suite pytest couvrant le moteur, le rejeu de l'API Aldes, le bus d'événements et la
persistance du mode — voir [docs/tests.md](docs/tests.md).

```bash
python3 -m pytest                 # toute la suite
python3 -m pytest --cov=server    # avec couverture
```

Le badge de couverture est mis à jour automatiquement par le CI à chaque push sur `main`.

### Tests E2E (Playwright)

Scénarios Gherkin dans `web/e2e/features/`, steps TypeScript dans `web/e2e/steps/`.

```bash
cd web && npm run build && npx playwright test
```

## Licence

Ce projet est distribué sous la licence **MIT** — voir [LICENSE](LICENSE).

## Notes / historique

- Les prototypes legacy (`dump_mqtt.py`, `mqtt_proxy.py`, `monitor_proxy.py`) ont été retirés — remplacés
  par les modules `server/*` et `sshrun.py`.
- `setup-dns.sh` configure le maskdns dnsmasq (voir « Installation complète sur une nouvelle machine »).
- La box doit pointer vers cette machine (rediriger `aldesiotsuite.azure-devices.net:8883` vers le pont,
  dans le DNS ou le NAT) pour se connecter au pont — soit réellement au cloud.
- En mode **bridge**, la box ne parle plus au cloud Azure (le pont joue le rôle d'Azure) ;
  en mode **proxy**, elle y reste réellement connectée. Dans les deux cas, les __commandes__
  vers la box passent par `devices/<boxid>/messages/devicebound`.
