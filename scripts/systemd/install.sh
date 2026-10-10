#!/usr/bin/env bash
# installe les units systemd (synchronisation + sauvegarde) et active les timers
# usage : sudo bash scripts/systemd/install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[1/4] Copie des units systemd…"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"
sed -e "s|__USER__|$RUN_USER|" -e "s|__WORKDIR__|$REPO_DIR|" \
    "$SCRIPT_DIR/dynastasie-sync.service" > /etc/systemd/system/dynastasie-sync.service
sed -e "s|__USER__|$RUN_USER|" -e "s|__WORKDIR__|$REPO_DIR|" \
    "$SCRIPT_DIR/dynastasie-backup.service" > /etc/systemd/system/dynastasie-backup.service
cp "$SCRIPT_DIR/dynastasie-sync.timer"   /etc/systemd/system/
cp "$SCRIPT_DIR/dynastasie-backup.timer" /etc/systemd/system/

echo "[2/4] Rechargement du daemon systemd…"
systemctl daemon-reload

echo "[3/4] Activation + démarrage du timer…"
systemctl enable --now dynastasie-sync.timer dynastasie-backup.timer

echo "[4/4] État du timer :"
systemctl status dynastasie-sync.timer dynastasie-backup.timer --no-pager

echo ""
echo "Prochain déclenchement :"
systemctl list-timers 'dynastasie-*' --no-pager
