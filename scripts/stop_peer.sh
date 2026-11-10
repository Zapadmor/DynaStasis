#!/usr/bin/env bash
# Bascule complète vers CETTE machine : arrête les conteneurs locaux, puis ceux de l'AUTRE machine
# (Streamlit ET API), attend la fin de la synchro Syncthing, vérifie la base, et seulement alors
# relance les conteneurs locaux — dans cet ordre, jamais l'inverse.
#
# La logique vit dans `handoff.py bascule` (testée) ; ce script n'en est que le point d'entrée.
# La base SQLite (db/, synchronisée par Syncthing) n'a qu'un seul écrivain valable à la fois.
# Vérifications avant de relancer ici :
#   - le pair est joignable et ses conteneurs sont réellement arrêtés ;
#   - Syncthing (API locale) : scan forcé, dossier à 100 % chez le pair, rien en attente ;
#   - sha256 de db/dynastasie.db identique des deux côtés, sans WAL en attente ;
#   - integrity_check ok, aucun -wal résiduel local, aucun nouveau fichier sync-conflict.
# Au moindre doute, rien n'est relancé et le message dit pourquoi (code 1). Un échec SSH ne prouve
# pas que l'autre machine est éteinte ; pour forcer malgré tout, utiliser le bouton « Forcer ».
# DYNASTASIS_PEER_SSH : cible SSH de l'autre machine (pas de défaut : mieux vaut échouer clairement).
# Nécessite une clé SSH acceptée sans mot de passe sur l'autre machine (BatchMode=yes).
set -u
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/handoff.py" bascule
