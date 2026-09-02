# Changelog

## [0.13.0] - 2026-09-02

### Ajouté
- **HA Discovery** : entité `binary_sensor` pour la protection anti-légionelles (`AntiL`) — `device_class: safety`

## [0.12.3] - 2026-09-02

### Ajouté
- **Infra** : endpoint `/healthz` pour liveness/readiness probes Kubernetes et docker-compose
- **Infra** : endpoint `/api/health` retourne status, uptime, mqtt_connected, box_connected

### Corrigé
- **Tests** : `test_dhw_level_sensor_config` mis à jour (device_class water supprimé dans un fix précédent)

## [0.8.5] - 2026-08-29

### Fixes
- **HA Discovery** : élimination du flicker "Inconnu" des entités climate — nettoyage ciblé des zones devenues inactives au lieu d'un nettoyage aveugle de tous les topics
- **HA Discovery** : persistance des zones actives dans `logs/zones.json` pour un nettoyage correct après redemarrage

### Ajouté
- Argument CLI `--zones-file` pour configurer le chemin de persistance des zones

## [0.8.4] - 2026-08-29

### Fixes
- **HA Discovery** : précision des températures à 0.1°C (au lieu de 1°C)
- **HA Discovery** : `temp_step` lu depuis le profil PAC (plutôt qu'en dur)
- **HA Discovery** : presets air et eau chaude chargés depuis le profil Aldes (noms français)
- **HA Discovery** : correspondances corrigées entre modes HVAC et programmes Aldes
- **MQTT** : variable `HA_MQTT_DRY_RUN` prise en compte effective (ordre de priorité : CLI > env > config persistée)
- **Tests** : ajout de tests pour la résolution du dry-run et les valeurs de discovery

## [0.8.3] - 2026-08-29

### Fixes
- **HA Discovery** : les zones apparaissent correctement dans HA (nommage "Zone N")
- **HA Discovery** : températures affichées avec une décimale dans HA

## [0.8.2] - 2026-08-29

### Fixes
- **HA Discovery** : zone index corrigé — Zone 2 dans bridge = Zone 2 dans HA

## [0.8.1] - 2026-08-29

### Fixes
- **HA Discovery** : correction de l'index des zones

## [0.8.0] - 2026-08-28

### Features
- **HA MQTT Auto-Discovery** : découverte automatique des entités PAC dans Home Assistant
- **Consigne HA** : publication immédiate de la consigne demandée sur le topic state
- **Config** : toggle pour activer/désactiver l'envoi des commandes HA vers la box
