# AGENTS.md — Conventions du projet Aldes Bridge

Ce document définit les règles à respecter pour toute modification du code.
**Tout agent IA ou contributeur DOIT suivre ces conventions.**

---

## Équipement

Le bridge Aldes connecte une **PAC air-air** (pompe à chaleur réversible) au cloud Aldes T.ONE AquaAir.
Ce n'est **pas** une VMC. Les modes de ventilation et de température contrôlent le ventilateur et le compresseur de la PAC.

---

## Repos liés

Deux repos doivent être mis à jour **ensemble** lors de tout changement de version :

| Repo | Rôle | Local |
|------|------|-------|
| [`saniho/aldes-bridge`](https://github.com/saniho/aldes-bridge) | Code bridge (backend + frontend + tests) | `/home/ubuntu/aldes-bridge` |
| [`saniho/aldes-haos-addons`](https://github.com/saniho/aldes-haos-addons) | Add-on Home Assistant OS (config + Dockerfile) | `/home/ubuntu/aldes-haos-addons` |

**Règle :** toute modification de version dans `aldes-bridge` doit être suivie d'un bump de version dans `aldes-haos-addons` (fichiers `aldes-bridge/config.yaml` et `aldes-bridge-beta/config.yaml`).

---

## Workflow obligatoire

### 1. Branche feature (jamais de commit direct sur `main`)

```
git checkout main && git pull
git checkout -b feature/<nom-court>
```

Nommage : `feature/air-modes`, `fix/history-labels`, `refactor/api-v2`, etc.

### 2. Versions semver

Règle stricte :
- **Patch** (0.x.1) : correction de bug, tweak UI, refactor sans ajout de fonctionnalité
- **Minor** (0.1.0) : nouvelle fonctionnalité (nouvel endpoint, nouveau panneau, nouveau helper)
- **Major** (1.0.0) : changement incompatible (API cassée, migration de DB)

Fichiers à modifier :
| Composant | Fichier | Clé |
|-----------|---------|-----|
| Backend   | `server/__init__.py` | `__version__ = "x.y.z"` |
| UI        | `web/package.json` | `"version": "x.y.z"` |
| Addon stable | `aldes-haos-addons/aldes-bridge/config.yaml` | `version: "x.y.z"` |
| Addon beta| `aldes-haos-addons/aldes-bridge-beta/config.yaml` | `version: "x.y.z"` |
| Dockerfile stable | `aldes-haos-addons/aldes-bridge/Dockerfile` | `CACHEBUST=vX.Y.Z` + `ALDES_ADDON_VERSION=vX.Y.Z` |
| Dockerfile beta   | `aldes-haos-addons/aldes-bridge-beta/Dockerfile` | `CACHEBUST=vX.Y.Z-beta` + `ALDES_ADDON_VERSION=vX.Y.Z-beta` |

**Règle beta vs stable :**
- **Branche `feature/*` ou `fix/*`** (avant merge sur `main`) → bump **uniquement** `aldes-bridge-beta/config.yaml` + son Dockerfile. Ne PAS toucher au config stable.
- **Merge sur `main`** (release) → bump `aldes-bridge/config.yaml` + son Dockerfile. Ne PAS toucher au config beta (déjà bumpé sur la feature branch).
- Le suffixe `.betaN` (ex: `0.13.2.beta1`) s'utilise uniquement pour le beta. Le stable utilise un semver strict (`0.13.2`).

**IMPORTANT :** les `CACHEBUST` et `ALDES_ADDON_VERSION` dans les Dockerfiles **doivent** être bumpés à chaque changement de version. Sans cela, Docker utilise le cache et ne reclone pas le repo — la version affichée dans les logs reste l'ancienne.

Les deux versions doivent être **identiques** et incrémentées **ensemble**.

### 3. Commits

Format conventionnel :
```
<type>(<scope>): <description courte>

<description optionnelle plus détaillée>
```

Types : `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`

Exemples :
- `feat(history): regrouper les capteurs par famille`
- `fix(air): ajouter tous les modes air (A-I) aux boutons rapides`
- `refactor(api): sérialiser les réponses en JSON stream`

Ne **jamais** mentionner "IA", "Copilot", "Claude", "GPT" ou similaire dans les commits.

### 4. Merge sur main (après validation)

```bash
git checkout main
git merge --no-ff feature/<nom> -m "Merge feature branch '<nom>' — <description>"
git push origin main
```

Le déploiement se fait via la **mise à jour de l'addon** dans Home Assistant (bump de version dans `aldes-haos-addons`).

### 5. Tests

Avant tout commit :
```bash
# Backend
python3 -m pytest tests/ -x -q

# Frontend (depuis web/)
npm run build
npx playwright test
```

---

## Structure du projet

```
aldes-bridge/
├── server/              # Backend Python (FastAPI + MQTT)
│   ├── __init__.py      # __version__
│   ├── main.py          # Point d'entrée
│   ├── api.py           # Routes HTTP
│   ├── aldes.py         # Mapping telemetrie Aldes
│   ├── mqtt.py          # Client MQTT
│   ├── history.py       # Stockage SQLite
│   └── appstate.py      # État applicatif
├── web/                 # Frontend React + Vite
│   ├── package.json     # version
│   ├── src/
│   │   ├── api.ts       # Appels API
│   │   ├── types.ts     # Types TypeScript
│   │   └── components/  # Composants React
│   └── e2e/             # Tests Playwright BDD
├── tests/               # Tests Python unitaires
├── docker-compose.yml   # Config container
└── AGENTS.md            # Ce fichier
```

## Convention de code

### Python
- Pas de commentaires inutiles
- Docstrings sur les fonctions publiques uniquement
- Type hints sur les signatures de fonctions

### TypeScript/React
- Pas de commentaires inutiles
- Composants fonctionnels + hooks
- CSS Modules (pas de styled-components)

### HTML / UI
- Pas d'emojis dans l'interface (sauf demande explicite)
- Libellés en français
- Format dates : HH:MM (Paris)

---

## Checklist avant chaque tâche

- [ ] Branche feature créée
- [ ] Versions bumpées si nécessaire
- [ ] Versions bumpées dans `aldes-haos-addons` (config-beta.yaml uniquement si feature, stable + beta si release)
- [ ] Versions bumpées dans `aldes-haos-addons` (Dockerfile-beta CACHEBUST + ALDES_ADDON_VERSION si feature, les deux si release)
- [ ] Tests passent
- [ ] Build OK
- [ ] Commit avec bon format
- [ ] Merge sur main après validation
