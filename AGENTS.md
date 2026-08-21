# AGENTS.md — Conventions du projet Aldes Bridge

Ce document définit les règles à respecter pour toute modification du code.
**Tout agent IA ou contributeur DOIT suivre ces conventions.**

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

### 4. Déploiement local (dev)

```bash
# Depuis la branche feature
./deploy.sh <branche-feature>
```

Vérifications après deploy :
- `curl -s http://192.168.1.90:8080/api/state | python3 -m json.tool`
- Vérifier `server_version` et `ui_version`
- Tester l'endpoint impacté

### 5. Merge sur main (après validation)

```bash
git checkout main
git merge --no-ff feature/<nom> -m "Merge feature branch '<nom>' — <description>"
git push origin main
./deploy.sh main
```

### 6. Tests

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
├── deploy.sh            # Script de déploiement
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
- [ ] Tests passent
- [ ] Build OK
- [ ] Deploy local vérifié
- [ ] Commit avec bon format
- [ ] Merge sur main après validation
