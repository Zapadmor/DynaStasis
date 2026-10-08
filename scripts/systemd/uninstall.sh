#!/usr/bin/env bash
# désactive et supprime les units systemd
# usage : sudo bash scripts/systemd/uninstall.sh

set -e

echo "[1/3] Arrêt et désactivation du timer…"
systemctl disable --now dynastasie-sync.timer 2>/dev/null || true

echo "[2/3] Suppression des units…"
rm -f /etc/systemd/system/dynastasie-sync.service
rm -f /etc/systemd/system/dynastasie-sync.timer

echo "[3/3] Rechargement du daemon…"
systemctl daemon-reload

echo "Timer dynastasie-sync désinstallé."
