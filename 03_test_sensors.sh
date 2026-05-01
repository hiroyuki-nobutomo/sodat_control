#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
NC='\033[0m' # No Color

CONFIG_FILE="config.yaml"
BACKUP_FILE="config.yaml.bak"

echo -e "${GREEN}--- Starting Sensor Sensing Test (3 min) ---${NC}"

# SMART PROXY: If running from installer, switch to installed instance
if [ ! -f "config.yaml" ]; then
    REAL_USER=${SUDO_USER:-$USER}
    REAL_HOME=$(eval echo ~$REAL_USER)
    INSTALLED_DIR="$REAL_HOME/sensor_sfc"
    
    if [ -d "$INSTALLED_DIR" ]; then
        echo "Running command in installed directory: $INSTALLED_DIR"
        cd "$INSTALLED_DIR"
        exec ./03_test_sensors.sh "$@"
    fi
fi

# Preflight: warn if TDSN7200 is not accessible
if command -v td-usb &> /dev/null; then
    if ! td-usb tdsn7200 get &> /dev/null; then
        echo "Warning: td-usb cannot access TDSN7200 as user '$USER'."
        echo "Check udev rules for 32ee:177d and replug the device."
    fi
fi

# 1. Backup Config
if [ -f "$CONFIG_FILE" ]; then
    echo "Backing up $CONFIG_FILE to $BACKUP_FILE..."
    cp "$CONFIG_FILE" "$BACKUP_FILE"
else
    echo -e "${RED}Error: $CONFIG_FILE not found!${NC}"
    echo "Please run ./01_install_update.sh first."
    exit 1
fi

# Set up a trap to restore the config on exit (Ctrl+C or normal completion)
trap 'echo "Restoring configuration from backup..."; mv "$BACKUP_FILE" "$CONFIG_FILE" 2>/dev/null || true; echo -e "${GREEN}--- Test Complete & Config Restored ---${NC}"; exit' EXIT

# 1.5 Clean Environment (HARD FIX)
echo "Ensuring no background service is running..."
sudo systemctl stop sensor_sfc || true

echo "Clearing old sensor data to prevent time-sync related upload errors..."
# Find the database path from config or use default
DB_PATH="data/sensor/sensor_data.db"
if [ -f "$DB_PATH" ]; then
    rm "$DB_PATH"
    echo "Old database removed."
fi

# 2. Configure for High-Frequency Test
echo "Configuring for 15s intervals..."

PYTHON_CMD="python3"
if [ -d ".venv" ]; then
    PYTHON_CMD=".venv/bin/python3"
fi

# Using the existing python helper to modify yaml reliably
$PYTHON_CMD scripts/util_config.py \
    --sensor-interval 15 \
    --camera-interval 15 \
    --upload-interval 15 \
    --upload-offset 10

# 3. Run Application
echo -e "${GREEN}Running Sensor Application for 180 seconds...${NC}"
# Use .venv python if available, else system python
PYTHON_CMD="python3"
if [ -d ".venv" ]; then
    PYTHON_CMD=".venv/bin/python3"
fi

# Run with timeout. timeout returns 124 on timeout, which is expected here.
timeout 180s $PYTHON_CMD -m src.main || true

echo -e "\n${GREEN}Test duration completed. Trap will now restore config.${NC}"
