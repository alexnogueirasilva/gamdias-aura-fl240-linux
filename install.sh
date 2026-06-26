#!/usr/bin/env bash
# Gamdias Aura FL240 — Linux installer
# Tested on Arch Linux / systemd

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/usr/local/lib/gamdias"
SCRIPT_NAME="gamdias_display.py"
SERVICE_NAME="gamdias-display"
UDEV_RULE="/etc/udev/rules.d/99-gamdias.rules"
VENDOR_ID="1b80"
PRODUCT_ID="b533"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[✔]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Checks ────────────────────────────────────────────────────────────────────

[[ $EUID -eq 0 ]] || error "Execute como root:  sudo bash install.sh"

[[ -f "$SCRIPT_DIR/$SCRIPT_NAME" ]] || error "Arquivo $SCRIPT_NAME não encontrado em $SCRIPT_DIR"

command -v python3 &>/dev/null || error "python3 não encontrado. Instale com o gerenciador de pacotes da sua distro."

REAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo '')}"
[[ -n "$REAL_USER" ]] || error "Não foi possível determinar o usuário. Execute via sudo, não como root diretamente."

# ── Detect device ─────────────────────────────────────────────────────────────

detect_hidraw() {
    for dev in /sys/class/hidraw/hidraw*/device/; do
        uevent="$dev../../uevent"
        [[ -f "$uevent" ]] || continue
        if grep -qi "HID_ID=0003:0000${VENDOR_ID}:0000${PRODUCT_ID}" "$uevent" 2>/dev/null; then
            basename "$(realpath "$dev/../..")"
            return 0
        fi
    done
    return 1
}

HIDRAW_NODE=""
if HIDRAW_NODE=$(detect_hidraw); then
    DEVICE="/dev/$HIDRAW_NODE"
    info "Dispositivo encontrado: $DEVICE"
else
    warn "Dispositivo não encontrado agora (pode estar desconectado)."
    warn "A udev rule vai configurá-lo automaticamente quando conectado."
    DEVICE="/dev/hidraw0"
fi

# ── Install script ────────────────────────────────────────────────────────────

mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/$SCRIPT_NAME" "$INSTALL_DIR/$SCRIPT_NAME"
chmod 644 "$INSTALL_DIR/$SCRIPT_NAME"

info "Script instalado em $INSTALL_DIR/$SCRIPT_NAME"

# ── udev rule ─────────────────────────────────────────────────────────────────

cat > "$UDEV_RULE" <<EOF
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="$VENDOR_ID", ATTRS{idProduct}=="$PRODUCT_ID", MODE="0660", GROUP="input"
EOF

udevadm control --reload-rules
udevadm trigger --subsystem-match=hidraw
info "Udev rule criada: $UDEV_RULE"

# ── grupo input ───────────────────────────────────────────────────────────────

if ! groups "$REAL_USER" | grep -q '\binput\b'; then
    usermod -aG input "$REAL_USER"
    warn "Usuário '$REAL_USER' adicionado ao grupo 'input'. Faça logout/login para aplicar."
else
    info "Usuário '$REAL_USER' já está no grupo 'input'."
fi

# ── systemd service ───────────────────────────────────────────────────────────

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Gamdias Aura FL240 Display Controller
After=systemd-udev-settle.service
Wants=systemd-udev-settle.service

[Service]
Type=simple
User=$REAL_USER
Group=input
ExecStart=/usr/bin/python3 $INSTALL_DIR/$SCRIPT_NAME
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
info "Serviço '$SERVICE_NAME' habilitado e iniciado."

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}Instalação concluída!${NC}"
echo ""
echo "  Status:   sudo systemctl status $SERVICE_NAME"
echo "  Logs:     journalctl -u $SERVICE_NAME -f"
echo "  Remover:  sudo bash $SCRIPT_DIR/uninstall.sh"
echo ""
[[ "$HIDRAW_NODE" == "" ]] && warn "Conecte o cooler e o display será ativado automaticamente."
