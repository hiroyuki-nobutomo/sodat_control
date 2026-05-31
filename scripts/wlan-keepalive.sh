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
#   - nudge() retries up to NUDGE_ATTEMPTS times within a single
#     trigger, waiting NUDGE_SETTLE seconds between tries and
#     verifying association via `iw link` — AOI's hidden-SSID AP
#     loses the first nudge often enough that a single retry is
#     not enough.
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

NUDGE_ATTEMPTS="${SODAT_WLAN_NUDGE_ATTEMPTS:-3}"
NUDGE_SETTLE="${SODAT_WLAN_NUDGE_SETTLE:-15}"

nudge_once() {
    # NetworkManager (default on Pi OS Bookworm) preferred; fall back
    # to wpa_cli reconfigure on older releases.
    if command -v nmcli >/dev/null 2>&1; then
        nmcli device disconnect "$IFACE" 2>/dev/null || true
        sleep 3
        nmcli device connect "$IFACE" 2>/dev/null || true
    elif command -v wpa_cli >/dev/null 2>&1; then
        wpa_cli -i "$IFACE" reconfigure 2>/dev/null || true
    else
        ip link set "$IFACE" down 2>/dev/null || true
        sleep 2
        ip link set "$IFACE" up 2>/dev/null || true
    fi
}

nudge() {
    # Try several times before giving up. AOI's hidden-SSID + flaky-AP
    # combination regularly loses the first nudge to a probe-response
    # race or DHCP timeout; without an inner retry, the next attempt
    # is gated by another MISS_THRESHOLD * INTERVAL of silence.
    local attempt
    for attempt in $(seq 1 "$NUDGE_ATTEMPTS"); do
        log "nudging $IFACE (attempt $attempt/$NUDGE_ATTEMPTS)"
        nudge_once
        sleep "$NUDGE_SETTLE"
        if iw dev "$IFACE" link 2>/dev/null | grep -q '^Connected to'; then
            log "nudge succeeded on attempt $attempt"
            return 0
        fi
        log "still not associated after attempt $attempt"
    done
    log "nudge gave up after $NUDGE_ATTEMPTS attempts; will retry next cycle"
    return 1
}

log "starting (interval=${INTERVAL}s threshold=${MISS_THRESHOLD})"

miss=0
while true; do
    sleep "$INTERVAL"

    # Power save creeps back after each link-up event (DHCP renew, roam,
    # etc.), so re-disable every cycle. Idempotent + cheap.
    disable_power_save

    # Two-stage health check, L2 then L3. The radio losing association
    # is the failure mode we built this watchdog for; pinging the
    # gateway covers the remaining "associated but no traffic" case
    # without churning the link on transient route flaps.
    if ! iw dev "$IFACE" link 2>/dev/null | grep -q '^Connected to'; then
        miss=$((miss + 1))
        log "$IFACE not associated (miss=$miss)"
    else
        gw="$(ip route 2>/dev/null | awk '/default/ {print $3; exit}')"
        if [ -z "$gw" ]; then
            miss=$((miss + 1))
            log "associated but no default route (miss=$miss)"
        elif ping -c 2 -W 3 "$gw" >/dev/null 2>&1; then
            miss=0
        else
            miss=$((miss + 1))
            log "gw $gw unreachable (miss=$miss)"
        fi
    fi

    if [ "$miss" -ge "$MISS_THRESHOLD" ]; then
        log "miss=$miss reached threshold; nudging $IFACE"
        nudge
        miss=0
    fi
done
