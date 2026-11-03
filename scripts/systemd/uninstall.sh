#!/usr/bin/env bash
# désactive et supprime les units systemd
# usage : sudo bash scripts/systemd/uninstall.sh

set -e

echo "[1/3] Arrêt et désactivation du timer/watcher…"
systemctl disable --now dynastasie-sync.timer dynastasie-backup.timer dynastasie-bascule.path 2>/dev/null || true

echo "[2/3] Suppression des units…"
rm -f /etc/systemd/system/dynastasie-sync.service /etc/systemd/system/dynastasie-backup.service /etc/systemd/system/dynastasie-backup.timer
rm -f /etc/systemd/system/dynastasie-sync.timer
rm -f /etc/systemd/system/dynastasie-bascule.service /etc/systemd/system/dynastasie-bascule.path

echo "[3/3] Rechargement du daemon…"
systemctl daemon-reload

echo "Timers dynastasie-sync, dynastasie-backup et le watcher dynastasie-bascule désinstallés."
