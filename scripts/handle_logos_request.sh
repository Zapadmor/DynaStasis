#!/usr/bin/env bash
# Traite une demande de synchro Logos (temps d'écran ADB) écrite par le bouton « Sync Écran »
# de l'UI dans data/logos_request.json. Lancé par le path unit systemd dynastasie-logos.path.
#
# Pourquoi cette indirection : le conteneur Streamlit est en réseau pont, donc il ne retrouve
# pas le téléphone (mDNS) et n'a pas adb. Ce script tourne sur l'hôte, hors conteneur ; seul le
# dossier data/ (monté en lecture/écriture) relie les deux mondes (même principe que la
# bascule, voir handle_bascule_request.sh). La base est la même (db/ monté dans le conteneur).
set -u

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUEST="$WORKDIR/data/logos_request.json"
RESULT="$WORKDIR/data/logos_result.json"
PYTHON_HOTE="${DYNASTASIS_HOST_PYTHON:-$WORKDIR/env/bin/python}"

[ -f "$REQUEST" ] || exit 0

NONCE=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('nonce', ''))" "$REQUEST" 2>/dev/null)
rm -f "$REQUEST"

write_result() {
    python3 - "$NONCE" "$1" "$2" "$RESULT" <<'PYEOF'
import datetime
import json
import os
import sys

nonce, ok, message, result_path = sys.argv[1:5]
payload = {
    "nonce": nonce,
    "ok": ok == "true",
    "message": message,
    "completed_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
}
tmp_path = result_path + ".tmp"
with open(tmp_path, "w") as f:
    json.dump(payload, f)
os.replace(tmp_path, result_path)
PYEOF
}

# Une seule synchro à la fois : une demande reçue pendant une synchro attend la fin de la première.
exec 9>"$WORKDIR/data/.logos_sync.lock"
flock 9

if [ ! -x "$PYTHON_HOTE" ]; then
    write_result false "Python de l'hôte introuvable ($PYTHON_HOTE)"
    exit 0
fi

# Passe par sync_runner : timeout, sync_checkpoints et logs_systeme sont alimentés comme pour
# la synchro planifiée. Sa sortie est du JSON-lines ; on en extrait le message de la source.
OUTPUT="$(cd "$WORKDIR" && "$PYTHON_HOTE" main.py sync --only logos 2>&1)"
RC=$?
MESSAGE="$(printf '%s' "$OUTPUT" | python3 -c '
import json, sys
msg = ""
for ligne in sys.stdin:
    try:
        ev = json.loads(ligne)
    except ValueError:
        msg = (msg + "\n" + ligne.strip()).strip()[-500:]  # trace brute (ex. traceback)
        continue
    if ev.get("event") == "source_fin":
        msg = ev.get("message") or ev.get("status", "")
    elif ev.get("event") == "source_ignoree":
        msg = "Source ignorée : " + str(ev.get("reason", ""))
print(msg[-500:])
')"
if [ $RC -eq 0 ]; then
    write_result true "${MESSAGE:-Synchronisation Logos terminée.}"
else
    write_result false "${MESSAGE:-Échec de la synchronisation Logos (voir journalctl -u dynastasie-logos).}"
fi
exit 0
