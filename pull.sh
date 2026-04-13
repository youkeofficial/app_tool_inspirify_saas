#!/bin/bash
# ==============================================================================
# Script de mise à jour rapide - Quote Generator
# Description: Synchronise le code avec GitHub et recompile le conteneur Docker
# Utilisation: ./pull.sh
# ==============================================================================

set -e

# Définition des couleurs
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}[1/2] Téléchargement des dernières mises à jour depuis Github...${NC}"
git pull

echo -e "${BLUE}[2/2] Recompilation et relance du conteneur Quote Generator...${NC}"
if command -v docker-compose &> /dev/null; then
    docker-compose up -d --build --force-recreate
else
    docker compose up -d --build --force-recreate
fi

echo -e "${GREEN}[SUCCÈS] Le générateur est à jour et en cours d'exécution !${NC}"