#!/bin/bash

# Simple script to test WiFi and show human-readable status
INTERFACE="wlan0"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "--- WiFi Connection Diagnostic ---"

# Check if interface exists
if ! ip link show "$INTERFACE" > /dev/null 2>&1; then
    echo -e "${RED}Error: Interface $INTERFACE not found.${NC}"
    exit 1
fi

# Get iwconfig output
OUTPUT=$(/sbin/iwconfig "$INTERFACE" 2>/dev/null)

if [[ $OUTPUT == *"ESSID:off/any"* ]] || [[ $OUTPUT == *"Not-Associated"* ]]; then
    echo -e "Status: ${RED}[No Connection]${NC}"
    echo "Reason: Not associated with any network."
    exit 0
fi

ESSID=$(echo "$OUTPUT" | grep 'ESSID:' | cut -d'"' -f2)
SIGNAL=$(echo "$OUTPUT" | grep 'Signal level=' | awk '{print $4}' | cut -d'=' -f2)
QUALITY=$(echo "$OUTPUT" | grep 'Link Quality=' | awk '{print $2}' | cut -d'=' -f2)

# Determine Label
LABEL="[Unknown]"
COLOR=$NC

if [ -n "$SIGNAL" ]; then
    # Use bash integer comparison (dBm are usually integers)
    if [[ "$SIGNAL" -ge -60 ]]; then
        LABEL="[Very Good]"
        COLOR=$GREEN
    elif [[ "$SIGNAL" -ge -70 ]]; then
        LABEL="[Good]"
        COLOR=$GREEN
    elif [[ "$SIGNAL" -ge -80 ]]; then
        LABEL="[Poor]"
        COLOR=$YELLOW
    else
        LABEL="[Very Poor]"
        COLOR=$RED
    fi
fi

IP=$(ip -4 addr show "$INTERFACE" | grep -oP '(?<=inet\s)\d+(\.\d+){3}')

echo -e "Human Status: ${COLOR}${LABEL}${NC}"
echo "Network (ESSID): $ESSID"
echo "Signal Strength: ${SIGNAL} dBm"
echo "Link Quality:    $QUALITY"
echo "IP Address:      ${IP:-None}"

if [ -z "$IP" ] && [ -n "$ESSID" ]; then
    echo -e "${YELLOW}Warning: Connected to WiFi but no IP address assigned (Check DHCP).${NC}"
fi
