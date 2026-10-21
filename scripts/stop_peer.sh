#!/usr/bin/env bash
# Stoppe le conteneur DynaStasis de l'AUTRE machine avant de reprendre le travail ici.
# La base SQLite (db/, synchronisée par Syncthing) n'a qu'un seul écrivain valable à la fois :
# avec `restart: unless-stopped`, le conteneur revient tout seul après un reboot, donc "je ne
# lance pas l'app des deux côtés" n'est pas fiable sans l'arrêter explicitement avant de switcher.
# DYNASTASIS_PEER_SSH : cible SSH de l'autre machine (ex. utilisateur@hote-distant) — pas de défaut,
# mieux vaut échouer clairement que deviner la mauvaise machine.
# Nécessite une clé SSH acceptée sans mot de passe sur l'autre machine (BatchMode=yes).
set -u

CONTENEUR="${DYNASTASIS_CONTAINER:-dynastasie-streamlit}"
PEER="${DYNASTASIS_PEER_SSH:-}"

if [ -z "$PEER" ]; then
    echo "DYNASTASIS_PEER_SSH non défini (ex. export DYNASTASIS_PEER_SSH=utilisateur@hote-distant)" >&2
    exit 2
fi

ssh -o BatchMode=yes -o ConnectTimeout=6 "$PEER" "docker stop '$CONTENEUR'"
