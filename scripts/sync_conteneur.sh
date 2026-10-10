#!/usr/bin/env bash
# Lance `python main.py sync` dans le conteneur DynaStasis (appelé par l'unité systemd).
# Conteneur arrêté ou Docker indisponible : on journalise et on sort sans erreur,
# le timer réessaiera à la prochaine échéance. Toute autre erreur est propagée.
set -u

CONTENEUR="${DYNASTASIS_CONTAINER:-dynastasie-streamlit}"

if ! command -v docker >/dev/null 2>&1; then
    echo "docker introuvable : synchronisation ignorée"
    exit 0
fi
if [ "$(docker inspect -f '{{.State.Running}}' "$CONTENEUR" 2>/dev/null)" != "true" ]; then
    echo "conteneur $CONTENEUR arrêté : synchronisation ignorée"
    exit 0
fi

exec docker exec "$CONTENEUR" python main.py sync
