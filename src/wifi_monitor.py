"""Wi-Fi connection health checker.

Wraps `iwconfig <interface>` and translates signal strength into a label
(`Very Good` / `Good` / `Poor` / `Very Poor`). Not a Sensor — it's a
network status helper used by the Application's periodic logging.
"""

import subprocess


class WifiMonitor:
    def __init__(self, interface: str = "wlan0"):
        self.interface = interface

    def get_status_label(self, signal_dbm: float) -> str:
        if signal_dbm >= -60:
            return "[Very Good]"
        elif signal_dbm >= -70:
            return "[Good]"
        elif signal_dbm >= -80:
            return "[Poor]"
        else:
            return "[Very Poor]"

    def check_wifi(self) -> str:
        """Checks WiFi status and returns a formatted log string."""
        try:
            result = subprocess.run(["/sbin/iwconfig", self.interface],
                                    capture_output=True, text=True,
                                    check=True, timeout=10)
            output = result.stdout

            if 'ESSID:off/any' in output or 'Not-Associated' in output:
                return f"WiFi Health: [No Connection] (Interface: {self.interface} is disconnected)"

            essid = "Unknown"
            if 'ESSID:"' in output:
                essid = output.split('ESSID:"')[1].split('"')[0]

            signal_dbm = None
            if "Signal level=" in output:
                level_str = output.split("Signal level=")[1].split()[0]
                try:
                    signal_dbm = float(level_str)
                except ValueError:
                    pass

            if signal_dbm is not None:
                label = self.get_status_label(signal_dbm)
                quality_str = ""
                if "Link Quality=" in output:
                    quality_str = output.split("Link Quality=")[1].split()[0]

                return f"WiFi Health: {label} (ESSID: '{essid}', Signal: {signal_dbm}dBm, Quality: {quality_str})"
            else:
                return f"WiFi Health: [Connected] (ESSID: '{essid}', but signal strength unknown)"

        except Exception as e:
            return f"WiFi Health: [Error] (Failed to check {self.interface}: {e})"
