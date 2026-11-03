#!/usr/bin/env bash
# installe les units systemd (synchronisation + sauvegarde + bascule) et active timers/path
# usage : sudo bash scripts/systemd/install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[1/5] Copie des units systemd…"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
sed -e "s|__USER__|$RUN_USER|" -e "s|__WORKDIR__|$REPO_DIR|" \
    "$SCRIPT_DIR/dynastasie-sync.service" > /etc/systemd/system/dynastasie-sync.service
sed -e "s|__USER__|$RUN_USER|" -e "s|__WORKDIR__|$REPO_DIR|" \
    "$SCRIPT_DIR/dynastasie-backup.service" > /etc/systemd/system/dynastasie-backup.service
sed -e "s|__USER__|$RUN_USER|" -e "s|__WORKDIR__|$REPO_DIR|" -e "s|__HOME__|$RUN_HOME|" \
    "$SCRIPT_DIR/dynastasie-bascule.service" > /etc/systemd/system/dynastasie-bascule.service
sed -e "s|__WORKDIR__|$REPO_DIR|" \
    "$SCRIPT_DIR/dynastasie-bascule.path" > /etc/systemd/system/dynastasie-bascule.path
cp "$SCRIPT_DIR/dynastasie-sync.timer"   /etc/systemd/system/
cp "$SCRIPT_DIR/dynastasie-backup.timer" /etc/systemd/system/

echo "[2/5] Rechargement du daemon systemd…"
systemctl daemon-reload

echo "[3/5] Activation + démarrage des timers et du watcher de bascule…"
systemctl enable --now dynastasie-sync.timer dynastasie-backup.timer dynastasie-bascule.path

echo "[4/5] État :"
systemctl status dynastasie-sync.timer dynastasie-backup.timer dynastasie-bascule.path --no-pager

echo ""
echo "[5/5] Rappel : pour que le bouton 'Basculer ici' fonctionne, créer"
echo "  $RUN_HOME/.config/dynastasie/peer.env"
echo "avec une ligne DYNASTASIS_PEER_SSH=utilisateur@hote-distant (jamais commité dans le repo)."

echo ""
echo "Prochain déclenchement :"
systemctl list-timers 'dynastasie-*' --no-pager
