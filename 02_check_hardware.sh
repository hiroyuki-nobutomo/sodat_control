#!/bin/bash

# --- Sensor SFC Hardware Health Checker ---
# This script can be run repeatedly by researchers to verify hardware
# connectivity and permissions, especially after hot-plugging devices.

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}--- Hardware Health Report ---${NC}"

# GOAT-LEVEL: Force kernel to refresh permissions and wait for settle
sudo udevadm trigger --action=add
sudo udevadm settle

# 1. Check Arduino (USB Serial)
if ls /dev/ttyACM* &> /dev/null; then
    echo -e "[OK] Arduino found at $(ls /dev/ttyACM* | xargs)"
else
    echo -e "[!!] ${YELLOW}Arduino NOT FOUND${NC} (Check USB cable)"
fi

# 2. Check BME280 (I2C)
if command -v i2cdetect &> /dev/null; then
    if i2cdetect -y 1 | grep -q "76"; then
        echo -e "[OK] BME280 Sensor found at I2C address 0x76"
    else
        echo -e "[!!] ${YELLOW}BME280 NOT FOUND${NC} (Check I2C wiring)"
    fi
fi

# 3. Check Tokyo Devices (HID)
# Logic: If binary is missing/broken, attempt to build it if hardware is detected
check_tokyo_devices() {
    if ! command -v td-usb &> /dev/null; then
        # Check if hardware is actually plugged in (using Vendor ID 32ee or 16c0)
        if lsusb | grep -qiE "32ee|16c0"; then
            echo -e "[..] Tokyo Device detected but 'td-usb' binary is missing."
            echo "Attempting automated source-build fallback..."
            
            BUILD_DIR="/tmp/td-usb-build"
            sudo rm -rf "$BUILD_DIR" && mkdir -p "$BUILD_DIR"
            if git clone -q https://github.com/tokyodevices/td-usb.git "$BUILD_DIR"; then
                cd "$BUILD_DIR"
                if gcc -Wno-incompatible-pointer-types -I/usr/include -Wall td-usb.c device_types.c tddevice.c ./linux/tdhid-libusb.c ./linux/tdtimer-posix.c ./devices/*.c -o td-usb -lusb-1.0 -lrt -lm &>/dev/null; then
                    sudo cp td-usb /usr/local/bin/
                    echo -e "[OK] 'td-usb' successfully built and installed."
                else
                    echo -e "[!!] ${RED}Source build failed.${NC} Please check internet/dependencies."
                fi
            fi
        fi
    fi

    if command -v td-usb &> /dev/null; then
        HID_LIST=$(td-usb list 2>/dev/null || echo "")
        if [ -n "$HID_LIST" ]; then
            echo -e "[OK] Tokyo Devices found:\n$HID_LIST"
        else
            echo -e "[!!] ${YELLOW}Tokyo Devices NOT FOUND${NC} (Check USB cables)"
        fi
    else
        echo -e "[!!] ${YELLOW}Tokyo Devices Tool (td-usb) not available.${NC}"
    fi
}

check_tokyo_devices

# 4. Check Camera
if ls /dev/video* &> /dev/null; then
    echo -e "[OK] USB Camera found at $(ls /dev/video* | head -n 1)"
else
    echo -e "[!!] ${YELLOW}USB Camera NOT FOUND${NC}"
fi

echo -e "\n-------------------------------------------------------"
echo "If a device shows [!!] NOT FOUND, please plug it in and"
echo "run this script again: ./02_check_hardware.sh"
echo "-------------------------------------------------------"
