# Flux des modes — diagrammes Mermaid

Schémas interactifs (rendus nativement par GitHub) des quatre modes du pont :
**proxy**, **bridge**, **listen** et **raw**. L'ancien schéma ASCII vit dans le README.

## Vue d'ensemble

```mermaid
flowchart LR
    subgraph Local["Réseau local"]
        Box["📦 Box Aldes T.One"]
        DNS["🌐 dnsmasq (maskdns)"]
        Bridge["⚙️ Aldes Bridge (le pont)"]
        UI["🖥️ WebUI / API :8080"]
        HA["🏠 Home Assistant (intégration saniho-ha)"]
        Broker["🏠 Broker MQTT local (mode raw)"]
    end
    Azure["☁️ Azure IoT Hub (réel)"]

    Box -->|"résout le nom"| DNS
    DNS -->|"aldesiotsuite.azure-devices.net → IP du pont"| Bridge
    Box <-->|"MQTT/TLS 8883"| Bridge
    Bridge -->|"proxy : relais MITM"| Azure
        Bridge -.->|"bridge : décroché du cloud"| Azure
    Box -.->|"raw : la box reste sur le broker"| Broker
    Broker <-->|"raw : le pont est client MQTT"| Bridge
    Bridge -.->|"listen : remontée seule (commandes bloquées)"| Azure
    Bridge ---|"HTTP 8080 / SSE"| UI
    Bridge ---|"API Aldes rejouée"| HA
```

Le **maskdns** est le point d'entrée : la box résout `aldesiotsuite.azure-devices.net`
vers l'IP du pont. C'est lui qui décide si les trames passent par le pont (`proxy`) ou
n'atteignent jamais le vrai cloud (`bridge`).

## Mode proxy — MITM transparent

La box passe par le pont **pour rejoindre Azure** : le pont relaie chaque trame
(télémetries **et** acquittements), reste invisible côté cloud, et peut observer /
injecter des commandes au passage.

```mermaid
sequenceDiagram
    autonumber
    participant Boite as 📦 Box Aldes
    participant Bridge as ⚙️ Aldes Bridge (proxy)
    participant Azure as ☁️ Azure IoT Hub

    Note over Boite,Azure: "La box résout aldesiotsuite.azure-devices.net vers le pont via le maskdns"
    Boite->>Bridge: CONNECT (TLS 8883)
    Bridge->>Azure: CONNECT (relais)
    Azure-->>Bridge: CONNACK
    Bridge-->>Boite: CONNACK
    Note over Boite,Azure: "Session établie — la box croit parler directement à Azure"
    loop Télémetries (par rafales, 2-3/min)
        Boite->>Bridge: PUBLISH (télémetrie T.ONE)
        Bridge->>Azure: PUBLISH (relais QoS0)
        Bridge-->>Bridge: capture → rejeu API Aldes (telemetry.json)
    end
    opt Commande injectée (WebUI / HA)
        Bridge-->>Boite: PUBLISH (devicebound, QoS0) — commande injectée
    end
```

Points clés :

- le pont **termine** la connexion TLS de la box (`server/engine.py`) et ouvre **sa propre**
  connexion TLS vers Azure (`server/proxy.py`) ;
- relais **bidirectionnel** : télémetries box→Azure, commandes cloud→box ;
- les injections boxward passent en **QoS0** (pas de suivi d'acquittement) ;
- la WebUI et la capture télémetrie fonctionnent pendant le relais.

## Mode bridge — faux broker (local / hors-ligne)

La box se connecte au pont qui **joue le rôle d'Azure**. Rien ne sort vers le cloud :
le pont termine la connexion et sert l'API Aldes rejouée à Home Assistant.

```mermaid
sequenceDiagram
    autonumber
    participant Boite as 📦 Box Aldes
    participant Bridge as ⚙️ Aldes Bridge (bridge)
    participant HA as 🏠 Home Assistant

    Note over Boite,Bridge: "La box croit parler à Azure — le pont joue le broker"
    Boite->>Bridge: CONNECT (TLS 8883)
    Bridge-->>Boite: CONNACK
    loop Télémetries (par rafales)
        Boite->>Bridge: PUBLISH (télémetrie T.ONE)
        Bridge-->>Bridge: capture + journal + confirmation consignes
    end
    Note over Bridge,HA: "Aucune communication avec le vrai cloud"
    HA->>Bridge: GET /aldesoc/v5/users/me/products
    Bridge-->>HA: products (déduits des télémetries captées)
    HA->>Bridge: PATCH .../updateThermostats ou POST .../commands
    Bridge->>Boite: PUBLISH (devicebound, QoS1) — commande injectée
    Boite-->>Bridge: PUBACK
    Note over Bridge: "consigne confirmée quand la box rejoue la valeur dans une télémetrie"
```

Points clés :

- commandes injectées en **QoS1** (suivi PUBACK) ;
- le rejeu de l'API Aldes est **lecture des télémetries captées** + écriture vers la box
  via `engine.inject` (`devices/<boxid>/messages/devicebound`) ;
- la **confirmation** d'une consigne arrive quand la box rejoue la valeur (`UsC<n>`)
  dans une télémetrie ultérieure (`_confirm_consignes_from`).

## Mode raw — client MQTT natif (bonus)

Le pont n'écoute plus la box : il se connecte **en client** au broker local configuré,
écoute les événements sur `evt_topic` et publie les commandes sur `cmd_topic`.

```mermaid
flowchart LR
    subgraph Local["Réseau local"]
        Box2["📦 Box Aldes"]
        Broker["🏠 Broker MQTT"]
        Bridge2["⚙️ Aldes Bridge (client natif)"]
    end
    Box2 <-->|"MQTT (pairing box / broker)"| Broker
    Broker -->|"événements (evt_topic)"| Bridge2
    Bridge2 -->|"commandes (cmd_topic)"| Broker
```

## Mode listen — remontée seule (écoute du cloud)

Comme le proxy, la box rejoint Azure via le pont : la **télémétrie remonte** vers le
cloud à l'identique. Mais les **PUBLISH venant d'Azure** (commandes devicebound) sont
**bloqués** : observés et journalisés (`blocked=True`, badge « BLOQUÉ » dans la WebUI),
acquittés côté Azure pour éviter des retries, **jamais livrés à la box**. Les autres
trames cloud→box (CONNACK, SUBACK, PINGRESP, PUBACK/PUBREC/PUBCOMP des télémetries)
sont relayées pour garder la session MQTT de la box vivante.

```mermaid
sequenceDiagram
    autonumber
    participant Boite as 📦 Box Aldes
    participant Bridge as ⚙️ Aldes Bridge (listen)
    participant Azure as ☁️ Azure IoT Hub

    Note over Boite,Azure: "Session établie comme en proxy — le cloud croit parler à la box"
    loop Télémetries (par rafales, 2-3/min)
        Boite->>Bridge: PUBLISH (télémetrie T.ONE)
        Bridge->>Azure: PUBLISH (relais QoS0)
        Bridge-->>Bridge: capture → rejeu API Aldes (telemetry.json)
    end
    Note over Azure,Bridge: "Les commandes cloud → box sont bloquées au passage"
    Azure->>Bridge: PUBLISH (devicebound, QoS1)
    Bridge-->>Azure: PUBACK (accusé de réception, rien n'est livré)
    Bridge-->>Bridge: journalisation blocked=True (badge BLOQUÉ)
    opt Injection locale (WebUI / HA)
        Bridge-->>Boite: PUBLISH (devicebound, QoS0) — commande injectée
    end
```

Points clés :

- les commandes cloud→box sont **acquittées côté Azure** (QoS1 → PUBACK, QoS2 →
  PUBREC puis PUBCOMP à la réception du PUBREL) mais **jamais transmises** à la box ;
- l'injection locale (WebUI / API) reste possible en **QoS0** comme en proxy ;
- le mode sert à **observer** ce que le cloud voudrait envoyer sans l'appliquer —
  pratique pour tester la sûreté d'une intégration HA sans commande réelle.

## Glossaire

| Terme | Signification |
|---|---|
| **devicebound** | topic `devices/<boxid>/messages/devicebound` — commandes vers la box (JSON-RPC `changeMode`, `changeConsigneC<n>`) |
| **télémetrie T.ONE** | PUBLISH boxward : `MT0..MT9` températures, `UsC0..UsC9` consignes, `UAM`/`UDM` modes, `NED` ECS, `dt` horodatage cadran box |
| **maskdns** | dnsmasq qui redirige `aldesiotsuite.azure-devices.net` vers le pont (`setup-dns.sh`) |
| **rejeu API Aldes** | endpoints `/oauth2/token`, `/aldesoc/v5/users/me/products`, `/…/updateThermostats`, `/…/commands` servis par le pont pour l'intégration HA |
| **MITM** | interception + relais : le pont se fait passer pour Azure devant la box et pour la box devant Azure |