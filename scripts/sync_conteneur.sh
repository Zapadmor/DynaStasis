#!/usr/bin/env bash
# Synchronisation planifiée (appelée par l'unité systemd) :
#  1. `python main.py sync --skip logos` dans le conteneur DynaStasis ;
#  2. `python main.py sync --only logos` sur l'hôte : le temps d'écran passe par ADB, dont la
#     découverte mDNS (téléphone retrouvé sur n'importe quel réseau) n'atteint pas un conteneur
#     en réseau pont. La base est la même (dossier db/ monté dans le conteneur).
# Conteneur arrêté ou Docker indisponible : on journalise et on continue, le timer réessaiera.
# Le code de retour vaut 1 si l'une des deux étapes a échoué.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTENEUR="${DYNASTASIS_CONTAINER:-dynastasie-streamlit}"
PYTHON_HOTE="${DYNASTASIS_HOST_PYTHON:-$ROOT/env/bin/python}"
rc=0

if ! command -v docker >/dev/null 2>&1; then
    echo "docker introuvable : synchronisation du conteneur ignorée"
elif [ "$(docker inspect -f '{{.State.Running}}' "$CONTENEUR" 2>/dev/null)" != "true" ]; then
    echo "conteneur $CONTENEUR arrêté : synchronisation du conteneur ignorée"
else
    docker exec "$CONTENEUR" python main.py sync --skip logos || rc=1
fi

if [ -x "$PYTHON_HOTE" ]; then
    (cd "$ROOT" && "$PYTHON_HOTE" main.py sync --only logos) || rc=1
else
    echo "Python de l'hôte introuvable ($PYTHON_HOTE) : source logos ignorée"
fi

exit $rc
