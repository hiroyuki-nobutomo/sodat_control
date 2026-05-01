#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}--- Interactive Device Configuration ---${NC}"

# Ensure we are in the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ -d "$SCRIPT_DIR/src" ]; then
    cd "$SCRIPT_DIR"
elif [ -d "$SCRIPT_DIR/../src" ]; then
    cd "$SCRIPT_DIR/.."
else
    echo "Error: Could not find project root (src/ folder missing)."
    exit 1
fi

if [ ! -d ".venv" ]; then
    REAL_USER=${SUDO_USER:-$USER}
    REAL_HOME=$(eval echo ~$REAL_USER)
    INSTALLED_DIR="$REAL_HOME/sensor_sfc"
    
    if [ -d "$INSTALLED_DIR" ]; then
        echo "Running command in installed directory: $INSTALLED_DIR"
        cd "$INSTALLED_DIR"
        exec ./05_configure.sh "$@"
    else
        echo -e "${RED}Error: Virtual environment (.venv) not found. Have you run setup?${NC}"
        echo "Please run ./01_install_update.sh first."
        exit 1
    fi
fi

while true; do
    echo "Select Device ID:"
    echo "1) S01"
    echo "2) A01"
    echo "3) A02"
    echo "4) A03"
    echo "5) Custom"
    read -p "Enter choice [1-5]: " choice

    case $choice in
        1) DEVICE_ID="S01"; break ;;
        2) DEVICE_ID="A01"; break ;;
        3) DEVICE_ID="A02"; break ;;
        4) DEVICE_ID="A03"; break ;;
        5) 
            while true; do
                read -p "Enter Custom Device ID (Cannot be empty): " DEVICE_ID
                if [ -n "$DEVICE_ID" ]; then
                    break 2 # Break both loops
                else
                    echo -e "${RED}Error: Custom Device ID cannot be empty.${NC}"
                fi
            done
            ;;
        *)
            echo -e "${RED}Invalid choice '$choice'. Please enter a number between 1 and 5.${NC}"
            ;;
    esac
done
echo "Selected Device ID: $DEVICE_ID"

# Interval Configuration
echo -e "\n--- Interval Configuration (Default: 1800s / 30 min) ---"

get_valid_integer() {
    local prompt_text="$1"
    local default_val="$2"
    local input_val
    while true; do
        read -p "$prompt_text" input_val
        input_val=${input_val:-$default_val}
        if [[ "$input_val" =~ ^[0-9]+$ ]] && [ "$input_val" -gt 0 ]; then
            echo "$input_val"
            break
        else
            echo -e "${RED}Invalid input. Please enter a positive number.${NC}" >&2
        fi
    done
}

SENSOR_INT=$(get_valid_integer "Env Sensors (BME/TDSN/IWS/Arduino) Interval [Enter for 1800]: " 1800)
CAMERA_INT=$(get_valid_integer "Camera Interval [Enter for 1800]: " 1800)
UPLOAD_INT=$(get_valid_integer "Upload Interval [Enter for 1800]: " 1800)
UPLOAD_OFFSET=$(get_valid_integer "Upload Start Offset [Enter for 300]: " 300)
RETENTION_DAYS=$(get_valid_integer "Local Data Retention (Days) [Enter for 90]: " 90)

echo "Configuring device..."
# Calls the helper script
if .venv/bin/python3 scripts/util_config.py \
    --device-id "$DEVICE_ID" \
    --sensor-interval "$SENSOR_INT" \
    --camera-interval "$CAMERA_INT" \
    --upload-interval "$UPLOAD_INT" \
    --upload-offset "$UPLOAD_OFFSET" \
    --retention-days "$RETENTION_DAYS"; then
    echo -e "${GREEN}Configuration updated successfully in config.yaml.${NC}"
else
    echo -e "${RED}Error: Configuration failed!${NC}"
    echo "Please check if config.yaml exists and is valid."
    exit 1
fi

echo -e "${GREEN}--- Configuration Complete! ---${NC}"
