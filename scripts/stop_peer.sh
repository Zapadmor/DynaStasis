#!/usr/bin/env bash
# Bascule complete : stoppe le conteneur DynaStasis de l'AUTRE machine, PUIS relance celui
# de la machine courante — dans cet ordre, jamais l'inverse.
# La base SQLite (db/, synchronisée par Syncthing) n'a qu'un seul écrivain valable à la fois :
# avec `restart: unless-stopped`, le conteneur revient tout seul après un reboot, donc "je ne
# lance pas l'app des deux côtés" n'est pas fiable sans l'arrêter explicitement avant de switcher.
# Si l'arrêt distant échoue (peer injoignable : éteint, VPN coupé, ou autre), le conteneur local
# n'est PAS relancé — un échec SSH ne prouve pas que l'autre machine est éteinte ; mieux vaut
# s'arrêter là que de risquer un double écrivain.
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

if ! ssh -o BatchMode=yes -o ConnectTimeout=6 "$PEER" "docker stop '$CONTENEUR'"; then
    echo "Échec de l'arrêt du conteneur distant ($PEER) — conteneur local NON relancé." >&2
    echo "Si l'autre machine est réellement éteinte (vérifié, pas supposé), relancer soi-même :" >&2
    echo "  docker restart '$CONTENEUR'" >&2
    exit 1
fi

docker restart "$CONTENEUR"
