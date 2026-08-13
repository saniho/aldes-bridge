#!/usr/bin/env bash
# Déploiement du conteneur aldes-bridge sur la box (192.168.1.90) :
#  - synchronise le dépôt git local sur la box (remote dédié au déploiement)
#  - rebuild de l'image Docker (stage web + runtime python)
#  - redémarre le conteneur
#
# Usage : ./deploy.sh [main|feature/...]
set -euo pipefail

BRANCH="${1:-main}"
cd "$(dirname "$0")"

echo "==> Branche cible : $BRANCH"
git push origin "$BRANCH"
git ls-remote origin "$BRANCH" | head -1

timeout 600 python3 sshrun.py "
set -e
cd /opt/aldes-bridge
git fetch origin
git checkout -f $BRANCH
git reset --hard origin/$BRANCH
docker compose build --pull bridge
docker compose up -d bridge
" 
