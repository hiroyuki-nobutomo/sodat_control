#!/bin/bash

# --- Sensor SFC Control Script ---
#
# Usage:
#   ./04_start_service.sh          -> Starts the background service (Production Mode).
#   ./04_start_service.sh --debug  -> Runs the app in the terminal (Debug Mode).
#   ./04_start_service.sh --stop   -> Stops the background service.
#   ./04_start_service.sh --log    -> Shows live logs.

# Automatically resolve project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ -d "$SCRIPT_DIR/src" ]; then
    cd "$SCRIPT_DIR"
elif [ -d "$SCRIPT_DIR/../src" ]; then
    cd "$SCRIPT_DIR/.."
else
    echo "Error: Could not find project root (src/ folder missing)."
    exit 1
fi

# SMART PROXY: If running from installer, switch to installed instance
if [ ! -d ".venv" ]; then
    REAL_USER=${SUDO_USER:-$USER}
    REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
    INSTALLED_DIR="$REAL_HOME/sensor_sfc"
    
    if [ -d "$INSTALLED_DIR" ]; then
        echo "Running command in installed directory: $INSTALLED_DIR"
        cd "$INSTALLED_DIR"
        exec ./04_start_service.sh "$@"
    else
        echo "❌ Error: Virtual environment (.venv) not found!"
        echo "Please run ./01_install_update.sh first."
        exit 1
    fi
fi

ACTION=${1:-start}

ensure_service_installed() {
    echo "Ensuring systemd service 'sensor_sfc' is configured..."
    
    SERVICE_FILE="sensor_sfc.service"
    PROJECT_ROOT=$(pwd)
    CURRENT_USER=${SUDO_USER:-$USER}

    cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Sensor SFC Data Collection
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_ROOT
ExecStart=$PROJECT_ROOT/.venv/bin/python3 -m src.main
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF

    sudo mv "$SERVICE_FILE" /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable sensor_sfc
    echo "✅ Service installed and enabled."
}

preflight_td_usb() {
    if ! command -v td-usb &> /dev/null; then
        return
    fi

    # Check TDSN7200
    OUTPUT_7200=$(td-usb tdsn7200 get 2>&1)
    if [[ "$OUTPUT_7200" == *"claim interface"* ]] || [[ "$OUTPUT_7200" == *"open error"* ]]; then
            echo "----------------------------------------------------------------"
            echo "WARNING: TDSN7200 detected but Permission Denied."
            echo "Run this command to fix:"
            echo "echo 'SUBSYSTEM==\"usb\", ATTR{idVendor}==\"32ee\", ATTR{idProduct}==\"177d\", MODE=\"0666\"' | sudo tee -a /etc/udev/rules.d/99-usb-tokyodevices.rules"
            echo "Then unplug and replug the sensor."
            echo "----------------------------------------------------------------"
    fi

    # Check TDSN7300
    OUTPUT_7300=$(td-usb tdsn7300 get 2>&1)
    if [[ "$OUTPUT_7300" == *"claim interface"* ]] || [[ "$OUTPUT_7300" == *"open error"* ]]; then
            echo "----------------------------------------------------------------"
            echo "WARNING: TDSN7300 detected but Permission Denied."
            echo "Run this command to fix:"
            echo "echo 'SUBSYSTEM==\"usb\", ATTR{idVendor}==\"32ee\", ATTR{idProduct}==\"1785\", MODE=\"0666\"' | sudo tee -a /etc/udev/rules.d/99-usb-tokyodevices.rules"
            echo "Then unplug and replug the sensor."
            echo "----------------------------------------------------------------"
    fi
}

if [ "$ACTION" == "--debug" ]; then
    echo "Stopping background service to free up resources..."
    sudo systemctl stop sensor_sfc
    
    echo "---------------------------------------------------"
    echo "Starting Sensor SFC in DEBUG MODE (Interactive)"
    echo "Press Ctrl+C to exit."
    echo "---------------------------------------------------"
    
    # Ensure environment is set up
    if [ ! -d ".venv" ]; then
        echo "Error: Virtual environment not found. Did you run 01_install_update.sh?"
        exit 1
    fi
    
    source .venv/bin/activate
    export PYTHONPATH=.
    preflight_td_usb
    python3 -m src.main

elif [ "$ACTION" == "--stop" ]; then
    ensure_service_installed
    echo "Stopping Sensor SFC Service..."
    sudo systemctl stop sensor_sfc
    sudo systemctl status sensor_sfc --no-pager

elif [ "$ACTION" == "--log" ]; then
    ensure_service_installed
    journalctl -u sensor_sfc -f

else
    # Default: Start Service
    ensure_service_installed
    echo "Starting Sensor SFC Service..."
    sudo systemctl start sensor_sfc
    
    # Wait a moment to capture immediate startup errors
    sleep 2
    
    # Check if active
    IS_ACTIVE=$(systemctl is-active sensor_sfc)
    if [ "$IS_ACTIVE" == "active" ]; then
        echo "✅ Service is RUNNING."
        echo "To see logs: ./04_start_service.sh --log"
        echo "To stop:     ./04_start_service.sh --stop"
    else
        echo "❌ Service failed to start."
        sudo systemctl status sensor_sfc --no-pager
        echo "Check logs with: ./04_start_service.sh --log"
    fi
fi
