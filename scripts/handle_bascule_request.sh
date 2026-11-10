#!/usr/bin/env bash
# Traite une demande de bascule ecrite par le bouton de l'UI dans data/bascule_request.json.
# Lance par le path unit systemd dynastasie-bascule.path des qu'un fichier de demande apparait.
#
# Pourquoi cette indirection par fichier : le conteneur Streamlit n'a ni cle SSH ni acces au
# socket Docker (un conteneur avec docker.sock monte peut lancer n'importe quel autre conteneur
# privilegie et prendre le controle de la machine hote — bien plus grave que l'acces SSH qu'on
# a deja ecarte une fois pour la meme raison). Ce script tourne sur l'hote, hors conteneur ; seul
# le dossier data/ (deja monte en lecture/ecriture) relie les deux mondes.
#
# DYNASTASIS_PEER_SSH doit etre defini pour le mode "bascule" — fourni par l'EnvironmentFile du
# service systemd (scripts/systemd/dynastasie-bascule.service), jamais commite dans le repo.
set -u

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUEST="$WORKDIR/data/bascule_request.json"
RESULT="$WORKDIR/data/bascule_result.json"
CONTENEURS="${DYNASTASIS_CONTAINERS:-dynastasie-streamlit,dynastasie-api}"

if [ ! -f "$REQUEST" ]; then
    exit 0
fi

MODE=$(python3 -c "import json; print(json.load(open('$REQUEST')).get('mode', ''))" 2>/dev/null)
NONCE=$(python3 -c "import json; print(json.load(open('$REQUEST')).get('nonce', ''))" 2>/dev/null)
rm -f "$REQUEST"

write_result() {
    local ok="$1" message="$2"
    python3 - "$NONCE" "$ok" "$message" "$RESULT" <<'PYEOF'
import datetime
import json
import os
import sys

nonce, ok, message, result_path = sys.argv[1:5]
payload = {
    "nonce": nonce,
    "ok": ok == "true",
    "message": message,
    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
tmp_path = result_path + ".tmp"
with open(tmp_path, "w") as f:
    json.dump(payload, f)
os.replace(tmp_path, result_path)
PYEOF
}

case "$MODE" in
    bascule)
        OUTPUT="$("$WORKDIR/scripts/stop_peer.sh" 2>&1)"
        if [ $? -eq 0 ]; then
            write_result true "$OUTPUT"
        else
            write_result false "$OUTPUT"
        fi
        ;;
    force_restart_local)
        # Streamlit d'abord (il migre la base), puis l'API ; un conteneur absent est ignoré.
        OUTPUT=""
        RC=0
        FIRST=1
        for C in ${CONTENEURS//,/ }; do
            OUT="$(docker restart "$C" 2>&1)"
            if [ $? -ne 0 ] && [ "$FIRST" = "1" ]; then RC=1; fi
            OUTPUT="$OUTPUT$OUT "
            FIRST=0
        done
        if [ "$RC" -eq 0 ]; then
            write_result true "Redémarrage local forcé : $OUTPUT"
        else
            write_result false "$OUTPUT"
        fi
        ;;
    *)
        write_result false "Mode de requête inconnu : '$MODE'"
        ;;
esac
