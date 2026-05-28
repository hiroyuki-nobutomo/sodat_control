#!/bin/bash
set -e

# --- Sensor SFC Unified Initialization Script (ULTRA-ROBUST) ---
# Handles Fresh Install, Legacy Update, and Golden Image reconfiguration.
# Automatically detects state, heals permissions, and reconciles paths.

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}--- Sensor SFC System Initialization ---${NC}"

# Current version — used when renaming orphaned scripts from the OLD version
CURRENT_VERSION="2"

# Manifest of scripts that belong to THIS version (at the project root)
CURRENT_SCRIPTS="01_install_update.sh 02_check_hardware.sh 03_test_sensors.sh 04_start_service.sh 05_configure.sh test_wifi.sh"

# 0. Pre-Flight Disk Space Check
# Ensure at least 100MB (102400 KB) of free space on the root partition
FREE_SPACE=$(df -k / | awk 'NR==2 {print $4}')
if [ "$FREE_SPACE" -lt 102400 ]; then
    echo -e "${RED}CRITICAL ERROR: Insufficient disk space!${NC}"
    echo "You only have $((FREE_SPACE / 1024)) MB free."
    echo "The update requires at least 100 MB of free space to proceed safely."
    echo "Please delete old images from data/images/ or free up space and try again."
    exit 1
fi

# 1. Permission Healing
# In case unzipped without +x bits, fix siblings immediately
chmod +x *.sh 2>/dev/null || true
chmod +x scripts/*.sh 2>/dev/null || true
chmod +x scripts/*.py 2>/dev/null || true

# 2. User & Path Discovery
# Ensure we target the real user's home, not /root if run with sudo
REAL_USER=${SUDO_USER:-$USER}
REAL_HOME=$(eval echo ~$REAL_USER)
DEFAULT_TARGET="$REAL_HOME/sensor_sfc"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
NEW_CODE_ROOT="$(dirname "$SCRIPT_DIR")"
# If running from root, BUNDLE_ROOT is the same as SCRIPT_DIR
if [[ -d "$SCRIPT_DIR/src" ]]; then NEW_CODE_ROOT="$SCRIPT_DIR"; fi

# 3. Bootstrap: Ensure rsync is available immediately
if ! command -v rsync &> /dev/null; then
    echo "Installing bootstrap dependencies (rsync)..."
    sudo apt-get update -qq && sudo apt-get install -y -qq rsync
fi

# 4. Safety: Stop existing service & Clear Hardware
echo "Ensuring hardware is free and services are stopped..."
sudo systemctl stop sensor_sfc 2>/dev/null || true
# Surgically kill only our python application to free I2C/Serial
sudo pkill -f "python3 -m src.main" 2>/dev/null || true

# GOAT-LEVEL: Forcefully rip hardware locks from zombie processes
# This prevents "Device or resource busy" errors during the update hand-off
echo "Forcefully releasing hardware locks..."
sudo fuser -k /dev/ttyACM* 2>/dev/null || true
sudo fuser -k /dev/video* 2>/dev/null || true

# 5. Fingerprint Discovery: Where is the OLD project?
find_existing_project() {
    # Search common locations, excluding the current bundle
    for search_dir in "$REAL_HOME" "$REAL_HOME/Desktop" "$REAL_HOME/Downloads" "/home/pi"; do
        if [ -d "$search_dir" ]; then
            # Find folders containing config.yaml, depth 2
            local found=$(find "$search_dir" -maxdepth 2 -name "config.yaml" 2>/dev/null)
            for f in $found; do
                local root=$(dirname "$f")
                if [ "$root" == "$NEW_CODE_ROOT" ]; then continue; fi
                if [ -f "$root/src/main.py" ]; then
                    echo "$root"
                    return
                fi
            done
        fi
    done
}

EXISTING_PATH=$(find_existing_project)

# 6. Determine Target Path & Mode
if [ -n "$EXISTING_PATH" ]; then
    echo -e "${YELLOW}Found existing project at: $EXISTING_PATH${NC}"
    read -p "Update this existing installation? [Y/n]: " choice
    if [[ ! $choice =~ ^[Nn]$ ]]; then
        TARGET_PATH="$EXISTING_PATH"
        MODE="UPDATE"
    else
        TARGET_PATH="$DEFAULT_TARGET"
        MODE="INSTALL"
    fi
else
    TARGET_PATH="$DEFAULT_TARGET"
    MODE="INSTALL"
    echo -e "No existing project detected. Will install to: ${GREEN}$TARGET_PATH${NC}"
fi

# 7. Path Reconciliation
if [ "$NEW_CODE_ROOT" != "$TARGET_PATH" ]; then
    echo "Syncing new version to: $TARGET_PATH..."
    sudo mkdir -p "$TARGET_PATH"
    
    # CRITICAL: Reclaim ownership of all old files before syncing.
    # Prevents "Permission Denied" if researcher accidentally created files with sudo.
    sudo chown -R $REAL_USER:$REAL_USER "$TARGET_PATH"
    
    if [ "$MODE" == "UPDATE" ] && [ -f "$TARGET_PATH/config.yaml" ]; then
        cp "$TARGET_PATH/config.yaml" "$TARGET_PATH/config.yaml.bak_$(date +%Y%m%d_%H%M%S)"
    fi

    # Perform the sync
    rsync -rt --exclude '.venv' --exclude 'dist' --exclude '.git' "$NEW_CODE_ROOT/" "$TARGET_PATH/"
    cd "$TARGET_PATH"
else
    echo "Running directly from: $TARGET_PATH"
    cd "$TARGET_PATH"
fi

# 7b. Orphan Script Cleanup (Version-Aware)
# Rename old scripts that are NOT part of the current version.
# Prefix: old_vN_ where N = the version they came from.
# Already-renamed scripts (old_v*_) are left untouched.

# Detect old version from the VERSION file (before we overwrite it)
OLD_VERSION="1"
if [ -f "$TARGET_PATH/VERSION" ]; then
    OLD_VERSION=$(cat "$TARGET_PATH/VERSION" | tr -d '[:space:]')
fi

# Write the current VERSION
echo "$CURRENT_VERSION" > "$TARGET_PATH/VERSION"

if [ "$MODE" == "UPDATE" ]; then
    echo "Cleaning up old scripts from v${OLD_VERSION}..."
    orphan_count=0
    for sh_file in "$TARGET_PATH"/*.sh; do
        [ -f "$sh_file" ] || continue
        basename_sh=$(basename "$sh_file")

        # Skip if already renamed from a previous update
        if [[ "$basename_sh" == old_v* ]]; then continue; fi

        # Skip if it's in the current manifest
        is_current=0
        for current in $CURRENT_SCRIPTS; do
            if [ "$basename_sh" == "$current" ]; then is_current=1; break; fi
        done
        if [ "$is_current" -eq 1 ]; then continue; fi

        # This is an orphan — rename it
        new_name="old_v${OLD_VERSION}_${basename_sh}"
        mv "$sh_file" "$TARGET_PATH/$new_name"
        echo -e "  ${YELLOW}Renamed:${NC} $basename_sh → $new_name"
        orphan_count=$((orphan_count + 1))
    done

    if [ "$orphan_count" -gt 0 ]; then
        echo -e "${GREEN}Renamed $orphan_count old script(s).${NC} You can safely delete old_v*_ files later."
    fi

    # Also clean old config backups — keep only the 3 most recent
    backup_count=$(ls -1 "$TARGET_PATH"/config.yaml.bak_* 2>/dev/null | wc -l)
    if [ "$backup_count" -gt 3 ]; then
        echo "Pruning old config backups (keeping 3 most recent)..."
        ls -1t "$TARGET_PATH"/config.yaml.bak_* | tail -n +4 | xargs rm -f
    fi

    # Clean stale artifacts
    rm -f "$TARGET_PATH"/sensor_sfc_deploy_clean.zip "$TARGET_PATH"/sensor_sfc_update.zip "$TARGET_PATH"/sensor_sfc_installer.zip "$TARGET_PATH"/sensor_sfc_v2.zip 2>/dev/null || true
    rm -f "$TARGET_PATH"/config.yaml.template 2>/dev/null || true
fi

# 8. Dependency & Environment Setup
I2C_WAS_JUST_ENABLED=0

if [ "$MODE" == "INSTALL" ]; then
    echo -e "${GREEN}Performing full system dependency check...${NC}"
    
    # Wait for unattended-upgrades to finish on fresh boot
    while sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || sudo fuser /var/lib/dpkg/lock >/dev/null 2>&1; do
        echo -e "${YELLOW}Waiting for background OS updates to finish... (This is normal on a fresh boot)${NC}"
        sleep 5
    done
    
    sudo apt-get update -qq
    sudo apt-get install -y -qq git rsync python3-venv python3-pip libusb-1.0-0-dev libusb-dev fswebcam libgpiod3 i2c-tools python3-lgpio
    
    # Enable I2C
    if [ -f /boot/firmware/config.txt ]; then
        if ! grep -q "^dtparam=i2c_arm=on" /boot/firmware/config.txt; then
            sudo sed -i 's/^#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' /boot/firmware/config.txt
            grep -q "dtparam=i2c_arm=on" /boot/firmware/config.txt || echo "dtparam=i2c_arm=on" | sudo tee -a /boot/firmware/config.txt
            I2C_WAS_JUST_ENABLED=1
        fi
    elif [ -f /boot/config.txt ]; then
        sudo raspi-config nonint do_i2c 0
        I2C_WAS_JUST_ENABLED=1
    fi
    
    # GOAT-LEVEL: Ensure i2c-dev module loads on boot
    if ! grep -q "^i2c-dev" /etc/modules; then
        echo "i2c-dev" | sudo tee -a /etc/modules > /dev/null
    fi
fi

# Always ensure groups
echo "Setting hardware permissions (dialout, i2c, video)..."
sudo usermod -a -G gpio,i2c,video,dialout $REAL_USER || true

# Always ensure Udev rules for Tokyo Devices (TDSN)
echo "Installing Udev rules for USB Sensors..."
sudo sh -c 'cat <<EOF > /etc/udev/rules.d/99-usb-tokyodevices.rules
SUBSYSTEM=="usb", ATTR{idVendor}=="32ee", ATTR{idProduct}=="177d", MODE="0666"
SUBSYSTEM=="usb", ATTR{idVendor}=="32ee", ATTR{idProduct}=="1785", MODE="0666"
SUBSYSTEM=="usb", ATTR{idVendor}=="16c0", ATTR{idProduct}=="05df", MODE="0666"
EOF'
sudo udevadm control --reload-rules
# GOAT-LEVEL: Force kernel to apply rules to ALREADY plugged-in devices immediately
sudo udevadm trigger --action=add

# Wi-Fi reliability — set the regulatory domain to JP (Pi 5's 5GHz radio
# refuses to associate on regulated channels without a country code), and
# install a keepalive watchdog that disables power-save on every boot and
# nudges wlan0 if the default gateway goes silent. Both are idempotent.
echo "Configuring Wi-Fi reliability (country + keepalive watchdog)..."
if command -v raspi-config >/dev/null 2>&1; then
    sudo raspi-config nonint do_wifi_country JP 2>/dev/null || true
fi
sudo install -m 0755 "$TARGET_PATH/scripts/wlan-keepalive.sh" /usr/local/sbin/wlan-keepalive.sh
sudo tee /etc/systemd/system/sodat-wlan-keepalive.service > /dev/null <<'EOF'
[Unit]
Description=Sodat WLAN keepalive (power save off + gateway watchdog)
After=network-online.target wpa_supplicant.service NetworkManager.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/sbin/wlan-keepalive.sh
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now sodat-wlan-keepalive.service || true

# Virtual Environment Integrity
echo "Building virtual environment (Resumable)..."
# Check if venv is healthy before deleting (survives weak field Wi-Fi)
if [ ! -f ".venv/bin/python3" ]; then
    rm -rf .venv
    python3 -m venv --system-site-packages .venv
fi
.venv/bin/pip install -q --resume-retries 10 --default-timeout=120 -r requirements.txt

# 9. Configuration Migration
echo "Migrating configuration..."
if [ ! -f "config.yaml" ] && [ -f "config.yaml.template" ]; then
    cp config.yaml.template config.yaml
fi
.venv/bin/python3 scripts/util_migrate.py

# 10. Finalize Service
echo "Finalizing systemd service..."
# Ensure permissions on all scripts in the final location
chmod +x *.sh 2>/dev/null || true
./04_start_service.sh --stop 2>/dev/null || true
./04_start_service.sh

# Delegate to standalone health tool
./02_check_hardware.sh

# 10.5 First-time device configuration (Device ID, intervals) — fresh installs only.
# Updates keep the researcher's existing config.yaml as-is.
if [ "$MODE" == "INSTALL" ] && [ -t 0 ]; then
    echo
    echo -e "${GREEN}=== First-time device configuration ===${NC}"
    echo "Set the Device ID for this Raspberry Pi (e.g. S01, A01). Defaults are fine for the rest."
    if sudo -u "$REAL_USER" ./05_configure.sh; then
        echo "Restarting service with the new configuration..."
        ./04_start_service.sh --stop 2>/dev/null || true
        ./04_start_service.sh
    else
        echo -e "${YELLOW}Device configuration skipped — you can run ./05_configure.sh later.${NC}"
    fi
fi

# 10.6 Google credentials presence check.
# Service runs fine without it, but cloud uploads will fail until placed.
# Accept either service_account.json (preferred) or legacy token.json.
SA_FILE="$TARGET_PATH/secrets/service_account.json"
LEGACY_TOKEN="$TARGET_PATH/secrets/token.json"
if [ ! -s "$SA_FILE" ] && [ ! -s "$LEGACY_TOKEN" ]; then
    echo
    echo -e "${YELLOW}=================================================================${NC}"
    echo -e "${YELLOW}[!] Google credentials NOT FOUND.${NC}"
    echo "Sensor data will be collected locally, but uploads to Google Drive /"
    echo "Sheets will FAIL until you place a Service Account key at:"
    echo -e "  ${GREEN}$SA_FILE${NC}"
    echo
    echo "From your PC, run (replace <host> with this Pi's hostname):"
    echo -e "  ${GREEN}scp service_account.json $REAL_USER@<host>.local:$TARGET_PATH/secrets/${NC}"
    echo "Then restart the service:"
    echo -e "  ${GREEN}./04_start_service.sh --stop && ./04_start_service.sh${NC}"
    echo "(The same service_account.json is used on every device in this project.)"
    echo -e "${YELLOW}=================================================================${NC}"
fi

echo -e "\n${GREEN}--- Initialization Complete! ---${NC}"
echo -e "Location: ${YELLOW}$TARGET_PATH${NC}"

if [ "$MODE" == "INSTALL" ]; then
    echo -e "\n${YELLOW}[!] PERMISSION NOTICE [!]${NC}"
    echo "You were just added to hardware groups (dialout, video, i2c)."
    echo "You SHOULD log out and log back in for these to apply to your terminal."
    echo -e "To skip logging out and test sensors ${GREEN}NOW${NC}, use this command:"
    echo -e "  ${GREEN}sg dialout -c './03_test_sensors.sh'${NC}"
fi

if [ "$I2C_WAS_JUST_ENABLED" -eq 1 ] && [ ! -e "/dev/i2c-1" ]; then
    echo -e "\n${RED}=================================================================${NC}"
    echo -e "${RED}[!] HARDWARE REBOOT REQUIRED [!]${NC}"
    echo "I2C hardware was just enabled on this OS, but requires a reboot to activate."
    echo -e "Please run: ${GREEN}sudo reboot${NC}"
    echo -e "${RED}=================================================================${NC}"
else
    echo -e "\n${GREEN}--- Installation Complete! ---${NC}"
    echo -e "Location: ${YELLOW}$TARGET_PATH${NC}"
    
    # Interactive prompt to run test immediately
    read -p "Would you like to run the sensor test now? [Y/n]: " run_test
    if [[ ! $run_test =~ ^[Nn]$ ]]; then
        echo -e "\n${GREEN}Switching to installed directory and running test...${NC}"
        cd "$TARGET_PATH"
        # Run as the real user to ensure file permissions are correct (not root)
        sudo -u $REAL_USER ./03_test_sensors.sh
    else
        echo -e "\nTo run the test later, please execute:"
        echo -e "  ${GREEN}cd $TARGET_PATH${NC}"
        echo -e "  ${GREEN}./03_test_sensors.sh${NC}"
    fi
fi
