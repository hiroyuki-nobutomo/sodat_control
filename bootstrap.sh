#!/bin/bash
set -e

# --- Sensor SFC v2 — Web One-Line Installer ---
#
# Usage (on a freshly-imaged Raspberry Pi with WiFi + SSH already up):
#   curl -fsSL https://raw.githubusercontent.com/hiroyuki-nobutomo/sodat_control/main/bootstrap.sh | sudo bash
#
# What it does:
#   1. Installs git (if missing)
#   2. Clones (or updates) this repository to ~/sodat_control
#   3. Hands off to 01_install_update.sh, which performs the full setup
#      (apt deps, I2C, udev rules, venv, systemd service, ...)
#
# Override the branch by setting SODAT_BRANCH, e.g.:
#   curl -fsSL .../bootstrap.sh | sudo SODAT_BRANCH=develop bash

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

REPO_URL="https://github.com/hiroyuki-nobutomo/sodat_control.git"
BRANCH="${SODAT_BRANCH:-main}"

# Resolve the real (non-root) user even when invoked via `sudo bash`
REAL_USER="${SUDO_USER:-$USER}"
if [ "$REAL_USER" = "root" ] || [ -z "$REAL_USER" ]; then
    echo -e "${RED}ERROR: This installer must be run via 'sudo bash' from a normal user.${NC}"
    echo "Example: curl -fsSL <url> | sudo bash"
    exit 1
fi
REAL_HOME=$(eval echo "~$REAL_USER")
BUNDLE_DIR="$REAL_HOME/sodat_control"

echo -e "${GREEN}=== Sodat Sensor SFC v2 — Web Installer ===${NC}"
echo -e "User:     ${YELLOW}$REAL_USER${NC}"
echo -e "Bundle:   ${YELLOW}$BUNDLE_DIR${NC}"
echo -e "Branch:   ${YELLOW}$BRANCH${NC}"
echo

# 1. Ensure git is available
if ! command -v git &> /dev/null; then
    echo "Installing git..."
    apt-get update -qq
    apt-get install -y -qq git ca-certificates
fi

# 2. Clone or update the bundle, owned by the real user
if [ -d "$BUNDLE_DIR/.git" ]; then
    echo -e "${YELLOW}Existing bundle found — pulling latest from '$BRANCH'...${NC}"
    sudo -u "$REAL_USER" git -C "$BUNDLE_DIR" fetch --depth=1 origin "$BRANCH"
    sudo -u "$REAL_USER" git -C "$BUNDLE_DIR" checkout "$BRANCH"
    sudo -u "$REAL_USER" git -C "$BUNDLE_DIR" reset --hard "origin/$BRANCH"
else
    echo "Cloning Sodat bundle..."
    sudo -u "$REAL_USER" git clone --depth=1 --branch "$BRANCH" "$REPO_URL" "$BUNDLE_DIR"
fi

# 3. Hand off to the unified installer
cd "$BUNDLE_DIR"
chmod +x ./*.sh

# Reattach stdin to the controlling terminal so 01_install_update.sh's
# interactive prompts (Y/N) work even when this script was piped from curl.
# `[ -e /dev/tty ]` is not enough — under cloud-init's runcmd the device
# node exists but cannot be opened, so we probe by actually opening it.
if { : </dev/tty; } 2>/dev/null; then
    ./01_install_update.sh < /dev/tty
else
    # Headless context (e.g. firstrun): defaults are accepted automatically.
    ./01_install_update.sh < /dev/null
fi
