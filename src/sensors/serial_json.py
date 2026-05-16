"""SerialJSON — Pull-model serial sensor that emits one JSON line per 'R' command.

Used for Arduino-attached probes (e.g., DFRobot Gravity EC V2 conductivity).
If `k_constant` is supplied and the JSON contains `voltage_v`, conductivity
in mS/cm is computed: EC = (k * voltage) / 0.5.
"""

import glob
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import serial

from src.models import SensorReading
from src.sensors.base import Sensor, register_sensor


@register_sensor("SerialJSON")
class SerialJSONSensor(Sensor):
    def __init__(self, sensor_id: str, interval: int = 60, port: str = "/dev/ttyACM0",
                 baud_rate: int = 9600, k_constant: Optional[float] = None):
        super().__init__(sensor_id, "SerialJSON", interval)
        self.port = port
        self.baud_rate = baud_rate
        self.k_constant = k_constant

    @classmethod
    def from_config(cls, config: dict, **_):
        return cls(
            sensor_id=config["id"],
            interval=config.get("interval_seconds", 60),
            port=config.get("port", "/dev/ttyACM0"),
            baud_rate=config.get("baud_rate", 9600),
            k_constant=config.get("k_constant"),
        )

    def _find_serial_port(self) -> str:
        """Finds the actual serial port, falling back to other ACM/USB ports if unplugged/moved."""
        if os.path.exists(self.port):
            return self.port

        potential_ports = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
        if potential_ports:
            fallback_port = potential_ports[0]
            logging.warning(f"Serial port {self.port} not found. Auto-discovering: {fallback_port}")
            return fallback_port

        raise FileNotFoundError(f"No serial device found (checked {self.port} and /dev/ttyACM*, /dev/ttyUSB*)")

    def read_data(self) -> SensorReading:
        try:
            actual_port = self._find_serial_port()
            with serial.Serial(actual_port, self.baud_rate, timeout=10) as ser:
                # Wait 2s for Arduino reboot (DTR toggle)
                time.sleep(2)

                ser.reset_input_buffer()
                ser.reset_output_buffer()

                # Send 'R' to trigger a reading (Pull Model)
                ser.write(b'R')
                ser.flush()

                raw_line = ser.readline()
                if not raw_line:
                    raise TimeoutError(f"No data received from {actual_port} after 'R' command")

                line_str = raw_line.decode('utf-8', errors='ignore').strip()

                try:
                    data = json.loads(line_str)
                    if not isinstance(data, dict):
                        raise ValueError("JSON root must be an object")

                    # Conductivity calc for DFRobot Gravity EC V2 (K=10): EC = (k * V) / 0.5
                    if self.k_constant is not None and "voltage_v" in data:
                        voltage = float(data["voltage_v"])
                        conductivity = (self.k_constant * voltage) / 0.5
                        data["conductivity_ms_cm"] = round(conductivity, 2)

                    return SensorReading(
                        sensor_id=self.sensor_id,
                        sensor_type=self.sensor_type,
                        value=data,
                        timestamp=datetime.now(timezone.utc),
                    )
                except json.JSONDecodeError:
                    raise ValueError(f"Invalid JSON received: {line_str}")

        except Exception as e:
            logging.error(f"Error reading from SerialJSONSensor ({self.port}): {e}")
            raise

    def get_measurement_keys(self) -> list[str]:
        # Dynamic JSON — headers are discovered on first upload.
        return []
