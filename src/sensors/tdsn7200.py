"""TDSN-7200 — USB temperature / humidity / pressure sensor, read via td-usb CLI."""

import logging
import subprocess
from datetime import datetime, timezone

from src.models import SensorReading
from src.sensors.base import Sensor, register_sensor


@register_sensor("TDSN7200")
class TDSN7200Sensor(Sensor):
    def __init__(self, sensor_id: str, interval: int = 60, model_name: str = "tdsn7200"):
        super().__init__(sensor_id, "TDSN7200", interval)
        self.model_name = model_name
        self.cmd = ["td-usb", self.model_name, "get"]

    def read_data(self) -> SensorReading:
        try:
            result = subprocess.run(self.cmd, capture_output=True, text=True,
                                    check=True, timeout=30)
            output = result.stdout.strip()

            parts = output.split(',')

            if len(parts) >= 3:
                return SensorReading(
                    sensor_id=self.sensor_id,
                    sensor_type=self.sensor_type,
                    value={
                        "temperature": float(parts[0]),
                        "humidity": float(parts[1]),
                        "pressure": float(parts[2]),
                    },
                    timestamp=datetime.now(timezone.utc),
                )
            else:
                raise ValueError(f"Unexpected output format: {output}")

        except subprocess.TimeoutExpired:
            logging.error(f"TDSN7200 ({self.model_name}): td-usb hung for >30s (USB stall?)")
            raise
        except Exception as e:
            msg = str(e)
            if "Could not claim interface" in msg or "Device open error" in msg:
                logging.error(
                    "Error reading from TDSN7200: permission denied. "
                    "Check udev rules for idVendor 32ee/idProduct 177d and replug."
                )
            else:
                logging.error(f"Error reading from TDSN7200 ({self.model_name}): {e}")
            raise

    def get_measurement_keys(self) -> list[str]:
        return ["temperature", "humidity", "pressure"]
