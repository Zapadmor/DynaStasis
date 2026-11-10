#!/usr/bin/env bash
# Synchronisation planifiée (appelée par l'unité systemd) :
#  1. `python main.py sync --skip logos` dans le conteneur DynaStasis ;
#  2. `python main.py sync --only logos` sur l'hôte : le temps d'écran passe par ADB, dont la
#     découverte mDNS (téléphone retrouvé sur n'importe quel réseau) n'atteint pas un conteneur
#     en réseau pont. La base est la même (dossier db/ monté dans le conteneur).
# Conteneur arrêté ou Docker indisponible : on journalise et on continue, le timer réessaiera.
# GARDE « UN SEUL ÉCRIVAIN » : l'étape hôte (logos) écrit aussi dans la base (init_db, migrations).
# Sur un PC dont le conteneur est arrêté (l'autre est l'écrivain actif, ou la bascule n'est pas
# validée), elle est ignorée : sinon ce PC modifie db/ au réveil/démarrage (timer Persistent),
# avant la fin de la synchro Syncthing, et provoque conflits et corruption.
# Le code de retour vaut 1 si l'une des deux étapes a échoué.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTENEUR="${DYNASTASIS_CONTAINER:-dynastasie-streamlit}"
PYTHON_HOTE="${DYNASTASIS_HOST_PYTHON:-$ROOT/env/bin/python}"
rc=0
ACTIF=0

if ! command -v docker >/dev/null 2>&1; then
    echo "docker introuvable : synchronisation du conteneur ignorée"
elif [ "$(docker inspect -f '{{.State.Running}}' "$CONTENEUR" 2>/dev/null)" != "true" ]; then
    echo "conteneur $CONTENEUR arrêté : synchronisation du conteneur ignorée"
else
    ACTIF=1
    docker exec "$CONTENEUR" python main.py sync --skip logos || rc=1
fi

if [ "$ACTIF" != "1" ]; then
    echo "ce PC n'est pas l'écrivain actif (conteneur $CONTENEUR arrêté) : source logos ignorée"
elif [ -x "$PYTHON_HOTE" ]; then
    (cd "$ROOT" && "$PYTHON_HOTE" main.py sync --only logos) || rc=1
else
    echo "Python de l'hôte introuvable ($PYTHON_HOTE) : source logos ignorée"
fi

exit $rc
