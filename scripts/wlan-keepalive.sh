#!/bin/bash
# Sodat WLAN keepalive watchdog.
#
# Two problems this script is here to solve:
#
#   (a) Power save on Pi's wlan0 is ON by default. Our upload cadence
#       leaves the link mostly idle, which lets the radio drop into
#       PSM. Some APs we've deployed against (notably AOI) don't
#       wake the station quickly, so the first packet after idle
#       times out and the upload is delayed by ~30 s. Worse, after
#       certain firmware updates the radio sometimes loses the
#       association entirely after a long idle.
#
#   (b) cloud-init / NetworkManager normally recovers a dropped link
#       on their own — but only if they notice. We've observed cases
#       where the link is administratively up but the default route
#       times out for tens of minutes before the OS kicks in.
#
# Strategy:
#   - Disable wlan0 power_save on every boot (it resets on every
#     interface up event, so a static config in
#     /etc/NetworkManager/conf.d/ alone doesn't always stick).
#   - Every INTERVAL seconds, ping the default gateway. After
#     MISS_THRESHOLD consecutive failures, nudge wlan0 to re-associate
#     (nmcli on Bookworm, wpa_cli on older releases as a fallback).
#
# Logs go to /var/log/sodat-wlan-keepalive.log. Service runs forever
# under systemd; restart loop is in the unit file, not here.

set -u

LOG=/var/log/sodat-wlan-keepalive.log
IFACE=wlan0
INTERVAL="${SODAT_WLAN_INTERVAL:-300}"        # seconds between gw pings
MISS_THRESHOLD="${SODAT_WLAN_MISS_THRESHOLD:-3}"

exec >>"$LOG" 2>&1

log() { echo "$(date -Is) $*"; }

disable_power_save() {
    iw dev "$IFACE" set power_save off 2>/dev/null || true
}

nudge() {
    # NetworkManager (default on Pi OS Bookworm) preferred; fall back
    # to wpa_cli reconfigure on older releases.
    if command -v nmcli >/dev/null 2>&1; then
        log "nudging $IFACE via nmcli disconnect+connect"
        nmcli device disconnect "$IFACE" 2>/dev/null || true
        sleep 3
        nmcli device connect "$IFACE" 2>/dev/null || true
    elif command -v wpa_cli >/dev/null 2>&1; then
        log "nudging $IFACE via wpa_cli reconfigure"
        wpa_cli -i "$IFACE" reconfigure 2>/dev/null || true
    else
        log "no nmcli/wpa_cli available; bouncing link with ip"
        ip link set "$IFACE" down 2>/dev/null || true
        sleep 2
        ip link set "$IFACE" up 2>/dev/null || true
    fi
}

log "starting (interval=${INTERVAL}s threshold=${MISS_THRESHOLD})"
disable_power_save

miss=0
while true; do
    sleep "$INTERVAL"

    # Power save can creep back on every link-up event (DHCP renew,
    # roam, etc.). Re-disable each cycle — it's idempotent and cheap.
    disable_power_save

    gw="$(ip route 2>/dev/null | awk '/default/ {print $3; exit}')"
    if [ -z "$gw" ]; then
        miss=$((miss + 1))
        log "no default route (miss=$miss)"
    elif ping -c 2 -W 3 "$gw" >/dev/null 2>&1; then
        miss=0
    else
        miss=$((miss + 1))
        log "gw $gw unreachable (miss=$miss)"
    fi

    if [ "$miss" -ge "$MISS_THRESHOLD" ]; then
        log "miss=$miss reached threshold; nudging $IFACE"
        nudge
        disable_power_save
        miss=0
    fi
done
