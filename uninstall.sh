#!/usr/bin/env bash
# Gamdias Aura FL240 — uninstaller

set -euo pipefail

SERVICE_NAME="gamdias-display"
INSTALL_DIR="/usr/local/lib/gamdias"
UDEV_RULE="/etc/udev/rules.d/99-gamdias.rules"

RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✔]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

[[ $EUID -eq 0 ]] || error "Execute como root:  sudo bash uninstall.sh"

systemctl stop    "$SERVICE_NAME" 2>/dev/null && info "Serviço parado."    || true
systemctl disable "$SERVICE_NAME" 2>/dev/null && info "Serviço desabilitado." || true
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload

rm -f "$UDEV_RULE"
udevadm control --reload-rules
info "Udev rule removida."

rm -rf "$INSTALL_DIR"
info "Arquivos removidos de $INSTALL_DIR."

echo ""
echo -e "${GREEN}Desinstalação concluída.${NC}"
