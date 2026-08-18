# Tests

La suite couvre le moteur, le rejeu de l'API Aldes, le bus d'événements et la persistance
du mode. Aucun mock externe : les tests ouvrent de vrais sockets MQTT/TLS en localhost et
un vrai serveur HTTP (uvicorn). Les noms suivent la convention `test_<comportement>_<cas>`
et sont volontairement explicites (chacun documente ce qu'il vérifie).

## Lancer

Depuis la racine du dépôt :

```bash
python3 -m pytest                 # toute la suite
python3 -m pytest -q              # version silencieuse
python3 -m pytest tests/test_engine.py    # un seul fichier
python3 -m pytest -k "qos"        # filtre par nom
```

Avec la couverture (identique au CI) :

```bash
python3 -m pytest --cov=server --cov-report=term-missing
```

Le badge de couverture du README (`docs/coverage.svg`) est régénéré automatiquement par le
workflow GitHub Actions `.github/workflows/ci.yml` à chaque push sur `main`.

## Les fichiers

### `tests/test_engine.py` — moteur (modes bridge / proxy / raw)

Simule la box et Azure avec de faux pairs :

- `FakeRawBroker` — faux broker MQTT (mode raw) : accepte le client du bridge,
  renvoie CONNACK+SUBACK, ré-émet un PUBLISH et capte les commandes reçues.
- `FakeRealBroker` — faux « Azure » : accepte une connexion TLS, répond CONNACK/SUBACK,
  renvoie un PUBLISH. Une variante simule la *mort silencieuse* d'Azure (fermeture
  de connexion sans DISCONNECT).
- `box_socket` / `read_packet` — helpers pour jouer le rôle de la box côté client.

Cas couverts : injection de commande en bridge (`test_bridge_inject`), QoS2
(`test_bridge_qos2`), relai + injection en proxy (`test_proxy_relay_inject`), coupure
silencieuse d'Azure (`test_proxy_silent_azure_death`), mode raw (`test_raw_native`),
stale handler (`test_stale_handler_does_not_reset_connected`), identité de session
(`test_session_ids_unique_across_reconnects`), cycle de vie du `SessionRegistry`
(`test_session_registry_lifecycle`) et thread-safety de `_pending` (point 6,
`test_raw_pending_thread_safety`).

### `tests/test_aldes_api.py` — rejeu de l'API Aldes

- Décodage : capture/merge de la télémétrie par produit, en-tête binaire préfixé,
  trames `MT*`/`UsC` (thermostats, modes, composition `people`/`isfHome`, champs
  produit), horodatage interprété dans le fuseau de la box, fallback produit vide.
- Persistance télémétrie : throttling + flush (`test_telemetry_persist_throttled_and_flush`),
  horodatage serveur.
- Endpoints HTTP via un vrai uvicorn + `_StubEngine` : OAuth (`/oauth2/token`),
  produits, endpoints d'écriture (`updateThermostats` / `commands`), rejet du JSON invalide.

### `tests/test_eventlog.py` — bus d'événements + log disque (point 8)

Vérifie la sécurité thread du bus : publication/lecture/rotation concurrentes
(`test_eventbus_concurrent_publish_read_rotate`).

### `tests/test_mode_persist.py` — persistance du mode

Le mode choisi via la WebUI est rejoué au redémarrage : écriture/écrasement,
relecture au démarrage, fichier manquant/invalide toléré (`test_set_mode_persists`,
`test_mode_change_overwrites`, `test_restart_uses_persisted_mode`,
`test_missing_or_invalid_file_returns_none`, `test_no_mode_file_no_crash`,
`test_snapshot_exposes_mode_file`).