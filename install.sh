#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ -f "${BASH_SOURCE[0]}" ]] && [[ -f "$(dirname "${BASH_SOURCE[0]}")/99-madcatz-mmo7.rules" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "$SCRIPT_DIR"
else
    echo "==> Fetching latest repository files..."
    TMP_DIR=$(mktemp -d)
    trap 'rm -rf "$TMP_DIR"' EXIT
    git clone --depth 1 https://github.com/bolidbake/mmo7plus-linux.git "$TMP_DIR"
    cd "$TMP_DIR"
fi

echo "==> Installing udev rule to /etc/udev/rules.d/99-madcatz-mmo7.rules..."
sudo install -Dm644 "99-madcatz-mmo7.rules" "/etc/udev/rules.d/99-madcatz-mmo7.rules"
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "==> Installing desktop entry and icon..."
sudo install -Dm644 "madcatz-mmo7.desktop" "/usr/share/applications/madcatz-mmo7.desktop"
sudo install -Dm644 "mmo7/assets/device.png" "/usr/share/pixmaps/madcatz-mmo7.png"

echo "==> Installing mmo7-config Python package..."
pip install --user --break-system-packages . 2>/dev/null || pip install --user .

if [[ ! -f /usr/local/bin/mmo7-config ]] && [[ -f "$HOME/.local/bin/mmo7-config" ]]; then
    sudo ln -sf "$HOME/.local/bin/mmo7-config" /usr/local/bin/mmo7-config
fi

echo "==> Done! Launch from your app menu or run: mmo7-config"
