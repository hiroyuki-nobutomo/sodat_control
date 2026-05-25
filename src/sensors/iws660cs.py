"""IWS-660CS — USB illuminance sensor, read via td-usb CLI."""

import logging
import subprocess
from datetime import datetime, timezone

from src.models import SensorReading
from src.sensors.base import Sensor, register_sensor


@register_sensor("IWS660CS")
class IWS660CSSensor(Sensor):
    def __init__(self, sensor_id: str, interval: int = 60, model_name: str = "iws660"):
        super().__init__(sensor_id, "IWS660CS", interval)
        self.model_name = model_name
        self.cmd = ["td-usb", self.model_name, "get"]

    def read_data(self) -> SensorReading:
        try:
            result = subprocess.run(self.cmd, capture_output=True, text=True, check=True, timeout=30)
            output = result.stdout.strip()

            if output.replace('.', '', 1).isdigit():
                return SensorReading(
                    sensor_id=self.sensor_id,
                    sensor_type=self.sensor_type,
                    value={"illuminance": float(output)},
                    timestamp=datetime.now(timezone.utc),
                )
            else:
                raise ValueError(f"Unexpected output format: {output}")

        except Exception as e:
            logging.error(f"Error reading from IWS660CS ({self.model_name}): {e}")
            raise

    def get_measurement_keys(self) -> list[str]:
        return ["illuminance"]
